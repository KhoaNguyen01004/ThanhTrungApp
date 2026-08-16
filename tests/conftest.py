"""
Pytest bootstrap — must run before any test module is imported.

`app/config.py` reads DB_PATH **at import time**, and `create_app()` then runs
`init_db()` (schema creation plus every migration in `run_all()`) against
whatever it resolved. So the first test module that happens to import anything
under `app/` decides which database the whole session writes to — and with
DB_PATH unset, `config.py` falls back to `BASE_DIR / "routing_system.db"`,
which is the **production database sitting in the repository**.

Individual modules setting DB_PATH in their own headers is not enough: it only
protects a run in which that module is imported first. `tests/test_routing.py`
imported `app.services.routing` without such a guard, and in `pytest tests/`
that was enough to point `init_db()` at the real file. It went unnoticed
because every migration then in `run_all()` was a no-op against an
already-migrated database; adding one that actually writes to `vehicles` turned
it into 88 "disk I/O error" failures.

A conftest is imported before the test modules it sits beside, so this is the
only place the guarantee can be made once, for every test file present and
future.
"""
import os
import tempfile

_BOOT_FD, _BOOT_DB = tempfile.mkstemp(suffix="-pytest-boot.db")
os.close(_BOOT_FD)

# Unconditional, not setdefault: an inherited DB_PATH from the developer's
# shell is exactly the situation this is protecting against. Modules that want
# their own disposable database still override it in their own headers.
os.environ["DB_PATH"] = _BOOT_DB
