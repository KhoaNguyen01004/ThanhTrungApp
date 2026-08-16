"""Route-layer tests for the Google Sheet import endpoints.

Why a route suite as well as tests/test_sheet_import.py
------------------------------------------------------
The parser suite proves the extraction is right. It is structurally blind to
everything these endpoints add on top of it: the tomorrow default, which sheet
failure maps to which HTTP status, the destructive-replace refusal, the
rollback when a plate does not resolve, and whether the driver name actually
reaches the database. Every one of those lives inside a request handler, which
is exactly where this codebase's Critical audit findings have historically
lived (see the header of tests/test_delivery_routes.py).

The sheet itself is never contacted. ``sheet_import_service.fetch_tab`` is
patched with a fixture, so these tests are as offline as the parser's.
"""
import json
import os
import sqlite3
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Same boot-order requirement as tests/test_delivery_routes.py: app/config.py
# reads DB_PATH at import time and app/__init__.py runs init_db() against it.
_BOOT_FD, _BOOT_DB = tempfile.mkstemp(suffix="-boot.db")
os.close(_BOOT_FD)
os.environ["DB_PATH"] = _BOOT_DB

from app import create_app                                       # noqa: E402
from app.database.migrations import add_vehicle_envelope_columns  # noqa: E402
from services.delivery import plan_service                       # noqa: E402
from services.delivery import sheet_import_service as sis        # noqa: E402
from services.delivery.database import init_delivery_tables      # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "huwei_plan_th08.json"

# The fixture's plan day. The endpoints default to *tomorrow*, so the clock is
# pinned rather than the fixture being regenerated daily.
SHEET_DAY = date(2026, 8, 10)

# The three plates in the fixture's 10-Aug rows. Written as the sheet writes
# them; the fleet rows below deliberately use the canonical form, and
# `50E-19793` deliberately disagrees with the sheet's `50H-197.93` on the
# prefix — that is the real mismatch found in the live data, and the operator
# chose serial-only matching for it.
FLEET = [
    ("50H-93963", "Box Truck"),
    ("50E-19793", "Box Truck"),
    ("50H-79107", "Box Truck"),
]


@pytest.fixture(scope="module")
def payload():
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def app():
    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture
def db(app):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_delivery_tables(path)

    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE vehicles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plate_number TEXT NOT NULL UNIQUE,
            vehicle_type TEXT NOT NULL DEFAULT '',
            current_driver TEXT NOT NULL DEFAULT '',
            container_config_id INTEGER DEFAULT NULL
        )
    """)
    add_vehicle_envelope_columns(conn)
    conn.executemany(
        "INSERT INTO vehicles (plate_number, vehicle_type) VALUES (?, ?)", FLEET)
    conn.commit()
    conn.close()

    app.config["DB_PATH"] = path
    yield path
    os.unlink(path)


@pytest.fixture
def client(app, db):
    with app.test_client() as c:
        yield c


@pytest.fixture
def sheet(payload):
    """Patch the network fetch with the fixture, for any tab asked for."""
    with patch.object(sis, "fetch_tab", side_effect=lambda tab, **kw: payload) as m:
        yield m


@pytest.fixture
def broken_sheet(payload):
    def _fetch(tab, **kw):
        raise sis.SheetFetchError("Could not reach the Google Sheet: timeout")
    with patch.object(sis, "fetch_tab", side_effect=_fetch):
        yield


def _commit(client, day=SHEET_DAY, **extra):
    body = {"date": day.isoformat() if hasattr(day, "isoformat") else day}
    body.update(extra)
    return client.post("/api/plans/import/sheet/commit", json=body)


def _preview(client, day=SHEET_DAY):
    return client.get("/api/plans/import/sheet/preview",
                      query_string={"date": day.isoformat()})


def _start_a_stop(db_path, plan_id):
    """Mark one stop of a plan as arrived — the state a replace must not eat."""
    conn = sqlite3.connect(db_path)
    conn.execute("""
        UPDATE stop_executions SET status = 'arrived'
         WHERE stop_id IN (
            SELECT s.id FROM delivery_plan_stops s
            JOIN vehicle_assignments va ON va.id = s.vehicle_assignment_id
            WHERE va.plan_id = ? LIMIT 1)
    """, (plan_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------
class TestPreview:

    def test_returns_the_day_grouped_by_truck(self, client, sheet):
        r = _preview(client)
        assert r.status_code == 200
        body = r.get_json()
        assert body["date"] == "2026-08-10"
        assert body["tab_name"] == "TH08"
        assert body["preview"]["total_assignments"] == 3
        assert body["preview"]["total_rows"] == 9

    def test_every_plate_resolves_despite_the_prefix_mismatch(self, client, sheet):
        body = _preview(client).get_json()
        assert body["preview"]["unknown_vehicles"] == []
        resolved = {a["vehicle_identifier"]: a["resolved_plate"]
                    for a in body["preview"]["assignments"]}
        assert resolved["50H-197.93"] == "50E-19793"

    def test_warnings_are_returned_for_review(self, client, sheet):
        body = _preview(client).get_json()
        fields = {w["field"] for w in body["warnings"]}
        assert {"coordinates", "station_code", "sequence", "address"} <= fields

    def test_defaults_to_tomorrow(self, client, sheet):
        """No ?date= means the next dispatch day, which is the whole point."""
        with patch("services.delivery.routes.date") as fake:
            fake.today.return_value = SHEET_DAY - timedelta(days=1)
            r = client.get("/api/plans/import/sheet/preview")
        assert r.get_json()["date"] == SHEET_DAY.isoformat()

    def test_a_bad_date_is_rejected_before_any_fetch(self, client, sheet):
        r = client.get("/api/plans/import/sheet/preview",
                       query_string={"date": "10-Aug-2026"})
        assert r.status_code == 400
        assert "YYYY-MM-DD" in r.get_json()["error"]
        sheet.assert_not_called()

    def test_preview_writes_nothing(self, client, sheet, db):
        _preview(client)
        assert plan_service.list_plans(db) == []

    def test_reports_an_existing_plan_for_the_date(self, client, sheet, db):
        plan_service.create_plan(db, "SINO_10_08_2026", SHEET_DAY.isoformat())
        body = _preview(client).get_json()
        assert len(body["existing_plans"]) == 1
        assert body["replace_blocked"] is False

    def test_flags_a_started_plan_before_the_dispatcher_commits(
            self, client, sheet, db):
        _commit(client)
        plan_id = plan_service.list_plans(db)[0]["id"]
        _start_a_stop(db, plan_id)
        body = _preview(client).get_json()
        assert body["replace_blocked"] is True
        assert body["existing_plans"][0]["active_executions"] == 1


# ---------------------------------------------------------------------------
# Sheet-side failures
# ---------------------------------------------------------------------------
class TestSheetFailures:

    def test_unreachable_sheet_is_502_not_500(self, client, broken_sheet):
        r = _preview(client)
        assert r.status_code == 502
        assert r.get_json()["reason"] == "fetch_failed"

    def test_a_date_with_no_rows_is_404(self, client, sheet):
        r = _preview(client, day=date(2026, 8, 31))
        assert r.status_code == 404
        assert r.get_json()["reason"] == "date_not_found"

    def test_a_changed_layout_is_its_own_reason(self, client, payload):
        """Must not be reported as an empty day.

        A layout change means the importer is reading the wrong columns; that
        has to be distinguishable from "the manager hasn't filled it in yet",
        because the two demand opposite responses.
        """
        broken = json.loads(json.dumps(payload))
        broken["table"]["cols"][11]["label"] = "Ghi chú thêm"
        with patch.object(sis, "fetch_tab", side_effect=lambda tab, **kw: broken):
            r = _preview(client)
        assert r.status_code == 502
        assert r.get_json()["reason"] == "layout_changed"

    def test_a_sheet_failure_leaves_no_partial_plan(self, client, broken_sheet, db):
        assert _commit(client).status_code == 502
        assert plan_service.list_plans(db) == []


# ---------------------------------------------------------------------------
# Commit
# ---------------------------------------------------------------------------
class TestCommit:

    def test_creates_plan_assignments_and_stops(self, client, sheet, db):
        r = _commit(client)
        assert r.status_code == 201
        body = r.get_json()
        assert body["assignments_created"] == 3
        assert body["stops_created"] == 9
        assert body["tab_name"] == "TH08"

        plan = plan_service.get_plan(db, body["plan_id"])
        assert plan["plan_date"] == "2026-08-10"
        assert plan["status"] == "confirmed"
        assert len(plan["assignments"]) == 3

    def test_plan_name_follows_the_operators_convention(self, client, sheet, db):
        plan = plan_service.get_plan(db, _commit(client).get_json()["plan_id"])
        assert plan["plan_name"] == "SINO_10_08_2026"

    def test_repaired_coordinates_reach_the_database(self, client, sheet, db):
        """9.585.868 / 1.059.744 in the sheet must land as 9.585868 / 105.9744."""
        plan = plan_service.get_plan(db, _commit(client).get_json()["plan_id"])
        stops = [s for a in plan["assignments"] for s in a["stops"]]
        stst28 = next(s for s in stops if s["station_code"] == "STST28")
        assert stst28["lat"] == pytest.approx(9.585868)
        assert stst28["lng"] == pytest.approx(105.9744)

    def test_a_stop_with_unusable_coordinates_is_stored_without_them(
            self, client, sheet, db):
        plan = plan_service.get_plan(db, _commit(client).get_json()["plan_id"])
        stops = [s for a in plan["assignments"] for s in a["stops"]]
        agct26 = next(s for s in stops if s["station_code"] == "AGCT26")
        assert agct26["lat"] is None and agct26["lng"] is None
        # …and it is still a stop, in sequence, per the operator's decision.
        assert agct26["planned_sequence"] == 2

    def test_non_huawei_stops_are_kept(self, client, sheet, db):
        plan = plan_service.get_plan(db, _commit(client).get_json()["plan_id"])
        codes = [s["station_code"] for a in plan["assignments"] for s in a["stops"]]
        assert "Non HW Delivery-DU" in codes

    def test_driver_name_is_stored_as_an_override_not_a_drivers_row(
            self, client, sheet, db):
        plan = plan_service.get_plan(db, _commit(client).get_json()["plan_id"])
        names = {a["driver_name"] for a in plan["assignments"]}
        assert {"NGÔ HỮU QUÍ", "NGUYỄN TUẤN TÚ", "TRẦN HOÀNG QUÂN"} == names
        assert all(a["driver_id"] is None for a in plan["assignments"])
        assert plan_service.list_drivers(db) == []

    def test_warnings_come_back_with_the_commit_too(self, client, sheet):
        assert _commit(client).get_json()["warnings"]

    def test_stops_are_executable_immediately(self, client, sheet, db):
        """Every stop needs a 'planned' stop_execution or dispatch can't act."""
        plan = plan_service.get_plan(db, _commit(client).get_json()["plan_id"])
        stops = [s for a in plan["assignments"] for s in a["stops"]]
        assert len(stops) == 9
        assert all(s["execution_status"] == "planned" for s in stops)

    def test_an_unknown_plate_aborts_and_leaves_no_empty_plan(
            self, client, sheet, db):
        """The rollback path: confirm_import writes nothing, so neither may we.

        Without the rollback the dispatcher would be left with the previous
        plan deleted and an empty shell in its place.
        """
        conn = sqlite3.connect(db)
        conn.execute("DELETE FROM vehicles WHERE plate_number = '50H-79107'")
        conn.commit()
        conn.close()

        r = _commit(client)
        assert r.status_code == 409
        assert r.get_json()["reason"] == "unknown_vehicles"
        assert "50H-791.07" in r.get_json()["unknown_vehicles"]
        assert plan_service.list_plans(db) == []


# ---------------------------------------------------------------------------
# The destructive-replace safeguard
# ---------------------------------------------------------------------------
class TestReplaceSafeguard:

    def test_re_running_replaces_a_plan_nobody_has_started(
            self, client, sheet, db):
        first = _commit(client).get_json()["plan_id"]
        second = _commit(client)
        assert second.status_code == 201
        assert second.get_json()["replaced_plan_ids"] == [first]

        plans = plan_service.list_plans(db)
        assert len(plans) == 1
        assert plans[0]["id"] == second.get_json()["plan_id"]

    def test_refuses_when_a_driver_has_started_a_stop(self, client, sheet, db):
        plan_id = _commit(client).get_json()["plan_id"]
        _start_a_stop(db, plan_id)

        r = _commit(client)
        assert r.status_code == 409
        assert r.get_json()["reason"] == "in_progress"
        # Nothing was touched.
        assert [p["id"] for p in plan_service.list_plans(db)] == [plan_id]

    def test_the_refusal_says_how_much_progress_is_at_stake(
            self, client, sheet, db):
        _start_a_stop(db, _commit(client).get_json()["plan_id"])
        error = _commit(client).get_json()["error"]
        assert "1 stop(s)" in error
        assert "override_in_progress" in error

    def test_the_explicit_override_goes_through(self, client, sheet, db):
        first = _commit(client).get_json()["plan_id"]
        _start_a_stop(db, first)

        r = _commit(client, override_in_progress=True)
        assert r.status_code == 201
        assert r.get_json()["replaced_plan_ids"] == [first]
        assert plan_service.get_plan(db, first) is None

    def test_a_completed_stop_also_blocks(self, client, sheet, db):
        """'arrived' is not the only state worth protecting."""
        plan_id = _commit(client).get_json()["plan_id"]
        conn = sqlite3.connect(db)
        conn.execute("""
            UPDATE stop_executions SET status = 'completed'
             WHERE stop_id IN (SELECT s.id FROM delivery_plan_stops s
                JOIN vehicle_assignments va ON va.id = s.vehicle_assignment_id
                WHERE va.plan_id = ? LIMIT 1)
        """, (plan_id,))
        conn.commit()
        conn.close()
        assert _commit(client).status_code == 409
