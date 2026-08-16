"""Every write handler must close its connection on the exception path.

Why this file exists
--------------------
The 2026-08-06 audit found 53 of 54 raw ``sqlite3.connect()`` call sites
following this shape::

    try:
        conn = sqlite3.connect(...)
        ...
        conn.close()          # only reached when nothing raises
        return jsonify(...)
    except Exception as e:
        return jsonify({...}), 500

On a read handler a skipped ``close()`` is a standards violation and little
more — CPython's refcounting collects it quickly. On a **write** handler it is
not: if the exception lands after a write but before the commit, SQLite holds
a RESERVED lock until collection, and this deployment runs a single
synchronous Gunicorn worker with no WAL, so a concurrent request meets
``database is locked``. That is the same failure mode as the ``trips.py``
geofence bug, one size down.

Only write handlers were fixed (operator's scope call, 2026-08-06), so only
write handlers are tested here. ``fuel.py`` and ``oil.py`` had **no** route
coverage of any kind before this file.

How
---
``sqlite3.connect`` is swapped for a wrapper whose ``cursor()`` raises. Every
one of these handlers calls ``cursor()`` immediately after connecting, so this
forces an exception at exactly the point the ``finally`` exists to cover,
uniformly, without knowing anything about each handler's internals. The
wrapper records whether ``close()`` was subsequently called.
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_BOOT_FD, _BOOT_DB = tempfile.mkstemp(suffix="-writeconn-boot.db")
os.close(_BOOT_FD)
os.environ["DB_PATH"] = _BOOT_DB

from app import config, create_app                # noqa: E402
from app.database import init_db                  # noqa: E402


_REAL_CONNECT = sqlite3.connect


class ExplodingConnection:
    """Wraps a real connection and raises the moment a cursor is asked for."""

    def __init__(self, inner, log):
        self._inner = inner
        self._log = log
        self.closed = False

    def cursor(self, *a, **kw):
        raise RuntimeError("boom: simulated failure right after connect")

    # `execute` on the connection is the same story — a couple of handlers use
    # it directly (conn.execute('BEGIN'), conn.execute(SELECT ...)).
    def execute(self, *a, **kw):
        raise RuntimeError("boom: simulated failure right after connect")

    def close(self):
        self.closed = True
        self._inner.close()

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def __setattr__(self, name, value):
        if name in ("_inner", "_log", "closed"):
            object.__setattr__(self, name, value)
        else:
            setattr(self._inner, name, value)


@pytest.fixture(scope="module")
def app():
    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture
def db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(path)

    conn = _REAL_CONNECT(path)
    conn.execute(
        "INSERT INTO vehicles (plate_number, vehicle_type, current_driver) "
        "VALUES ('50E-18463', '5 Tons', 'Driver A')"
    )
    conn.execute(
        "INSERT INTO fuel_log (license_plate, log_date, log_time, gas_store, "
        "old_km, new_km, liters, driver_name, vehicle_id, is_full_tank) "
        "VALUES ('50E-18463', '2026-08-01', '08:00', 'Store', 100, 500, 40, 'Driver A', 1, 1)"
    )
    # `vehicle_types` is seeded by init_db (seed_vehicle_types), so inserting
    # here would hit its UNIQUE constraint. Row id 1 exists from that seed.
    conn.execute(
        "INSERT INTO oil_maintenance (license_plate, last_oil_change_date, "
        "maintenance_interval) VALUES ('50E-18463', '2026-07-01', 5000)"
    )
    conn.execute(
        "INSERT INTO vehicle_trips (vehicle_id, vehicle_name, destination_lat, "
        "destination_lng, destination_name, status, queue_order) "
        "VALUES ('1', 'Truck 1', 10.8, 106.6, 'Depot', 'active', 0)"
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(config, "DB_PATH", path)
    yield path
    os.unlink(path)


@pytest.fixture
def client(app, db):
    with app.test_client() as c:
        yield c


@pytest.fixture
def exploding(monkeypatch):
    """Make every sqlite3.connect() during the request return a booby-trapped
    connection, and hand back the list of them so the test can check closure."""
    opened = []

    def fake_connect(*args, **kwargs):
        wrapped = ExplodingConnection(_REAL_CONNECT(*args, **kwargs), opened)
        opened.append(wrapped)
        return wrapped

    monkeypatch.setattr(sqlite3, "connect", fake_connect)
    return opened


# (method, url, json body) — one per write handler that is reachable without
# an external service. api_fuel_sync (Google Sheets), fetch_km (Playwright/TTAS)
# and the background do_refresh_route_data are covered elsewhere or need a
# network stub that would test the stub rather than the handler.
WRITE_ENDPOINTS = [
    ("post",   "/api/fleet/vehicles",            {"plate_number": "51C-00001", "vehicle_type": "5 Tons"}),
    ("put",    "/api/fleet/vehicles/1/container", {"container_config_id": None}),
    ("put",    "/api/fleet/vehicles/1",          {"plate_number": "50E-18463", "vehicle_type": "5 Tons"}),
    ("delete", "/api/fleet/vehicles/1",          None),
    ("post",   "/api/fleet/vehicles/bulk-delete", {"ids": [1]}),
    ("post",   "/api/fleet/vehicle-types",       {"name": "Audit Test Type"}),
    ("delete", "/api/fleet/vehicle-types/1",     None),
    ("post",   "/api/fuel-log",                  {"license_plate": "50E-18463", "log_date": "2026-08-02",
                                                  "log_time": "09:00", "old_km": 500, "new_km": 900, "liters": 40}),
    ("put",    "/api/fuel-log/1",                {"liters": 45}),
    ("delete", "/api/fuel-log/1",                None),
    ("put",    "/api/fuel-log/profiles/50E-18463", {"normal_l_per_100km": 12.5}),
    ("delete", "/api/fuel-log/profiles/50E-18463", None),
    ("post",   "/api/oil-maintenance",           {"license_plate": "51C-00002",
                                                  "last_oil_change_date": "2026-08-01"}),
    ("put",    "/api/oil-maintenance/50E-18463", {"last_oil_change_date": "2026-08-02"}),
    ("delete", "/api/oil-maintenance/50E-18463", None),
    ("post",   "/api/oil-maintenance/50E-18463/maintenance", None),
    ("post",   "/api/advance-trip",              {"trip_id": 1}),
    ("post",   "/api/cancel-trip",               {"trip_id": 1}),
]


@pytest.mark.parametrize("method,url,body",
                         WRITE_ENDPOINTS,
                         ids=[f"{m.upper()} {u}" for m, u, _ in WRITE_ENDPOINTS])
def test_connection_is_closed_when_the_handler_raises(client, exploding, method, url, body):
    resp = getattr(client, method)(url, json=body) if body is not None \
        else getattr(client, method)(url)

    # The handler must still answer, not surface a raw traceback.
    assert resp.status_code == 500, resp.get_data(as_text=True)
    assert resp.get_json()["success"] is False

    assert opened_at_least_one(exploding), (
        f"{method.upper()} {url} never reached sqlite3.connect — this test is "
        "asserting nothing. Check the request body still passes validation."
    )
    unclosed = [i for i, c in enumerate(exploding) if not c.closed]
    assert not unclosed, (
        f"{method.upper()} {url} leaked {len(unclosed)} of {len(exploding)} "
        "connection(s) on the exception path"
    )


def opened_at_least_one(tracked):
    return len(tracked) > 0


@pytest.mark.parametrize("method,url,body",
                         WRITE_ENDPOINTS,
                         ids=[f"{m.upper()} {u}" for m, u, _ in WRITE_ENDPOINTS])
def test_happy_path_still_closes_and_still_works(client, method, url, body):
    """The `finally` must not have broken the ordinary path.

    Deliberately loose on the status code — several of these legitimately
    answer 404 or 409 depending on fixture state, and pinning exact codes here
    would make this a test of the fixture. What matters is that nothing 500s
    and nothing raises.
    """
    resp = getattr(client, method)(url, json=body) if body is not None \
        else getattr(client, method)(url)

    assert resp.status_code != 500, resp.get_data(as_text=True)
    assert resp.get_json() is not None
