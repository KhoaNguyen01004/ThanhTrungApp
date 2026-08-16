"""
Google Sheets Fuel Log Synchronization Service

Reads fuel records from a Google Spreadsheet and synchronizes them
into the local ``fuel_log`` table.

Usage::

    from services.google_sheet_service import GoogleSheetService

    GoogleSheetService().sync_to_database()
"""

import logging
import os
import re
import sqlite3
import time
from datetime import datetime
from typing import Any, Optional

import gspread
from google.oauth2.service_account import Credentials

from services.plate_utils import normalize_plate

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults – can be overridden via constructor argument or environment variable
# ---------------------------------------------------------------------------
DEFAULT_CREDENTIALS_PATH = "credentials.json"
DEFAULT_SPREADSHEET_ID = "1vb1Xdrs459n4-oxTbmKteUy9mxa69HY9MLK7NYZ0GWA"
DEFAULT_WORKSHEET_NAME = "DINH_MUC_TONG"
DEFAULT_TABLE_RANGE = "B3:P"

# Mapping: spreadsheet column header -> fuel_log column name
HEADER_TO_FIELD = {
    "NGAY": "log_date",
    "GIO": "log_time",
    "CUA_HANG": "gas_store",
    "XE": "license_plate",
    "KM_CU": "old_km",
    "KM_MOI": "new_km",
    "LIT": "liters",
    "DON_GIA": "unit_price",
    "TAI_XE": "driver_name",
    "NOTE": "notes",
}

# Spreadsheet columns we intentionally ignore
IGNORED_HEADERS = frozenset({"STT", "Δ KM", "THANH_TIEN", "DINH_MUC", "IN_RANGE?"})

INTEGER_FIELDS = {"old_km", "new_km", "unit_price"}
FLOAT_FIELDS = {"liters"}

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------
def _strip_currency(value: str) -> str:
    """Remove currency symbols (``₫``, ``$``, etc.) and surrounding whitespace."""
    return re.sub(r'[^\d,.\-]', '', value.strip())


def parse_int(value: Any) -> Optional[int]:
    """Parse a cell value to ``int``, handling thousand-separators and currency symbols."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    cleaned = _strip_currency(str(value))
    if not cleaned:
        return None
    cleaned = cleaned.replace(",", "").replace(".", "")
    try:
        return int(cleaned)
    except (ValueError, TypeError):
        return None


def parse_float(value: Any) -> Optional[float]:
    """Parse a cell value to ``float``, handling thousand-separators and currency symbols.

    Supports both Vietnamese (``1.234,56``) and international (``1,234.56``) formats.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = _strip_currency(str(value))
    if not cleaned:
        return None

    # Determine decimal-separator convention
    if "." in cleaned and "," in cleaned:
        # Whichever appears last is the decimal separator
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        # Single comma – treat as decimal if it's the only one, else thousand-sep
        if cleaned.count(",") == 1:
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")

    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def parse_date_ngay(value: Any) -> Optional[str]:
    """Parse a spreadsheet date to ``YYYY-MM-DD``.

    Accepts ``DD/MM/YYYY`` (the spreadsheet format) and ``YYYY-MM-DD``.
    """
    if not value or not isinstance(value, str):
        return None
    value = value.strip()
    if not value:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def parse_time_gio(value: Any) -> Optional[str]:
    """Parse a spreadsheet time to ``HH:MM``."""
    if not value or not isinstance(value, str):
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%H:%M").strftime("%H:%M")
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------
class GoogleSheetService:
    """Synchronise fuel-log records from a Google Spreadsheet into the local database.

    Parameters are read from environment variables when not passed explicitly::

        GOOGLE_CREDENTIALS_PATH  (default: ``credentials.json``)
        GOOGLE_SHEET_ID          (default: the spreadsheet ID from the task brief)
        GOOGLE_WORKSHEET_NAME    (default: ``DINH_MUC_TONG``)
        GOOGLE_TABLE_RANGE       (default: ``B3:P``)
        DB_PATH                  (default: ``routing_system.db``)
    """

    def __init__(
        self,
        credentials_path: Optional[str] = None,
        spreadsheet_id: Optional[str] = None,
        worksheet_name: Optional[str] = None,
        table_range: Optional[str] = None,
        db_path: Optional[str] = None,
    ) -> None:
        self.credentials_path = (
            credentials_path
            or os.getenv("GOOGLE_CREDENTIALS_PATH")
            or DEFAULT_CREDENTIALS_PATH
        )
        self.spreadsheet_id = (
            spreadsheet_id
            or os.getenv("GOOGLE_SHEET_ID")
            or DEFAULT_SPREADSHEET_ID
        )
        self.worksheet_name = (
            worksheet_name
            or os.getenv("GOOGLE_WORKSHEET_NAME")
            or DEFAULT_WORKSHEET_NAME
        )
        self.table_range = (
            table_range
            or os.getenv("GOOGLE_TABLE_RANGE")
            or DEFAULT_TABLE_RANGE
        )
        self.db_path = (
            db_path
            or os.getenv("DB_PATH")
            or "routing_system.db"
        )
        self._worksheet: Any = None

    # -- Google Sheets access ------------------------------------------------

    def _get_worksheet(self):
        """Return a :class:`gspread.Worksheet`, caching it after the first call."""
        if self._worksheet is not None:
            return self._worksheet

        creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
        if creds_json:
            import json
            creds = Credentials.from_service_account_info(
                json.loads(creds_json), scopes=SCOPES
            )
        else:
            creds = Credentials.from_service_account_file(
                self.credentials_path, scopes=SCOPES
            )
        client = gspread.authorize(creds)
        workbook = client.open_by_key(self.spreadsheet_id)
        self._worksheet = workbook.worksheet(self.worksheet_name)
        return self._worksheet

    # -- Fetch & normalise ---------------------------------------------------

    def fetch_records(self) -> list[dict[str, Any]]:
        """Read all rows from the configured spreadsheet range.

        Returns a list of dictionaries keyed by spreadsheet column header.
        Completely empty rows are skipped.
        """
        worksheet = self._get_worksheet()
        values = worksheet.get(self.table_range)

        if not values or len(values) < 1:
            return []

        raw_headers = values[0]
        rows = values[1:]

        headers = [h.strip() if h else "" for h in raw_headers]

        records: list[dict[str, Any]] = []
        for row in rows:
            extended = row + [""] * (len(headers) - len(row))
            record = {}
            empty = True
            for h, v in zip(headers, extended):
                record[h] = v
                if v and str(v).strip():
                    empty = False
            if not empty:
                records.append(record)

        return records

    def normalize_record(self, row: dict[str, Any]) -> dict[str, Any]:
        """Convert a raw spreadsheet row into a ``fuel_log``-compatible dictionary.

        Handles type conversion, currency cleaning, date/time parsing, and
        ignores columns that have no counterpart in the database.
        """
        normalized: dict[str, Any] = {}

        for sheet_header, field_name in HEADER_TO_FIELD.items():
            raw = row.get(sheet_header)

            if field_name in INTEGER_FIELDS:
                normalized[field_name] = parse_int(raw)
            elif field_name in FLOAT_FIELDS:
                normalized[field_name] = parse_float(raw)
            else:
                normalized[field_name] = str(raw).strip() if raw is not None else ""

        # Re-parse date/time with explicit formatters
        parsed_date = parse_date_ngay(row.get("NGAY"))
        if parsed_date is not None:
            normalized["log_date"] = parsed_date

        parsed_time = parse_time_gio(row.get("GIO"))
        if parsed_time is not None:
            normalized["log_time"] = parsed_time

        # Default: assume full-tank (matches the DB default)
        normalized["is_full_tank"] = 1

        return normalized

    # -- Duplicate detection -------------------------------------------------

    @staticmethod
    def _build_unique_key(record: dict[str, Any]) -> tuple:
        """Return a stable unique key for a normalised record.

        Uses ``(normalized_license_plate, log_date, log_time, new_km)`` – a
        combination that is resilient to row insertions (unstable STT).

        The plate is normalised so that a record with ``09473`` and one with
        ``50H-09473`` are treated as duplicates of each other.
        """
        return (
            normalize_plate(record.get("license_plate") or ""),
            record.get("log_date") or "",
            record.get("log_time") or "",
            record.get("new_km") or 0,
        )

    def _fetch_existing_keys(self) -> set[tuple]:
        """Query all existing unique-key tuples from the ``fuel_log`` table.

        Plates are normalised so that e.g. ``09473`` and ``50H-09473``
        produce the same key, preventing duplicate insertions when the
        spreadsheet and database use different plate formats.
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT license_plate, log_date, log_time, new_km FROM fuel_log"
            )
            return {
                (normalize_plate(r[0]), r[1], r[2], r[3]) for r in cur.fetchall()
            }
        finally:
            conn.close()

    def _build_plate_map(self) -> dict[str, tuple[str, int]]:
        """Build a mapping of normalised suffix → ``(full_plate, vehicle_id)``.

        Used to resolve partial plates from the spreadsheet (e.g. ``09473``)
        to the corresponding vehicle in the database (e.g. ``50H-09473``).

        When multiple vehicles share the same suffix (e.g. a numeric-only
        duplicate and the original full-plate vehicle), the **full plate**
        (non-numeric) is preferred so that the original vehicle is used.
        """
        mapping: dict[str, tuple[str, int]] = {}
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.cursor()
            cur.execute("SELECT id, plate_number FROM vehicles")
            for vid, vplate in cur.fetchall():
                key = normalize_plate(vplate)
                if not key:
                    continue
                is_numeric = vplate.isdigit() and len(vplate) == 5
                # Always prefer a full (non-numeric) plate over a numeric-only one
                if not is_numeric or key not in mapping:
                    mapping[key] = (vplate, vid)
        finally:
            conn.close()
        return mapping

    def get_new_records(self) -> list[dict[str, Any]]:
        """Return spreadsheet records that do not already exist in the database.

        Plates are resolved to full canonical form before duplicate detection,
        so a row containing ``09473`` will be matched against an existing
        record whose plate is ``50H-09473``.

        Records whose plate suffix does **not** match any existing vehicle
        are skipped — the system never creates new vehicles from sync data.
        """
        raw = self.fetch_records()
        existing = self._fetch_existing_keys()
        plate_map = self._build_plate_map()

        result: list[dict[str, Any]] = []
        skip_count = 0
        for r in raw:
            norm = self.normalize_record(r)

            # Resolve partial plate → full plate, or skip if unknown
            plate = norm.get("license_plate", "")
            suffix = normalize_plate(plate)
            if suffix in plate_map:
                full_plate, vehicle_id = plate_map[suffix]
                norm["license_plate"] = full_plate
                norm["vehicle_id"] = vehicle_id
            elif suffix:
                logger.warning(
                    "Skipping record with unknown plate '%s' (suffix '%s') "
                    "- no matching vehicle found.",
                    plate, suffix,
                )
                skip_count += 1
                continue

            if self._build_unique_key(norm) not in existing:
                result.append(norm)

        if skip_count:
            logger.info("Skipped %d record(s) with no matching vehicle.", skip_count)

        return result

    # -- Database insertion --------------------------------------------------

    @staticmethod
    def _val(value: Any, default: Any = "") -> Any:
        """Return ``value`` if not ``None``, else ``default``."""
        return default if value is None else value

    def _insert_record(self, record: dict[str, Any]) -> bool:
        """Insert a single row into ``fuel_log``.  Returns ``True`` on success.

        The ``vehicle_id`` column is populated when the plate was resolved
        to an existing vehicle via :meth:`_build_plate_map`.
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO fuel_log
                    (license_plate, log_date, log_time, gas_store,
                     old_km, new_km, liters, driver_name,
                     unit_price, notes, is_full_tank, vehicle_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self._val(record.get("license_plate"), ""),
                    self._val(record.get("log_date"), ""),
                    self._val(record.get("log_time"), ""),
                    self._val(record.get("gas_store"), ""),
                    self._val(record.get("old_km"), 0),
                    self._val(record.get("new_km"), 0),
                    self._val(record.get("liters"), 0.0),
                    self._val(record.get("driver_name"), ""),
                    record.get("unit_price"),  # unit_price has no default in schema
                    self._val(record.get("notes"), ""),
                    self._val(record.get("is_full_tank"), 1),
                    record.get("vehicle_id"),  # None → SQL NULL
                ),
            )
            conn.commit()
            return True
        except Exception as exc:
            logger.error("Failed to insert record %s: %s", record, exc)
            return False
        finally:
            conn.close()

    # -- Orchestration -------------------------------------------------------

    def sync_to_database(self) -> dict[str, int]:
        """Perform a complete synchronisation from Google Sheets to the database.

        The method:
        * Reads all rows from the spreadsheet.
        * Filters out rows that already exist in the DB (duplicate detection).
        * Inserts only new rows.
        * Logs a summary of the operation.

        Returns a dictionary with keys ``fetched``, ``inserted``, ``duplicate``,
        and ``failed``.
        """
        start = time.perf_counter()
        summary: dict[str, int] = {
            "fetched": 0,
            "inserted": 0,
            "duplicate": 0,
            "skipped": 0,
            "failed": 0,
        }

        header = f"{'=' * 34}\nGoogle Sheet Synchronization\n{'=' * 34}"
        print(header)
        print()

        try:
            _t = time.perf_counter()
            raw_records = self.fetch_records()
            print(f"fetch_records: {time.perf_counter() - _t:.2f}s")
            summary["fetched"] = len(raw_records)

            if not raw_records:
                print("No records found in spreadsheet.")
                self._print_footer(start, summary)
                return summary

            _t = time.perf_counter()
            existing_keys = self._fetch_existing_keys()
            print(f"fetch_existing_keys: {time.perf_counter() - _t:.2f}s")

            _t = time.perf_counter()
            plate_map = self._build_plate_map()
            print(f"build_plate_map: {time.perf_counter() - _t:.2f}s")

            _t = time.perf_counter()
            for raw in raw_records:
                try:
                    norm = self.normalize_record(raw)

                    # Resolve partial plate → full plate
                    plate = norm.get("license_plate", "")
                    suffix = normalize_plate(plate)
                    if suffix in plate_map:
                        full_plate, vehicle_id = plate_map[suffix]
                        norm["license_plate"] = full_plate
                        norm["vehicle_id"] = vehicle_id
                    elif suffix:
                        logger.warning(
                            "Skipping record with unknown plate '%s' (suffix '%s') "
                            "- no matching vehicle found.",
                            plate, suffix,
                        )
                        summary["skipped"] = summary.get("skipped", 0) + 1
                        continue

                    key = self._build_unique_key(norm)

                    if key in existing_keys:
                        summary["duplicate"] += 1
                        continue

                    if self._insert_record(norm):
                        summary["inserted"] += 1
                        existing_keys.add(key)
                    else:
                        summary["failed"] += 1

                except Exception as exc:
                    logger.error("Error processing row %s: %s", raw, exc)
                    summary["failed"] += 1

        except Exception as exc:
            logger.error("Synchronization failed: %s", exc)
            raise

        elapsed = time.perf_counter() - start
        summary["duration_sec"] = round(elapsed, 2)
        self._print_footer(elapsed, summary)
        return summary

    @staticmethod
    def _print_footer(elapsed: float, summary: dict[str, int]) -> None:
        print(f"Fetched rows:      {summary['fetched']}")
        print(f"Inserted rows:     {summary['inserted']}")
        print(f"Duplicate rows:    {summary['duplicate']}")
        print(f"Skipped rows:      {summary.get('skipped', 0)}")
        print(f"Failed rows:       {summary['failed']}")
        print()
        print(f"Completed in:\n{elapsed:.2f} seconds")
