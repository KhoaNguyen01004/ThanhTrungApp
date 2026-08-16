"""
Migration script: export old vehicle_trips data into the new delivery schema.

Idempotent: safe to run multiple times. Will skip if a delivery plan with
description 'Migrated from legacy vehicle_trips' already exists.

Usage:
    python scripts/migrate_to_delivery.py
    python scripts/migrate_to_delivery.py --force    # re-run even if already migrated
"""
import sys
import os
import json as _json
import sqlite3
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "routing_system.db")


def get_conn(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def migrate(force=False):
    conn = get_conn(DB_PATH)
    c = conn.cursor()

    # Idempotency check
    c.execute("SELECT COUNT(*) as cnt FROM delivery_plans WHERE description = 'Migrated from legacy vehicle_trips'")
    already = c.fetchone()["cnt"]
    if already > 0 and not force:
        print(f"Migration already completed ({already} plan(s) found).")
        print("Run with --force to re-run (will create duplicate plans).")
        conn.close()
        return

    # Check if old table has data
    c.execute("SELECT COUNT(*) as cnt FROM vehicle_trips")
    count = c.fetchone()["cnt"]
    print(f"Found {count} trips in vehicle_trips")

    if count == 0:
        print("Nothing to migrate.")
        conn.close()
        return

    c.execute("SELECT * FROM vehicle_trips ORDER BY created_at")
    trips = [dict(r) for r in c.fetchall()]

    # Group by vehicle
    vehicle_groups = defaultdict(list)
    for t in trips:
        vehicle_groups[t["vehicle_id"]].append(t)

    dates = [t.get("created_at", "")[:10] for t in trips if t.get("created_at")]
    plan_date = dates[0] if dates else datetime.now().strftime("%Y-%m-%d")
    plan_name = f"Migration Plan {plan_date}"

    c.execute(
        "INSERT INTO delivery_plans (plan_name, plan_date, description, status, imported_at) VALUES (?, ?, ?, 'completed', ?)",
        (plan_name, plan_date, "Migrated from legacy vehicle_trips", datetime.now().isoformat())
    )
    plan_id = c.lastrowid
    print(f"Created delivery plan #{plan_id}: {plan_name}")

    assignment_seq = 0
    total_stops = 0

    # Resolve every vehicle up front and abort if any is unknown. This script
    # used to INSERT a vehicle for any key it couldn't find, which is how a
    # migration silently populated `vehicles` with rows nobody registered.
    # Vehicles are core data — created only through Vehicle Management.
    from services.vehicle_identity import VehicleIndex

    c.execute("SELECT id, plate_number FROM vehicles")
    vehicle_index = VehicleIndex(c.fetchall())

    resolved: dict[str, int] = {}
    unknown: list[str] = []
    for vehicle_key in vehicle_groups:
        ref = vehicle_index.resolve(vehicle_key)
        if ref is None:
            # Legacy vehicle_trips.vehicle_id is TEXT and sometimes holds a
            # numeric vehicles.id rather than a plate — accept that too.
            c.execute("SELECT id FROM vehicles WHERE CAST(id AS TEXT) = ?", (str(vehicle_key),))
            row = c.fetchone()
            if row:
                resolved[vehicle_key] = row["id"]
                continue
            unknown.append(vehicle_key)
        else:
            resolved[vehicle_key] = ref.id

    if unknown:
        raise SystemExit(
            "Aborting: these vehicles from vehicle_trips are not registered in "
            "the fleet:\n  " + "\n  ".join(sorted(unknown)) +
            "\n\nAdd them in Vehicle Management, then re-run. "
            "This script will not create them."
        )

    for vehicle_key, vehicle_trips in vehicle_groups.items():
        assignment_seq += 1
        vehicle_id = resolved[vehicle_key]

        driver_name = vehicle_trips[0].get("driver_name", "")
        c.execute("SELECT id FROM drivers WHERE name = ?", (driver_name,))
        driver_row = c.fetchone()
        if driver_row:
            driver_id = driver_row["id"]
        elif driver_name:
            c.execute("INSERT INTO drivers (name) VALUES (?)", (driver_name,))
            driver_id = c.lastrowid
        else:
            driver_id = None

        c.execute(
            "INSERT INTO vehicle_assignments (plan_id, vehicle_id, driver_id, sequence, notes) VALUES (?, ?, ?, ?, ?)",
            (plan_id, vehicle_id, driver_id, assignment_seq,
             f"Migrated {len(vehicle_trips)} trip(s)")
        )
        assignment_id = c.lastrowid

        stop_seq = 0
        for t in vehicle_trips:
            stops_for_trip = []

            if t.get("pickup_lat") and t.get("pickup_lng"):
                stop_seq += 1
                stops_for_trip.append({
                    "planned_sequence": stop_seq,
                    "station_code": "",
                    "station_name": t.get("pickup_name", "Pickup") or "Pickup",
                    "address": "",
                    "lat": t["pickup_lat"],
                    "lng": t["pickup_lng"],
                    "manager_name": "",
                    "manager_phone": "",
                    "product_description": t.get("customer_name", ""),
                    "note": "",
                })

            waypoints_raw = t.get("waypoints")
            if waypoints_raw:
                try:
                    wps = _json.loads(waypoints_raw)
                    for wp in wps:
                        stop_seq += 1
                        stops_for_trip.append({
                            "planned_sequence": stop_seq,
                            "station_code": "",
                            "station_name": wp.get("name", "Waypoint"),
                            "address": "",
                            "lat": wp["lat"],
                            "lng": wp["lng"],
                            "manager_name": "",
                            "manager_phone": "",
                            "product_description": "",
                            "note": "",
                        })
                except Exception:
                    pass

            if t.get("destination_lat") and t.get("destination_lng"):
                stop_seq += 1
                stops_for_trip.append({
                    "planned_sequence": stop_seq,
                    "station_code": "",
                    "station_name": t.get("destination_name", "Destination") or "Destination",
                    "address": "",
                    "lat": t["destination_lat"],
                    "lng": t["destination_lng"],
                    "manager_name": "",
                    "manager_phone": "",
                    "product_description": t.get("customer_name", ""),
                    "note": "",
                })

            for s in stops_for_trip:
                c.execute("""
                    INSERT INTO delivery_plan_stops
                        (vehicle_assignment_id, planned_sequence, station_code, station_name,
                         address, lat, lng, manager_name, manager_phone, product_description, note)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    assignment_id,
                    s["planned_sequence"],
                    s["station_code"],
                    s["station_name"],
                    s.get("address", ""),
                    s.get("lat"),
                    s.get("lng"),
                    s.get("manager_name", ""),
                    s.get("manager_phone", ""),
                    s.get("product_description", ""),
                    s.get("note", ""),
                ))
                stop_id = c.lastrowid

                trip_status = t.get("status", "queued")
                if trip_status == "completed":
                    exec_status = "completed"
                elif trip_status == "canceled":
                    exec_status = "cancelled"
                else:
                    exec_status = "planned"

                c.execute("""
                    INSERT INTO stop_executions (stop_id, execution_sequence, status, completed_at)
                    VALUES (?, ?, ?, ?)
                """, (stop_id, s["planned_sequence"], exec_status,
                      t.get("completed_at") if exec_status == "completed" else None))

                total_stops += 1

    conn.commit()
    print(f"Migration complete: {assignment_seq} assignments, {total_stops} stops")
    conn.close()


if __name__ == "__main__":
    force = "--force" in sys.argv
    migrate(force=force)
