"""
Column migrations and data backfill for existing databases.

Extracted from app.py's init_db() (Section 6.4.1, Phase 5). Each function
is idempotent — safe to run on every startup. `run_all()` preserves the
original relative execution order from init_db().
"""
import json
import logging

logger = logging.getLogger(__name__)


def migrate_legacy_vehicle_trips_schema(conn):
    """Rename+recreate vehicle_trips if it predates the id-primary-key schema.

    Must run before schema.create_tables() only in the sense that it
    detects and renames an old-shaped table out of the way; if the table
    doesn't exist yet or is already correctly shaped, this is a no-op and
    create_tables()'s `CREATE TABLE IF NOT EXISTS` handles the fresh-install
    case either way.
    """
    c = conn.cursor()
    c.execute("PRAGMA table_info(vehicle_trips)")
    table_info = c.fetchall()

    needs_migration = False
    if len(table_info) > 0:
        if table_info[0][1] != 'id' or table_info[0][5] != 1:
            needs_migration = True

    if not needs_migration:
        return

    print("Migrating vehicle_trips table to new schema...")

    c.execute("ALTER TABLE vehicle_trips RENAME TO vehicle_trips_old")

    c.execute('''
        CREATE TABLE vehicle_trips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id TEXT NOT NULL,
            vehicle_name TEXT,
            destination_lat REAL,
            destination_lng REAL,
            destination_name TEXT,
            pickup_lat REAL,
            pickup_lng REAL,
            pickup_name TEXT,
            customer_name TEXT,
            last_known_eta REAL,
            last_known_distance REAL,
            vehicle_type TEXT,
            status TEXT DEFAULT 'queued',
            queue_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    c.execute("PRAGMA table_info(vehicle_trips_old)")
    old_columns = [col[1] for col in c.fetchall()]

    columns_to_select = []
    for col in old_columns:
        if col in [
            'vehicle_id', 'vehicle_name', 'destination_lat', 'destination_lng',
            'destination_name', 'pickup_lat', 'pickup_lng', 'pickup_name',
            'customer_name', 'last_known_eta', 'last_known_distance',
            'vehicle_type', 'status', 'queue_order', 'created_at', 'updated_at'
        ]:
            columns_to_select.append(col)

    placeholders = ','.join('?' * len(columns_to_select))
    c.execute(f'''
        INSERT INTO vehicle_trips ({','.join(columns_to_select)})
        SELECT {','.join(columns_to_select)} FROM vehicle_trips_old
    ''')

    c.execute("DROP TABLE vehicle_trips_old")

    conn.commit()
    print("Migration complete!")


def add_missing_vehicle_trips_columns(conn):
    c = conn.cursor()
    existing_columns = [col[1] for col in c.execute("PRAGMA table_info(vehicle_trips)")]
    required_columns = [
        ('destination_name', 'TEXT'),
        ('pickup_lat', 'REAL'),
        ('pickup_lng', 'REAL'),
        ('pickup_name', 'TEXT'),
        ('vehicle_type', 'TEXT'),
        ('customer_name', 'TEXT'),
        ('status', 'TEXT'),
        ('queue_order', 'INTEGER'),
        ('phase', 'TEXT'),
        ('completed_at', 'TIMESTAMP'),
        ('driver_name', 'TEXT'),
        ('waypoints', 'TEXT'),  # JSON array of {name, lat, lng}
        ('canceled_at', 'TIMESTAMP'),
        ('cancel_reason', 'TEXT'),
    ]
    for col_name, col_type in required_columns:
        if col_name not in existing_columns:
            try:
                c.execute(f"ALTER TABLE vehicle_trips ADD COLUMN {col_name} {col_type}")
            except Exception:
                pass  # column may already exist despite PRAGMA
    conn.commit()


def add_missing_fuel_columns(conn):
    c = conn.cursor()

    # Migration: add is_full_tank if missing
    try:
        c.execute("ALTER TABLE fuel_log ADD COLUMN is_full_tank INTEGER NOT NULL DEFAULT 1")
    except Exception:
        pass

    # Migration: add anomaly_multiplier if missing
    try:
        c.execute("ALTER TABLE fuel_vehicle_profile ADD COLUMN anomaly_multiplier REAL DEFAULT NULL")
    except Exception:
        pass

    # Add vehicle_id column to fuel_log if missing
    c.execute("PRAGMA table_info(fuel_log)")
    fuel_cols = {col[1] for col in c.fetchall()}
    if 'vehicle_id' not in fuel_cols:
        c.execute("ALTER TABLE fuel_log ADD COLUMN vehicle_id INTEGER DEFAULT NULL")

    conn.commit()


def add_vehicle_envelope_columns(conn):
    """Physical envelope of the vehicle itself, for ORS routing restrictions.

    Distinct from container_configs, which describes the *cargo compartment*
    for the bin-packing planner. The two are not interchangeable: a 2.35 m
    cargo box sits on a truck well over 3 m tall, and payload_kg excludes the
    entire kerb weight. Feeding cargo figures to a router would produce routes
    that look height-checked and are not (docs/VEHICLE_ROUTING_PLAN.md §3).

    All nullable with no default. NULL means "unknown", and an unknown
    restriction is omitted from the ORS request entirely — a 0 would be sent
    as a real limit and match nothing.
    """
    c = conn.cursor()
    c.execute("PRAGMA table_info(vehicles)")
    existing = {col[1] for col in c.fetchall()}

    for col_name, col_type in [
        ("gross_weight_kg", "INTEGER DEFAULT NULL"),
        ("overall_height_mm", "INTEGER DEFAULT NULL"),
        ("overall_width_mm", "INTEGER DEFAULT NULL"),
        ("overall_length_mm", "INTEGER DEFAULT NULL"),
        ("axle_load_kg", "INTEGER DEFAULT NULL"),
    ]:
        if col_name not in existing:
            c.execute(f"ALTER TABLE vehicles ADD COLUMN {col_name} {col_type}")

    conn.commit()


def seed_vehicle_types(conn):
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM vehicle_types")
    if c.fetchone()[0] == 0:
        default_types = ["1 Ton", "1.5 Tons", "2 Tons", "3.5 Tons", "5 Tons", "8 Tons", "Tractor Head", "Container Truck"]
        for t in default_types:
            c.execute("INSERT OR IGNORE INTO vehicle_types (name) VALUES (?)", (t,))
    conn.commit()


def backfill_vehicles_from_fuel_log(conn):
    """Link existing fuel_log rows to the vehicles they belong to.

    **Link-only. This never creates a vehicle and never edits one.**

    It used to upsert every distinct plate in `fuel_log` into `vehicles` on
    each boot, with `ON CONFLICT DO UPDATE SET current_driver = ...` — so a
    driver name typed on a fuel form silently became the vehicle's official
    current driver, and any plate not already stored byte-identically became a
    new vehicle row. `vehicles` is core data maintained through Vehicle
    Management; startup code has no business editing it.

    Plates are resolved through services.vehicle_identity, which matches on
    the 5-digit serial, so `09473` and `50H-09473` link to the same vehicle.
    Unlinkable plates are left alone and reported in the log rather than
    conjured into existence.
    """
    from services.vehicle_identity import VehicleIndex

    c = conn.cursor()
    c.execute(
        "SELECT DISTINCT license_plate FROM fuel_log "
        "WHERE license_plate IS NOT NULL AND license_plate != '' AND vehicle_id IS NULL"
    )
    unlinked_plates = [r[0] for r in c.fetchall()]
    if not unlinked_plates:
        return

    c.execute("SELECT id, plate_number FROM vehicles")
    index = VehicleIndex(c.fetchall())

    linked, unresolved = 0, []
    for plate in unlinked_plates:
        ref = index.resolve(plate)
        if ref is None:
            unresolved.append(plate)
            continue
        # Normalise the fuel_log row onto the fleet's canonical plate and link
        # it. This edits fuel history (operational data), never the vehicle.
        c.execute(
            "UPDATE fuel_log SET license_plate = ?, vehicle_id = ? "
            "WHERE license_plate = ? AND vehicle_id IS NULL",
            (ref.plate_number, ref.id, plate)
        )
        linked += c.rowcount

    conn.commit()

    if linked:
        logger.info("Linked %d fuel_log row(s) to existing vehicles.", linked)
    if unresolved:
        logger.warning(
            "%d fuel_log plate(s) match no registered vehicle and were left "
            "unlinked — add them in Vehicle Management if they are real: %s",
            len(unresolved), ", ".join(sorted(unresolved)[:20]),
        )


def migrate_tlp_extensions(conn2):
    """TLP: container_config_id / vehicle_id columns + one-time tlp_trucks → container_configs migration.

    Runs on a second connection after init_tlp_tables() has created the
    base TLP tables, matching the original init_db()'s two-connection
    structure.
    """
    c2 = conn2.cursor()

    # Add container_config_id to vehicles if missing
    c2.execute("PRAGMA table_info(vehicles)")
    vcols = {col[1] for col in c2.fetchall()}
    if 'container_config_id' not in vcols:
        c2.execute("ALTER TABLE vehicles ADD COLUMN container_config_id INTEGER DEFAULT NULL")

    # Add vehicle_id to tlp_load_plans if missing (migration from truck_id)
    c2.execute("PRAGMA table_info(tlp_load_plans)")
    lpcols = {col[1] for col in c2.fetchall()}
    if 'vehicle_id' not in lpcols:
        c2.execute("ALTER TABLE tlp_load_plans ADD COLUMN vehicle_id INTEGER DEFAULT NULL")

    # Migrate tlp_trucks → container_configs + features (one-time).
    #
    # This is the only place outside Vehicle Management that writes a core
    # vehicle field (container_config_id, i.e. the vehicle's dimensions), and
    # it is deliberately kept: it does not act on new data, it relocates
    # dimensions the user already entered from the retired `tlp_trucks` table
    # into `container_configs`. Double-guarded — it runs only when
    # `container_configs` is empty AND `tlp_trucks` still exists, so it fires
    # once in a database's lifetime and is inert thereafter.
    #
    # It logs what it changed. A migration that rewrites core fleet data
    # without saying so is the thing being avoided, not migration itself.
    try:
        existing = c2.execute("SELECT id FROM container_configs LIMIT 1").fetchone()
        if not existing:
            trucks = c2.execute("SELECT * FROM tlp_trucks").fetchall()
            if trucks:
                logger.warning(
                    "One-time migration: moving %d vehicle container spec(s) from "
                    "the retired tlp_trucks table into container_configs, and "
                    "relinking vehicles.container_config_id. Verify dimensions in "
                    "Vehicle Management afterwards.", len(trucks),
                )
            for t in trucks:
                c2.execute("""
                    INSERT INTO container_configs (name, cargo_length_mm, cargo_width_mm, cargo_height_mm, payload_kg)
                    VALUES (?, ?, ?, ?, ?)
                """, (t["name"], t["cargo_length"], t["cargo_width"], t["cargo_height"], t["payload_kg"]))
                cc_id = c2.lastrowid

                if t.get("rear_door_width") and t.get("rear_door_height"):
                    c2.execute("""
                        INSERT INTO container_features (container_config_id, feature_type, label, geometry_json)
                        VALUES (?, 'rear_door', 'Rear Door', ?)
                    """, (cc_id, json.dumps({"width_mm": t["rear_door_width"], "height_mm": t["rear_door_height"]})))

                if t.get("has_side_door") and t.get("side_door_width") and t.get("side_door_height"):
                    c2.execute("""
                        INSERT INTO container_features (container_config_id, feature_type, label, geometry_json)
                        VALUES (?, 'side_door', 'Side Door', ?)
                    """, (cc_id, json.dumps({
                        "width_mm": t["side_door_width"],
                        "height_mm": t["side_door_height"],
                        "position_from_front_mm": 0,
                    })))

                c2.execute(
                    "UPDATE vehicles SET container_config_id = ? WHERE plate_number = ?",
                    (cc_id, t["plate_number"])
                )

            # Migrate load plans: truck_id → vehicle_id
            plans = c2.execute("SELECT id, truck_id FROM tlp_load_plans WHERE vehicle_id IS NULL").fetchall()
            for pl in plans:
                truck_row = c2.execute("SELECT plate_number FROM tlp_trucks WHERE id = ?",
                                       (pl["truck_id"],)).fetchone()
                if truck_row:
                    vrow = c2.execute("SELECT id FROM vehicles WHERE plate_number = ?",
                                     (truck_row["plate_number"],)).fetchone()
                    if vrow:
                        c2.execute("UPDATE tlp_load_plans SET vehicle_id = ? WHERE id = ?",
                                  (vrow["id"], pl["id"]))
    except Exception as e:
        print(f"TLP migration note: {e}")

    conn2.commit()


def run_all(conn):
    """Run all pre-TLP migrations in original init_db() order.

    migrate_tlp_extensions() is NOT included here — it needs its own
    connection with row_factory=sqlite3.Row and must run after
    init_tlp_tables(), so callers invoke it separately (see app/__init__.py).
    """
    migrate_legacy_vehicle_trips_schema(conn)
    add_missing_vehicle_trips_columns(conn)
    add_missing_fuel_columns(conn)
    add_vehicle_envelope_columns(conn)
    seed_vehicle_types(conn)
    backfill_vehicles_from_fuel_log(conn)
