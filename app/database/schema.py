"""
Table definitions (CREATE TABLE IF NOT EXISTS statements).

Extracted from app.py's init_db() (Section 6.4.1, Phase 4). All statements
are idempotent (IF NOT EXISTS), so create_tables() is safe to call on
every startup regardless of whether the tables already exist.
"""


def create_tables(conn):
    c = conn.cursor()

    # Create table with all required columns (in case it didn't exist).
    # If a legacy-schema vehicle_trips table exists, migrations.py's
    # migrate_legacy_vehicle_trips_schema() must run BEFORE this — it
    # renames the old table out of the way first. Calling this first on
    # a fresh database is also safe: IF NOT EXISTS is a true no-op once
    # the table exists in any shape.
    c.execute('''
        CREATE TABLE IF NOT EXISTS vehicle_trips (
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

    # Geofence event log table
    c.execute('''
        CREATE TABLE IF NOT EXISTS geofence_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id TEXT NOT NULL,
            vehicle_name TEXT,
            trip_id INTEGER,
            event_type TEXT NOT NULL,
            location_name TEXT NOT NULL,
            lat REAL,
            lng REAL,
            phase INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # ----- Oil Change Maintenance Tables -----
    c.execute('''
        CREATE TABLE IF NOT EXISTS oil_maintenance (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            license_plate        TEXT    NOT NULL UNIQUE,
            last_oil_change_km   INTEGER NOT NULL DEFAULT 0,
            last_oil_change_date TEXT    NOT NULL,
            maintenance_interval INTEGER NOT NULL DEFAULT 5000,
            created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS oil_km_log (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            license_plate TEXT NOT NULL,
            log_date      TEXT NOT NULL,
            km            INTEGER NOT NULL DEFAULT 0,
            fetched_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(license_plate, log_date)
        )
    ''')

    # ----- Fuel Efficiency / Refuel Log Table -----
    c.execute('''
        CREATE TABLE IF NOT EXISTS fuel_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            license_plate   TEXT    NOT NULL,
            log_date        TEXT    NOT NULL,
            log_time        TEXT    NOT NULL,
            gas_store       TEXT    NOT NULL DEFAULT '',
            old_km          INTEGER NOT NULL DEFAULT 0,
            new_km          INTEGER NOT NULL DEFAULT 0,
            liters          REAL    NOT NULL DEFAULT 0,
            driver_name     TEXT    NOT NULL DEFAULT '',
            unit_price      REAL    DEFAULT NULL,
            notes           TEXT    DEFAULT '',
            is_full_tank    INTEGER NOT NULL DEFAULT 1,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # ----- Fuel Vehicle Profile (manual normal L/100km per vehicle) -----
    c.execute('''
        CREATE TABLE IF NOT EXISTS fuel_vehicle_profile (
            license_plate       TEXT PRIMARY KEY,
            normal_l_per_100km  REAL NOT NULL DEFAULT 10.0,
            anomaly_multiplier  REAL DEFAULT NULL,
            updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # ----- Master Vehicles Table -----
    c.execute('''
        CREATE TABLE IF NOT EXISTS vehicles (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            plate_number    TEXT NOT NULL UNIQUE,
            vehicle_type    TEXT NOT NULL DEFAULT '',
            current_driver  TEXT NOT NULL DEFAULT '',
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # ----- Vehicle Types Table -----
    c.execute('''
        CREATE TABLE IF NOT EXISTS vehicle_types (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
    ''')

    # ----- Google Sheet Sync History Table -----
    c.execute('''
        CREATE TABLE IF NOT EXISTS sync_history (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            fetched_rows    INTEGER NOT NULL DEFAULT 0,
            inserted_rows   INTEGER NOT NULL DEFAULT 0,
            duplicate_rows  INTEGER NOT NULL DEFAULT 0,
            failed_rows     INTEGER NOT NULL DEFAULT 0,
            duration_sec    REAL    NOT NULL DEFAULT 0,
            status          TEXT    NOT NULL DEFAULT 'success',
            error_message   TEXT    DEFAULT NULL,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
