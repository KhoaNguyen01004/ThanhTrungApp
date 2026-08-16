"""
Huawei/Huwei dispatch-plan extraction from the operator's Google Sheet.

The dispatcher's planning sheet ("Kế hoạch Giao hàng Huwei") is owned by the
operator's manager, not by this system. We **read** it and never write to it:
the only endpoint used is Google's public ``gviz/tq`` query endpoint, which has
no write path at all, so no code path here can modify the source document even
by accident. There is also no credential involved — the sheet is link-shared,
so an unauthenticated GET is sufficient. (``services/google_sheet_service.py``
uses a service account for the *fuel* sheet; that sheet is ours, this one is
not, and we cannot add a service account to a document we do not own.)

The output of :func:`fetch_plan_for_date` is a list of row dicts in exactly the
shape ``services.delivery.plan_service.preview_import`` /
``confirm_import`` already consume from the Excel importer, plus a list of
warnings for the dispatcher to eyeball before committing.

Why this module is as defensive as it is
----------------------------------------
The sheet is hand-maintained prose, not an export, and every one of these was
observed in the live document on 2026-08-09:

* **The date column is text, not dates.** Values seen: ``21-Jul``, ``2-Aug``
  (no leading zero), ``10-Aug``, and ``01-th8`` (a Vietnamese ``tháng 8``
  slip). None of them carry a year.
* **Continuation rows leave the date cell blank.** Two rows in TH08 have an
  empty column A and belong to the day above, so the date must be
  forward-filled before any date match.
* **The coordinate columns are text in three mutually incompatible formats.**
  ``9,636058`` (comma decimal), ``9.60967`` (clean), and ``9.585.868`` /
  ``1.059.744`` — where a thousands separator has *replaced* the decimal
  point, so the true values are 9.585868 and 105.9744. A bare ``float()``
  either raises or, far worse, silently yields a coordinate in the wrong
  province. See :func:`parse_coordinate`.
* **Only the first row of each vehicle block carries the plate and driver.**
  The rest of the block is blank in those columns.
* **Plates are written inconsistently** — ``50H 19793``, ``50H-197.93`` and
  ``51D08660`` all appear, sometimes for the same truck. Resolution is left to
  ``services.vehicle_identity``, which matches on the 5-digit serial; this
  module passes the raw string through untouched.
* **Driver names carry typos** (``TRẦN`` vs ``TRẬN``) and one row has a note
  where the name should be. Names therefore go to
  ``vehicle_assignments.driver_name_override`` and never create ``drivers``
  rows.
"""

from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable, Optional

import requests

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration — overridable by environment variable, same pattern as
# services/google_sheet_service.py. This module deliberately does not import
# app.config, which raises at import time when .env is absent; the parser must
# stay importable in a bare test environment.
# ---------------------------------------------------------------------------
DEFAULT_SHEET_ID = os.getenv(
    "HUWEI_PLAN_SHEET_ID", "1mOFmDTH66G4iC-exCoZo7Gf9Mex-t_cVT16EYFXFLIE"
)
DEFAULT_TAB_PREFIX = os.getenv("HUWEI_PLAN_TAB_PREFIX", "TH")
DEFAULT_TIMEOUT = int(os.getenv("HUWEI_PLAN_FETCH_TIMEOUT", "30"))

GVIZ_URL = "https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq"

# ---------------------------------------------------------------------------
# Sheet layout
# ---------------------------------------------------------------------------
# Keyed by spreadsheet column letter rather than by header text on purpose:
# columns S onward have no header at all, and gviz returns cells for them
# regardless. HEADER_ANCHORS below guards against the columns being reordered.
COLUMNS = {
    "date": "A",
    "carrier": "B",
    "vehicle": "C",
    "driver_name": "D",
    "driver_id_number": "E",
    "driver_phone": "F",
    "vehicle_type": "G",
    "sequence": "H",
    "station_code": "I",
    "incident_note": "J",
    "product_description": "K",
    "lat": "L",
    "lng": "M",
    "address": "N",
    "province": "O",
    "district": "P",
    "manager_name": "Q",
    "manager_phone": "R",
}

# Columns S.. hold unlabelled free-text handling notes ("Để được trong phòng
# máy thiết bị", "Thuê xe ba gác", distances, ...). Count varies by row. They
# are tab-joined into `note`, matching the format already present in
# delivery_plan_stops.note from the Excel importer.
NOTE_EXTRA_FIRST_COLUMN = "S"

# Substring that must appear (accent- and case-insensitively) in the gviz label
# for the given column. If any fails, the manager has reordered or inserted
# columns and every mapping below is suspect — we refuse rather than import
# garbage into a dispatch plan.
HEADER_ANCHORS = {
    "A": "date",
    "C": "so xe",
    "D": "tai xe",
    "H": "stt",
    "I": "tram phat",
    "K": "kgs",
    "L": "lat",
    "M": "long",
    "N": "dia chi",
}

# Sentinel in column J meaning "nothing to report" — 300+ rows carry it and it
# would otherwise become noise in every note.
NO_INCIDENT_TOKENS = {"khong co phat sinh"}

# Placeholders that mean "empty" in the trailing note columns. '0' is included
# because the sheet uses it as a filler there; it is NOT treated as empty in
# any other column.
NOTE_PLACEHOLDERS = {"", "0", "#n/a", "-", "n/a"}


# ---------------------------------------------------------------------------
# Coordinate repair
# ---------------------------------------------------------------------------
# The fleet operates in the Mekong Delta / southern Vietnam. These bounds are
# what makes decimal-point recovery unambiguous: they do not overlap, so for a
# given digit string at most one decimal placement can be a valid latitude and
# at most one can be a valid longitude.
VN_LAT_RANGE = (8.0, 24.0)
VN_LNG_RANGE = (102.0, 110.0)


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------
MONTH_NAMES = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

# The sheet's dates carry no year, so it is inferred from the requested date.
# The inference is never trusted blindly: the chosen year must put the parsed
# date within this many days of the requested date, otherwise the row is
# reported instead of being silently attributed to a plausible-looking year.
# 120 days is wider than the ~1 month a dispatch tab spans and far narrower
# than the 183 days at which every month/day would trivially qualify.
DATE_INFERENCE_WINDOW_DAYS = 120


class SheetImportError(Exception):
    """Base class for every failure in this module."""


class SheetFetchError(SheetImportError):
    """The sheet could not be retrieved or the response was not gviz JSON."""


class SheetTabMissing(SheetFetchError):
    """The named worksheet does not exist in the spreadsheet.

    Split out from SheetFetchError because the tab search in
    :func:`fetch_plan_for_date` must tolerate a month tab that has not been
    created yet while still failing loudly on a genuine outage. Collapsing the
    two reported "no plan for that date" whenever the network was down, sending
    the dispatcher to check a sheet that was fine.
    """


class SheetLayoutError(SheetImportError):
    """The sheet's columns are not where this importer expects them."""


class SheetDateNotFound(SheetImportError):
    """No row in any candidate tab carries the requested date."""


@dataclass
class Warning_:
    """One thing a dispatcher should look at before committing the import."""

    sheet_row: Optional[int]
    field: str
    message: str
    station_code: str = ""

    def as_dict(self) -> dict:
        return {
            "sheet_row": self.sheet_row,
            "field": self.field,
            "message": self.message,
            "station_code": self.station_code,
        }


@dataclass
class ExtractResult:
    rows: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    tab_name: str = ""

    def as_dict(self) -> dict:
        return {
            "rows": self.rows,
            "warnings": [w.as_dict() for w in self.warnings],
            "tab_name": self.tab_name,
        }


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _strip_accents(text: str) -> str:
    """Fold Vietnamese text to plain ASCII letters.

    ``Đ``/``đ`` must be handled explicitly: unlike the tone-marked vowels it is
    a distinct letter rather than a base plus a combining mark, so NFD leaves it
    untouched and ``ĐỊA CHỈ GIAO HÀNG`` folds to ``đia chi giao hang`` — which
    then fails a header check written as ``dia chi``.
    """
    text = str(text).replace("Đ", "D").replace("đ", "d")
    return "".join(
        ch for ch in unicodedata.normalize("NFD", text)
        if unicodedata.category(ch) != "Mn"
    )


def _fold(text: str) -> str:
    """Lowercase, accent-stripped, whitespace-collapsed — for header matching."""
    return re.sub(r"\s+", " ", _strip_accents(str(text or "")).lower()).strip()


def column_index(letter: str) -> int:
    """'A' -> 0, 'S' -> 18, 'AA' -> 26."""
    total = 0
    for ch in letter.upper():
        total = total * 26 + (ord(ch) - ord("A") + 1)
    return total - 1


def _cell(row: list, letter: str) -> str:
    idx = column_index(letter)
    if idx >= len(row):
        return ""
    value = row[idx]
    if value is None:
        return ""
    return str(value).strip()


def parse_coordinate(raw, kind: str) -> tuple[Optional[float], Optional[str]]:
    """Recover a decimal degree value from the sheet's inconsistent formatting.

    ``kind`` is ``"lat"`` or ``"lng"`` and selects the plausibility window that
    disambiguates where the decimal point belongs.

    The sheet writes the same column three different ways — ``9,636058``,
    ``9.60967``, and ``9.585.868`` where the decimal point was lost to
    thousands-separator formatting. Rather than guess at the formatting, this
    reduces the cell to its digits and then asks which single decimal placement
    yields a coordinate inside Vietnam. Because the latitude and longitude
    windows do not overlap, that placement is unique in practice:

    >>> parse_coordinate("9.585.868", "lat")[0]
    9.585868
    >>> parse_coordinate("1.059.744", "lng")[0]
    105.9744
    >>> parse_coordinate("106,491648", "lng")[0]
    106.491648

    Returns ``(value, None)`` on success and ``(None, reason)`` when the cell
    is empty, has no digits, or cannot be placed inside the window. A caller
    that gets ``None`` must leave the coordinate empty and surface the reason —
    it must never fall back to a "best guess" number, which is the failure this
    function exists to prevent.
    """
    if raw is None:
        return None, "coordinate is empty"

    # A genuine float (should the sheet ever be fixed to hold numbers) needs no
    # repair — only a range check.
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        value = float(raw)
        low, high = VN_LAT_RANGE if kind == "lat" else VN_LNG_RANGE
        if low <= value <= high:
            return value, None
        return None, f"{kind} {value} is outside Vietnam ({low}–{high})"

    text = str(raw).strip()
    if not text:
        return None, "coordinate is empty"

    negative = text.lstrip().startswith("-")
    digits = re.sub(r"\D", "", text)
    if not digits:
        return None, f"{kind} {text!r} contains no digits"
    digits = digits.lstrip("0") or "0"

    low, high = VN_LAT_RANGE if kind == "lat" else VN_LNG_RANGE
    candidates = []
    for split in range(1, min(len(digits), 3) + 1):
        whole, frac = digits[:split], digits[split:]
        try:
            value = float(f"{whole}.{frac}") if frac else float(whole)
        except ValueError:  # pragma: no cover - defensive
            continue
        if negative:
            value = -value
        if low <= value <= high:
            candidates.append(value)

    unique = sorted(set(candidates))
    if not unique:
        return None, (
            f"{kind} {text!r} cannot be read as a coordinate inside Vietnam "
            f"({low}–{high})"
        )
    if len(unique) > 1:
        # Not reachable with the current windows, but the windows are config,
        # not a law of nature. Refusing beats picking one at random.
        return None, (
            f"{kind} {text!r} is ambiguous — could be any of "
            f"{', '.join(str(c) for c in unique)}"
        )
    return unique[0], None


def parse_sheet_date(
    text, reference: date
) -> tuple[Optional[date], Optional[str]]:
    """Parse a year-less, hand-typed date cell against a reference date.

    Handles every form observed in the sheet: ``21-Jul``, ``2-Aug``, ``10-Aug``,
    ``01-th8`` (Vietnamese *tháng 8*), and numeric ``21/07`` / ``21-07``.
    Numeric pairs are read day-first, matching Vietnamese convention and the
    rest of the document.

    The year is inferred by picking, from the reference year and its
    neighbours, the one that places the date closest to ``reference``. That
    inference is then **validated**: if the winning candidate is further than
    :data:`DATE_INFERENCE_WINDOW_DAYS` from the reference, or if two years tie,
    the date is still returned but with a warning string, because a
    year-less cell that lands four months from the day being planned is more
    likely a typo than a real plan.
    """
    if text is None:
        return None, "date cell is empty"
    raw = str(text).strip()
    if not raw:
        return None, "date cell is empty"

    tokens = [t for t in re.split(r"[^0-9A-Za-zÀ-ỹ]+", raw) if t]
    if len(tokens) < 2:
        return None, f"date {raw!r} is not recognisable as a day and month"

    day = month = None
    for token in tokens:
        folded = _fold(token)
        if folded.isdigit():
            number = int(folded)
            if day is None:
                day = number
            elif month is None:
                month = number
            continue
        # 'th8', 'thang8', 'thg8' -> month 8
        vn = re.fullmatch(r"th(?:a?ng?)?\.?(\d{1,2})", folded)
        if vn:
            month = int(vn.group(1))
            continue
        if folded in MONTH_NAMES:
            month = MONTH_NAMES[folded]
            continue
        vn_bare = re.fullmatch(r"th(?:a?ng?)?", folded)
        if vn_bare:
            continue  # 'thang 8' split into two tokens; digit handled above
        return None, f"date {raw!r} contains unrecognised text {token!r}"

    # 'thang 8' style leaves the month sitting in `day` if it arrived first.
    if month is None and day is not None and len(tokens) >= 2:
        return None, f"date {raw!r} is missing a month"
    if day is None or month is None:
        return None, f"date {raw!r} is missing a day or a month"
    if not 1 <= month <= 12:
        return None, f"date {raw!r} has month {month} out of range"

    best = None
    for year in (reference.year - 1, reference.year, reference.year + 1):
        try:
            candidate = date(year, month, day)
        except ValueError:
            continue  # 29 Feb in a non-leap year, day 31 in a 30-day month
        delta = abs((candidate - reference).days)
        if best is None or delta < best[0]:
            best = (delta, candidate, False)
        elif delta == best[0]:
            best = (best[0], best[1], True)

    if best is None:
        return None, f"date {raw!r} is not a real calendar date"

    delta, parsed, tied = best
    if tied:
        return parsed, (
            f"date {raw!r} is equally close to two years; read as "
            f"{parsed.isoformat()}"
        )
    if delta > DATE_INFERENCE_WINDOW_DAYS:
        return parsed, (
            f"date {raw!r} has no year in the sheet; the nearest reading "
            f"({parsed.isoformat()}) is {delta} days from the requested "
            f"{reference.isoformat()}"
        )
    return parsed, None


def _clean_phone(value: str) -> str:
    """Reduce a phone cell to digits, undoing two numeric-cell corruptions.

    The sheet's phone columns are text in some rows and *numeric* in others,
    and a numeric cell loses information twice on the way here:

    * **Sheets drops the leading zero.** ``0939746130`` typed into a
      number-formatted cell is the integer 939746130, and gviz reports it as
      such. Every Vietnamese mobile number starts ``0``, so a 9-digit result
      is that zero missing and nothing else — it is restored, not guessed.
    * **gviz reports the value as a float, and the old regex welded the
      fraction on.** ``cell["v"]`` is ``939746130.0``; ``_cell`` stringifies it
      to ``"939746130.0"``; stripping non-digits deleted the decimal point and
      left the trailing ``0`` attached, yielding ``9397461300``. The fraction
      is therefore removed *before* the digit strip.

    Both were observed together in production: on 2026-08-15 one manager's
    single number was stored three ways across 14 stops — ``0939746130`` from
    a text cell, ``939746130`` and ``9397461300`` from numeric ones. 85 of the
    118 malformed rows carried the welded zero, with no exceptions, which is
    what identified the float as the cause rather than the dispatcher's typing.

    A number that already starts ``0``, or that carries a ``+`` country
    prefix, is left alone — those arrive as text and were never corrupted.
    """
    raw = re.sub(r"\s+", "", value or "")
    # "939746130.0" / "939746130,0" — a float that lost nothing but its point.
    # Only an all-zero fraction is dropped; anything else is not this bug and
    # is left for the digit strip to deal with as before.
    raw = re.sub(r"^(\+?\d+)[.,]0+$", r"\1", raw)
    digits = re.sub(r"[^\d+]", "", raw)
    # 9 significant digits is a VN mobile number minus its leading zero.
    if len(digits) == 9 and digits.isdigit():
        digits = "0" + digits
    return digits


def candidate_tabs(target: date, prefix: str = DEFAULT_TAB_PREFIX) -> list:
    """Tab names to search, most recent first.

    The sheet keeps one tab per month (``TH08``, ``TH07``). The requested date
    normally lives in its own month's tab, but a tab spans slightly more than
    its month — TH08 held rows from 21-Jul onward — so the previous month's tab
    is a fallback rather than a guess.
    """
    previous_month = (target.replace(day=1) - timedelta(days=1))
    names = [f"{prefix}{target.month:02d}", f"{prefix}{previous_month.month:02d}"]
    seen = []
    for name in names:
        if name not in seen:
            seen.append(name)
    return seen


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def _parse_gviz_payload(body: str) -> dict:
    """Unwrap the ``…setResponse({...});`` envelope gviz replies with."""
    match = re.search(r"setResponse\(\s*(\{.*\})\s*\)\s*;?\s*$", body, re.S)
    if not match:
        raise SheetFetchError(
            "Response was not a Google Visualisation payload. The sheet may "
            "no longer be shared by link, or the id may be wrong."
        )
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise SheetFetchError(f"Could not decode the sheet response: {exc}")

    if payload.get("status") == "error":
        errors = payload.get("errors", [])
        detail = "; ".join(
            e.get("detailed_message") or e.get("message", "") for e in errors
        )
        reasons = {str(e.get("reason", "")).lower() for e in errors}
        folded = _fold(detail)
        # gviz has no dedicated "no such worksheet" status, so the tab-missing
        # case has to be recognised from the message. If Google ever rephrases
        # it this falls through to a plain SheetFetchError — which surfaces
        # Google's own wording to the dispatcher rather than pretending the day
        # was empty, so the failure mode of this heuristic is loud, not silent.
        if "not_found" in reasons or "invalid sheet" in folded or "sheet name" in folded:
            raise SheetTabMissing(f"Worksheet not found: {detail}")
        raise SheetFetchError(f"Google rejected the query: {detail}")
    return payload


def fetch_tab(
    tab_name: str,
    sheet_id: str = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """GET one worksheet through gviz. Read-only; there is no write variant."""
    sheet_id = sheet_id or DEFAULT_SHEET_ID
    params = {
        "tqx": "out:json",
        "sheet": tab_name,
        "headers": "1",
        "tq": "select *",
    }
    try:
        response = requests.get(
            GVIZ_URL.format(sheet_id=sheet_id), params=params, timeout=timeout
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise SheetFetchError(f"Could not reach the Google Sheet: {exc}")
    return _parse_gviz_payload(response.text)


def grid_from_payload(payload: dict) -> tuple[list, list]:
    """Flatten a gviz payload into ``(header_labels, rows_of_strings)``.

    Cell values are taken from ``v`` and fall back to the formatted ``f``.
    Every column in this sheet is text — including the coordinates, which is
    the whole reason :func:`parse_coordinate` exists — so no type coercion
    happens here.
    """
    table = payload.get("table") or {}
    cols = table.get("cols") or []
    labels = [c.get("label", "") for c in cols]

    rows = []
    for entry in table.get("rows") or []:
        cells = entry.get("c") or []
        row = []
        for cell in cells:
            if not cell:
                row.append("")
                continue
            value = cell.get("v")
            if value is None:
                value = cell.get("f")
            row.append("" if value is None else value)
        rows.append(row)
    return labels, rows


def validate_layout(labels: list) -> None:
    """Refuse to import if the columns have moved."""
    problems = []
    for letter, expected in HEADER_ANCHORS.items():
        idx = column_index(letter)
        actual = _fold(labels[idx]) if idx < len(labels) else ""
        if expected not in actual:
            problems.append(
                f"column {letter} should contain {expected!r} but reads "
                f"{actual or '(empty)'!r}"
            )
    if problems:
        raise SheetLayoutError(
            "The planning sheet's columns are not where this importer expects "
            "them: " + "; ".join(problems) + ". The sheet layout changed — the "
            "column map in sheet_import_service.COLUMNS needs updating before "
            "importing again."
        )


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def _row_is_blank(row: list) -> bool:
    return not any(str(v).strip() for v in row)


def _is_stop_row(row: list) -> bool:
    """A row describes a stop if it carries any stop-level content.

    Separator rows (the sheet uses a blank cyan row between days) and rows
    holding only a leftover date fail this test.
    """
    return any(
        _cell(row, COLUMNS[key])
        for key in ("station_code", "product_description", "lat", "lng", "address")
    )


def _assemble_note(row: list) -> str:
    parts = []
    incident = _cell(row, COLUMNS["incident_note"])
    if incident and _fold(incident) not in NO_INCIDENT_TOKENS:
        parts.append(incident)
    start = column_index(NOTE_EXTRA_FIRST_COLUMN)
    for value in row[start:]:
        text = str(value or "").strip()
        if _fold(text) in NOTE_PLACEHOLDERS:
            continue
        parts.append(text)
    return "\t".join(parts)


def extract_day(rows: list, target: date, tab_name: str = "") -> ExtractResult:
    """Turn a worksheet grid into import rows for one dispatch day.

    Two pieces of state are carried down the sheet, because the document only
    writes them once per block:

    * the **date**, which continuation rows leave blank;
    * the **vehicle, driver and vehicle type**, which appear only on the first
      row of each truck's block. A new non-empty plate cell starts a new block.

    Forward-filling happens over the whole tab in sheet order *before* the date
    filter, since a block's identity is established by rows that may themselves
    be outside the requested day.
    """
    result = ExtractResult(tab_name=tab_name)

    current_date: Optional[date] = None
    current_date_warned = False
    vehicle = driver_name = vehicle_type = ""
    sequence_in_block = 0
    date_warnings_seen = set()

    for offset, row in enumerate(rows):
        sheet_row = offset + 2  # gviz consumed row 1 as the header

        if _row_is_blank(row):
            continue

        date_text = _cell(row, COLUMNS["date"])
        if date_text:
            parsed, warning = parse_sheet_date(date_text, target)
            if warning and warning not in date_warnings_seen:
                date_warnings_seen.add(warning)
                result.warnings.append(
                    Warning_(sheet_row=sheet_row, field="date", message=warning)
                )
            current_date = parsed
            current_date_warned = parsed is None
        # else: continuation row — keep current_date

        plate = _cell(row, COLUMNS["vehicle"])
        if plate:
            vehicle = plate
            driver_name = _cell(row, COLUMNS["driver_name"])
            vehicle_type = _cell(row, COLUMNS["vehicle_type"])
            sequence_in_block = 0

        if current_date != target:
            continue
        if not _is_stop_row(row):
            continue

        sequence_in_block += 1
        station_code = _cell(row, COLUMNS["station_code"])

        if not vehicle:
            result.warnings.append(Warning_(
                sheet_row=sheet_row, field="vehicle", station_code=station_code,
                message="no vehicle found for this stop — the plate cell above "
                        "it is empty",
            ))
        if not station_code:
            result.warnings.append(Warning_(
                sheet_row=sheet_row, field="station_code",
                message="station code (TRẠM PHÁT) is empty",
            ))

        lat, lat_problem = parse_coordinate(_cell(row, COLUMNS["lat"]), "lat")
        lng, lng_problem = parse_coordinate(_cell(row, COLUMNS["lng"]), "lng")
        if lat is None or lng is None:
            # A half coordinate is worse than none: it would place the stop on
            # the equator or the prime meridian. Drop both and say why.
            reason = lat_problem or lng_problem
            if lat_problem and lng_problem and lat_problem != lng_problem:
                reason = f"{lat_problem}; {lng_problem}"
            lat = lng = None
            result.warnings.append(Warning_(
                sheet_row=sheet_row, field="coordinates",
                station_code=station_code,
                message=f"{reason} — imported without coordinates, so this "
                        "stop has no map marker or ETA until it is filled in",
            ))

        sequence_text = _cell(row, COLUMNS["sequence"])
        try:
            sequence = int(float(sequence_text)) if sequence_text else sequence_in_block
        except ValueError:
            sequence = sequence_in_block
            result.warnings.append(Warning_(
                sheet_row=sheet_row, field="sequence",
                station_code=station_code,
                message=f"priority (STT ƯU TIÊN) {sequence_text!r} is not a "
                        f"number — using position {sequence_in_block} instead",
            ))

        address = _cell(row, COLUMNS["address"])
        if not address:
            fallback = [
                _cell(row, COLUMNS["district"]),
                _cell(row, COLUMNS["province"]),
            ]
            address = ", ".join(p for p in fallback if p)
            if address:
                result.warnings.append(Warning_(
                    sheet_row=sheet_row, field="address",
                    station_code=station_code,
                    message="delivery address is empty — using the district and "
                            f"province instead ({address})",
                ))

        result.rows.append({
            "vehicle": vehicle,
            "driver_name": driver_name,
            "vehicle_type": vehicle_type,
            "sequence": sequence,
            "station_code": station_code,
            "station_name": station_code,
            "address": address,
            "lat": lat,
            "lng": lng,
            "manager_name": _cell(row, COLUMNS["manager_name"]),
            "manager_phone": _clean_phone(_cell(row, COLUMNS["manager_phone"])),
            "product_description": _cell(row, COLUMNS["product_description"]),
            "note": _assemble_note(row),
            "sheet_row": sheet_row,
        })

    if current_date_warned:
        logger.debug("Unparseable date cells were present in tab %s", tab_name)
    return result


def fetch_plan_for_date(
    target: date,
    sheet_id: str = None,
    tab_names: list = None,
    fetcher: Callable[..., dict] = None,
) -> ExtractResult:
    """Read the plan for one date, trying the month's tab then the previous.

    ``fetcher`` is injected so the parser can be exercised against fixtures
    without touching the network; production leaves it at :func:`fetch_tab`.
    """
    fetcher = fetcher or fetch_tab
    tabs = tab_names or candidate_tabs(target)

    missing = []
    for tab in tabs:
        try:
            payload = fetcher(tab, sheet_id=sheet_id)
        except SheetTabMissing as exc:
            # A month tab that does not exist yet is normal on the 1st; keep
            # looking rather than failing the whole import. Note this catches
            # *only* SheetTabMissing — a SheetFetchError from an outage
            # propagates, because "the network is down" and "the plan isn't
            # filled in" need opposite responses from the dispatcher.
            logger.info("Tab %s does not exist: %s", tab, exc)
            missing.append(tab)
            continue
        labels, rows = grid_from_payload(payload)
        validate_layout(labels)
        result = extract_day(rows, target, tab_name=tab)
        if result.rows:
            return result

    tried = ", ".join(tabs)
    detail = f" (could not open: {', '.join(missing)})" if missing else ""
    raise SheetDateNotFound(
        f"No stops dated {target.isoformat()} were found in the planning "
        f"sheet. Tabs searched: {tried}{detail}. Check that the plan for that "
        "date has been filled in."
    )
