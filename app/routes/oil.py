"""
Oil change maintenance tracker: CRUD + TTAS KM-log scraping.

Extracted from app.py (Section 6.4.1, Phase 11).
"""
import sqlite3
import time
from datetime import date as _date, datetime as _datetime, timedelta as _timedelta

from flask import Blueprint, jsonify, render_template, request

from app import config, state
from app.utils.export import csv_response
from app.services.ttas_client import ensure_session, refresh_session, _parse_ttas_total_km
from main import fetch_report as _playwright_fetch_report

bp = Blueprint("oil", __name__)


def _store_km_log(entries: list):
    """Upsert parsed KM entries into oil_km_log using INSERT OR REPLACE.

    Each entry is a cumulative total from the oil change date to log_date.
    Delete any older entries for the same vehicle so they don't double-count.
    """
    if not entries:
        return
    conn = None
    try:
        conn = sqlite3.connect(config.DB_PATH, timeout=10)
        c = conn.cursor()
        for entry in entries:
            # Delete older cumulative entries for this vehicle (they are superseded)
            c.execute(
                "DELETE FROM oil_km_log WHERE license_plate = ? AND log_date < ?",
                (entry["license_plate"], entry["log_date"])
            )
            c.execute(
                "INSERT OR REPLACE INTO oil_km_log (license_plate, log_date, km) VALUES (?, ?, ?)",
                (entry["license_plate"], entry["log_date"], entry["daily_km"])
            )
        conn.commit()
        print(f"[OilTracker] Stored {len(entries)} entries: {entries[0]['license_plate']} log_date={entries[0]['log_date']} km={entries[0]['daily_km']}")
    except Exception as e:
        print(f"[OilTracker] DB write error: {e}")
        raise
    finally:
        if conn is not None:
            conn.close()


def _compute_oil_metrics(vehicle_row: dict, km_log_rows: list) -> dict:
    """Compute derived maintenance metrics for a vehicle."""
    total_km = sum(r["km"] for r in km_log_rows)
    interval = vehicle_row["maintenance_interval"] or 5000
    remaining = interval - total_km
    pct = round((total_km / interval) * 100, 1) if interval else 0
    if pct < 70:
        status = "safe"
    elif pct < 90:
        status = "warning"
    else:
        status = "danger"
    result = {k: v for k, v in vehicle_row.items() if k != "last_oil_change_km"}
    result.update({
        "total_km_since_change": total_km,
        "remaining_km": remaining,
        "progress_pct": pct,
        "maintenance_status": status,
    })
    return result


@bp.route("/oil-change")
def oil_change_page():
    return render_template("oil-change.html")


@bp.route("/api/oil-maintenance", methods=["GET"])
def api_oil_maintenance_list():
    """Return all vehicles with computed oil change metrics."""
    try:
        conn = sqlite3.connect(config.DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM oil_maintenance ORDER BY license_plate")
        vehicles = [dict(row) for row in c.fetchall()]

        results = []
        for v in vehicles:
            c.execute(
                "SELECT km, log_date FROM oil_km_log WHERE license_plate = ? AND log_date >= ? ORDER BY log_date",
                (v["license_plate"], v["last_oil_change_date"])
            )
            km_rows = [dict(r) for r in c.fetchall()]
            results.append(_compute_oil_metrics(v, km_rows))

        conn.close()
        resp = jsonify({"success": True, "data": results})
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        return resp
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route("/api/oil-maintenance/export")
def api_oil_maintenance_export():
    """Export oil maintenance data as CSV."""
    try:
        conn = sqlite3.connect(config.DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM oil_maintenance ORDER BY license_plate")
        vehicles = [dict(row) for row in c.fetchall()]

        rows = []
        for v in vehicles:
            c.execute(
                "SELECT km, log_date FROM oil_km_log WHERE license_plate = ? AND log_date >= ? ORDER BY log_date",
                (v["license_plate"], v["last_oil_change_date"])
            )
            km_rows = [dict(r) for r in c.fetchall()]
            rows.append(_compute_oil_metrics(v, km_rows))

        conn.close()

        headers = [
            "License Plate", "Last Change Date",
            "Interval (km)", "KM Since Change", "Remaining KM",
            "Progress (%)", "Status"
        ]
        csv_rows = [
            [
                r["license_plate"], r["last_oil_change_date"], r["maintenance_interval"],
                r["total_km_since_change"], r["remaining_km"], r["progress_pct"], r["maintenance_status"],
            ]
            for r in rows
        ]
        return csv_response(headers, csv_rows, "oil_maintenance_report.csv")
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route("/api/oil-maintenance", methods=["POST"])
def api_oil_maintenance_create():
    """Create a new vehicle oil maintenance record."""
    conn = None
    try:
        data = request.json or {}
        plate    = (data.get("license_plate") or "").strip().upper()
        dt       = (data.get("last_oil_change_date") or "").strip()
        interval = int(data.get("maintenance_interval") or 5000)

        if not plate:
            return jsonify({"success": False, "message": "license_plate is required"}), 400
        if not dt:
            return jsonify({"success": False, "message": "last_oil_change_date is required"}), 400

        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        c.execute(
            "INSERT INTO oil_maintenance (license_plate, last_oil_change_date, maintenance_interval) VALUES (?, ?, ?)",
            (plate, dt, interval)
        )
        conn.commit()
        return jsonify({"success": True, "message": "Vehicle added"})
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "message": "Vehicle with that license plate already exists"}), 409
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn is not None:
            conn.close()


@bp.route("/api/oil-maintenance/<plate>", methods=["PUT"])
def api_oil_maintenance_update(plate):
    """Update an existing vehicle oil maintenance record."""
    conn = None
    try:
        data     = request.json or {}
        plate    = plate.strip().upper()
        dt       = (data.get("last_oil_change_date") or "").strip()
        interval = int(data.get("maintenance_interval") or 5000)

        if not dt:
            return jsonify({"success": False, "message": "last_oil_change_date is required"}), 400

        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        c.execute(
            "UPDATE oil_maintenance SET last_oil_change_date=?, maintenance_interval=?, updated_at=CURRENT_TIMESTAMP WHERE license_plate=?",
            (dt, interval, plate)
        )
        if c.rowcount == 0:
            return jsonify({"success": False, "message": "Vehicle not found"}), 404
        # When oil change date is updated, clear all KM logs (they were computed from old date)
        c.execute("DELETE FROM oil_km_log WHERE license_plate=?", (plate,))
        conn.commit()
        return jsonify({"success": True, "message": "Vehicle updated"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn is not None:
            conn.close()


@bp.route("/api/oil-maintenance/<plate>", methods=["DELETE"])
def api_oil_maintenance_delete(plate):
    """Delete a vehicle oil maintenance record and its KM log."""
    conn = None
    try:
        plate = plate.strip().upper()
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM oil_maintenance WHERE license_plate=?", (plate,))
        c.execute("DELETE FROM oil_km_log WHERE license_plate=?", (plate,))
        conn.commit()
        return jsonify({"success": True, "message": "Vehicle deleted"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn is not None:
            conn.close()


@bp.route("/api/oil-maintenance/<plate>/maintenance", methods=["POST"])
def api_oil_maintenance_mark_done(plate):
    """Mark oil change as done: set last_oil_change_date to today and clear KM logs."""
    conn = None
    try:
        plate = plate.strip().upper()
        today = _date.today().strftime("%Y-%m-%d")
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        c.execute(
            "UPDATE oil_maintenance SET last_oil_change_date=?, updated_at=CURRENT_TIMESTAMP WHERE license_plate=?",
            (today, plate)
        )
        if c.rowcount == 0:
            return jsonify({"success": False, "message": "Vehicle not found"}), 404
        # Clear all KM logs since they were computed from the old oil change date
        c.execute("DELETE FROM oil_km_log WHERE license_plate=?", (plate,))
        conn.commit()
        return jsonify({"success": True, "message": f"Oil change marked as done for {plate}"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn is not None:
            conn.close()


@bp.route("/api/oil-maintenance/fetch-km", methods=["POST"])
def api_oil_maintenance_fetch_km():
    """Scrape the TTAS report for all vehicles from their last oil change date to yesterday."""
    # Scoped tightly and closed before the scrape below, which is slow: this
    # handler goes on to drive Playwright once per vehicle, and holding a
    # connection open across that would keep a handle on the DB file for the
    # whole run. The try/finally only guards the read.
    conn = None
    try:
        conn = sqlite3.connect(config.DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT license_plate, last_oil_change_date FROM oil_maintenance")
        vehicles = [dict(row) for row in c.fetchall()]
    finally:
        if conn is not None:
            conn.close()
            conn = None

    try:
        if not vehicles:
            return jsonify({"success": True, "message": "No vehicles to update", "vehicles_fetched": 0})

        # Determine start date and yesterday's date
        today = _date.today()
        yesterday = today - _timedelta(days=1)

        # Use the existing fleet session
        try:
            session = ensure_session()
        except Exception:
            try:
                session = refresh_session()
            except Exception as e:
                return jsonify({"success": False, "message": f"TTAS session error: {e}"}), 503

        vehicles_fetched = 0
        total_entries = 0
        errors = []

        total_vehicles = len(vehicles)
        with state.oil_fetch_lock:
            state.oil_fetch_progress.clear()
            state.oil_fetch_progress['total'] = total_vehicles
            state.oil_fetch_progress['current'] = 0
            state.oil_fetch_progress['plate'] = ''
            state.oil_fetch_progress['status'] = 'fetching'
            state.oil_fetch_progress['started_at'] = time.time()

        for idx, v in enumerate(vehicles, start=1):
            plate = v["license_plate"]
            with state.oil_fetch_lock:
                state.oil_fetch_progress['current'] = idx
                state.oil_fetch_progress['plate'] = plate
            try:
                start_date = _datetime.strptime(v["last_oil_change_date"], "%Y-%m-%d").date()
                if start_date > yesterday:
                    # Last change date was today or in the future
                    continue

                start_date_str = start_date.strftime("%d/%m/%Y")
                yesterday_str = yesterday.strftime("%d/%m/%Y")

                # Use Playwright-based fetch (handles login + report in one session)
                html = _playwright_fetch_report(plate, start_date_str, yesterday_str)
                entries = _parse_ttas_total_km(html, plate, yesterday_str)
                _store_km_log(entries)

                vehicles_fetched += 1
                total_entries += len(entries)
            except Exception as e:
                errors.append(f"{plate}: {e}")

        with state.oil_fetch_lock:
            state.oil_fetch_progress['status'] = 'done'

        msg = f"Fetched data for {vehicles_fetched} vehicle(s), {total_entries} KM entry/entries stored."
        if errors:
            msg += f" Errors on {len(errors)} vehicle(s)."

        return jsonify({
            "success": True,
            "message": msg,
            "vehicles_fetched": vehicles_fetched,
            "entries_stored": total_entries,
            "errors": errors[:10]
        })
    except Exception as e:
        with state.oil_fetch_lock:
            state.oil_fetch_progress['status'] = 'error'
            state.oil_fetch_progress['error'] = str(e)
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route("/api/oil-maintenance/fetch-progress")
def api_oil_fetch_progress():
    with state.oil_fetch_lock:
        return jsonify(dict(state.oil_fetch_progress) if state.oil_fetch_progress else {"status": "idle"})
