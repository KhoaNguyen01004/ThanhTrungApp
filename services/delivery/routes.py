import os
import json
import logging
from flask import Blueprint, jsonify, request, send_file, current_app
from datetime import date, datetime, timedelta
from pathlib import Path

# Module scope, and from app.services.ttas_client — not `from app import ...`.
# The old deferred `from app import fetch_vehicle_data` inside a bare
# `except Exception` resolved to the app *package*, which never exported that
# name, so every call raised ImportError, was swallowed, and returned an empty
# vehicle list. GPS silently never worked (audit C-01). Importing at module
# scope means a regression of this kind aborts create_app() instead of
# degrading one request at a time.
from app.services.ttas_client import fetch_vehicle_data
from app.services.vehicle_specs import build_ors_options
from services.plate_utils import normalize_plate

from . import plan_service
from . import sheet_import_service
from . import execution_service
from . import eta_service
from . import image_service
from . import export_service
from . import tracking_service

logger = logging.getLogger(__name__)

bp = Blueprint("delivery", __name__, url_prefix="/api")


def _db():
    return current_app.config.get("DB_PATH", current_app.root_path + "/routing_system.db")


def _ors_config():
    return (
        os.getenv("ORS_API_KEY", ""),
        os.getenv("ORS_BASE_URL", ""),
    )


def _ttas_vehicles():
    """Live GPS for the whole fleet, normalized.

    Returns ``(positions, source, error)``. ``fetch_vehicle_data`` already
    handles its own live→sample fallback and never raises, so the only
    exceptions reachable here are genuine bugs in normalization — logged with
    a traceback rather than flattened into an empty list, so the next C-01
    cannot hide.
    """
    try:
        raw, source, err = fetch_vehicle_data()
        return [tracking_service.normalize_gps_position(v) for v in raw], source, err
    except Exception as e:
        logger.exception("GPS normalization failed")
        return [], "error", f"{type(e).__name__}: {e}"


def _gps_by_plate_key(positions):
    """Index GPS positions by 5-digit plate serial.

    ``normalize_plate`` collapses the ``50E-18463`` / ``50E18463`` /
    ``50E 18463`` / ``18463`` variants that TTAS and the ``vehicles`` table
    disagree about onto one key (audit C-03). The previous
    ``.strip().lower()`` on both sides matched only byte-identical strings —
    and matched nothing at all, since the GPS side of the comparison read a
    field that was never emitted.
    """
    by_key = {}
    for position in positions:
        key = position.get("plate_key")
        if not key:
            continue
        if key in by_key:
            logger.warning(
                "Two GPS devices share plate serial %s (%r and %r) — keeping the first",
                key, by_key[key].get("device_name"), position.get("device_name"),
            )
            continue
        by_key[key] = position
    return by_key


# ===========================
# Drivers
# ===========================
@bp.route("/drivers", methods=["GET"])
def list_drivers():
    return jsonify(plan_service.list_drivers(_db()))


@bp.route("/drivers", methods=["POST"])
def create_driver():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Driver name is required"}), 400
    driver_id = plan_service.create_driver(_db(), name, data.get("phone", ""), data.get("license_number", ""))
    return jsonify({"id": driver_id}), 201


# ===========================
# Plans
# ===========================
@bp.route("/plans", methods=["GET"])
def list_plans():
    status = request.args.get("status")
    return jsonify(plan_service.list_plans(_db(), status))


@bp.route("/plans", methods=["POST"])
def create_plan():
    data = request.get_json(force=True)
    name = (data.get("plan_name") or "").strip()
    plan_date = (data.get("plan_date") or "").strip()
    if not name:
        return jsonify({"error": "plan_name is required"}), 400
    if not plan_date:
        return jsonify({"error": "plan_date is required"}), 400
    plan_id = plan_service.create_plan(_db(), name, plan_date, data.get("description", ""), data.get("created_by", ""))
    return jsonify({"id": plan_id}), 201


@bp.route("/plans/<int:plan_id>", methods=["GET"])
def get_plan(plan_id):
    plan = plan_service.get_plan(_db(), plan_id)
    if not plan:
        return jsonify({"error": "Plan not found"}), 404
    return jsonify(plan)


@bp.route("/plans/<int:plan_id>", methods=["PUT"])
def update_plan(plan_id):
    data = request.get_json(force=True)
    ok = plan_service.update_plan(_db(), plan_id, **data)
    if not ok:
        return jsonify({"error": "Plan not found or no changes"}), 404
    return jsonify({"ok": True})


@bp.route("/plans/<int:plan_id>", methods=["DELETE"])
def delete_plan(plan_id):
    ok = plan_service.delete_plan(_db(), plan_id)
    if not ok:
        return jsonify({"error": "Plan not found"}), 404
    return jsonify({"ok": True})


@bp.route("/plans/batch-delete", methods=["POST"])
def batch_delete_plans():
    data = request.get_json(force=True)
    plan_ids = data.get("plan_ids", [])
    if not plan_ids:
        return jsonify({"error": "plan_ids is required"}), 400
    plan_service.delete_plans(_db(), plan_ids)
    return jsonify({"ok": True})


@bp.route("/plans/clear", methods=["POST"])
def clear_plans():
    plan_service.clear_plans(_db())
    return jsonify({"ok": True})


@bp.route("/plans/<int:plan_id>/confirm", methods=["POST"])
def confirm_plan(plan_id):
    ok = plan_service.update_plan(_db(), plan_id, status="confirmed")
    if not ok:
        return jsonify({"error": "Plan not found"}), 404
    return jsonify({"ok": True})


# ===========================
# Excel Import Pipeline
# ===========================
@bp.route("/plans/import/parse", methods=["POST"])
def import_parse():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files["file"]
    tmp_path = Path(current_app.root_path) / "_import_temp.xlsx"
    file.save(str(tmp_path))
    try:
        rows = plan_service.parse_excel_rows(str(tmp_path))
        # db_path lets the preview report which plates resolve to fleet
        # vehicles, so unknown ones surface here rather than as a failure at
        # save time.
        preview = plan_service.preview_import(rows, db_path=_db())
        return jsonify(preview)
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


# ===========================
# Google Sheet Import Pipeline
# ===========================
# Reads the manager's planning sheet directly instead of the
# download-xlsx-then-upload round trip. Read-only: see
# services/delivery/sheet_import_service for why no write path exists.

def _sheet_target_date(raw):
    """Resolve the ?date= parameter, defaulting to tomorrow.

    Tomorrow, not today: this button plans the *next* dispatch day, which is
    what the dispatcher fills the sheet for.
    """
    if not raw:
        return date.today() + timedelta(days=1), None
    try:
        return datetime.strptime(str(raw).strip(), "%Y-%m-%d").date(), None
    except ValueError:
        return None, f"date must be YYYY-MM-DD, got {raw!r}"


def _read_sheet(target):
    """Fetch + parse, mapping sheet failures onto HTTP statuses.

    Returns ``(extract, None)`` or ``(None, (payload, status))``. A layout
    change and an empty day are different problems and must not be collapsed:
    the first means this importer is now reading the wrong columns and must not
    be trusted, the second is routine.
    """
    try:
        return sheet_import_service.fetch_plan_for_date(target), None
    except sheet_import_service.SheetDateNotFound as e:
        return None, ({"error": str(e), "reason": "date_not_found"}, 404)
    except sheet_import_service.SheetLayoutError as e:
        logger.error("Planning sheet layout changed: %s", e)
        return None, ({"error": str(e), "reason": "layout_changed"}, 502)
    except sheet_import_service.SheetFetchError as e:
        logger.warning("Planning sheet unreachable: %s", e)
        return None, ({"error": str(e), "reason": "fetch_failed"}, 502)


@bp.route("/plans/import/sheet/preview", methods=["GET"])
def import_sheet_preview():
    target, err = _sheet_target_date(request.args.get("date"))
    if err:
        return jsonify({"error": err}), 400

    extract, failure = _read_sheet(target)
    if failure:
        return jsonify(failure[0]), failure[1]

    preview = plan_service.preview_import(extract.rows, db_path=_db())
    existing = plan_service.plans_for_date(_db(), target.isoformat())

    return jsonify({
        "date": target.isoformat(),
        "tab_name": extract.tab_name,
        "warnings": [w.as_dict() for w in extract.warnings],
        "preview": preview,
        "existing_plans": existing,
        # Surfaced so the dispatcher is told *before* committing that a
        # re-import would discard delivery progress, rather than discovering it
        # from a 409.
        "replace_blocked": any(p["active_executions"] for p in existing),
    })


@bp.route("/plans/import/sheet/commit", methods=["POST"])
def import_sheet_commit():
    data = request.get_json(silent=True) or {}
    target, err = _sheet_target_date(data.get("date"))
    if err:
        return jsonify({"error": err}), 400

    extract, failure = _read_sheet(target)
    if failure:
        return jsonify(failure[0]), failure[1]

    day = target.isoformat()
    existing = plan_service.plans_for_date(_db(), day)
    blocking = [p for p in existing if p["active_executions"]]
    if blocking and not data.get("override_in_progress"):
        # 409, matching the UnknownVehicles precedent: the request is
        # well-formed, it conflicts with state. Nothing has been written.
        return jsonify({
            "error": (
                f"The plan for {day} already has "
                f"{sum(p['active_executions'] for p in blocking)} stop(s) that "
                "drivers have started. Replacing it would delete that "
                "progress. Re-send with override_in_progress to proceed anyway."
            ),
            "reason": "in_progress",
            "existing_plans": blocking,
        }), 409

    for plan in existing:
        plan_service.delete_plan(_db(), plan["id"])

    plan_id = plan_service.create_plan(
        _db(),
        plan_name=f"SINO_{target.strftime('%d_%m_%Y')}",
        plan_date=day,
        description=f"Imported from Google Sheet tab {extract.tab_name}",
        created_by="sheet-import",
    )

    try:
        summary = plan_service.confirm_import(_db(), plan_id, extract.rows)
    except plan_service.UnknownVehicles as e:
        # Roll the empty plan back. confirm_import writes nothing when it
        # raises, so leaving the shell behind would put an empty plan on the
        # dashboard for a date whose real plan was just deleted.
        plan_service.delete_plan(_db(), plan_id)
        return jsonify({
            "error": str(e),
            "reason": "unknown_vehicles",
            "unknown_vehicles": e.identifiers,
        }), 409
    except Exception as e:
        plan_service.delete_plan(_db(), plan_id)
        logger.exception("Sheet import failed for %s", day)
        return jsonify({"error": str(e), "reason": "import_failed"}), 400

    summary.update({
        "plan_id": plan_id,
        "date": day,
        "tab_name": extract.tab_name,
        "replaced_plan_ids": [p["id"] for p in existing],
        "warnings": [w.as_dict() for w in extract.warnings],
    })
    return jsonify(summary), 201


@bp.route("/plans/import/save", methods=["POST"])
def import_save():
    data = request.get_json(force=True)
    plan_id = data.get("plan_id")
    rows = data.get("rows")
    if not plan_id or not rows:
        return jsonify({"error": "plan_id and rows are required"}), 400
    try:
        summary = plan_service.confirm_import(_db(), plan_id, rows)
        return jsonify(summary), 201
    except plan_service.UnknownVehicles as e:
        # 409, not 400: the request is well-formed, it conflicts with fleet
        # state. The identifier list tells the dispatcher exactly which plates
        # to check. There is no override — an import never adds vehicles.
        return jsonify({
            "error": str(e),
            "unknown_vehicles": e.identifiers,
        }), 409
    except Exception as e:
        logger.exception("Import failed for plan %s", plan_id)
        return jsonify({"error": str(e)}), 400


# ===========================
# Vehicle Assignments
# ===========================
@bp.route("/assignments", methods=["GET"])
def list_assignments():
    plan_id = request.args.get("plan_id", type=int)
    return jsonify(plan_service.list_assignments(_db(), plan_id))


@bp.route("/assignments", methods=["POST"])
def create_assignment():
    data = request.get_json(force=True)
    plan_id = data.get("plan_id")
    vehicle_id = data.get("vehicle_id")
    if not plan_id or not vehicle_id:
        return jsonify({"error": "plan_id and vehicle_id are required"}), 400
    assignment_id = plan_service.create_assignment(
        _db(), plan_id, vehicle_id,
        driver_id=data.get("driver_id"),
        driver_name=data.get("driver_name"),
        sequence=data.get("sequence", 0),
        notes=data.get("notes", ""),
    )
    return jsonify({"id": assignment_id}), 201


@bp.route("/assignments/<int:assignment_id>", methods=["GET"])
def get_assignment(assignment_id):
    a = plan_service.get_assignment(_db(), assignment_id)
    if not a:
        return jsonify({"error": "Assignment not found"}), 404
    return jsonify(a)


@bp.route("/assignments/<int:assignment_id>", methods=["PUT"])
def update_assignment(assignment_id):
    data = request.get_json(force=True)
    ok = plan_service.update_assignment(_db(), assignment_id, **data)
    if not ok:
        return jsonify({"error": "Assignment not found or no changes"}), 404
    return jsonify({"ok": True})


@bp.route("/assignments/<int:assignment_id>", methods=["DELETE"])
def delete_assignment(assignment_id):
    ok = plan_service.delete_assignment(_db(), assignment_id)
    if not ok:
        return jsonify({"error": "Assignment not found"}), 404
    return jsonify({"ok": True})


# ===========================
# Stops
# ===========================
@bp.route("/stops", methods=["GET"])
def list_stops():
    assignment_id = request.args.get("assignment_id", type=int)
    if not assignment_id:
        return jsonify({"error": "assignment_id is required"}), 400
    # can_revert is stamped on here rather than computed in the browser so the
    # Revert button and the endpoint that honours it read the same clock.
    stops = execution_service.annotate_revertible(
        plan_service.list_stops(_db(), assignment_id)
    )
    return jsonify(stops)


@bp.route("/stops", methods=["POST"])
def create_stop():
    data = request.get_json(force=True)
    assignment_id = data.get("vehicle_assignment_id") or data.get("assignment_id")
    if not assignment_id:
        return jsonify({"error": "assignment_id is required"}), 400
    stop_id = plan_service.create_stop(
        _db(), assignment_id,
        data.get("planned_sequence", 0),
        station_code=data.get("station_code", ""),
        station_name=data.get("station_name", ""),
        address=data.get("address", ""),
        lat=data.get("lat"),
        lng=data.get("lng"),
        manager_name=data.get("manager_name", ""),
        manager_phone=data.get("manager_phone", ""),
        product_description=data.get("product_description", ""),
        note=data.get("note", ""),
    )
    return jsonify({"id": stop_id}), 201


@bp.route("/stops/<int:stop_id>", methods=["GET"])
def get_stop(stop_id):
    stop = plan_service.get_stop(_db(), stop_id)
    if not stop:
        return jsonify({"error": "Stop not found"}), 404
    images = image_service.list_images(_db(), stop_id)
    stop["images"] = images
    return jsonify(stop)


@bp.route("/stops/<int:stop_id>", methods=["PUT"])
def update_stop(stop_id):
    data = request.get_json(force=True)
    ok = plan_service.update_stop(_db(), stop_id, **data)
    if not ok:
        return jsonify({"error": "Stop not found or no changes"}), 404
    return jsonify({"ok": True})


@bp.route("/stops/<int:stop_id>", methods=["DELETE"])
def delete_stop(stop_id):
    ok = plan_service.delete_stop(_db(), stop_id)
    if not ok:
        return jsonify({"error": "Stop not found"}), 404
    return jsonify({"ok": True})


@bp.route("/stops/<int:stop_id>/skip", methods=["POST"])
def skip_stop(stop_id):
    data = request.get_json(force=True) or {}
    ok = execution_service.skip_stop(_db(), stop_id, data.get("reason", ""))
    if not ok:
        return jsonify({"error": "Stop not found"}), 404
    return jsonify({"ok": True})


@bp.route("/stops/<int:stop_id>/cancel", methods=["POST"])
def cancel_stop(stop_id):
    data = request.get_json(force=True) or {}
    ok = execution_service.cancel_stop(_db(), stop_id, data.get("reason", ""))
    if not ok:
        return jsonify({"error": "Stop not found"}), 404
    return jsonify({"ok": True})


@bp.route("/stops/<int:stop_id>/history", methods=["GET"])
def stop_status_history(stop_id):
    """The stop's recorded phase changes, oldest first.

    Empty for anything last touched before the log existed — nothing was
    backfilled, since inventing a history defeats the point of keeping one.
    """
    return jsonify(execution_service.list_status_events(_db(), stop_id))


@bp.route("/stops/reorder", methods=["POST"])
def reorder_stops():
    data = request.get_json(force=True)
    assignment_id = data.get("assignment_id")
    stop_ids = data.get("stop_ids")
    if not assignment_id or not stop_ids:
        return jsonify({"error": "assignment_id and stop_ids are required"}), 400
    ok, msg = execution_service.reorder_stops(_db(), assignment_id, stop_ids)
    if not ok:
        return jsonify({"error": msg}), 400
    return jsonify({"ok": True, "status": msg})


@bp.route("/stops/insert", methods=["POST"])
def insert_temp_stop():
    data = request.get_json(force=True)
    assignment_id = data.get("assignment_id")
    after_seq = data.get("after_sequence", 0)
    if not assignment_id:
        return jsonify({"error": "assignment_id is required"}), 400
    stop_id = execution_service.insert_temp_stop(
        _db(), assignment_id, after_seq,
        station_code=data.get("station_code", ""),
        station_name=data.get("station_name", ""),
        address=data.get("address", ""),
        lat=data.get("lat"),
        lng=data.get("lng"),
        manager_name=data.get("manager_name", ""),
        manager_phone=data.get("manager_phone", ""),
        product_description=data.get("product_description", ""),
        note=data.get("note", ""),
    )
    return jsonify({"id": stop_id}), 201


# ===========================
# Execution
# ===========================
@bp.route("/execution/current", methods=["GET"])
def get_current_stop():
    assignment_id = request.args.get("assignment_id", type=int)
    if not assignment_id:
        return jsonify({"error": "assignment_id is required"}), 400
    stop = execution_service.get_current_stop(_db(), assignment_id)
    if not stop:
        return jsonify({"message": "No active stop", "stop": None})
    return jsonify(stop)


@bp.route("/execution/advance", methods=["POST"])
def advance_stop():
    data = request.get_json(force=True)
    stop_id = data.get("stop_id")
    if not stop_id:
        return jsonify({"error": "stop_id is required"}), 400

    # Optional optimistic-concurrency token: the status the dispatcher's screen
    # was showing when they pressed Advance. Lets a double-tap (or a second
    # dispatcher) be rejected instead of silently double-stepping the stop.
    expected_status = data.get("expected_status")

    # Present only when the dispatcher has been told proof is missing and has
    # typed why it cannot be supplied.
    override_reason = data.get("override_reason", "")

    ok, msg = execution_service.advance_stop(
        _db(), stop_id, expected_status=expected_status, override_reason=override_reason
    )
    if not ok:
        if msg == execution_service.PROOF_REQUIRED:
            # 422 rather than 409: the request was well formed and the stop is
            # exactly where the client thought — it just isn't allowed yet.
            # A distinct code and flag mean the dashboard can offer the
            # override without pattern-matching on English.
            missing = execution_service.missing_proof(_db(), stop_id)
            labels = {"unload": "unloaded goods", "door": "locked door"}
            return jsonify({
                "error": "This stop needs a photo of the "
                         + " and the ".join(labels.get(m, m) for m in missing)
                         + " before it can be completed.",
                "proof_required": True,
                "missing": missing,
            }), 422
        # 409 when the stop simply moved on — the client should refresh, not
        # treat it as a malformed request.
        status_code = 409 if "already" in msg or "just advanced" in msg else 400
        return jsonify({"error": msg, "conflict": status_code == 409}), status_code
    return jsonify({"ok": True, "status": msg})


@bp.route("/execution/revert", methods=["POST"])
def revert_stop():
    """Undo the last Advance/Skip/Cancel on a stop.

    Advance is a single unconfirmed tap next to Skip and Cancel, pressed on a
    phone in a moving vehicle — a mis-tap needs a way back that isn't a
    hand-edited database row.
    """
    data = request.get_json(force=True)
    stop_id = data.get("stop_id")
    if not stop_id:
        return jsonify({"error": "stop_id is required"}), 400

    # Same optimistic-concurrency token as /execution/advance: the status the
    # dispatcher's screen was showing. A Revert button left on a stale panel
    # is refused rather than stepping back from somewhere unexpected.
    expected_status = data.get("expected_status")

    ok, msg = execution_service.revert_stop(_db(), stop_id, expected_status=expected_status)
    if not ok:
        status_code = 409 if "already" in msg or "just changed" in msg else 400
        return jsonify({"error": msg, "conflict": status_code == 409}), status_code
    return jsonify({"ok": True, "status": msg})


@bp.route("/execution/dashboard", methods=["GET"])
def get_dashboard():
    data = execution_service.get_dashboard_data(_db())
    vehicles, source, err = _ttas_vehicles()
    gps_by_key = _gps_by_plate_key(vehicles)

    matched = 0
    for entry in data:
        key = normalize_plate(entry.get("plate_number"))
        if key and key in gps_by_key:
            entry["gps"] = gps_by_key[key]
            matched += 1

    if data and not matched and gps_by_key:
        logger.warning(
            "No assignment matched any of %d GPS positions — check plate formats",
            len(gps_by_key),
        )

    return jsonify({
        "assignments": data,
        "gps_source": source,
        "gps_error": err,
        # Surfaced so the dashboard can show a degraded-GPS badge instead of
        # a green "Live" pill over an empty map, which is what let C-01 go
        # unnoticed for the module's entire life.
        "gps_matched": matched,
        "gps_available": len(gps_by_key),
    })


@bp.route("/execution/progress", methods=["GET"])
def get_progress():
    assignment_id = request.args.get("assignment_id", type=int)
    if not assignment_id:
        return jsonify({"error": "assignment_id is required"}), 400
    return jsonify(execution_service.get_assignment_progress(_db(), assignment_id))


# ===========================
# ETA
# ===========================
@bp.route("/eta", methods=["GET"])
def get_eta():
    assignment_id = request.args.get("assignment_id", type=int)
    if not assignment_id:
        return jsonify({"error": "assignment_id is required"}), 400

    stops = plan_service.list_stops(_db(), assignment_id)
    remaining = [s for s in stops if s.get("execution_status") in ("planned", "enroute")]

    vehicles, _, _ = _ttas_vehicles()
    assignment = plan_service.get_assignment(_db(), assignment_id)
    plate_key = normalize_plate(assignment.get("plate_number")) if assignment else ""

    # _ttas_vehicles() has already normalized these. The old code called
    # normalize_gps_position() a second time here, on an already-normalized
    # dict whose keys are lat/lng rather than latitude/longitude — which
    # coerced both to 0.0 and placed the vehicle at 0°N 0°E (audit C-02).
    current_gps = _gps_by_plate_key(vehicles).get(plate_key) if plate_key else None

    if not current_gps or current_gps.get("lat") is None or current_gps.get("lng") is None:
        return jsonify({"error": "Vehicle GPS not available", "etas": []})

    # Routing restrictions for this specific truck. `source` says whether they
    # came from the vehicle's own record or from a type estimate — the
    # dashboard shows the difference, because a route computed from a guess
    # must not read like one computed from the registration certificate.
    ors_options, restrictions_source = build_ors_options(assignment or {})

    ors_key, ors_base = _ors_config()
    etas = eta_service.calculate_etas_for_stops(
        ors_key, ors_base,
        current_gps["lat"], current_gps["lng"],
        remaining,
        assignment_id=assignment_id,
        options=ors_options,
    )

    remaining_distance_km = etas[-1]["cumulative_km"] if etas and etas[-1].get("cumulative_km") is not None else 0.0
    remaining_duration_sec = etas[-1]["cumulative_sec"] if etas and etas[-1].get("cumulative_sec") is not None else 0.0
    travelled_distance_km = eta_service.calculate_travelled_distance_km(
        stops, current_gps["lat"], current_gps["lng"]
    )

    return jsonify({
        "etas": etas,
        "gps": current_gps,
        "remaining_distance_km": remaining_distance_km,
        "remaining_duration_sec": remaining_duration_sec,
        "travelled_distance_km": travelled_distance_km,
        "total_distance_km": round(travelled_distance_km + remaining_distance_km, 2),
        # What the route was computed under, so a warning can name the actual
        # limits rather than saying "some restriction" — ORS never reports
        # which one blocked a route, and finding out costs one extra request
        # per restriction per leg.
        "restrictions": (ors_options or {}).get("profile_params", {}).get("restrictions") or {},
        "ors_vehicle_type": (ors_options or {}).get("vehicle_type"),
        "restrictions_source": restrictions_source,
    })


# ===========================
# Images per Stop
# ===========================
@bp.route("/stops/<int:stop_id>/images", methods=["GET"])
def list_stop_images(stop_id):
    return jsonify(image_service.list_images(_db(), stop_id))


@bp.route("/stops/<int:stop_id>/images", methods=["POST"])
def upload_stop_image(stop_id):
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files["file"]
    category = request.form.get("category", "extra")
    gps_lat = request.form.get("gps_lat", type=float)
    gps_lng = request.form.get("gps_lng", type=float)
    captured_at = request.form.get("captured_at")
    uploaded_by = request.form.get("uploaded_by", "")

    try:
        img_id = image_service.upload_image(
            _db(), stop_id, file, category=category,
            gps_lat=gps_lat, gps_lng=gps_lng,
            captured_at=captured_at, uploaded_by=uploaded_by,
        )
    except image_service.UploadRejected as e:
        return jsonify({"error": str(e)}), 400

    if not img_id:
        return jsonify({"error": "Stop not found"}), 404
    return jsonify({"id": img_id}), 201


# ===========================
# Images (generic)
# ===========================
# ===========================
# End-of-day export
# ===========================
@bp.route("/export/summary", methods=["GET"])
def export_summary():
    """What a given delivery day contains, including which stops are short of
    proof — asked before the download, while a driver is still reachable."""
    day = request.args.get("date", "")
    if not day:
        return jsonify({"error": "date is required (YYYY-MM-DD)"}), 400
    return jsonify(export_service.day_summary(_db(), day))


@bp.route("/export/day-images", methods=["GET"])
def list_day_images():
    day = request.args.get("date", "")
    if not day:
        return jsonify({"error": "date is required (YYYY-MM-DD)"}), 400
    return jsonify(export_service.list_day_images(_db(), day, request.args.get("category")))


@bp.route("/export/day-images", methods=["POST"])
def upload_day_image():
    """One loading or empty-container photo, one request.

    Deliberately not a batch endpoint: MAX_CONTENT_LENGTH is 25 MB for the
    whole request, so a day's loading photos would not fit in one POST — and
    uploading them individually means a failed ZIP download doesn't discard
    everything that was just handed over.
    """
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    day = request.form.get("date", "")
    category = request.form.get("category", "")
    try:
        image_id = export_service.add_day_image(
            _db(), day, category, request.files["file"],
            label=request.form.get("label", ""),
        )
    except image_service.UploadRejected as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"id": image_id}), 201


@bp.route("/export/day-images/<int:image_id>", methods=["DELETE"])
def delete_day_image(image_id):
    if not export_service.delete_day_image(_db(), image_id):
        return jsonify({"error": "Image not found"}), 404
    return jsonify({"ok": True})


@bp.route("/export/day.zip", methods=["GET"])
def download_day_zip():
    """Assemble and stream the day's handover ZIP.

    A plain GET, so the browser downloads it directly. Note this blocks the
    single production worker while it builds — acceptable at end of day, when
    dispatch is quiet, and stated here so the next person does not have to
    discover it.
    """
    day = request.args.get("date", "")
    if not day:
        return jsonify({"error": "date is required (YYYY-MM-DD)"}), 400
    folder_name = request.args.get("name", "")
    buffer = export_service.build_day_zip(
        _db(), day, folder_name, loading_date=request.args.get("loading_date") or None
    )
    filename = f"{image_service._safe_path_segment(folder_name, 'export')}.zip"
    return send_file(buffer, mimetype="application/zip",
                     as_attachment=True, download_name=filename)


@bp.route("/images/<int:image_id>/file", methods=["GET"])
def serve_image(image_id):
    img = image_service.get_image(_db(), image_id)
    if not img:
        return jsonify({"error": "Image not found"}), 404

    # relative_path is read back out of the database. Rows written before the
    # S-04 path-traversal fix could point outside the upload root, so confirm
    # containment here rather than trusting stored data.
    full_path = (image_service.DATA_ROOT / img["relative_path"]).resolve()
    if not full_path.is_relative_to(image_service.UPLOAD_ROOT.resolve()):
        logger.warning("Refusing to serve image %s outside upload root: %s", image_id, full_path)
        return jsonify({"error": "Image not found"}), 404
    if not full_path.exists():
        return jsonify({"error": "File not found on disk"}), 404
    # send_file defaults to conditional=True for a path, which is what makes
    # Range requests work — and video evidence is unplayable without them:
    # a browser seeking in a <video> issues a Range request and treats a 200
    # with the whole body as a non-seekable stream. Don't pass conditional=False
    # here, and don't swap this for a bare Response.
    return send_file(str(full_path))


@bp.route("/images/<int:image_id>", methods=["DELETE"])
def delete_image(image_id):
    ok = image_service.delete_image(_db(), image_id)
    if not ok:
        return jsonify({"error": "Image not found"}), 404
    return jsonify({"ok": True})
