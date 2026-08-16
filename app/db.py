"""
Centralized SQLite connection management.

Replaces the duplicated `get_conn(db_path)` / `_get_db()` helpers that were
copy-pasted across services/delivery/plan_service.py, execution_service.py,
image_service.py, and truck_load_planner/routes.py — one of which
(image_service.py) omitted `PRAGMA foreign_keys = ON` entirely, silently
allowing orphaned rows. SQLite pragmas are per-connection, not persisted to
the database file, so `foreign_keys` must be set on every new connection —
DatabaseManager.connect() does this by default so callers can't forget it.
"""
from contextlib import contextmanager
import sqlite3


class DatabaseManager:
    """Encapsulates SQLite connections for a single database file.

    Each `connect()` call yields a connection scoped to the `with` block:
    commits on clean exit, rolls back and re-raises on exception, and
    always closes. `sqlite3.Row` row_factory is set so callers can keep
    using both `row["col"]` and `dict(row)`, matching the previous
    get_conn()-based code.
    """

    def __init__(self, db_path: str):
        self._db_path = db_path

    @contextmanager
    def connect(self, enable_fk: bool = True):
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        if enable_fk:
            conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
