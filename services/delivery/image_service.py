import logging
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.db import DatabaseManager

logger = logging.getLogger(__name__)

#: Root that uploads live under and that ``relative_path`` is stored
#: relative to. Defaults to the repository, which is right for local dev;
#: in production DATA_DIR points at Render's mounted disk, because the
#: container filesystem is wiped on every deploy and proof photos must not
#: be. Deliberately the *parent* of DeliveryPlans/ so that rows written
#: before the disk existed ("DeliveryPlans/2026/...") still resolve.
DATA_ROOT = Path(os.getenv("DATA_DIR") or Path(__file__).resolve().parent.parent.parent)
UPLOAD_ROOT = DATA_ROOT / "DeliveryPlans"

# Only media types the dashboard actually renders. The stored file is served
# back by GET /api/images/<id>/file via send_file(), which infers Content-Type
# from the extension — so an uploaded .html or .svg would be served as
# text/html or image/svg+xml from the application's own origin, i.e. stored
# XSS with full session access (audit S-05). SVG is excluded deliberately: it
# is an image format that can execute script.
#
# Video is whitelisted the same way, and for the same reason: every extension
# here maps to a video/* type, so send_file cannot be talked into serving an
# active content type. Do not relax this to a MIME sniff — the browser-supplied
# Content-Type on a multipart part is attacker-controlled, the extension is
# what send_file will actually key off later.
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm"}
ALLOWED_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS

# Per-kind, because the two differ by an order of magnitude and a single cap
# would have to be the video one — which would then let a 100 MB "photo"
# through. Video evidence arrives from a phone on a mobile connection, so 100 MB
# is roughly 1-2 minutes of 1080p; the whole-request cap in app/config.py
# (MAX_UPLOAD_MB) has to stay above this or Werkzeug rejects the upload before
# this function ever runs, with a far less useful error.
MAX_IMAGE_BYTES = 10 * 1024 * 1024    # 10 MB — phone photos
MAX_VIDEO_BYTES = 100 * 1024 * 1024   # 100 MB — phone video

#: Retained under its original name: callers outside this module treated it as
#: "the upload limit" when photos were the only thing uploadable.
MAX_UPLOAD_BYTES = MAX_IMAGE_BYTES

_UNSAFE_SEGMENT_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


class UploadRejected(ValueError):
    """Raised when an upload fails validation. Carries a user-safe message."""


def _safe_path_segment(value: Optional[str], fallback: str) -> str:
    """Reduce a user-supplied string to one safe filesystem path component.

    ``station_code`` and ``category`` are attacker-controlled (Excel import,
    POST /api/stops, and the upload form) and were previously interpolated
    straight into the upload path, so a value of ``../../../static/js`` let
    mkdir + save write anywhere inside the repository (audit S-04).

    Separators and traversal sequences are stripped rather than escaped, and
    a value that reduces to nothing (or to a bare dot sequence) falls back to
    a constant so the path always has a well-formed component.
    """
    text = (value or "").strip()
    text = text.replace("/", "_").replace("\\", "_")
    text = _UNSAFE_SEGMENT_CHARS.sub("_", text)
    text = text.strip("._")
    if not text or set(text) <= {".", "_"}:
        return fallback
    return text[:64]


def media_kind(name: Optional[str]) -> str:
    """Classify a stored file as ``"image"`` or ``"video"`` by extension.

    Derived rather than stored in a column, so rows written before video was
    accepted classify correctly too and no migration is needed. Anything
    unrecognised reads as ``"image"``: every row that predates this function
    is a photo, and the dashboard's image path is the safe default to fall
    back to — an <img> with a bad source shows a broken thumbnail, whereas a
    <video> pointing at a JPEG shows nothing at all.
    """
    return "video" if Path(name or "").suffix.lower() in VIDEO_EXTENSIONS else "image"


def _validate_upload(file_storage) -> str:
    """Check extension and size. Returns the normalized extension."""
    original_name = file_storage.filename or ""
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise UploadRejected(
            f"Unsupported file type '{ext or original_name}'. "
            f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    is_video = ext in VIDEO_EXTENSIONS
    limit = MAX_VIDEO_BYTES if is_video else MAX_IMAGE_BYTES

    # FileStorage wraps a SpooledTemporaryFile; seek to the end to size it
    # without reading the whole payload into memory, then rewind so save()
    # still writes the complete file.
    stream = file_storage.stream
    stream.seek(0, 2)
    size = stream.tell()
    stream.seek(0)
    if size > limit:
        # Name the kind, or a driver told "the limit is 10 MB" after picking a
        # 40 MB video has no way to tell that video has a different allowance.
        raise UploadRejected(
            f"{'Video' if is_video else 'Image'} is {size // 1024 // 1024} MB; "
            f"the limit for {'video' if is_video else 'images'} is "
            f"{limit // 1024 // 1024} MB."
        )
    if size == 0:
        raise UploadRejected("File is empty.")

    return ext


def ensure_folder(category: str, plan_date: str, plate: str, station_code: str) -> Path:
    try:
        dt = datetime.fromisoformat(plan_date)
    except (ValueError, TypeError):
        dt = datetime.now()

    folder = (UPLOAD_ROOT / str(dt.year) / f"{dt.month:02d}" / f"{dt.day:02d}"
              / _safe_path_segment(plate, "unknown-vehicle")
              / _safe_path_segment(station_code, "unknown-station")
              / _safe_path_segment(category, "extra"))

    # Belt and braces: even with every segment sanitized, confirm the
    # resolved path is still inside UPLOAD_ROOT before creating it.
    resolved = folder.resolve()
    if not resolved.is_relative_to(UPLOAD_ROOT.resolve()):
        raise UploadRejected("Invalid upload destination.")

    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def upload_image(db_path: str, stop_id: int, file_storage,
                 category: str = "extra",
                 plan_date: Optional[str] = None,
                 plate: Optional[str] = None,
                 station_code: Optional[str] = None,
                 gps_lat: Optional[float] = None,
                 gps_lng: Optional[float] = None,
                 captured_at: Optional[str] = None,
                 uploaded_by: str = "") -> Optional[int]:
    with DatabaseManager(db_path).connect() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT s.id, s.station_code, va.plan_id, dp.plan_date, v.plate_number
            FROM delivery_plan_stops s
            JOIN vehicle_assignments va ON va.id = s.vehicle_assignment_id
            JOIN delivery_plans dp ON dp.id = va.plan_id
            JOIN vehicles v ON v.id = va.vehicle_id
            WHERE s.id = ?
        """, (stop_id,))
        stop_info = c.fetchone()

        if not stop_info:
            return None

        plan_date = plan_date or stop_info["plan_date"]
        plate = plate or stop_info["plate_number"]
        station_code = station_code or stop_info["station_code"]

        ext = _validate_upload(file_storage)

        folder = ensure_folder(category, plan_date, plate, station_code)
        original_name = file_storage.filename or f"image_{datetime.now().timestamp()}"
        # Timestamp alone is second-granularity, so two photos of the same
        # stop and category taken in the same second collided and one
        # silently overwrote the other — two DB rows pointing at one file,
        # i.e. lost proof-of-delivery evidence (audit C-08). The uuid suffix
        # keeps the sortable timestamp prefix while making collision
        # impossible.
        filename = f"{int(datetime.now().timestamp())}-{uuid.uuid4().hex[:8]}{ext}"
        file_path = folder / filename

        file_storage.save(str(file_path))

        relative = str(file_path.relative_to(DATA_ROOT))

        try:
            c.execute("""
                INSERT INTO delivery_stop_images
                    (stop_id, category, filename, relative_path, original_filename,
                     gps_lat, gps_lng, captured_at, uploaded_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (stop_id, category, filename, relative,
                  original_name, gps_lat, gps_lng, captured_at, uploaded_by))
        except Exception:
            if file_path.exists():
                file_path.unlink()
            raise

        return c.lastrowid


def _with_kind(row: dict) -> dict:
    """Attach ``media_kind`` to a row on the way out.

    Keyed off the stored ``filename`` rather than ``original_filename``: the
    stored name is the one this module generated from a validated extension,
    while the original is whatever the client sent.
    """
    row["media_kind"] = media_kind(row.get("filename"))
    return row


def list_images(db_path: str, stop_id: int):
    with DatabaseManager(db_path).connect() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT * FROM delivery_stop_images
            WHERE stop_id = ?
            ORDER BY uploaded_at DESC
        """, (stop_id,))
        return [_with_kind(dict(r)) for r in c.fetchall()]


def get_image(db_path: str, image_id: int) -> Optional[dict]:
    with DatabaseManager(db_path).connect() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM delivery_stop_images WHERE id = ?", (image_id,))
        row = c.fetchone()
        return _with_kind(dict(row)) if row else None


def delete_image(db_path: str, image_id: int) -> bool:
    with DatabaseManager(db_path).connect() as conn:
        c = conn.cursor()
        c.execute("SELECT relative_path FROM delivery_stop_images WHERE id = ?", (image_id,))
        row = c.fetchone()
        if row:
            full_path = DATA_ROOT / row["relative_path"]
            try:
                if full_path.exists():
                    full_path.unlink()
            except Exception as e:
                logger.warning("Failed to delete file %s: %s", full_path, e)

        c.execute("DELETE FROM delivery_stop_images WHERE id = ?", (image_id,))
        return c.rowcount > 0
