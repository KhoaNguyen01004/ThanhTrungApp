"""Tests for the route refresher: what it still writes, and what it must not.

Why this file exists
--------------------
``app/routes/trips.py`` had no tests. The 2026-08-06 audit found that its
per-trip loop opened an explicit ``conn.execute('BEGIN')`` inside a ``for``,
which can never work:

  * Python's sqlite3 already opens a transaction implicitly before the
    driver-name ``UPDATE`` that precedes it, so the explicit BEGIN raised
    ``cannot start a transaction within a transaction``; and
  * on the normal path neither commit branch ran, so the transaction stayed
    open and the *next* iteration's BEGIN raised the same error.

The per-trip ``except`` printed and moved on, so the symptom was not an error
anybody saw. That is the worst shape of bug to have no test for, hence these.

What changed on 2026-08-10
--------------------------
The loop used to advance ``vehicle_trips.phase`` whenever GPS put a truck
inside its target's geofence. **That was deleted at the operator's request** —
phase is a dispatcher decision, and a refresh that moved it on its own meant
the board disagreed with the person responsible for it.

So the five tests that asserted auto-advance are gone, replaced by
``TestPhaseIsNeverWritten``, which asserts the opposite and is the regression
guard for the whole change. The transaction and per-trip-isolation tests are
kept: their subject is the loop's error handling, which still exists.

``TestLazyRouteRefresh`` covers the other half of that change — ``/api/route-data``
rebuilding an empty cache on demand, because under Gunicorn nothing else fills
it and the fleet map's Phase line was resetting to "N/A" on every page load.
"""
import json
import os
import sqlite3
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_BOOT_FD, _BOOT_DB = tempfile.mkstemp(suffix="-trips-boot.db")
os.close(_BOOT_FD)
os.environ["DB_PATH"] = _BOOT_DB

from app import config, state                      # noqa: E402
from app.database import init_db                   # noqa: E402
from app.routes import trips as trips_module       # noqa: E402


# A square around (10.80, 106.60), ~0.02 degrees a side. The shape is copied
# from a real entry in manual_locations.json — a "polygons" list of [lat, lng]
# pairs — rather than invented. A fixture in a format production never sends
# asserts a contract that does not exist, which is exactly how the delivery
# suite came to pass against code that could not work (audit T-01/T-02).
#
# Still here after the geofence removal, and deliberately: INSIDE is now the
# position that must *not* cause anything to happen, so the tests need a fence
# that a real is_point_in_location() would have matched.
DEPOT_POLYGON = {
    "polygons": [[
        [10.79, 106.59],
        [10.81, 106.59],
        [10.81, 106.61],
        [10.79, 106.61],
    ]],
    "type": "multi_polygon",
}
INSIDE = (10.80, 106.60)
OUTSIDE = (10.50, 106.20)


@pytest.fixture
def db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(path)
    monkeypatch.setattr(config, "DB_PATH", path)
    yield path
    os.unlink(path)


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch):
    """`state` is process-global and the refresher writes the route cache."""
    monkeypatch.setattr(state, "known_locations", {"Depot": DEPOT_POLYGON})
    monkeypatch.setattr(state, "route_data_cache", {})
    monkeypatch.setattr(state, "last_manual_update", 0)
    # Without these two the lazy-refresh tests leak into each other: the first
    # one to run stamps the timestamps and every later one sees a fresh cache.
    monkeypatch.setattr(state, "route_cache_refreshed_at", 0.0)
    monkeypatch.setattr(state, "route_refresh_attempted_at", 0.0)
    yield


@pytest.fixture(autouse=True)
def no_network():
    """Never let a test reach OpenRouteService.

    `do_refresh_route_data` calls get_route_coords once per trip; the real one
    falls back to a straight line on failure, but only after a request attempt.
    """
    with patch.object(trips_module, "get_route_coords", return_value={
        "coordinates": [[106.6, 10.8], [106.7, 10.9]],
        "distance": 12.3,
        "duration": 900,
        "status": "ok",
    }):
        yield


def _add_trip(db, vehicle_id, *, status="active", phase=1, driver_name="Old Driver",
              dest_name="Depot", dest=INSIDE, queue_order=0, waypoints=None):
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO vehicle_trips (vehicle_id, vehicle_name, destination_lat, "
        "destination_lng, destination_name, status, queue_order, phase, "
        "driver_name, waypoints) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (str(vehicle_id), f"Truck {vehicle_id}", dest[0], dest[1], dest_name,
         status, queue_order, str(phase), driver_name,
         json.dumps(waypoints) if waypoints else None),
    )
    trip_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return trip_id


def _raw_ttas(vehicle_id, lat, lng, driver="New Driver"):
    """A raw TTAS DevList item, the shape fetch_vehicle_data returns."""
    return {
        "id": str(vehicle_id),
        "devimei": f"IMEI-{vehicle_id}",
        "biensoxe": f"50E-1846{vehicle_id}",
        "latitude": str(lat),
        "longitude": str(lng),
        "speed": "Chạy 42km/h",
        "ad3": "Nổ",
        "trktime": "06/08/2026 09:00:00",
        "driver": driver,
    }


def _with_positions(*items):
    return patch.object(trips_module, "fetch_vehicle_data",
                        return_value=(list(items), "live", None))


def _trip(db, trip_id):
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        return dict(conn.execute(
            "SELECT * FROM vehicle_trips WHERE id = ?", (trip_id,)).fetchone())
    finally:
        conn.close()


# ── Inducing a per-trip failure ───────────────────────────────────────
#
# Before 2026-08-10 a trip could be made to fail mid-iteration just by giving
# it a waypoint with no 'lat' — the geofence block would raise on the lookup.
# With that block gone the loop body is one parameterized UPDATE, which cannot
# be made to fail through its inputs. So the failure is induced at the driver
# instead: a proxy connection that raises on the driver-name UPDATE for one
# chosen trip. sqlite3.Cursor is a C type and cannot be monkeypatched, hence
# the wrapper rather than a patch on the cursor class.

class _FlakyCursor:
    def __init__(self, inner, fail_when):
        self._inner = inner
        self._fail_when = fail_when

    def execute(self, sql, params=()):
        if self._fail_when(sql, params):
            raise sqlite3.OperationalError("induced failure")
        return self._inner.execute(sql, params)

    def __getattr__(self, name):
        return getattr(self._inner, name)


class _FlakyConnection:
    def __init__(self, inner, fail_when):
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "_fail_when", fail_when)

    def cursor(self):
        return _FlakyCursor(self._inner.cursor(), self._fail_when)

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def __setattr__(self, name, value):
        # `conn.row_factory = sqlite3.Row` has to reach the real connection,
        # or every `dict(row)` in the code under test fails.
        setattr(self._inner, name, value)


@contextmanager
def _driver_update_fails_for(trip_id):
    real_connect = sqlite3.connect

    def fail_when(sql, params):
        return "SET driver_name" in sql and params and str(params[1]) == str(trip_id)

    def fake_connect(*args, **kwargs):
        return _FlakyConnection(real_connect(*args, **kwargs), fail_when)

    with patch.object(trips_module.sqlite3, "connect", side_effect=fake_connect):
        yield


class TestRefreshLoop:

    def test_all_active_trips_are_processed(self, db, capsys):
        """Three trips, all with a changed driver name.

        Against the pre-2026-08-06 code every one of these raised
        "cannot start a transaction within a transaction" and was swallowed by
        the per-trip handler. The driver-name write is the observable proof
        the iteration actually ran to its commit.
        """
        ids = [_add_trip(db, v) for v in (1, 2, 3)]

        with _with_positions(*[_raw_ttas(v, *OUTSIDE) for v in (1, 2, 3)]):
            assert trips_module.do_refresh_route_data() is True

        assert "cannot start a transaction" not in capsys.readouterr().out
        for trip_id in ids:
            assert _trip(db, trip_id)["driver_name"] == "New Driver"

    def test_no_transaction_is_left_open(self, db):
        """The leftover open transaction is what held a RESERVED lock across
        this function's ORS calls. A second connection writing afterwards is
        the direct test of that."""
        _add_trip(db, 1)

        with _with_positions(_raw_ttas(1, *OUTSIDE)):
            trips_module.do_refresh_route_data()

        conn = sqlite3.connect(db, timeout=1.0)
        try:
            conn.execute("UPDATE vehicle_trips SET customer_name = 'x'")
            conn.commit()
        finally:
            conn.close()

    def test_one_failing_trip_does_not_stop_the_others(self, db):
        """The per-trip handler stays deliberately broad: a trip whose write
        raises must not cost the rest of the loop their work."""
        broken = _add_trip(db, 1)
        healthy = _add_trip(db, 2)

        with _driver_update_fails_for(broken):
            with _with_positions(_raw_ttas(1, *OUTSIDE), _raw_ttas(2, *OUTSIDE)):
                assert trips_module.do_refresh_route_data() is True

        assert _trip(db, broken)["driver_name"] == "Old Driver"     # rolled back
        assert _trip(db, healthy)["driver_name"] == "New Driver"    # committed

    def test_a_rolled_back_trip_keeps_its_previous_driver_name(self, db):
        """The driver-name UPDATE sits inside the transaction, so it rolls back
        with the rest of the iteration rather than leaking through."""
        broken = _add_trip(db, 1, driver_name="Old Driver")

        with _driver_update_fails_for(broken):
            with _with_positions(_raw_ttas(1, *INSIDE, driver="New Driver")):
                trips_module.do_refresh_route_data()

        assert _trip(db, broken)["driver_name"] == "Old Driver"


class TestPhaseIsNeverWritten:
    """The 2026-08-10 change, from the operator's side.

    Every case here puts a truck squarely inside its target's geofence — the
    exact condition that used to advance or complete a trip — and asserts that
    nothing about the trip's position in the plan moved. Reverting the deletion
    in do_refresh_route_data() must fail all four.
    """

    def test_arrival_does_not_complete_a_single_stop_trip(self, db):
        trip_id = _add_trip(db, 1, dest_name="Depot", dest=INSIDE)

        with _with_positions(_raw_ttas(1, *INSIDE)):
            trips_module.do_refresh_route_data()

        row = _trip(db, trip_id)
        assert row["status"] == "active"
        assert int(row["phase"]) == 1

    def test_arrival_does_not_advance_a_multi_stop_trip(self, db):
        trip_id = _add_trip(
            db, 1, dest_name="Far Place", dest=OUTSIDE,
            waypoints=[{"name": "Depot", "lat": INSIDE[0], "lng": INSIDE[1]}],
        )

        with _with_positions(_raw_ttas(1, *INSIDE)):
            trips_module.do_refresh_route_data()

        row = _trip(db, trip_id)
        assert row["status"] == "active"
        assert int(row["phase"]) == 1

    def test_arrival_does_not_activate_the_queued_trip(self, db):
        arriving = _add_trip(db, 1, queue_order=0)
        queued = _add_trip(db, 1, status="queued", queue_order=1)

        with _with_positions(_raw_ttas(1, *INSIDE)):
            trips_module.do_refresh_route_data()

        assert _trip(db, arriving)["status"] == "active"
        assert _trip(db, queued)["status"] == "queued"

    def test_repeated_refreshes_leave_phase_alone(self, db):
        """A dispatcher advances to phase 2, then the page is refreshed a few
        times while the truck sits inside phase 1's fence. Phase 2 stands."""
        # Phase 2's own target is the fenced one, so the pre-2026-08-10 code
        # completes this trip on the first refresh — without that the test
        # passes against the deleted behaviour too and guards nothing.
        trip_id = _add_trip(
            db, 1, phase=2, dest_name="Depot", dest=INSIDE,
            waypoints=[{"name": "Far Place", "lat": OUTSIDE[0], "lng": OUTSIDE[1]}],
        )

        with _with_positions(_raw_ttas(1, *INSIDE)):
            for _ in range(3):
                trips_module.do_refresh_route_data()

        assert int(_trip(db, trip_id)["phase"]) == 2

    def test_no_geofence_event_is_recorded(self, db):
        """The arrival log went with the advance. The table stays — it holds
        real history — but nothing writes to it any more."""
        _add_trip(db, 1, dest_name="Depot", dest=INSIDE)

        with _with_positions(_raw_ttas(1, *INSIDE)):
            trips_module.do_refresh_route_data()

        conn = sqlite3.connect(db)
        try:
            count = conn.execute("SELECT COUNT(*) FROM geofence_events").fetchone()[0]
        finally:
            conn.close()
        assert count == 0


class TestLazyRouteRefresh:
    """/api/route-data rebuilding the cache on demand.

    do_refresh_route_data is stubbed here on purpose: what is under test is the
    staleness and single-flight logic around it, not the rebuild itself, which
    TestRefreshLoop covers against a real database.
    """

    @pytest.fixture
    def client(self, db):
        from app import create_app
        app = create_app()
        app.config["TESTING"] = True
        return app.test_client()

    def test_empty_cache_is_rebuilt_on_request(self, client):
        with patch.object(trips_module, "do_refresh_route_data") as refresh:
            resp = client.get("/api/route-data")

        assert resp.status_code == 200
        assert refresh.call_count == 1

    def test_a_fresh_cache_is_not_rebuilt(self, client, monkeypatch):
        monkeypatch.setattr(state, "route_data_cache", {"1-1": {"trip_id": 1}})
        monkeypatch.setattr(state, "route_cache_refreshed_at", time.time())

        with patch.object(trips_module, "do_refresh_route_data") as refresh:
            resp = client.get("/api/route-data")

        assert resp.status_code == 200
        assert refresh.call_count == 0
        assert resp.get_json() == [{"trip_id": 1}]

    def test_a_stale_cache_is_rebuilt(self, client, monkeypatch):
        monkeypatch.setattr(state, "route_data_cache", {"1-1": {"trip_id": 1}})
        monkeypatch.setattr(state, "route_cache_refreshed_at",
                            time.time() - config.ROUTE_REFRESH_INTERVAL - 1)

        with patch.object(trips_module, "do_refresh_route_data") as refresh:
            client.get("/api/route-data")

        assert refresh.call_count == 1

    def test_a_failing_refresh_still_answers_200(self, client):
        """A TTAS outage must not blank a page that renders fine without us."""
        with patch.object(trips_module, "do_refresh_route_data",
                          side_effect=RuntimeError("TTAS down")):
            resp = client.get("/api/route-data")

        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_a_failing_refresh_is_not_retried_on_every_request(self, client):
        """An empty cache reads as stale forever. Without the attempt stamp,
        every request during an outage starts its own doomed refresh and blocks
        on it — the cache never fills, so the staleness check never says no."""
        with patch.object(trips_module, "do_refresh_route_data",
                          side_effect=RuntimeError("TTAS down")) as refresh:
            for _ in range(5):
                client.get("/api/route-data")

        assert refresh.call_count == 1
