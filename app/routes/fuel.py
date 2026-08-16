"""
Fuel efficiency / refuel log CRUD, profiles, CSV export, and Google Sheet sync.

Extracted from app.py (Section 6.4.1, Phase 10).
"""
import sqlite3
from contextlib import contextmanager

from flask import Blueprint, jsonify, render_template, request

from app import config, state
from app.utils.export import csv_response
from services import vehicle_identity

bp = Blueprint("fuel", __name__)


@contextmanager
def _db(conn=None):
    """Yield a connection, opening one only when the caller has none.

    The helpers below are called once per fuel_log row. Each used to open its
    own connection, so `GET /api/fuel-log` over the 323 rows in this fleet's
    database opened on the order of 1,300 of them for a single request —
    which, behind render.yaml's single synchronous Gunicorn worker, blocks
    every other request for the duration (2026-08-06 audit).

    The `conn` parameter is optional so the standalone call sites (the create
    and update handlers, which compute one entry) keep working untouched; only
    the loops pass a connection down.
    """
    if conn is not None:
        yield conn
        return
    own = sqlite3.connect(config.DB_PATH)
    try:
        yield own
    finally:
        own.close()


def _compute_fuel_entry(row: dict, conn=None) -> dict:
    """Add computed fields to a fuel_log row.

    Individual fields (distance_km, liters) always stay as the entry's own values.
    For partial fills (is_full_tank=0): l_per_100km=0 (no efficiency computed).
    For full fills (is_full_tank=1): l_per_100km is computed from accumulated
    distance and liters since the previous full-tank entry.
    """
    entry = dict(row)
    entry["is_full_tank"] = bool(entry.get("is_full_tank", True))
    entry["accumulated"] = False
    entry["accumulated_distance_km"] = entry.get("distance_km", 0)
    entry["accumulated_liters"] = entry.get("liters", 0)
    entry["distance_km"] = max(0, (entry["new_km"] or 0) - (entry["old_km"] or 0))

    raw_liters = entry["liters"] or 0
    entry["total_cost"] = round(raw_liters * (entry.get("unit_price") or 0), 2)
    entry["is_anomaly"] = False

    # Missing KM — cannot compute efficiency
    if not (entry.get("old_km") and entry.get("new_km")):
        entry["l_per_100km"] = 0
        entry["is_anomaly"] = True
        return entry

    if not entry["is_full_tank"]:
        entry["l_per_100km"] = 0
        return entry

    # Full tank – compute accumulated distance & liters since last full tank
    plate = entry["license_plate"]
    entry_id = entry["id"]
    with _db(conn) as db:
        c = db.cursor()
        c.execute(
            "SELECT COALESCE(MAX(id), 0) FROM fuel_log "
            "WHERE license_plate = ? AND is_full_tank = 1 AND id < ?",
            (plate, entry_id)
        )
        prev_full_id = c.fetchone()[0]
        if prev_full_id > 0:
            c.execute(
                "SELECT SUM(new_km - old_km), SUM(liters) FROM fuel_log "
                "WHERE license_plate = ? AND id > ? AND id <= ?",
                (plate, prev_full_id, entry_id)
            )
        else:
            c.execute(
                "SELECT SUM(new_km - old_km), SUM(liters) FROM fuel_log "
                "WHERE license_plate = ? AND id <= ?",
                (plate, entry_id)
            )
        total_km, total_l = c.fetchone()

    total_km = total_km or 0
    total_l = total_l or 0
    entry["accumulated_distance_km"] = total_km
    entry["accumulated_liters"] = total_l
    entry["l_per_100km"] = round((total_l / total_km * 100), 2) if total_km > 0 else 0
    entry["accumulated"] = True
    return entry


def _get_normal_l_per_100km(plate: str, conn=None) -> float:
    """Look up the user-defined normal L/100km for a vehicle."""
    try:
        with _db(conn) as db:
            c = db.cursor()
            c.execute("SELECT normal_l_per_100km FROM fuel_vehicle_profile WHERE license_plate = ?", (plate,))
            row = c.fetchone()
        return float(row[0]) if row else 0
    except Exception:
        return 0


def _compute_baseline(plate: str, exclude_id: int = None, conn=None) -> float:
    """Compute moving average of l_per_100km of last 5 entries for a plate.
    If a manual normal_l_per_100km is set for this vehicle, returns that instead."""
    manual = _get_normal_l_per_100km(plate, conn)
    if manual > 0:
        return manual
    with _db(conn) as db:
        c = db.cursor()
        if exclude_id:
            c.execute(
                "SELECT old_km, new_km, liters FROM fuel_log WHERE license_plate = ? AND id != ? AND is_full_tank = 1 ORDER BY id DESC LIMIT 5",
                (plate, exclude_id)
            )
        else:
            c.execute(
                "SELECT old_km, new_km, liters FROM fuel_log WHERE license_plate = ? AND is_full_tank = 1 ORDER BY id DESC LIMIT 5",
                (plate,)
            )
        rows = c.fetchall()
    ratios = []
    for old_km, new_km, liters in rows:
        d = (new_km or 0) - (old_km or 0)
        if d > 0 and (liters or 0) > 0:
            ratios.append(liters / d * 100)
    # Fallback: if no full-tank entries, include all entries
    if not ratios:
        with _db(conn) as db:
            c = db.cursor()
            if exclude_id:
                c.execute(
                    "SELECT old_km, new_km, liters FROM fuel_log WHERE license_plate = ? AND id != ? ORDER BY id DESC LIMIT 5",
                    (plate, exclude_id)
                )
            else:
                c.execute(
                    "SELECT old_km, new_km, liters FROM fuel_log WHERE license_plate = ? ORDER BY id DESC LIMIT 5",
                    (plate,)
                )
            rows = c.fetchall()
        for old_km, new_km, liters in rows:
            d = (new_km or 0) - (old_km or 0)
            if d > 0 and (liters or 0) > 0:
                ratios.append(liters / d * 100)
    return sum(ratios) / len(ratios) if ratios else 0


def _get_anomaly_multiplier(plate: str, conn=None) -> float:
    """Return the anomaly threshold multiplier for a vehicle.
    Default: 1.50 if vehicle type contains 'Container', else 1.20.
    User can override via fuel_vehicle_profile.anomaly_multiplier."""
    try:
        vtype = ""
        with _db(conn) as db:
            c = db.cursor()
            c.execute("SELECT vehicle_type FROM vehicles WHERE plate_number = ?", (plate,))
            row = c.fetchone()
            if row:
                vtype = row[0] or ""
            c.execute("SELECT anomaly_multiplier FROM fuel_vehicle_profile WHERE license_plate = ?", (plate,))
            row = c.fetchone()
        if row and row[0] is not None:
            return float(row[0])
        return 1.50 if "container" in vtype.lower() else 1.20
    except Exception:
        return 1.20


def _apply_anomaly_flag(entry: dict, baseline: float, conn=None) -> dict:
    """Mark entry as anomaly if l_per_100km is outside expected range.

    Anomalies include:
    * l_per_100km > baseline × anomaly_multiplier (unusually high consumption)
    * l_per_100km > 0 and l_per_100km < 8 (unrealistically low consumption - likely data error)

    Anomalous entries have l_per_100km reset to 0 so they are excluded
    from charts and averages while remaining visible in the table as flagged.
    """
    entry["baseline"] = round(baseline, 2)
    entry["normal_l_per_100km"] = round(_get_normal_l_per_100km(entry["license_plate"], conn), 2)
    entry["anomaly_multiplier"] = _get_anomaly_multiplier(entry["license_plate"], conn)

    # Unrealistically low consumption (< 8 L/100km) — data error
    if 0 < entry["l_per_100km"] < 8:
        entry["is_anomaly"] = True
        entry["l_per_100km"] = 0
        return entry

    # Unusually high consumption (> baseline × multiplier)
    if baseline > 0 and entry["l_per_100km"] > baseline * entry["anomaly_multiplier"]:
        entry["is_anomaly"] = True
        return entry

    return entry


@bp.route("/fuel-efficiency")
def fuel_efficiency_page():
    return render_template("fuel-efficiency.html", mode="regular")


@bp.route("/fuel-container")
def fuel_container_page():
    return render_template("fuel-efficiency.html", mode="container")


def _enrich_fuel_entry(entry: dict, conn=None) -> dict:
    """Add vehicle_type from vehicles table to a fuel entry."""
    if entry.get("vehicle_id"):
        try:
            with _db(conn) as db:
                c = db.cursor()
                c.execute("SELECT vehicle_type, current_driver FROM vehicles WHERE id = ?", (entry["vehicle_id"],))
                row = c.fetchone()
            if row:
                entry["vehicle_type"] = row[0] or ""
                if not entry.get("driver_name"):
                    entry["driver_name"] = row[1] or ""
        except Exception:
            pass
    return entry


@bp.route("/api/fuel-log", methods=["GET"])
def api_fuel_log_list():
    conn = None
    try:
        conn = sqlite3.connect(config.DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        plate = request.args.get("license_plate", "").strip().upper()
        month = request.args.get("month", "").strip()
        mode = request.args.get("mode", "").strip()
        vehicle_ids = request.args.get("vehicle_ids", "").strip()

        conditions = []
        params = []
        if plate:
            conditions.append("license_plate = ?")
            params.append(plate)
        if month:
            conditions.append("log_date LIKE ?")
            params.append(f"{month}%")
        if vehicle_ids:
            ids = [x.strip() for x in vehicle_ids.split(",") if x.strip().isdigit()]
            if ids:
                conditions.append(f"vehicle_id IN ({','.join('?' * len(ids))})")
                params.extend(ids)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        c.execute(f"SELECT * FROM fuel_log {where} ORDER BY log_date DESC, log_time DESC", params)
        rows = [dict(r) for r in c.fetchall()]

        # The connection stays open for the loop and is handed to each helper.
        # Previously each of the four opened its own per row, so this endpoint
        # opened ~6 connections × N rows — over 1,300 for the 323 rows in this
        # fleet's database, all of them serialised behind the single Gunicorn
        # worker (2026-08-06 audit).
        results = []
        for r in rows:
            entry = _compute_fuel_entry(r, conn)
            entry = _enrich_fuel_entry(entry, conn)
            baseline = _compute_baseline(entry["license_plate"], entry["id"], conn)
            entry = _apply_anomaly_flag(entry, baseline, conn)
            if mode:
                is_container = (entry.get("vehicle_type") or "").lower().find("container") >= 0
                if (mode == "container" and not is_container) or (mode == "regular" and is_container):
                    continue
            results.append(entry)

        return jsonify({"success": True, "data": results})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn is not None:
            conn.close()


@bp.route("/api/fuel-log/months", methods=["GET"])
def api_fuel_log_months():
    """Return all distinct months (YYYY-MM) that have fuel_log entries."""
    try:
        mode = request.args.get("mode", "").strip()
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        if mode == "container":
            c.execute("SELECT DISTINCT substr(f.log_date,1,7) AS ym FROM fuel_log f LEFT JOIN vehicles v ON f.vehicle_id = v.id WHERE v.vehicle_type LIKE '%Container%' ORDER BY ym DESC")
        elif mode == "regular":
            c.execute("SELECT DISTINCT substr(f.log_date,1,7) AS ym FROM fuel_log f LEFT JOIN vehicles v ON f.vehicle_id = v.id WHERE (v.vehicle_type NOT LIKE '%Container%' OR v.vehicle_type IS NULL OR v.vehicle_type = '') ORDER BY ym DESC")
        else:
            c.execute("SELECT DISTINCT substr(log_date,1,7) AS ym FROM fuel_log ORDER BY ym DESC")
        months = [r[0] for r in c.fetchall()]
        conn.close()
        return jsonify({"success": True, "data": months})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route("/api/fuel-log/days", methods=["GET"])
def api_fuel_log_days():
    """Return all distinct days in a given month (YYYY-MM-DD) that have entries."""
    try:
        month = request.args.get("month", "").strip()
        mode = request.args.get("mode", "").strip()
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        conditions = ["f.log_date LIKE ?"]
        params = [f"{month}%"]
        if mode == "container":
            conditions.append("v.vehicle_type LIKE '%Container%'")
        elif mode == "regular":
            conditions.append("(v.vehicle_type NOT LIKE '%Container%' OR v.vehicle_type IS NULL OR v.vehicle_type = '')")
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        c.execute(f"SELECT DISTINCT f.log_date FROM fuel_log f LEFT JOIN vehicles v ON f.vehicle_id = v.id {where} ORDER BY f.log_date", params)
        days = [r[0] for r in c.fetchall()]
        conn.close()
        return jsonify({"success": True, "data": days})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route("/api/fuel-log/stats", methods=["GET"])
def api_fuel_log_stats():
    """Monthly stats: total distance, total fuel, avg L/100km, anomaly count."""
    try:
        month = request.args.get("month", "").strip()
        conn = sqlite3.connect(config.DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        if month:
            c.execute("SELECT * FROM fuel_log WHERE log_date LIKE ?", (f"{month}%",))
        else:
            c.execute("SELECT * FROM fuel_log")
        rows = [dict(r) for r in c.fetchall()]
        conn.close()

        total_distance = 0
        total_fuel = 0.0
        valid_entries = 0
        total_anomalies = 0
        sum_l100 = 0.0

        for r in rows:
            entry = _compute_fuel_entry(r)
            entry = _enrich_fuel_entry(entry)
            baseline = _compute_baseline(entry["license_plate"], entry["id"])
            entry = _apply_anomaly_flag(entry, baseline)
            dist = entry.get("distance_km", 0)
            liters = entry.get("liters", 0)
            if dist > 0 and liters > 0:
                total_distance += dist
                total_fuel += liters
                sum_l100 += entry["l_per_100km"]
                valid_entries += 1
            if entry.get("is_anomaly"):
                total_anomalies += 1

        avg_l_per_100km = round(sum_l100 / valid_entries, 2) if valid_entries > 0 else 0
        return jsonify({
            "success": True,
            "total_distance": total_distance,
            "total_fuel": round(total_fuel, 2),
            "avg_l_per_100km": avg_l_per_100km,
            "entry_count": len(rows),
            "anomaly_count": total_anomalies
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route("/api/fuel-log", methods=["POST"])
def api_fuel_log_create():
    conn = None
    try:
        data = request.json or {}
        vehicle_id = data.get("vehicle_id")
        plate = (data.get("license_plate") or "").strip().upper()
        log_date = (data.get("log_date") or "").strip()
        log_time = (data.get("log_time") or "").strip()
        gas_store = (data.get("gas_store") or "").strip()
        old_km = int(data.get("old_km") or 0)
        new_km = int(data.get("new_km") or 0)
        liters = float(data.get("liters") or 0)
        driver_name = (data.get("driver_name") or "").strip()
        unit_price = data.get("unit_price")
        if unit_price is not None:
            unit_price = float(unit_price)
        notes = (data.get("notes") or "").strip()
        is_full_tank = data.get("is_full_tank", True)
        if isinstance(is_full_tank, str):
            is_full_tank = is_full_tank.lower() in ("1", "true", "yes")
        is_full_tank = 1 if is_full_tank else 0

        # If vehicle_id is provided, look up plate and driver from vehicles table
        if vehicle_id:
            conn = sqlite3.connect(config.DB_PATH)
            try:
                c = conn.cursor()
                c.execute("SELECT plate_number, current_driver FROM vehicles WHERE id = ?", (vehicle_id,))
                row = c.fetchone()
            finally:
                conn.close()
                conn = None
            if row:
                if not plate:
                    plate = row[0]
                if not driver_name:
                    driver_name = row[1] or ""

        if not plate:
            return jsonify({"success": False, "message": "License plate is required"}), 400
        if not log_date:
            return jsonify({"success": False, "message": "Date is required"}), 400
        if not log_time:
            return jsonify({"success": False, "message": "Time is required"}), 400
        if new_km < old_km:
            return jsonify({"success": False, "message": "New KM must be >= Old KM"}), 400
        if liters <= 0:
            return jsonify({"success": False, "message": "Liters must be > 0"}), 400

        distance_km = new_km - old_km
        warnings = []
        if distance_km > 2000:
            warnings.append("Distance exceeds 2000 km — please verify.")
        if distance_km < 1:
            warnings.append("Distance is less than 1 km — please verify.")

        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()

        # The `vehicles` table is the source of truth. This endpoint used to
        # upsert into it — creating a vehicle for any unrecognised plate and
        # overwriting `current_driver` from whatever name was typed on the
        # fuel form. Both were silent background edits to core fleet data, and
        # because the ON CONFLICT matched on the exact plate string, logging
        # fuel for "50E18463" against a stored "50E-18463" created a duplicate
        # row (same root cause as audit C-05).
        #
        # Resolution is loose (exact → canonical → 5-digit serial), so the
        # unknown-vehicle path only triggers for a plate that genuinely isn't
        # in the fleet, not for a formatting difference.
        vehicle_ref = vehicle_identity.resolve(conn, plate)
        if vehicle_ref is None:
            return jsonify(
                vehicle_identity.unknown_vehicle_response(plate, driver_name)
            ), 409

        # Store the fleet's canonical plate rather than whatever was typed, so
        # fuel history stays joinable. This normalizes the *new* record only —
        # it never rewrites the vehicle.
        plate = vehicle_ref.plate_number
        vehicle_id = vehicle_ref.id

        c.execute(
            "INSERT INTO fuel_log (license_plate, log_date, log_time, gas_store, old_km, new_km, liters, driver_name, unit_price, notes, vehicle_id, is_full_tank) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (plate, log_date, log_time, gas_store, old_km, new_km, liters, driver_name, unit_price, notes, vehicle_id, is_full_tank)
        )
        conn.commit()
        new_id = c.lastrowid
        # Closed here rather than left to the finally: the helpers below open
        # their own connections, and holding this one across them serves no
        # purpose. The finally is the guarantee, not the mechanism.
        conn.close()
        conn = None

        entry = _compute_fuel_entry({
            "id": new_id, "license_plate": plate, "log_date": log_date, "log_time": log_time,
            "gas_store": gas_store, "old_km": old_km, "new_km": new_km, "liters": liters,
            "driver_name": driver_name, "unit_price": unit_price, "notes": notes, "created_at": "",
            "vehicle_id": vehicle_id, "is_full_tank": is_full_tank
        })
        entry = _enrich_fuel_entry(entry)
        baseline = _compute_baseline(plate, new_id)
        entry = _apply_anomaly_flag(entry, baseline)

        resp = {"success": True, "message": "Fuel log entry created", "entry": entry}
        if warnings:
            resp["warnings"] = warnings
        return jsonify(resp)
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn is not None:
            conn.close()


@bp.route("/api/fuel-log/<int:entry_id>", methods=["PUT"])
def api_fuel_log_update(entry_id):
    conn = None
    try:
        data = request.json or {}
        conn = sqlite3.connect(config.DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        c.execute("SELECT * FROM fuel_log WHERE id = ?", (entry_id,))
        existing = c.fetchone()
        if not existing:
            return jsonify({"success": False, "message": "Entry not found"}), 404

        vehicle_id = data.get("vehicle_id", existing["vehicle_id"])
        plate = (data.get("license_plate") or existing["license_plate"]).strip().upper()

        # Same rule as the create path: an edit may not introduce a plate that
        # isn't a real vehicle, and may not create one to make itself valid.
        vehicle_ref = vehicle_identity.resolve(conn, plate)
        if vehicle_ref is None:
            return jsonify(
                vehicle_identity.unknown_vehicle_response(
                    plate, (data.get("driver_name") or existing["driver_name"] or "").strip()
                )
            ), 409
        plate = vehicle_ref.plate_number
        vehicle_id = vehicle_ref.id

        log_date = (data.get("log_date") or existing["log_date"]).strip()
        log_time = (data.get("log_time") or existing["log_time"]).strip()
        gas_store = (data.get("gas_store") if "gas_store" in data else existing["gas_store"]).strip()
        old_km = int(data.get("old_km", existing["old_km"]))
        new_km = int(data.get("new_km", existing["new_km"]))
        liters = float(data.get("liters", existing["liters"]))
        driver_name = (data.get("driver_name") if "driver_name" in data else existing["driver_name"]).strip()
        unit_price = data.get("unit_price", existing["unit_price"])
        if unit_price is not None:
            unit_price = float(unit_price)
        notes = (data.get("notes") if "notes" in data else existing["notes"]).strip()
        is_full_tank = data.get("is_full_tank", existing["is_full_tank"])
        if isinstance(is_full_tank, str):
            is_full_tank = is_full_tank.lower() in ("1", "true", "yes")
        is_full_tank = 1 if is_full_tank else 0

        if new_km < old_km:
            return jsonify({"success": False, "message": "New KM must be >= Old KM"}), 400
        if liters <= 0:
            return jsonify({"success": False, "message": "Liters must be > 0"}), 400

        distance_km = new_km - old_km
        warnings = []
        if distance_km > 2000:
            warnings.append("Distance exceeds 2000 km — please verify.")
        if distance_km < 1:
            warnings.append("Distance is less than 1 km — please verify.")

        c.execute(
            "UPDATE fuel_log SET license_plate=?, log_date=?, log_time=?, gas_store=?, old_km=?, new_km=?, liters=?, driver_name=?, unit_price=?, notes=?, vehicle_id=?, is_full_tank=? WHERE id=?",
            (plate, log_date, log_time, gas_store, old_km, new_km, liters, driver_name, unit_price, notes, vehicle_id, is_full_tank, entry_id)
        )
        conn.commit()

        c.execute("SELECT * FROM fuel_log WHERE id = ?", (entry_id,))
        updated = dict(c.fetchone())
        conn.close()
        conn = None

        entry = _compute_fuel_entry(updated)
        entry = _enrich_fuel_entry(entry)
        baseline = _compute_baseline(plate, entry_id)
        entry = _apply_anomaly_flag(entry, baseline)

        resp = {"success": True, "message": "Fuel log entry updated", "entry": entry}
        if warnings:
            resp["warnings"] = warnings
        return jsonify(resp)
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn is not None:
            conn.close()


@bp.route("/api/fuel-log/<int:entry_id>", methods=["DELETE"])
def api_fuel_log_delete(entry_id):
    conn = None
    try:
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM fuel_log WHERE id = ?", (entry_id,))
        if c.rowcount == 0:
            return jsonify({"success": False, "message": "Entry not found"}), 404
        conn.commit()
        return jsonify({"success": True, "message": "Entry deleted"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn is not None:
            conn.close()


@bp.route("/api/fuel-log/last-km")
def api_fuel_log_last_km():
    """Return the latest new_km for a given license plate."""
    try:
        plate = request.args.get("plate", "").strip().upper()
        if not plate:
            return jsonify({"success": False, "message": "plate required"}), 400
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        c.execute("SELECT new_km FROM fuel_log WHERE license_plate = ? ORDER BY id DESC LIMIT 1", (plate,))
        row = c.fetchone()
        conn.close()
        return jsonify({"success": True, "new_km": row[0] if row else 0})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route("/api/fuel-log/summary")
def api_fuel_log_summary():
    try:
        month = request.args.get("month", "").strip()
        conn = sqlite3.connect(config.DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        if month:
            c.execute("SELECT DISTINCT license_plate FROM fuel_log WHERE log_date LIKE ? ORDER BY license_plate", (f"{month}%",))
        else:
            c.execute("SELECT DISTINCT license_plate FROM fuel_log ORDER BY license_plate")
        plates = [r["license_plate"] for r in c.fetchall()]

        summaries = []
        total_anomalies = 0
        fleet_sum_l100 = fleet_cnt = 0
        for plate in plates:
            if month:
                c.execute(
                    "SELECT * FROM fuel_log WHERE license_plate = ? AND log_date LIKE ? ORDER BY log_date DESC, log_time DESC",
                    (plate, f"{month}%")
                )
            else:
                c.execute(
                    "SELECT * FROM fuel_log WHERE license_plate = ? ORDER BY log_date DESC, log_time DESC",
                    (plate,)
                )
            rows = [dict(r) for r in c.fetchall()]
            entries = [_compute_fuel_entry(r) for r in rows]
            baseline = _compute_baseline(plate)
            entries = [_apply_anomaly_flag(e, baseline) for e in entries]
            anomalies = [e for e in entries if e["is_anomaly"]]
            total_anomalies += len(anomalies)
            valid = [e for e in entries if e["l_per_100km"] > 0]
            sum_l100 = sum(e["l_per_100km"] for e in valid)
            cnt = len(valid)
            fleet_sum_l100 += sum_l100
            fleet_cnt += cnt
            summaries.append({
                "license_plate": plate,
                "total_entries": len(entries),
                "avg_l_per_100km": round(sum_l100 / cnt, 2) if cnt > 0 else 0,
                "baseline": round(baseline, 2),
                "active_anomalies": len(anomalies),
                "total_liters": round(sum(e["liters"] for e in entries), 2),
                "total_cost": round(sum(e["total_cost"] for e in entries), 2)
            })

        conn.close()
        return jsonify({
            "success": True,
            "data": summaries,
            "total_anomalies": total_anomalies,
            "total_entries": sum(s["total_entries"] for s in summaries),
            "fleet_avg_l_per_100km": round(fleet_sum_l100 / fleet_cnt, 2) if fleet_cnt > 0 else 0
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route("/api/fuel-log/export")
def api_fuel_log_export():
    conn = None
    try:
        conn = sqlite3.connect(config.DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        plate = request.args.get("license_plate", "").strip().upper()
        month = request.args.get("month", "").strip()
        mode = request.args.get("mode", "").strip()
        conditions = []
        params = []
        if plate:
            conditions.append("f.license_plate = ?")
            params.append(plate)
        if month:
            conditions.append("f.log_date LIKE ?")
            params.append(f"{month}%")
        if mode == "container":
            conditions.append("v.vehicle_type LIKE '%Container%'")
        elif mode == "regular":
            conditions.append("(v.vehicle_type NOT LIKE '%Container%' OR v.vehicle_type IS NULL OR v.vehicle_type = '')")
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        c.execute(f"SELECT f.* FROM fuel_log f LEFT JOIN vehicles v ON f.vehicle_id = v.id {where} ORDER BY f.log_date DESC, f.log_time DESC", params)
        rows = [dict(r) for r in c.fetchall()]

        headers = [
            "ID", "License Plate", "Date", "Time", "Gas Store",
            "Old KM", "New KM", "Distance KM", "Liters",
            "L/100km", "Unit Price", "Total Cost",
            "Driver Name", "Notes", "Anomaly",
            "Full Tank", "Accum Distance KM", "Accum Liters"
        ]
        # Same connection reuse as api_fuel_log_list — this loop runs over the
        # whole unfiltered table when no month is selected.
        csv_rows = []
        for r in rows:
            entry = _compute_fuel_entry(r, conn)
            baseline = _compute_baseline(entry["license_plate"], entry["id"], conn)
            entry = _apply_anomaly_flag(entry, baseline, conn)
            csv_rows.append([
                entry["id"], "\t" + entry["license_plate"], entry["log_date"], entry["log_time"],
                entry["gas_store"], entry["old_km"], entry["new_km"],
                entry["distance_km"], entry["liters"], entry["l_per_100km"],
                entry.get("unit_price") or "",
                entry["total_cost"], entry["driver_name"], entry["notes"],
                "Yes" if entry["is_anomaly"] else "No",
                "Yes" if entry["is_full_tank"] else "No",
                entry.get("accumulated_distance_km", ""),
                entry.get("accumulated_liters", "")
            ])

        return csv_response(headers, csv_rows, "fuel_efficiency_report.csv")
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn is not None:
            conn.close()


@bp.route("/api/fuel-log/profiles", methods=["GET"])
def api_fuel_log_profiles_list():
    """Return all vehicle fuel profiles with their normal L/100km."""
    try:
        conn = sqlite3.connect(config.DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM fuel_vehicle_profile ORDER BY license_plate")
        profiles = [dict(r) for r in c.fetchall()]
        conn.close()

        # Also include vehicles that have fuel_log entries but no profile yet
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        c.execute("SELECT DISTINCT license_plate FROM fuel_log ORDER BY license_plate")
        all_plates = [r[0] for r in c.fetchall()]
        conn.close()

        known = {p["license_plate"] for p in profiles}
        for plate in all_plates:
            if plate not in known:
                profiles.append({
                    "license_plate": plate,
                    "normal_l_per_100km": _get_normal_l_per_100km(plate),
                    "anomaly_multiplier": _get_anomaly_multiplier(plate),
                    "updated_at": None
                })

        return jsonify({"success": True, "data": profiles})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route("/api/fuel-log/profiles/<path:plate>", methods=["PUT"])
def api_fuel_log_profile_update(plate):
    """Create or update a vehicle's normal L/100km and/or anomaly multiplier."""
    conn = None
    try:
        plate = plate.strip().upper()
        data = request.json or {}
        normal = data.get("normal_l_per_100km")
        anomaly_mult = data.get("anomaly_multiplier")

        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()

        # Check if profile exists
        c.execute("SELECT * FROM fuel_vehicle_profile WHERE license_plate = ?", (plate,))
        exists = c.fetchone()

        if normal is not None:
            normal = float(normal)
            if normal <= 0:
                return jsonify({"success": False, "message": "normal_l_per_100km must be > 0"}), 400
        if anomaly_mult is not None:
            anomaly_mult = float(anomaly_mult)
            if anomaly_mult < 1.0:
                return jsonify({"success": False, "message": "anomaly_multiplier must be >= 1.0"}), 400

        if exists:
            updates = ["updated_at = CURRENT_TIMESTAMP"]
            params = []
            if normal is not None:
                updates.append("normal_l_per_100km = ?")
                params.append(normal)
            if anomaly_mult is not None:
                updates.append("anomaly_multiplier = ?")
                params.append(anomaly_mult)
            params.append(plate)
            c.execute(f"UPDATE fuel_vehicle_profile SET {', '.join(updates)} WHERE license_plate = ?", params)
        else:
            c.execute(
                "INSERT INTO fuel_vehicle_profile (license_plate, normal_l_per_100km, anomaly_multiplier, updated_at) "
                "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                (plate, normal or 10.0, anomaly_mult)
            )

        conn.commit()
        parts = []
        if normal is not None:
            parts.append(f"Normal L/100km = {normal}")
        if anomaly_mult is not None:
            parts.append(f"Multiplier = {anomaly_mult}")
        return jsonify({"success": True, "message": f"Profile for {plate}: {', '.join(parts)}"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn is not None:
            conn.close()


@bp.route("/api/fuel-log/profiles/<path:plate>", methods=["DELETE"])
def api_fuel_log_profile_delete(plate):
    """Remove a vehicle's manual normal L/100km (revert to computed baseline)."""
    conn = None
    try:
        plate = plate.strip().upper()
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM fuel_vehicle_profile WHERE license_plate = ?", (plate,))
        conn.commit()
        return jsonify({"success": True, "message": f"Normal L/100km for {plate} cleared"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn is not None:
            conn.close()


# ---------------------------------------------------------------------------
# Google Sheet Sync Endpoints
# ---------------------------------------------------------------------------
@bp.route("/api/fuel/sync", methods=["POST"])
def api_fuel_sync():
    """Trigger a Google Sheet synchronisation and store the result."""
    if not state.sync_lock.acquire(blocking=False):
        return jsonify({"success": False, "message": "Sync already in progress"}), 429
    try:
        from services.google_sheet_service import GoogleSheetService

        svc = GoogleSheetService(db_path=config.DB_PATH)
        result = svc.sync_to_database()

        conn = sqlite3.connect(config.DB_PATH)
        try:
            c = conn.cursor()
            c.execute(
                """INSERT INTO sync_history
                   (fetched_rows, inserted_rows, duplicate_rows, failed_rows, duration_sec, status)
                   VALUES (?, ?, ?, ?, ?, 'success')""",
                (result["fetched"], result["inserted"],
                 result["duplicate"], result["failed"],
                 result.get("duration_sec", 0)),
            )
            conn.commit()
            history_id = c.lastrowid
        finally:
            conn.close()

        return jsonify({"success": True, "data": {**result, "history_id": history_id}})
    except Exception as e:
        import traceback
        traceback.print_exc()

        conn = sqlite3.connect(config.DB_PATH)
        try:
            c = conn.cursor()
            c.execute(
                """INSERT INTO sync_history
                   (fetched_rows, inserted_rows, duplicate_rows, failed_rows, duration_sec, status, error_message)
                   VALUES (0, 0, 0, 0, 0, 'error', ?)""",
                (str(e),),
            )
            conn.commit()
        finally:
            conn.close()

        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        state.sync_lock.release()


@bp.route("/api/fuel/sync/history")
def api_fuel_sync_history():
    """Return recent sync history entries."""
    limit = request.args.get("limit", 20)
    try:
        limit = int(limit)
    except (ValueError, TypeError):
        limit = 20
    try:
        conn = sqlite3.connect(config.DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute(
            "SELECT * FROM sync_history ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return jsonify({"success": True, "data": rows})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route("/api/fuel/sync/last")
def api_fuel_sync_last():
    """Return the most recent sync result."""
    try:
        conn = sqlite3.connect(config.DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM sync_history ORDER BY created_at DESC LIMIT 1")
        row = c.fetchone()
        conn.close()
        return jsonify({"success": True, "data": dict(row) if row else None})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
