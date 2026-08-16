import sqlite3
import logging

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS drivers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT DEFAULT '',
    license_number TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS delivery_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_name TEXT NOT NULL,
    plan_date DATE NOT NULL,
    description TEXT DEFAULT '',
    status TEXT DEFAULT 'draft',
    imported_at TIMESTAMP,
    created_by TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS vehicle_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER NOT NULL REFERENCES delivery_plans(id) ON DELETE CASCADE,
    vehicle_id INTEGER NOT NULL REFERENCES vehicles(id),
    driver_id INTEGER REFERENCES drivers(id),
    -- Free-text driver for this plan only. Most drivers exist solely as
    -- vehicles.current_driver text and have no drivers row, so driver_id is
    -- usually NULL. A dispatcher who types a stand-in driver during plan
    -- creation is recording who drove *that day* — deliberately not promoted
    -- to a drivers record, and it must outrank the vehicle's default
    -- everywhere the plan is read back.
    driver_name_override TEXT DEFAULT '',
    sequence INTEGER NOT NULL DEFAULT 0,
    notes TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS delivery_plan_stops (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_assignment_id INTEGER NOT NULL REFERENCES vehicle_assignments(id) ON DELETE CASCADE,
    planned_sequence INTEGER NOT NULL DEFAULT 0,
    station_code TEXT DEFAULT '',
    station_name TEXT DEFAULT '',
    address TEXT DEFAULT '',
    lat REAL,
    lng REAL,
    manager_name TEXT DEFAULT '',
    manager_phone TEXT DEFAULT '',
    product_description TEXT DEFAULT '',
    note TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS stop_executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stop_id INTEGER NOT NULL REFERENCES delivery_plan_stops(id) ON DELETE CASCADE,
    execution_sequence INTEGER NOT NULL DEFAULT 0,
    status TEXT DEFAULT 'planned',
    skip_reason TEXT DEFAULT '',
    cancel_reason TEXT DEFAULT '',
    actual_arrival_at TIMESTAMP,
    actual_departure_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- One row per phase change, written inside the same transaction as the
-- change itself so the log cannot drift from the status it describes.
--
-- There is deliberately no `changed_by`: the module has no authentication
-- (see CHANGELOG 2026-07-31), and a column that is always blank is worse
-- than an absent one — it implies an accountability this system cannot
-- provide. This is an operational log, not a tamper-proof audit trail.
CREATE TABLE IF NOT EXISTS stop_status_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stop_id INTEGER NOT NULL REFERENCES delivery_plan_stops(id) ON DELETE CASCADE,
    from_status TEXT NOT NULL DEFAULT '',
    to_status TEXT NOT NULL,
    action TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    occurred_at TIMESTAMP NOT NULL
);

-- Photos that belong to a *day* rather than to any one stop: the loading
-- shots taken the evening before, and the empty-container shot each driver
-- sends once everything is delivered. Neither passes through the stop flow,
-- so neither has a stop_id to hang off — they are handed over during the
-- end-of-day export instead.
--
-- `day_date` is the delivery day being exported, in ISO form, even for
-- loading photos that were taken the day before: they are filed under the
-- delivery they belong to, which is how the operator's folders already read.
CREATE TABLE IF NOT EXISTS delivery_day_images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day_date TEXT NOT NULL,
    category TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    filename TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    original_filename TEXT DEFAULT '',
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS delivery_stop_images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stop_id INTEGER NOT NULL REFERENCES delivery_plan_stops(id) ON DELETE CASCADE,
    category TEXT NOT NULL DEFAULT 'extra',
    filename TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    original_filename TEXT DEFAULT '',
    gps_lat REAL,
    gps_lng REAL,
    captured_at TIMESTAMP,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    uploaded_by TEXT DEFAULT ''
);
"""

INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_vehicle_assignments_plan ON vehicle_assignments(plan_id);
CREATE INDEX IF NOT EXISTS idx_vehicle_assignments_vehicle ON vehicle_assignments(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_delivery_plan_stops_assignment ON delivery_plan_stops(vehicle_assignment_id);
CREATE INDEX IF NOT EXISTS idx_stop_executions_stop ON stop_executions(stop_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_stop_executions_unique ON stop_executions(stop_id);
CREATE INDEX IF NOT EXISTS idx_delivery_stop_images_stop ON delivery_stop_images(stop_id);
-- (stop_id, id) rather than (stop_id): every read of this table is "the
-- events for one stop, in order", and revert reads only the newest — which
-- this serves from the index without sorting.
CREATE INDEX IF NOT EXISTS idx_stop_status_events_stop ON stop_status_events(stop_id, id);
CREATE INDEX IF NOT EXISTS idx_delivery_day_images_day ON delivery_day_images(day_date);
"""


# Columns added after the original schema shipped. CREATE TABLE IF NOT EXISTS
# is a no-op on a database that already has the table, so a new column in
# SCHEMA_SQL never reaches an existing routing_system.db without this.
_ADDED_COLUMNS = [
    ("vehicle_assignments", "driver_name_override", "TEXT DEFAULT ''"),
]


def _add_missing_columns(c):
    for table, column, decl in _ADDED_COLUMNS:
        c.execute(f"PRAGMA table_info({table})")
        existing = {row[1] for row in c.fetchall()}
        if column in existing:
            continue
        try:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
            logger.info("Added column %s.%s", table, column)
        except Exception as e:
            logger.warning("Add column %s.%s: %s", table, column, e)


def init_delivery_tables(db_path: str):
    conn = sqlite3.connect(db_path)
    try:
        c = conn.cursor()

        for stmt in SCHEMA_SQL.split(";"):
            stmt = stmt.strip()
            if stmt:
                c.execute(stmt)

        for stmt in INDEXES_SQL.split(";"):
            stmt = stmt.strip()
            if stmt:
                try:
                    c.execute(stmt)
                except Exception as e:
                    logger.warning("Index: %s", e)

        _add_missing_columns(c)

        conn.commit()
        logger.info("Delivery tables initialized.")
    finally:
        conn.close()
