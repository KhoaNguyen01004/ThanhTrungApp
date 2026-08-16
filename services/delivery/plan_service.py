import logging
from datetime import date, datetime
from typing import Optional

from app.db import DatabaseManager
from services.plate_utils import normalize_plate
from services.vehicle_identity import build_index, canonical_plate

logger = logging.getLogger(__name__)


# The driver shown for an assignment. A free-text name typed during plan
# creation wins over the linked drivers row — the dispatcher was recording a
# stand-in for that day. Aliased to ``driver_name`` (not the raw column name)
# so it does not collide with the ``va.*`` these queries also select.
DRIVER_NAME_SQL = "COALESCE(NULLIF(va.driver_name_override, ''), d.name) AS driver_name"


# ---- Drivers ----

def list_drivers(db_path: str):
    with DatabaseManager(db_path).connect() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM drivers ORDER BY name")
        result = [dict(r) for r in c.fetchall()]
        seen = set(r["name"] for r in result if r.get("name"))
        c.execute("SELECT DISTINCT current_driver FROM vehicles WHERE current_driver IS NOT NULL AND current_driver != ''")
        for row in c.fetchall():
            name = row["current_driver"].strip()
            if name and name not in seen:
                result.append({"id": None, "name": name, "phone": "", "license_number": ""})
                seen.add(name)
        return result


def create_driver(db_path: str, name: str, phone: str = "", license_number: str = ""):
    with DatabaseManager(db_path).connect() as conn:
        c = conn.cursor()
        c.execute("INSERT INTO drivers (name, phone, license_number) VALUES (?, ?, ?)",
                  (name, phone, license_number))
        return c.lastrowid


# ---- Delivery Plans ----

def list_plans(db_path: str, status: Optional[str] = None):
    with DatabaseManager(db_path).connect() as conn:
        c = conn.cursor()
        if status:
            c.execute("SELECT * FROM delivery_plans WHERE status = ? ORDER BY plan_date DESC, created_at DESC", (status,))
        else:
            c.execute("SELECT * FROM delivery_plans ORDER BY plan_date DESC, created_at DESC")
        return [dict(r) for r in c.fetchall()]


def get_plan(db_path: str, plan_id: int):
    with DatabaseManager(db_path).connect() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM delivery_plans WHERE id = ?", (plan_id,))
        row = c.fetchone()
        if not row:
            return None
        plan = dict(row)

        c.execute(f"""
            SELECT va.*, v.plate_number, {DRIVER_NAME_SQL}
            FROM vehicle_assignments va
            LEFT JOIN vehicles v ON v.id = va.vehicle_id
            LEFT JOIN drivers d ON d.id = va.driver_id
            WHERE va.plan_id = ?
            ORDER BY va.sequence
        """, (plan_id,))
        assignments = [dict(r) for r in c.fetchall()]

        for assignment in assignments:
            c.execute("""
                SELECT s.*, e.id as execution_id, e.execution_sequence, e.status as execution_status,
                       e.skip_reason, e.cancel_reason, e.actual_arrival_at, e.actual_departure_at, e.completed_at
                FROM delivery_plan_stops s
                LEFT JOIN stop_executions e ON e.stop_id = s.id
                WHERE s.vehicle_assignment_id = ?
                ORDER BY COALESCE(e.execution_sequence, s.planned_sequence)
            """, (assignment["id"],))
            assignment["stops"] = [dict(r) for r in c.fetchall()]

        plan["assignments"] = assignments
        return plan


def plans_for_date(db_path: str, plan_date: str):
    """Plans on one date, each with a count of stops that have left 'planned'.

    ``active_executions`` is what makes a re-import destructive: deleting a
    plan cascades to its stops and their ``stop_executions``, so any stop a
    driver has already arrived at, completed, skipped or cancelled would lose
    that record. The Google Sheet importer refuses to replace a plan with a
    non-zero count unless the caller explicitly overrides.
    """
    with DatabaseManager(db_path).connect() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT p.id, p.plan_name, p.plan_date, p.status, p.imported_at,
                   (SELECT COUNT(*)
                      FROM stop_executions e
                      JOIN delivery_plan_stops s ON s.id = e.stop_id
                      JOIN vehicle_assignments va ON va.id = s.vehicle_assignment_id
                     WHERE va.plan_id = p.id
                       AND e.status != 'planned') AS active_executions
            FROM delivery_plans p
            WHERE p.plan_date = ?
            ORDER BY p.created_at
        """, (plan_date,))
        return [dict(r) for r in c.fetchall()]


def create_plan(db_path: str, plan_name: str, plan_date: str, description: str = "", created_by: str = ""):
    with DatabaseManager(db_path).connect() as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO delivery_plans (plan_name, plan_date, description, status, created_by) VALUES (?, ?, ?, 'draft', ?)",
            (plan_name, plan_date, description, created_by)
        )
        return c.lastrowid


def update_plan(db_path: str, plan_id: int, **kwargs):
    allowed = {"plan_name", "plan_date", "description", "status", "created_by"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False
    updates["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [plan_id]
    with DatabaseManager(db_path).connect() as conn:
        c = conn.cursor()
        c.execute(f"UPDATE delivery_plans SET {set_clause} WHERE id = ?", vals)
        return c.rowcount > 0


def delete_plan(db_path: str, plan_id: int):
    with DatabaseManager(db_path).connect() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM delivery_plans WHERE id = ?", (plan_id,))
        return c.rowcount > 0


def delete_plans(db_path: str, plan_ids: list[int]):
    with DatabaseManager(db_path).connect() as conn:
        c = conn.cursor()
        placeholders = ",".join("?" * len(plan_ids))
        c.execute(f"DELETE FROM delivery_plans WHERE id IN ({placeholders})", plan_ids)
        return c.rowcount > 0


def clear_plans(db_path: str):
    with DatabaseManager(db_path).connect() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM delivery_plans")
        return True


# ---- Vehicle Assignments ----

def list_assignments(db_path: str, plan_id: Optional[int] = None):
    with DatabaseManager(db_path).connect() as conn:
        c = conn.cursor()
        if plan_id:
            c.execute(f"""
                SELECT va.*, v.plate_number, {DRIVER_NAME_SQL}
                FROM vehicle_assignments va
                LEFT JOIN vehicles v ON v.id = va.vehicle_id
                LEFT JOIN drivers d ON d.id = va.driver_id
                WHERE va.plan_id = ?
                ORDER BY va.sequence
            """, (plan_id,))
        else:
            c.execute(f"""
                SELECT va.*, v.plate_number, {DRIVER_NAME_SQL}
                FROM vehicle_assignments va
                LEFT JOIN vehicles v ON v.id = va.vehicle_id
                LEFT JOIN drivers d ON d.id = va.driver_id
                ORDER BY va.plan_id, va.sequence
            """)
        return [dict(r) for r in c.fetchall()]


def get_assignment(db_path: str, assignment_id: int):
    with DatabaseManager(db_path).connect() as conn:
        c = conn.cursor()
        c.execute(f"""
            SELECT va.*, v.plate_number, v.vehicle_type, {DRIVER_NAME_SQL},
                   v.gross_weight_kg, v.overall_height_mm, v.overall_width_mm,
                   v.overall_length_mm, v.axle_load_kg
            FROM vehicle_assignments va
            LEFT JOIN vehicles v ON v.id = va.vehicle_id
            LEFT JOIN drivers d ON d.id = va.driver_id
            WHERE va.id = ?
        """, (assignment_id,))
        row = c.fetchone()
        if not row:
            return None
        return dict(row)


def create_assignment(db_path: str, plan_id: int, vehicle_id: int,
                      driver_id: Optional[int] = None, sequence: int = 0, notes: str = "",
                      driver_name: Optional[str] = None):
    with DatabaseManager(db_path).connect() as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO vehicle_assignments (plan_id, vehicle_id, driver_id, driver_name_override, sequence, notes)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (plan_id, vehicle_id, driver_id, (driver_name or "").strip(), sequence, notes)
        )
        return c.lastrowid


def update_assignment(db_path: str, assignment_id: int, **kwargs):
    if "driver_name" in kwargs:
        kwargs["driver_name_override"] = (kwargs.pop("driver_name") or "").strip()
    allowed = {"vehicle_id", "driver_id", "driver_name_override", "sequence", "notes"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False
    vals = list(updates.values()) + [assignment_id]
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    with DatabaseManager(db_path).connect() as conn:
        c = conn.cursor()
        c.execute(f"UPDATE vehicle_assignments SET {set_clause} WHERE id = ?", vals)
        return c.rowcount > 0


def delete_assignment(db_path: str, assignment_id: int):
    with DatabaseManager(db_path).connect() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM vehicle_assignments WHERE id = ?", (assignment_id,))
        return c.rowcount > 0


# ---- Delivery Plan Stops ----

def list_stops(db_path: str, assignment_id: int):
    with DatabaseManager(db_path).connect() as conn:
        c = conn.cursor()
        # plan_date rides along because correctability is decided per plan-day
        # (execution_service.can_revert), and carrying it here keeps that
        # answer computable from a single row rather than needing a second
        # lookup per request.
        c.execute("""
            SELECT s.*, e.id as execution_id, e.execution_sequence, e.status as execution_status,
                   e.skip_reason, e.cancel_reason, e.actual_arrival_at, e.actual_departure_at, e.completed_at,
                   dp.plan_date
            FROM delivery_plan_stops s
            LEFT JOIN stop_executions e ON e.stop_id = s.id
            LEFT JOIN vehicle_assignments va ON va.id = s.vehicle_assignment_id
            LEFT JOIN delivery_plans dp ON dp.id = va.plan_id
            WHERE s.vehicle_assignment_id = ?
            ORDER BY COALESCE(e.execution_sequence, s.planned_sequence)
        """, (assignment_id,))
        return [dict(r) for r in c.fetchall()]


def get_stop(db_path: str, stop_id: int):
    with DatabaseManager(db_path).connect() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT s.*, e.id as execution_id, e.execution_sequence, e.status as execution_status,
                   e.skip_reason, e.cancel_reason, e.actual_arrival_at, e.actual_departure_at, e.completed_at
            FROM delivery_plan_stops s
            LEFT JOIN stop_executions e ON e.stop_id = s.id
            WHERE s.id = ?
        """, (stop_id,))
        row = c.fetchone()
        if not row:
            return None
        return dict(row)


def create_stop(db_path: str, assignment_id: int, planned_sequence: int,
                station_code: str = "", station_name: str = "", address: str = "",
                lat: Optional[float] = None, lng: Optional[float] = None,
                manager_name: str = "", manager_phone: str = "",
                product_description: str = "", note: str = ""):
    with DatabaseManager(db_path).connect() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO delivery_plan_stops
                (vehicle_assignment_id, planned_sequence, station_code, station_name,
                 address, lat, lng, manager_name, manager_phone, product_description, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (assignment_id, planned_sequence, station_code, station_name,
              address, lat, lng, manager_name, manager_phone, product_description, note))
        stop_id = c.lastrowid

        c.execute("""
            INSERT INTO stop_executions (stop_id, execution_sequence, status)
            VALUES (?, ?, 'planned')
        """, (stop_id, planned_sequence))
        return stop_id


def update_stop(db_path: str, stop_id: int, **kwargs):
    allowed = {"station_code", "station_name", "address", "lat", "lng",
               "manager_name", "manager_phone", "product_description", "note"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False
    vals = list(updates.values()) + [stop_id]
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    with DatabaseManager(db_path).connect() as conn:
        c = conn.cursor()
        c.execute(f"UPDATE delivery_plan_stops SET {set_clause} WHERE id = ?", vals)
        return c.rowcount > 0


def delete_stop(db_path: str, stop_id: int):
    with DatabaseManager(db_path).connect() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM stop_executions WHERE stop_id = ?", (stop_id,))
        c.execute("DELETE FROM delivery_plan_stops WHERE id = ?", (stop_id,))
        return c.rowcount > 0


def bulk_create_stops(db_path: str, assignment_id: int, stops: list[dict]):
    with DatabaseManager(db_path).connect() as conn:
        c = conn.cursor()
        for s in stops:
            c.execute("""
                INSERT INTO delivery_plan_stops
                    (vehicle_assignment_id, planned_sequence, station_code, station_name,
                     address, lat, lng, manager_name, manager_phone, product_description, note)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                assignment_id,
                s.get("planned_sequence", 0),
                s.get("station_code", ""),
                s.get("station_name", ""),
                s.get("address", ""),
                s.get("lat"),
                s.get("lng"),
                s.get("manager_name", ""),
                s.get("manager_phone", ""),
                s.get("product_description", ""),
                s.get("note", ""),
            ))
            stop_id = c.lastrowid
            c.execute("""
                INSERT INTO stop_executions (stop_id, execution_sequence, status)
                VALUES (?, ?, 'planned')
            """, (stop_id, s.get("planned_sequence", 0)))
        return True


# ---- Excel Import Pipeline ----

def parse_excel_rows(file_path: str):
    try:
        import openpyxl
    except ImportError:
        raise RuntimeError("openpyxl is required for Excel import. Install with: pip install openpyxl")

    wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []

    headers = [str(h).strip().lower() if h else "" for h in rows[0]]
    data_rows = rows[1:]

    col_map = {}
    for i, h in enumerate(headers):
        if "xe" in h or "vehicle" in h or "plate" in h or "biển" in h or "bsx" in h:
            col_map["vehicle"] = i
        elif "sequence" in h or "thứ tự" in h or "stt" in h or "order" in h:
            col_map["sequence"] = i
        elif "station_code" in h or "mã trạm" in h or "mã" in h:
            col_map["station_code"] = i
        elif "station" in h or "trạm" in h or "name" in h or "tên" in h:
            col_map["station_name"] = i
        elif "address" in h or "địa chỉ" in h or "dia chi" in h:
            col_map["address"] = i
        elif "lat" in h or "latitude" in h or "vĩ độ" in h:
            col_map["lat"] = i
        elif "lng" in h or "longitude" in h or "kinh độ" in h or "long" in h:
            col_map["lng"] = i
        elif "manager" in h or "quản lý" in h or "ql" in h or "người" in h:
            col_map["manager_name"] = i
        elif "phone" in h or "điện thoại" in h or "sdt" in h or "mobile" in h:
            col_map["manager_phone"] = i
        elif "product" in h or "hàng" in h or "sản phẩm" in h or "sp" in h:
            col_map["product_description"] = i
        elif "note" in h or "ghi chú" in h or "note" in h:
            col_map["note"] = i

    parsed = []
    for row in data_rows:
        if not any(v is not None for v in row):
            continue
        entry = {}
        for key, idx in col_map.items():
            if idx < len(row):
                entry[key] = row[idx]
        parsed.append(entry)
    return parsed


def validate_import_rows(rows: list[dict]) -> list[dict]:
    errors = []
    for i, row in enumerate(rows):
        row_errors = []
        if not row.get("vehicle"):
            row_errors.append(f"Row {i+2}: missing vehicle identifier")
        if not row.get("station_code") and not row.get("station_name"):
            row_errors.append(f"Row {i+2}: missing station code or name")
        lat = row.get("lat")
        lng = row.get("lng")
        if lat is not None:
            try:
                lat = float(lat)
                if not (-90 <= lat <= 90):
                    row_errors.append(f"Row {i+2}: invalid latitude")
            except (TypeError, ValueError):
                row_errors.append(f"Row {i+2}: latitude is not a number")
        if lng is not None:
            try:
                lng = float(lng)
                if not (-180 <= lng <= 180):
                    row_errors.append(f"Row {i+2}: invalid longitude")
            except (TypeError, ValueError):
                row_errors.append(f"Row {i+2}: longitude is not a number")
        errors.append({"row": i + 2, "errors": row_errors})
    return errors


class UnknownVehicles(ValueError):
    """Raised when an import references vehicles that aren't in the fleet.

    Always fatal. An import never creates vehicles — not silently, and not
    behind an opt-in flag. `vehicles` is the master table that fuel, oil, TLP
    and delivery all key off, and letting a spreadsheet add rows to it is how
    this codebase accumulated the duplicates `tests/merge_duplicate_vehicles.py`
    exists to clean up (audit C-05). Adding a truck is a Vehicle Management
    action.

    In practice an unknown plate here almost always means a typo or a new
    truck nobody registered — not a plate format this resolver can't handle,
    since it already matches on the 5-digit serial that identifies a vehicle
    regardless of whether the sheet wrote `50E-18463`, `50E18463` or `18463`.
    """

    def __init__(self, identifiers):
        self.identifiers = list(identifiers)
        listed = ", ".join(repr(i) for i in self.identifiers)
        super().__init__(
            f"These vehicles are not in the fleet: {listed}. "
            "Check for a typo in the plate number, or add the vehicle under "
            "Vehicle Management before importing."
        )


def _group_rows_by_vehicle(rows: list[dict], index) -> list[dict]:
    """Group import rows by the vehicle they resolve to.

    Grouping used to key on the raw spreadsheet string, so a file mixing
    ``50E-18463`` and ``50E18463`` produced *two* assignments for one physical
    truck and split the driver's stops across two dashboard rows (audit L-03).
    Rows now group by resolved vehicle id.

    Unresolved identifiers group by their 5-digit serial, because that is what
    actually distinguishes a vehicle in this fleet — ``51D-77777``,
    ``51D77777`` and a bare ``77777`` are one truck, so they must be reported
    as one problem, not three. Falls back to canonical form (and then the raw
    string) for the pathological case of an identifier containing no digits.
    """
    groups: dict = {}
    for row in rows:
        identifier = str(row.get("vehicle", "") or "").strip()
        ref = index.resolve(identifier)
        if ref:
            key = ("id", ref.id)
        else:
            key = ("raw", normalize_plate(identifier)
                          or canonical_plate(identifier)
                          or identifier)

        group = groups.get(key)
        if group is None:
            group = {"identifier": identifier, "ref": ref, "rows": []}
            groups[key] = group
        group["rows"].append(row)

    for group in groups.values():
        group["rows"].sort(key=lambda s: int(s.get("sequence", 0) or 0))
    return list(groups.values())


def preview_import(rows: list[dict], db_path: Optional[str] = None) -> dict:
    """Dry-run summary shown before the dispatcher commits an import.

    When ``db_path`` is supplied, each assignment additionally reports whether
    its vehicle resolves to a fleet row and how — so unknown plates surface
    here, before the strict check in ``confirm_import`` can surprise anyone.
    """
    errors = validate_import_rows(rows)
    has_errors = any(e["errors"] for e in errors)

    if db_path:
        with DatabaseManager(db_path).connect() as conn:
            groups = _group_rows_by_vehicle(rows, build_index(conn))
    else:
        groups = _group_rows_by_vehicle(rows, _NullIndex())

    assignments_preview = []
    for group in groups:
        ref = group["ref"]
        assignments_preview.append({
            "vehicle_identifier": group["identifier"],
            "resolved": ref is not None,
            "vehicle_id": ref.id if ref else None,
            "resolved_plate": ref.plate_number if ref else None,
            "matched_by": ref.matched_by if ref else None,
            "stop_count": len(group["rows"]),
            "stops": [
                {
                    "sequence": s.get("sequence"),
                    "station_code": str(s.get("station_code", "") or ""),
                    "station_name": str(s.get("station_name", "") or ""),
                    "address": str(s.get("address", "") or ""),
                    "lat": s.get("lat"),
                    "lng": s.get("lng"),
                    "product": str(s.get("product_description", "") or ""),
                }
                for s in group["rows"]
            ]
        })

    unknown = [a["vehicle_identifier"] for a in assignments_preview if not a["resolved"]]

    return {
        "total_rows": len(rows),
        "total_assignments": len(assignments_preview),
        "has_errors": has_errors,
        "errors": errors,
        "assignments": assignments_preview,
        "unknown_vehicles": unknown if db_path else [],
        "vehicles_checked": bool(db_path),
    }


class _NullIndex:
    """Used when preview_import is called without a database — every
    identifier is simply unresolved, preserving the old preview behaviour."""

    def resolve(self, identifier):
        return None


def confirm_import(db_path: str, plan_id: int, import_data: list[dict]) -> dict:
    """Write a parsed import into plans/assignments/stops/executions.

    Vehicle identity goes through ``services.vehicle_identity``. Every plate
    must already resolve to a fleet vehicle — an unrecognised one aborts the
    whole import via ``UnknownVehicles`` and nothing is written. Imports do
    not create vehicles under any circumstance.
    """
    with DatabaseManager(db_path).connect() as conn:
        c = conn.cursor()
        index = build_index(conn)
        groups = _group_rows_by_vehicle(import_data, index)

        unresolved = [g["identifier"] for g in groups if g["ref"] is None]
        if unresolved:
            raise UnknownVehicles(unresolved)

        stops_created = 0
        for seq, group in enumerate(groups, start=1):
            # driver_name_override, not a drivers row. An import never creates
            # master records — the same rule UnknownVehicles enforces for
            # vehicles. The Google Sheet importer supplies this; the Excel
            # importer does not set `driver_name`, so its behaviour is
            # unchanged and the override stays empty, leaving DRIVER_NAME_SQL
            # to fall back to drivers.name exactly as before.
            driver_name = ""
            for row in group["rows"]:
                candidate = str(row.get("driver_name", "") or "").strip()
                if candidate:
                    driver_name = candidate
                    break

            c.execute(
                "INSERT INTO vehicle_assignments "
                "(plan_id, vehicle_id, sequence, driver_name_override) "
                "VALUES (?, ?, ?, ?)",
                (plan_id, group["ref"].id, seq, driver_name)
            )
            assignment_id = c.lastrowid

            for s in group["rows"]:
                planned_seq = int(s.get("sequence", 0) or 0)
                c.execute("""
                    INSERT INTO delivery_plan_stops
                        (vehicle_assignment_id, planned_sequence, station_code, station_name,
                         address, lat, lng, manager_name, manager_phone, product_description, note)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    assignment_id,
                    planned_seq,
                    str(s.get("station_code", "") or ""),
                    str(s.get("station_name", "") or ""),
                    str(s.get("address", "") or ""),
                    s.get("lat"),
                    s.get("lng"),
                    str(s.get("manager_name", "") or ""),
                    str(s.get("manager_phone", "") or ""),
                    str(s.get("product_description", "") or ""),
                    str(s.get("note", "") or ""),
                ))
                stop_id = c.lastrowid
                c.execute("""
                    INSERT INTO stop_executions (stop_id, execution_sequence, status)
                    VALUES (?, ?, 'planned')
                """, (stop_id, planned_seq))
                stops_created += 1

        # Once, after the loop — not once per vehicle. This UPDATE used to sit
        # inside the per-vehicle loop, so it ran N times redundantly and, for
        # an import that produced no groups at all, zero times: the function
        # returned success while the plan stayed 'draft' and never appeared on
        # the dashboard (audit L-06). Scheduled for Phase 3, but restructuring
        # this loop made leaving the bug in place indefensible.
        if groups:
            c.execute(
                "UPDATE delivery_plans SET status = 'confirmed', imported_at = ? WHERE id = ?",
                (datetime.now().isoformat(), plan_id)
            )

        return {
            "ok": True,
            "assignments_created": len(groups),
            "stops_created": stops_created,
            "plan_confirmed": bool(groups),
        }
