"""
Vehicle management: master vehicle CRUD + vehicle types.

Extracted from app.py (Section 6.4.1, Phase 9).
"""
import json
import sqlite3

from flask import Blueprint, jsonify, render_template, request

from app import config
from app.services.vehicle_specs import (
    ENVELOPE_FIELDS,
    coerce_envelope_value,
    resolve_envelope,
    validate_envelope,
)

bp = Blueprint("fleet", __name__)


def _envelope_from_request(data):
    """Envelope values off the request body, blanks preserved as None."""
    return {field: coerce_envelope_value(data.get(field)) for field in ENVELOPE_FIELDS}


def _cargo_from_request(data):
    """Cargo figures from the same payload, for the consistency checks.

    Only what the request itself carries — the form posts the cargo group and
    the envelope group together, so a mismatch is caught at the moment it is
    introduced rather than on some later read.
    """
    return {
        "cargo_length_mm": coerce_envelope_value(data.get("cargo_length_mm")),
        "cargo_width_mm": coerce_envelope_value(data.get("cargo_width_mm")),
        "cargo_height_mm": coerce_envelope_value(data.get("cargo_height_mm")),
        "payload_kg": coerce_envelope_value(data.get("payload_kg")),
    }


def _envelope_assignments(envelope):
    """(sql_fragment, params) for the envelope columns of an UPDATE/INSERT."""
    columns = list(ENVELOPE_FIELDS)
    fragment = ", ".join(f"{col}=?" for col in columns)
    return fragment, [envelope[col] for col in columns]


@bp.route("/vehicle-management")
def vehicle_management_page():
    return render_template("vehicle-management.html")


@bp.route("/truck-load-planner")
def truck_load_planner():
    return render_template("truck-load-planner.html")


@bp.route("/api/fleet/vehicles", methods=["GET"])
def api_vehicles_list():
    try:
        conn = sqlite3.connect(config.DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        q = request.args.get("q", "").strip()
        if q:
            c.execute(
                "SELECT v.*, cc.name AS container_name, cc.cargo_length_mm, cc.cargo_width_mm, cc.cargo_height_mm, cc.payload_kg "
                "FROM vehicles v LEFT JOIN container_configs cc ON cc.id = v.container_config_id "
                "WHERE v.plate_number LIKE ? ORDER BY v.plate_number",
                (f"%{q}%",)
            )
        else:
            c.execute(
                "SELECT v.*, cc.name AS container_name, cc.cargo_length_mm, cc.cargo_width_mm, cc.cargo_height_mm, cc.payload_kg "
                "FROM vehicles v LEFT JOIN container_configs cc ON cc.id = v.container_config_id "
                "ORDER BY v.plate_number"
            )
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        # `envelope_source` lets the vehicles table show which trucks still
        # have no routing envelope of their own. Phase B's real cost is data
        # entry across 36 vehicles, and a gap nobody can see is a gap nobody
        # closes (docs/VEHICLE_ROUTING_PLAN.md B4).
        for row in rows:
            _, row["envelope_source"] = resolve_envelope(row)
        return jsonify({"success": True, "data": rows})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route("/api/fleet/vehicles", methods=["POST"])
def api_vehicles_create():
    conn = None
    try:
        data = request.json or {}
        plate = (data.get("plate_number") or "").strip().upper()
        vtype = (data.get("vehicle_type") or "").strip()
        driver = (data.get("current_driver") or "").strip()
        if not plate:
            return jsonify({"success": False, "message": "Plate number is required"}), 400

        envelope = _envelope_from_request(data)
        errors, warnings = validate_envelope(envelope, _cargo_from_request(data))
        if errors:
            return jsonify({"success": False, "message": errors[0], "errors": errors}), 400

        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        envelope_cols = ", ".join(ENVELOPE_FIELDS)
        envelope_marks = ", ".join("?" for _ in ENVELOPE_FIELDS)
        c.execute(
            f"INSERT INTO vehicles (plate_number, vehicle_type, current_driver, {envelope_cols}) "
            f"VALUES (?, ?, ?, {envelope_marks})",
            (plate, vtype, driver, *[envelope[f] for f in ENVELOPE_FIELDS])
        )
        vehicle_id = c.lastrowid
        # Create container config if dimensions provided
        cargo_len = data.get("cargo_length_mm")
        if cargo_len:
            cargo_wid = data.get("cargo_width_mm", 0)
            cargo_hei = data.get("cargo_height_mm", 0)
            payload = data.get("payload_kg", 0)
            c.execute(
                "INSERT INTO container_configs (name, cargo_length_mm, cargo_width_mm, cargo_height_mm, payload_kg) VALUES (?, ?, ?, ?, ?)",
                (f"{plate} container", cargo_len, cargo_wid, cargo_hei, payload)
            )
            cc_id = c.lastrowid
            for feat in data.get("features", []):
                geo = feat.get("geometry", {})
                c.execute(
                    "INSERT INTO container_features (container_config_id, feature_type, label, geometry_json) VALUES (?, ?, ?, ?)",
                    (cc_id, feat["feature_type"], feat.get("label", ""), json.dumps(geo))
                )
            c.execute("UPDATE vehicles SET container_config_id = ? WHERE id = ?", (cc_id, vehicle_id))
        conn.commit()
        return jsonify({
            "success": True,
            "message": "Vehicle created",
            # Non-blocking: the value was saved. Surfaced so an odd number gets
            # a second look instead of being silently accepted.
            "warnings": warnings,
            "vehicle": {
                "id": vehicle_id, "plate_number": plate,
                "vehicle_type": vtype, "current_driver": driver, **envelope,
            },
        })
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "message": "Vehicle with that plate number already exists"}), 409
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn is not None:
            conn.close()


@bp.route("/api/fleet/vehicles/<int:vehicle_id>/container", methods=["PUT"])
def api_vehicle_set_container(vehicle_id):
    """Link a vehicle to a container config, or remove the link."""
    conn = None
    try:
        data = request.json or {}
        cc_id = data.get("container_config_id")
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        if cc_id:
            c.execute("UPDATE vehicles SET container_config_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                      (cc_id, vehicle_id))
        else:
            c.execute("UPDATE vehicles SET container_config_id = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                      (vehicle_id,))
        conn.commit()
        affected = c.rowcount
        if affected == 0:
            return jsonify({"success": False, "message": "Vehicle not found"}), 404
        return jsonify({"success": True, "message": "Container config updated"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn is not None:
            conn.close()


@bp.route("/api/fleet/vehicles/<int:vehicle_id>", methods=["PUT"])
def api_vehicles_update(vehicle_id):
    conn = None
    try:
        data = request.json or {}
        plate = (data.get("plate_number") or "").strip().upper()
        vtype = (data.get("vehicle_type") or "").strip()
        driver = (data.get("current_driver") or "").strip()
        if not plate:
            return jsonify({"success": False, "message": "Plate number is required"}), 400

        envelope = _envelope_from_request(data)
        errors, warnings = validate_envelope(envelope, _cargo_from_request(data))
        if errors:
            return jsonify({"success": False, "message": errors[0], "errors": errors}), 400

        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        envelope_fragment, envelope_params = _envelope_assignments(envelope)
        c.execute(
            "UPDATE vehicles SET plate_number=?, vehicle_type=?, current_driver=?, "
            f"{envelope_fragment}, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (plate, vtype, driver, *envelope_params, vehicle_id)
        )
        if c.rowcount == 0:
            return jsonify({"success": False, "message": "Vehicle not found"}), 404
        # Handle container config
        cargo_len = data.get("cargo_length_mm")
        if cargo_len:
            cargo_wid = data.get("cargo_width_mm", 0)
            cargo_hei = data.get("cargo_height_mm", 0)
            payload = data.get("payload_kg", 0)
            c.execute("SELECT container_config_id FROM vehicles WHERE id = ?", (vehicle_id,))
            row = c.fetchone()
            existing_cc_id = row[0] if row else None
            if existing_cc_id:
                c.execute(
                    "UPDATE container_configs SET name=?, cargo_length_mm=?, cargo_width_mm=?, cargo_height_mm=?, payload_kg=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (f"{plate} container", cargo_len, cargo_wid, cargo_hei, payload, existing_cc_id)
                )
                if "features" in data:
                    c.execute("DELETE FROM container_features WHERE container_config_id = ?", (existing_cc_id,))
                    for feat in data.get("features", []):
                        geo = feat.get("geometry", {})
                        c.execute(
                            "INSERT INTO container_features (container_config_id, feature_type, label, geometry_json) VALUES (?, ?, ?, ?)",
                            (existing_cc_id, feat["feature_type"], feat.get("label", ""), json.dumps(geo))
                        )
            else:
                c.execute(
                    "INSERT INTO container_configs (name, cargo_length_mm, cargo_width_mm, cargo_height_mm, payload_kg) VALUES (?, ?, ?, ?, ?)",
                    (f"{plate} container", cargo_len, cargo_wid, cargo_hei, payload)
                )
                cc_id = c.lastrowid
                for feat in data.get("features", []):
                    geo = feat.get("geometry", {})
                    c.execute(
                        "INSERT INTO container_features (container_config_id, feature_type, label, geometry_json) VALUES (?, ?, ?, ?)",
                        (cc_id, feat["feature_type"], feat.get("label", ""), json.dumps(geo))
                    )
                c.execute("UPDATE vehicles SET container_config_id = ? WHERE id = ?", (cc_id, vehicle_id))
        conn.commit()
        return jsonify({"success": True, "message": "Vehicle updated", "warnings": warnings})
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "message": "Plate number already exists"}), 409
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn is not None:
            conn.close()


@bp.route("/api/fleet/vehicles/<int:vehicle_id>", methods=["DELETE"])
def api_vehicles_delete(vehicle_id):
    conn = None
    try:
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        # Delete container config and features if present
        c.execute("SELECT container_config_id FROM vehicles WHERE id=?", (vehicle_id,))
        row = c.fetchone()
        if row and row[0]:
            c.execute("DELETE FROM container_features WHERE container_config_id = ?", (row[0],))
            c.execute("DELETE FROM container_configs WHERE id = ?", (row[0],))
        c.execute("DELETE FROM vehicles WHERE id=?", (vehicle_id,))
        if c.rowcount == 0:
            return jsonify({"success": False, "message": "Vehicle not found"}), 404
        c.execute("UPDATE fuel_log SET vehicle_id = NULL WHERE vehicle_id = ?", (vehicle_id,))
        conn.commit()
        return jsonify({"success": True, "message": "Vehicle deleted"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn is not None:
            conn.close()


@bp.route("/api/fleet/vehicles/bulk-delete", methods=["POST"])
def api_vehicles_bulk_delete():
    """Delete multiple vehicles by ID. Runs inside a transaction."""
    conn = None
    try:
        data = request.json or {}
        ids = data.get("ids", [])
        if not ids:
            return jsonify({"success": False, "message": "No vehicle IDs provided"}), 400

        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        conn.execute("BEGIN")

        try:
            deleted = 0
            for vid in ids:
                # Delete container config and features if present
                c.execute("SELECT container_config_id FROM vehicles WHERE id=?", (vid,))
                row = c.fetchone()
                if row and row[0]:
                    c.execute("DELETE FROM container_features WHERE container_config_id = ?", (row[0],))
                    c.execute("DELETE FROM container_configs WHERE id = ?", (row[0],))
                c.execute("DELETE FROM vehicles WHERE id=?", (vid,))
                if c.rowcount > 0:
                    c.execute("UPDATE fuel_log SET vehicle_id = NULL WHERE vehicle_id = ?", (vid,))
                    deleted += 1
            conn.commit()
            return jsonify({"success": True, "message": f"{deleted} vehicle(s) deleted", "deleted": deleted})
        except Exception:
            conn.rollback()
            raise
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn is not None:
            conn.close()


@bp.route("/api/fleet/vehicles/search")
def api_vehicles_search():
    """Autocomplete: returns matching vehicles with plate, type, driver."""
    try:
        q = request.args.get("q", "").strip()
        if not q:
            return jsonify({"success": True, "data": []})
        conn = sqlite3.connect(config.DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute(
            "SELECT id, plate_number, vehicle_type, current_driver FROM vehicles WHERE plate_number LIKE ? ORDER BY plate_number LIMIT 10",
            (f"%{q}%",)
        )
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return jsonify({"success": True, "data": rows})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# ----- Vehicle Types -----
@bp.route("/api/fleet/vehicle-types", methods=["GET"])
def api_vehicle_types_list():
    try:
        conn = sqlite3.connect(config.DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM vehicle_types ORDER BY name")
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return jsonify({"success": True, "data": rows})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route("/api/fleet/vehicle-types", methods=["POST"])
def api_vehicle_types_create():
    conn = None
    try:
        data = request.json or {}
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"success": False, "message": "Type name is required"}), 400
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO vehicle_types (name) VALUES (?)", (name,))
        conn.commit()
        type_id = c.lastrowid
        return jsonify({"success": True, "message": "Type added", "id": type_id, "name": name})
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "message": "Type already exists"}), 409
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn is not None:
            conn.close()


@bp.route("/api/fleet/vehicle-types/<int:type_id>", methods=["DELETE"])
def api_vehicle_types_delete(type_id):
    conn = None
    try:
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM vehicle_types WHERE id = ?", (type_id,))
        if c.rowcount == 0:
            return jsonify({"success": False, "message": "Type not found"}), 404
        conn.commit()
        return jsonify({"success": True, "message": "Type deleted"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn is not None:
            conn.close()
