"""
Database initialization orchestrator.

init_db() preserves app.py's original init_db() execution order exactly:
legacy vehicle_trips migration check -> create all tables -> column
migrations/backfill -> TLP table init -> TLP-specific migrations (second
connection, matching the original's conn/conn2 split).
"""
import sqlite3

from truck_load_planner.db import init_tlp_tables

from . import schema, migrations


def init_db(db_path: str):
    conn = sqlite3.connect(db_path)
    migrations.migrate_legacy_vehicle_trips_schema(conn)
    schema.create_tables(conn)
    migrations.run_all(conn)
    conn.close()

    # ----- TLP: container link + migration -----
    init_tlp_tables(db_path)

    conn2 = sqlite3.connect(db_path)
    conn2.row_factory = sqlite3.Row
    migrations.migrate_tlp_extensions(conn2)
    conn2.close()
