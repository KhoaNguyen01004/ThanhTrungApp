"""
Database initialization for Truck Load Planner tables.
Called from app.py:init_db().
"""

import sqlite3


TABLES = {
    "container_configs": """
        CREATE TABLE IF NOT EXISTS container_configs (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            name              TEXT NOT NULL DEFAULT '',
            cargo_length_mm   REAL NOT NULL,
            cargo_width_mm    REAL NOT NULL,
            cargo_height_mm   REAL NOT NULL,
            payload_kg        REAL NOT NULL DEFAULT 0,
            created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """,
    "container_features": """
        CREATE TABLE IF NOT EXISTS container_features (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            container_config_id INTEGER NOT NULL REFERENCES container_configs(id),
            feature_type        TEXT NOT NULL,
            label               TEXT NOT NULL DEFAULT '',
            geometry_json       TEXT NOT NULL DEFAULT '{}',
            created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """,
    "tlp_packages": """
        CREATE TABLE IF NOT EXISTS tlp_packages (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            name             TEXT NOT NULL,
            length           REAL NOT NULL,
            width            REAL NOT NULL,
            height           REAL NOT NULL,
            weight_kg        REAL NOT NULL,
            allow_stacking   INTEGER DEFAULT 0,
            allow_rotation   INTEGER DEFAULT 0,
            fragile          INTEGER DEFAULT 0,
            color            TEXT DEFAULT '#3b82f6',
            created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """,
    "tlp_shipments": """
        CREATE TABLE IF NOT EXISTS tlp_shipments (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name     TEXT NOT NULL,
            reference_number  TEXT,
            notes             TEXT,
            created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """,
    "tlp_shipment_items": """
        CREATE TABLE IF NOT EXISTS tlp_shipment_items (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            shipment_id   INTEGER NOT NULL REFERENCES tlp_shipments(id),
            package_id    INTEGER NOT NULL REFERENCES tlp_packages(id),
            quantity      INTEGER NOT NULL DEFAULT 1,
            notes         TEXT,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """,
    "tlp_load_plans": """
        CREATE TABLE IF NOT EXISTS tlp_load_plans (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT,
            vehicle_id   INTEGER,
            shipment_id  INTEGER REFERENCES tlp_shipments(id),
            planner      TEXT,
            notes        TEXT,
            status       TEXT DEFAULT 'draft',
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """,
    "tlp_placements": """
        CREATE TABLE IF NOT EXISTS tlp_placements (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            load_plan_id      INTEGER NOT NULL REFERENCES tlp_load_plans(id),
            shipment_item_id  INTEGER REFERENCES tlp_shipment_items(id),
            package_id        INTEGER NOT NULL REFERENCES tlp_packages(id),
            x                 REAL NOT NULL,
            y                 REAL NOT NULL,
            z                 REAL NOT NULL,
            rotation          INTEGER DEFAULT 0,
            stack_level       INTEGER DEFAULT 0,
            load_sequence     INTEGER,
            created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """,
}


def init_tlp_tables(db_path: str):
    """Create all TLP tables if they don't exist, and run migrations."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    for table_name, ddl in TABLES.items():
        try:
            c.execute(ddl)
        except Exception as e:
            print(f"Warning: Could not create {table_name}: {e}")

    # Migrations for existing databases
    c.execute("PRAGMA table_info(tlp_load_plans)")
    lp_cols = {col[1] for col in c.fetchall()}
    if "vehicle_id" not in lp_cols and "truck_id" in lp_cols:
        c.execute("ALTER TABLE tlp_load_plans ADD COLUMN vehicle_id INTEGER DEFAULT NULL")

    c.execute("PRAGMA table_info(tlp_packages)")
    pkg_cols = {col[1] for col in c.fetchall()}
    if "default_qty" not in pkg_cols:
        c.execute("ALTER TABLE tlp_packages ADD COLUMN default_qty INTEGER DEFAULT 1")

    # Migrations for stacking model
    c.execute("PRAGMA table_info(tlp_packages)")
    pkg_cols2 = {col[1] for col in c.fetchall()}
    if "max_top_weight_kg" not in pkg_cols2:
        c.execute("ALTER TABLE tlp_packages ADD COLUMN max_top_weight_kg REAL DEFAULT 0")
    if "max_stack_layers" not in pkg_cols2:
        c.execute("ALTER TABLE tlp_packages ADD COLUMN max_stack_layers INTEGER DEFAULT 0")

    conn.commit()
    conn.close()
