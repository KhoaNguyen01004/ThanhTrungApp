"""Centralized vehicle identity resolution.

Why this exists
---------------
The audit (docs/DELIVERY_AUDIT_2026-07-31.md §5) found seven competing
plate-identity implementations across the codebase with five mutually
incompatible semantics — last-5-digits, alnum-uppercase, strip-uppercase,
strip-lowercase, and raw exact match. The delivery module's Excel import used
the last of those, and on any mismatch **created a new row in `vehicles`**
rather than failing, silently polluting the table that fuel, oil, TLP and
delivery all key off (audit C-05).

That failure mode is not hypothetical: `tests/merge_duplicate_vehicles.py`
exists specifically to clean up duplicates the Google Sheet sync created the
same way.

The rule this module enforces
-----------------------------
**This module never writes.** It has no create, insert or upsert path at all.
``resolve()`` returns a ``VehicleRef`` or ``None``, so callers are forced to
decide what an unknown vehicle means in their context instead of defaulting
to an INSERT. Adding a truck to the fleet is a Vehicle Management action
(``app/routes/fleet.py``), never a side effect of importing a spreadsheet or
logging a delivery.

Identity in this fleet
----------------------
The **last 5 digits are the vehicle's identity**. Records legitimately arrive
as ``50E-18463``, ``50E18463`` or a bare ``18463`` depending on the source,
and all three mean the same truck — so a match on the 5-digit serial is a
real match, not a fuzzy guess. Two rows sharing a serial therefore means
duplicate data, which ``VehicleIndex`` detects and refuses to resolve rather
than picking one arbitrarily.

Deliberately NOT built here
---------------------------
A `vehicle_aliases` table. ``normalize_plate`` already collapses every
formatting variant actually observed in this fleet's data (hyphen, space,
case, bare serial), so an alias registry would be a table with no rows
solving a problem that does not yet exist. ``_match_candidates`` is the seam
to add one behind if genuinely arbitrary aliases (nicknames, old plates after
a re-registration) ever appear.
"""
import logging
import re
import sqlite3
from dataclasses import dataclass
from typing import Iterable, Optional
from urllib.parse import urlencode

from services.plate_utils import normalize_plate

logger = logging.getLogger(__name__)

_NON_ALNUM = re.compile(r"[^A-Za-z0-9]")


@dataclass(frozen=True)
class VehicleRef:
    """A resolved vehicle. ``matched_by`` records which strategy succeeded —
    useful for logging and for telling a dispatcher *why* a plate matched."""
    id: int
    plate_number: str
    matched_by: str  # "exact" | "canonical" | "serial"


def canonical_plate(plate: Optional[str]) -> str:
    """Uppercase, alphanumeric-only form: ``50E-18463`` / ``50e 18463`` →
    ``50E18463``. Matches the normalization ``app/services/ttas_client.py``
    already uses when matching plates against TTAS report dropdowns."""
    if not plate:
        return ""
    return _NON_ALNUM.sub("", str(plate)).upper()


def _is_bare_serial(plate: str) -> bool:
    """A plate that is nothing but the 5-digit serial — the shape the Google
    Sheet sync used to create as a duplicate row. When both a bare serial and
    a full plate match, the full plate is the original and wins."""
    return plate.isdigit() and len(plate) == 5


class VehicleIndex:
    """Snapshot of the `vehicles` table, indexed for identity resolution.

    Built once per operation and reused, rather than issuing a query per
    lookup — an Excel import resolves one plate per vehicle group, and
    `app/routes/fuel.py` currently re-scans the whole table on every insert
    (audit P-06).
    """

    def __init__(self, rows: Iterable):
        self._by_exact: dict[str, VehicleRef] = {}
        self._by_canonical: dict[str, VehicleRef] = {}
        self._by_serial: dict[str, VehicleRef] = {}
        self._ambiguous_serials: set[str] = set()

        for row in rows:
            vid, plate = (row["id"], row["plate_number"]) if isinstance(row, sqlite3.Row) else (row[0], row[1])
            if not plate:
                continue
            ref = VehicleRef(id=vid, plate_number=plate, matched_by="exact")
            self._by_exact.setdefault(plate, ref)

            canonical = canonical_plate(plate)
            if canonical:
                self._by_canonical.setdefault(canonical, ref)

            serial = normalize_plate(plate)
            if not serial:
                continue
            existing = self._by_serial.get(serial)
            if existing is None:
                self._by_serial[serial] = ref
            elif _is_bare_serial(existing.plate_number) and not _is_bare_serial(plate):
                # Full plate supersedes a bare-serial duplicate row.
                self._by_serial[serial] = ref
            elif _is_bare_serial(plate):
                pass  # keep the full plate already stored
            else:
                # Two genuinely different full plates sharing a serial. Refuse
                # to guess rather than silently attach stops to the wrong truck.
                self._ambiguous_serials.add(serial)
                logger.warning(
                    "Plate serial %s is ambiguous between %r and %r — serial "
                    "matching disabled for it",
                    serial, existing.plate_number, plate,
                )

    def resolve(self, identifier: Optional[str]) -> Optional[VehicleRef]:
        """Resolve any plate-ish string to a vehicle, or None.

        Strictest match first so an exact stored plate is never overridden by
        a looser one:
          1. exact `plate_number`
          2. canonical form (case/separator-insensitive)
          3. 5-digit serial (handles a bare `18463` from a spreadsheet)
        """
        text = (identifier or "").strip()
        if not text:
            return None

        hit = self._by_exact.get(text)
        if hit:
            # One exception to exact-match-wins: a row whose plate_number is a
            # bare 5-digit serial is a known duplicate artifact (see
            # tests/merge_duplicate_vehicles.py), not a real vehicle. If the
            # full plate is also present, resolve to that instead — otherwise
            # new delivery assignments would attach to the row that a future
            # merge is going to delete.
            if _is_bare_serial(hit.plate_number):
                full = self._by_serial.get(normalize_plate(text))
                if full and not _is_bare_serial(full.plate_number):
                    return VehicleRef(full.id, full.plate_number, "serial")
            return hit

        canonical = canonical_plate(text)
        if canonical:
            hit = self._by_canonical.get(canonical)
            if hit:
                return VehicleRef(hit.id, hit.plate_number, "canonical")

        serial = normalize_plate(text)
        if serial and serial not in self._ambiguous_serials:
            hit = self._by_serial.get(serial)
            if hit:
                return VehicleRef(hit.id, hit.plate_number, "serial")

        return None

    def __len__(self) -> int:
        return len(self._by_exact)


def build_index(conn) -> VehicleIndex:
    c = conn.cursor()
    c.execute("SELECT id, plate_number FROM vehicles")
    return VehicleIndex(c.fetchall())


def resolve(conn, identifier: Optional[str]) -> Optional[VehicleRef]:
    """One-shot resolution. Prefer ``build_index()`` when resolving several
    identifiers against the same connection."""
    return build_index(conn).resolve(identifier)


# NOTE: this module has no write path, by design. There is intentionally no
# create_vehicle() here. Adding a truck to the fleet is a Vehicle Management
# action (app/routes/fleet.py), never a side effect of importing a
# spreadsheet or logging a delivery — that is precisely how the duplicate
# rows in `vehicles` accumulated in the first place.


# Vietnamese plates: two province digits, one or two series letters, then the
# 4-5 digit serial — "50E-18463". Used only to suggest a well-formed plate on
# the Vehicle Management form; never to rewrite stored data.
_PLATE_SHAPE = re.compile(r"^(\d{2}[A-Z]{1,2})[-\s]?(\d{4,5})$")


def suggest_plate_format(identifier: Optional[str]) -> str:
    """Best-effort canonical display form for a plate the user just typed.

    ``50E18463`` / ``50e 18463`` → ``50E-18463``, matching how this fleet
    stores plates. Returns the input uppercased and trimmed when the shape
    isn't recognised (e.g. a bare ``18463``) — a suggestion the user can
    correct, never a silent rewrite.
    """
    text = (identifier or "").strip().upper()
    if not text:
        return ""
    match = _PLATE_SHAPE.match(text)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    return text


def unknown_vehicle_response(identifier: Optional[str], driver_name: str = "") -> dict:
    """Body for a request that named a vehicle which isn't in the fleet.

    The system does not create vehicles from operational data — the user is
    sent to Vehicle Management to add it deliberately. Everything already
    known from the rejected record is passed along so the form arrives
    pre-filled rather than blank.
    """
    plate = (identifier or "").strip()
    suggested = suggest_plate_format(plate)
    params = urlencode({"new": "1", "plate": suggested, "driver": driver_name or ""})
    return {
        "success": False,
        "error_code": "unknown_vehicle",
        "message": (
            f"'{plate}' is not a registered vehicle. Add it in Vehicle "
            f"Management first — nothing was saved."
        ),
        "unknown_vehicle": {
            "entered": plate,
            "suggested_plate": suggested,
            "serial": normalize_plate(plate),
            "current_driver": driver_name or "",
        },
        "redirect_to": f"/vehicle-management?{params}",
    }
