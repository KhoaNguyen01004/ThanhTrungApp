"""Route-layer tests for the fuel log API.

Why this file exists
--------------------
``app/routes/fuel.py`` had **no** test coverage of any kind before
2026-08-06 — nothing in the repo issued a request to ``/api/fuel-log``.

The change these tests exist for is a performance fix that must not alter a
single byte of the response: ``api_fuel_log_list`` called four helpers per
row, each of which opened its own connection (and two of those opened a
second), so listing the 323 fuel_log rows in this fleet's database opened
over a thousand connections for one request — behind render.yaml's single
synchronous Gunicorn worker, blocking everything else meanwhile.

``test_response_is_unchanged_by_connection_reuse`` is the one that matters:
it captures the full payload with the helpers opening their own connections
(the old behaviour, still reachable because the ``conn`` parameter is
optional) and asserts the endpoint produces exactly that.
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_BOOT_FD, _BOOT_DB = tempfile.mkstemp(suffix="-fuel-boot.db")
os.close(_BOOT_FD)
os.environ["DB_PATH"] = _BOOT_DB

from app import config, create_app                     # noqa: E402
from app.database import init_db                       # noqa: E402
from app.routes import fuel as fuel_module             # noqa: E402

_REAL_CONNECT = sqlite3.connect


@pytest.fixture(scope="module")
def app():
    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture
def db(monkeypatch):
    """Two vehicles and 40 fuel entries — enough rows for an O(N) connection
    count to be unmistakably different from an O(1) one."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(path)

    conn = _REAL_CONNECT(path)
    conn.execute("INSERT INTO vehicles (plate_number, vehicle_type, current_driver) "
                 "VALUES ('50E-18463', '5 Tons', 'Driver A')")
    conn.execute("INSERT INTO vehicles (plate_number, vehicle_type, current_driver) "
                 "VALUES ('51C-09999', 'Container', 'Driver B')")
    km = 1000
    for i in range(40):
        vehicle_id = 1 if i % 2 == 0 else 2
        plate = '50E-18463' if vehicle_id == 1 else '51C-09999'
        conn.execute(
            "INSERT INTO fuel_log (license_plate, log_date, log_time, gas_store, "
            "old_km, new_km, liters, driver_name, unit_price, notes, vehicle_id, is_full_tank) "
            "VALUES (?, ?, '08:00', 'Store', ?, ?, ?, 'Driver', 22000, '', ?, ?)",
            (plate, f"2026-07-{(i % 28) + 1:02d}", km, km + 400, 45 + (i % 7),
             vehicle_id, 1 if i % 3 else 0),
        )
        km += 400
    conn.execute("INSERT INTO fuel_vehicle_profile (license_plate, normal_l_per_100km, "
                 "anomaly_multiplier) VALUES ('51C-09999', 11.5, 1.4)")
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
def count_connections(monkeypatch):
    """Count sqlite3.connect() calls made during a request."""
    calls = []

    def counting_connect(*args, **kwargs):
        calls.append(args[0] if args else kwargs.get("database"))
        return _REAL_CONNECT(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", counting_connect)
    return calls


def test_response_is_unchanged_by_connection_reuse(client, db, monkeypatch):
    """The payload must be byte-identical to what the per-helper-connection
    version produced.

    The old behaviour is reproduced by wrapping each helper so it ignores the
    connection it is handed and opens its own — which is what the optional
    `conn` parameter makes possible to express.
    """
    after = client.get("/api/fuel-log").get_json()

    originals = {name: getattr(fuel_module, name) for name in (
        "_compute_fuel_entry", "_enrich_fuel_entry",
        "_compute_baseline", "_apply_anomaly_flag")}

    def ignoring(fn):
        def wrapper(*args, **kwargs):
            kwargs.pop("conn", None)
            # Every one of these takes `conn` as its trailing positional.
            return fn(*args[:fn.__code__.co_argcount - 1], **kwargs)
        return wrapper

    for name, fn in originals.items():
        monkeypatch.setattr(fuel_module, name, ignoring(fn))

    before = client.get("/api/fuel-log").get_json()

    assert json.dumps(before, sort_keys=True) == json.dumps(after, sort_keys=True)


def test_list_opens_a_constant_number_of_connections(client, db, count_connections):
    """O(1), not O(rows). The exact number is not the point and would make
    this a change-detector — the point is that it does not scale with N."""
    resp = client.get("/api/fuel-log")
    assert resp.status_code == 200
    assert len(resp.get_json()["data"]) == 40

    assert len(count_connections) <= 3, (
        f"{len(count_connections)} connections opened for 40 rows — the "
        "helpers are opening their own again"
    )


def test_export_opens_a_constant_number_of_connections(client, db, count_connections):
    resp = client.get("/api/fuel-log/export")
    assert resp.status_code == 200
    assert len(count_connections) <= 3, (
        f"{len(count_connections)} connections opened for the CSV export"
    )


def test_helpers_still_work_with_no_connection_passed(db):
    """The `conn` parameter is optional precisely so the create/update handlers
    keep working unchanged. That path has to stay alive."""
    row = {"id": 3, "license_plate": "50E-18463", "log_date": "2026-07-03",
           "log_time": "08:00", "gas_store": "Store", "old_km": 1800,
           "new_km": 2200, "liters": 47, "driver_name": "Driver",
           "unit_price": 22000, "notes": "", "vehicle_id": 1, "is_full_tank": 1}

    entry = fuel_module._compute_fuel_entry(dict(row))
    entry = fuel_module._enrich_fuel_entry(entry)
    baseline = fuel_module._compute_baseline("50E-18463", 3)
    entry = fuel_module._apply_anomaly_flag(entry, baseline)

    assert entry["vehicle_type"] == "5 Tons"
    assert entry["baseline"] == round(baseline, 2)
    assert "l_per_100km" in entry


def test_a_manual_profile_still_overrides_the_computed_baseline(client, db):
    """`_get_normal_l_per_100km` is reached twice per entry through two
    different helpers; threading a connection through both must not change
    which value wins."""
    data = client.get("/api/fuel-log?license_plate=51C-09999").get_json()["data"]
    assert data
    assert all(e["baseline"] == 11.5 for e in data)
    assert all(e["anomaly_multiplier"] == 1.4 for e in data)


def test_filters_are_unaffected(client, db):
    all_rows = client.get("/api/fuel-log").get_json()["data"]
    one_plate = client.get("/api/fuel-log?license_plate=50E-18463").get_json()["data"]
    by_month = client.get("/api/fuel-log?month=2026-07").get_json()["data"]

    assert len(all_rows) == 40
    assert len(one_plate) == 20
    assert all(e["license_plate"] == "50E-18463" for e in one_plate)
    assert len(by_month) == 40
