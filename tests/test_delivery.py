import io
import logging
import os
import sys
import json
import sqlite3
import tempfile
import pytest
import requests
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.delivery import plan_service
from services.delivery import execution_service
from services.delivery import eta_service
from services.delivery import image_service
from services.delivery import tracking_service
from services import vehicle_identity
from services.delivery.database import init_delivery_tables
from app.database.migrations import add_vehicle_envelope_columns
from app.db import DatabaseManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_upload_root(tmp_path, monkeypatch):
    """Keep uploaded test images out of the repository.

    image_service derives UPLOAD_ROOT from its own file location, so the image
    tests were writing real .jpg files into the project's DeliveryPlans/ folder
    and leaving them behind — dozens had accumulated across previous runs. It
    also made test_delete_image_removes_file depend on the checkout being
    writable, which it isn't on every machine.
    """
    from services.delivery import image_service

    root = tmp_path / "DeliveryPlans"
    root.mkdir()
    monkeypatch.setattr(image_service, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(image_service, "UPLOAD_ROOT", root)
    yield root


@pytest.fixture
def db_path():
    """Create a fresh SQLite database with all delivery + vehicles tables."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    # Init delivery tables first
    init_delivery_tables(path)

    # Also create vehicles table (normally created by app.py init_db)
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS vehicles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plate_number TEXT NOT NULL UNIQUE,
            vehicle_type TEXT DEFAULT '',
            current_driver TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Run the real migration rather than restating its column list here — a
    # duplicated list drifts silently until a query on the new columns fails.
    add_vehicle_envelope_columns(conn)
    conn.execute("INSERT INTO vehicles (plate_number, current_driver) VALUES ('TEST-01', 'Test Driver')")
    conn.commit()
    conn.close()

    yield path

    os.unlink(path)


def _create_plan(db_path, name="Test Plan", plan_date=None):
    """Defaults to *today*, because a plan under execution is today's work.

    This used to be a hard-coded 2026-07-26, which was fine while nothing
    depended on the date. Correctability is now decided per plan-day
    (execution_service.can_revert), so a frozen date would have silently
    meant "closed record" and every revert test would have been asserting
    the refusal path.
    """
    return plan_service.create_plan(
        db_path, name, plan_date or date.today().isoformat()
    )


def _create_vehicle_assignment(db_path, plan_id, vehicle_id=1):
    return plan_service.create_assignment(db_path, plan_id, vehicle_id, sequence=1)


def _create_stop(db_path, assignment_id, seq, station_name="Stop", lat=10.8, lng=106.6):
    return plan_service.create_stop(
        db_path, assignment_id, seq,
        station_code=f"S{seq:03d}", station_name=station_name,
        address=f"{seq} Test St", lat=lat, lng=lng,
        manager_name="Mr T", manager_phone="0900000000",
        product_description="Test Product",
    )


def _give_proof(db_path, stop_id, categories=None):
    """Attach the photos a completion requires, without touching the disk.

    The gate reads delivery_stop_images, not the filesystem, so rows are
    enough — and a test that had to write real .jpg files to advance a stop
    would be slower and would leave litter behind (the reason
    isolated_upload_root exists at all).
    """
    conn = sqlite3.connect(db_path)
    for cat in (categories or execution_service.PROOF_CATEGORIES):
        conn.execute(
            "INSERT INTO delivery_stop_images (stop_id, category, filename, relative_path) "
            "VALUES (?, ?, ?, ?)",
            (stop_id, cat, f"{cat}.jpg", f"DeliveryPlans/{cat}.jpg"),
        )
    conn.commit()
    conn.close()


def _clear_status_events(db_path, stop_id):
    """Erase a stop's phase log, standing in for every stop last touched
    before the log existed — nothing was backfilled, so those are real."""
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM stop_status_events WHERE stop_id = ?", (stop_id,))
    conn.commit()
    conn.close()


def _backdate(db_path, stop_id, minutes):
    """Push a stop's action timestamps into the past.

    Used to prove correctability is *not* governed by elapsed time any more:
    the rule is the plan's date, so an action hours old on today's plan must
    still be correctable.
    """
    then = (datetime.now() - timedelta(minutes=minutes)).isoformat()
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE stop_executions SET "
        "  actual_arrival_at = CASE WHEN actual_arrival_at IS NULL THEN NULL ELSE ? END, "
        "  completed_at      = CASE WHEN completed_at      IS NULL THEN NULL ELSE ? END "
        "WHERE stop_id = ?",
        (then, then, stop_id),
    )
    conn.commit()
    conn.close()


# ===========================================================================
# 1. ETA Calculation Tests
# ===========================================================================

class TestEtaService:
    """Tests for eta_service.py: Haversine fallback and ORS integration."""

    def test_get_distance_meters(self):
        d = eta_service.get_distance_meters(10.8, 106.6, 10.9, 106.7)
        assert d > 10000  # ~15 km
        assert d < 20000

    def test_get_distance_meters_zero(self):
        d = eta_service.get_distance_meters(10.8, 106.6, 10.8, 106.6)
        assert d == 0.0

    def test_calculate_eta_no_api_key_fallback(self):
        result = eta_service.calculate_eta("", "", 10.8, 106.6, 10.9, 106.7)
        assert result["source"] == "haversine"
        assert result["distance_km"] > 10
        assert result["duration_sec"] is None

    # ORS is reached through app.services.routing.request_directions now, so
    # these patch requests.post there rather than requests.get here. The GET
    # directions endpoint cannot carry an options body at all, which is why
    # avoid_borders and the planned vehicle restrictions needed the move.
    @patch("app.services.routing.requests.post")
    def test_calculate_eta_ors_success(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.ok = True
        mock_post.return_value.json.return_value = {
            "features": [{
                "geometry": {"coordinates": [[106.6, 10.8], [106.7, 10.9]]},
                "properties": {"segments": [{"distance": 15000, "duration": 900}]}
            }]
        }
        result = eta_service.calculate_eta("fake_key", "https://api.ors/v2/directions", 10.8, 106.6, 10.9, 106.7)
        assert result["source"] == "ors"
        assert result["route_status"] == "ok"
        assert result["distance_km"] == 15.0
        assert result["duration_sec"] == 900
        # GeoJSON [lng, lat] must be converted to Leaflet [lat, lng]
        assert result["geometry"] == [[10.8, 106.6], [10.9, 106.7]]

    @patch("app.services.routing.requests.post")
    def test_calculate_eta_sends_avoid_borders(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.ok = True
        mock_post.return_value.json.return_value = {
            "features": [{
                "geometry": {"coordinates": [[106.6, 10.8], [106.7, 10.9]]},
                "properties": {"segments": [{"distance": 15000, "duration": 900}]}
            }]
        }
        eta_service.calculate_eta("fake_key", "https://api.ors/v2/directions", 10.8, 106.6, 10.9, 106.7)

        _, kwargs = mock_post.call_args
        body = kwargs["json"]
        assert body["options"]["avoid_borders"] == "all"
        # [lng, lat] pairs, in ORS order, origin first.
        assert body["coordinates"] == [[106.6, 10.8], [106.7, 10.9]]
        assert kwargs["headers"]["Authorization"] == "fake_key"

    def test_calculate_eta_no_api_key_has_no_geometry(self):
        result = eta_service.calculate_eta("", "", 10.8, 106.6, 10.9, 106.7)
        assert result["geometry"] is None
        assert result["route_status"] == "not_configured"

    @patch("app.services.routing.requests.post")
    def test_calculate_eta_ors_failure_fallback(self, mock_post):
        mock_post.side_effect = requests.RequestException("Connection error")
        result = eta_service.calculate_eta("fake_key", "https://api.ors/v2/directions", 10.8, 106.6, 10.9, 106.7)
        assert result["source"] == "haversine_fallback"
        assert result["route_status"] == "unavailable"
        assert result["distance_km"] > 10
        assert result["duration_sec"] is None

    @patch("app.services.routing.requests.post")
    def test_calculate_eta_no_route_is_not_reported_as_a_fallback(self, mock_post):
        # ORS reports "no route" as HTTP 404 with 2009 in the body. Reading the
        # status before the body would turn a routing finding into an
        # indistinguishable network error — which is the whole point of the
        # split, since with avoid_borders on, this is how a cross-border-only
        # destination announces itself.
        mock_post.return_value.status_code = 404
        mock_post.return_value.ok = False
        mock_post.return_value.json.return_value = {
            "error": {"code": 2009, "message": "Route could not be found between locations."}
        }
        result = eta_service.calculate_eta("fake_key", "https://api.ors/v2/directions", 10.8, 106.6, 10.9, 106.7)
        assert result["route_status"] == "no_route"
        assert result["source"] == "haversine_no_route"
        assert result["duration_sec"] is None

    @patch("app.services.routing.requests.post")
    def test_calculate_eta_point_not_found_is_also_no_route(self, mock_post):
        mock_post.return_value.status_code = 404
        mock_post.return_value.ok = False
        mock_post.return_value.json.return_value = {
            "error": {"code": 2010, "message": "Point was not found."}
        }
        result = eta_service.calculate_eta("fake_key", "https://api.ors/v2/directions", 10.8, 106.6, 10.9, 106.7)
        assert result["route_status"] == "no_route"

    # ── Phase C: the degraded-route ladder ───────────────────────────
    def _ors_ok(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.ok = True
        mock_post.return_value.json.return_value = {
            "features": [{
                "geometry": {"coordinates": [[106.6, 10.8], [106.7, 10.9]]},
                "properties": {"segments": [{"distance": 15000, "duration": 900}]}
            }]
        }

    def _ors_no_route(self, mock_post):
        mock_post.return_value.status_code = 404
        mock_post.return_value.ok = False
        mock_post.return_value.json.return_value = {
            "error": {"code": 2009, "message": "Route could not be found between locations."}
        }

    OPTIONS = {"vehicle_type": "hgv",
               "profile_params": {"restrictions": {"height": 3.2, "weight": 8.5}}}

    @patch("app.services.routing.requests.post")
    def test_a_route_found_under_restrictions_is_compliant(self, mock_post):
        self._ors_ok(mock_post)
        result = eta_service.calculate_eta("k", "https://api.ors/v2/directions",
                                           10.8, 106.6, 10.9, 106.7, options=self.OPTIONS)
        assert result["restriction_status"] == "compliant"
        sent = mock_post.call_args.kwargs["json"]["options"]
        assert sent["vehicle_type"] == "hgv"
        assert sent["profile_params"]["restrictions"]["height"] == 3.2

    @patch("app.services.routing.requests.post")
    def test_a_route_with_no_restrictions_to_apply_is_unrestricted_not_compliant(self, mock_post):
        self._ors_ok(mock_post)
        result = eta_service.calculate_eta("k", "https://api.ors/v2/directions",
                                           10.8, 106.6, 10.9, 106.7, options=None)
        # "We did not check" must never read as "we checked and it passed".
        assert result["restriction_status"] == "unrestricted"

    @patch("app.services.routing.requests.post")
    def test_no_compliant_route_retries_relaxed_and_marks_it_violated(self, mock_post):
        responses = []

        def side_effect(*args, **kwargs):
            responses.append(kwargs["json"]["options"])
            resp = MagicMock()
            if len(responses) == 1:
                resp.status_code, resp.ok = 404, False
                resp.json.return_value = {"error": {"code": 2009, "message": "no route"}}
            else:
                resp.status_code, resp.ok = 200, True
                resp.json.return_value = {
                    "features": [{
                        "geometry": {"coordinates": [[106.6, 10.8], [106.7, 10.9]]},
                        "properties": {"segments": [{"distance": 21000, "duration": 1500}]}
                    }]
                }
            return resp

        mock_post.side_effect = side_effect
        result = eta_service.calculate_eta("k", "https://api.ors/v2/directions",
                                           10.8, 106.6, 10.9, 106.7, options=self.OPTIONS)

        assert result["restriction_status"] == "violated"
        assert result["route_status"] == "ok"
        assert result["geometry"] is not None      # a line to draw, in red
        assert len(responses) == 2

        # The second attempt drops the dimensions but keeps vehicle_type, and
        # avoid_borders survives both — the border rule is not part of what
        # degrades.
        assert "profile_params" not in responses[1]
        assert responses[1]["vehicle_type"] == "hgv"
        assert responses[0]["avoid_borders"] == "all"
        assert responses[1]["avoid_borders"] == "all"

    @patch("app.services.routing.requests.post")
    def test_no_route_even_relaxed_gives_up_rather_than_looping(self, mock_post):
        self._ors_no_route(mock_post)
        result = eta_service.calculate_eta("k", "https://api.ors/v2/directions",
                                           10.8, 106.6, 10.9, 106.7, options=self.OPTIONS)
        assert result["route_status"] == "no_route"
        assert result["restriction_status"] == "unknown"
        assert mock_post.call_count == 2       # tried, relaxed, stopped

    @patch("app.services.routing.requests.post")
    def test_an_unrestricted_leg_does_not_retry(self, mock_post):
        self._ors_no_route(mock_post)
        eta_service.calculate_eta("k", "https://api.ors/v2/directions",
                                  10.8, 106.6, 10.9, 106.7, options=None)
        # Nothing to relax, so a second call would be a wasted request against
        # a rate limit /api/eta is already close to.
        assert mock_post.call_count == 1

    @patch("app.services.routing.requests.post")
    def test_a_transport_failure_is_not_retried_as_a_restriction_problem(self, mock_post):
        mock_post.side_effect = requests.RequestException("connection reset")
        result = eta_service.calculate_eta("k", "https://api.ors/v2/directions",
                                           10.8, 106.6, 10.9, 106.7, options=self.OPTIONS)
        assert result["route_status"] == "unavailable"
        assert mock_post.call_count == 1

    @patch("app.services.routing.requests.post")
    def test_calculate_eta_server_error_is_unavailable_not_no_route(self, mock_post):
        mock_post.return_value.status_code = 503
        mock_post.return_value.ok = False
        mock_post.return_value.text = "Service Unavailable"
        mock_post.return_value.json.return_value = {"error": {"code": 2099, "message": "boom"}}
        result = eta_service.calculate_eta("fake_key", "https://api.ors/v2/directions", 10.8, 106.6, 10.9, 106.7)
        assert result["route_status"] == "unavailable"

    @patch("services.delivery.eta_service.calculate_eta")
    def test_calculate_etas_for_stops(self, mock_calc_eta):
        mock_calc_eta.return_value = {"source": "haversine", "distance_km": 5.0, "duration_sec": 300}
        stops = [
            {"id": 1, "lat": 10.81, "lng": 106.61},
            {"id": 2, "lat": 10.82, "lng": 106.62},
            {"id": 3, "lat": None, "lng": None},
        ]
        results = eta_service.calculate_etas_for_stops("", "", 10.8, 106.6, stops)
        assert len(results) == 3
        assert results[0]["cumulative_sec"] == 300
        assert results[1]["cumulative_sec"] == 600
        assert results[2]["cumulative_sec"] is None  # no coords
        assert results[2]["distance_km"] is None

    def test_calculate_etas_empty_list(self):
        assert eta_service.calculate_etas_for_stops("", "", 10.8, 106.6, []) == []

    @patch("services.delivery.eta_service.calculate_eta")
    def test_calculate_etas_tracks_cumulative_km_and_geometry(self, mock_calc_eta):
        mock_calc_eta.return_value = {
            "source": "ors", "distance_km": 5.0, "duration_sec": 300,
            "geometry": [[10.8, 106.6], [10.81, 106.61]],
        }
        stops = [{"id": 1, "lat": 10.81, "lng": 106.61}, {"id": 2, "lat": 10.82, "lng": 106.62}]
        results = eta_service.calculate_etas_for_stops("", "", 10.8, 106.6, stops)
        assert results[0]["cumulative_km"] == 5.0
        assert results[1]["cumulative_km"] == 10.0
        assert results[0]["geometry"] == [[10.8, 106.6], [10.81, 106.61]]

    @patch("services.delivery.eta_service.calculate_eta")
    def test_route_cache_hit_skips_recompute(self, mock_calc_eta):
        mock_calc_eta.return_value = {"source": "haversine", "distance_km": 5.0, "duration_sec": 300, "geometry": None}
        stops = [{"id": 1, "lat": 10.81, "lng": 106.61}]

        r1 = eta_service.calculate_etas_for_stops("", "", 10.8, 106.6, stops, assignment_id=90001)
        r2 = eta_service.calculate_etas_for_stops("", "", 10.8, 106.6, stops, assignment_id=90001)

        assert mock_calc_eta.call_count == 1
        assert r1 == r2

    @patch("services.delivery.eta_service.calculate_eta")
    def test_route_cache_invalidated_when_the_vehicle_specs_change(self, mock_calc_eta):
        mock_calc_eta.return_value = {"source": "ors", "distance_km": 5.0,
                                      "duration_sec": 300, "geometry": None}
        stops = [{"id": 1, "lat": 10.8, "lng": 106.6}]
        short = {"vehicle_type": "hgv",
                 "profile_params": {"restrictions": {"height": 3.0}}}
        tall = {"vehicle_type": "hgv",
                "profile_params": {"restrictions": {"height": 4.0}}}

        eta_service.calculate_etas_for_stops("k", "u", 10.0, 106.0, stops,
                                             assignment_id=1, options=short)
        eta_service.calculate_etas_for_stops("k", "u", 10.0, 106.0, stops,
                                             assignment_id=1, options=short)
        assert mock_calc_eta.call_count == 1          # identical -> cached

        # An assignment's vehicle is fixed, so without the restriction
        # fingerprint in the key this would keep serving the 3.0 m route until
        # the process restarted.
        eta_service.calculate_etas_for_stops("k", "u", 10.0, 106.0, stops,
                                             assignment_id=1, options=tall)
        assert mock_calc_eta.call_count == 2

    @patch("services.delivery.eta_service.calculate_eta")
    def test_route_cache_invalidated_by_gps_move(self, mock_calc_eta):
        mock_calc_eta.return_value = {"source": "haversine", "distance_km": 5.0, "duration_sec": 300, "geometry": None}
        stops = [{"id": 1, "lat": 10.81, "lng": 106.61}]

        eta_service.calculate_etas_for_stops("", "", 10.8, 106.6, stops, assignment_id=90002)
        eta_service.calculate_etas_for_stops("", "", 11.5, 107.3, stops, assignment_id=90002)

        assert mock_calc_eta.call_count == 2

    @patch("services.delivery.eta_service.calculate_eta")
    def test_route_cache_tolerates_tiny_gps_jitter(self, mock_calc_eta):
        mock_calc_eta.return_value = {"source": "haversine", "distance_km": 5.0, "duration_sec": 300, "geometry": None}
        stops = [{"id": 1, "lat": 10.81, "lng": 106.61}]

        eta_service.calculate_etas_for_stops("", "", 10.80000, 106.60000, stops, assignment_id=90003)
        eta_service.calculate_etas_for_stops("", "", 10.80001, 106.60001, stops, assignment_id=90003)

        assert mock_calc_eta.call_count == 1

    @patch("services.delivery.eta_service.calculate_eta")
    def test_route_cache_invalidated_by_stop_change(self, mock_calc_eta):
        mock_calc_eta.return_value = {"source": "haversine", "distance_km": 5.0, "duration_sec": 300, "geometry": None}
        stops1 = [{"id": 1, "lat": 10.81, "lng": 106.61}]
        stops2 = [{"id": 2, "lat": 10.82, "lng": 106.62}]

        eta_service.calculate_etas_for_stops("", "", 10.8, 106.6, stops1, assignment_id=90004)
        eta_service.calculate_etas_for_stops("", "", 10.8, 106.6, stops2, assignment_id=90004)

        assert mock_calc_eta.call_count == 2

    @patch("services.delivery.eta_service.calculate_eta")
    def test_route_cache_bypassed_without_assignment_id(self, mock_calc_eta):
        mock_calc_eta.return_value = {"source": "haversine", "distance_km": 5.0, "duration_sec": 300, "geometry": None}
        stops = [{"id": 1, "lat": 10.81, "lng": 106.61}]

        eta_service.calculate_etas_for_stops("", "", 10.8, 106.6, stops)
        eta_service.calculate_etas_for_stops("", "", 10.8, 106.6, stops)

        assert mock_calc_eta.call_count == 2

    def test_travelled_distance_zero_when_nothing_passed(self):
        stops = [{"id": 1, "lat": 10.81, "lng": 106.61, "planned_sequence": 1, "execution_status": "planned"}]
        assert eta_service.calculate_travelled_distance_km(stops, 10.8, 106.6) == 0.0

    def test_travelled_distance_sums_passed_stops(self):
        stops = [
            {"id": 1, "lat": 10.81, "lng": 106.61, "planned_sequence": 1, "execution_status": "completed"},
            {"id": 2, "lat": 10.82, "lng": 106.62, "planned_sequence": 2, "execution_status": "skipped"},
            {"id": 3, "lat": 10.83, "lng": 106.63, "planned_sequence": 3, "execution_status": "planned"},
        ]
        result = eta_service.calculate_travelled_distance_km(stops, 10.82, 106.62)
        assert result > 0


# ===========================================================================
# 1b. Tracking Service Tests (defensive speed parsing)
# ===========================================================================

def _raw_ttas(**overrides):
    """A raw TTAS DevList item — the actual input contract of
    normalize_gps_position(). Keys are TTAS's own, NOT normalize_vehicle()'s
    output names."""
    item = {
        "biensoxe": "50E-18463",
        "latitude": "10.8",
        "longitude": "106.6",
        "speed": "Chạy 42km/h",
        "ad3": "Nổ",
        "trktime": "2026-07-30 10:00:00",
        "driver": "Nguyen Van A",
    }
    item.update(overrides)
    return item


class TestTrackingService:
    """Tests for tracking_service.py.

    These previously fed hand-written dicts keyed on speed_status /
    vehicle_status / last_update — the OUTPUT names of normalize_vehicle(),
    not the raw TTAS input names the function actually receives. They passed
    against a function that could never work in production (audit C-02/T-02).
    They now use real raw-TTAS field names.
    """

    def test_emits_device_name_and_plate_key(self):
        # The regression that broke the entire dashboard: no device_name was
        # emitted, so no GPS position could ever be matched to a vehicle.
        result = tracking_service.normalize_gps_position(_raw_ttas())
        assert result["device_name"] == "50E-18463"
        assert result["plate_key"] == "18463"

    @pytest.mark.parametrize("plate,expected_key", [
        ("50E-18463", "18463"),
        ("50E18463", "18463"),
        ("50E 18463", "18463"),
        ("18463", "18463"),
        ("50e-18463", "18463"),
    ])
    def test_plate_key_is_stable_across_formats(self, plate, expected_key):
        result = tracking_service.normalize_gps_position(_raw_ttas(biensoxe=plate))
        assert result["plate_key"] == expected_key

    def test_reads_raw_ttas_field_names(self):
        result = tracking_service.normalize_gps_position(_raw_ttas())
        assert result["speed"] == "Chạy 42km/h"       # from "speed", not "speed_status"
        assert result["engine_status"] == "Nổ"         # from "ad3"
        assert result["last_update"] == "2026-07-30 10:00:00"  # from "trktime"
        assert result["driver_name"] == "Nguyen Van A"  # from "driver"
        assert result["vehicle_status"] == "running"    # derived from the speed phrase

    def test_coordinates_are_floats(self):
        result = tracking_service.normalize_gps_position(_raw_ttas())
        assert result["lat"] == pytest.approx(10.8)
        assert result["lng"] == pytest.approx(106.6)

    def test_missing_coordinates_become_none_not_zero(self):
        # safe_float() coerces junk to 0.0; 0,0 is the Gulf of Guinea, not a
        # vehicle position, so it must be reported as "no fix".
        result = tracking_service.normalize_gps_position(
            _raw_ttas(latitude=None, longitude=None)
        )
        assert result["lat"] is None
        assert result["lng"] is None

    def test_malformed_coordinates_do_not_raise(self):
        # A bare float() here used to raise ValueError inside a list
        # comprehension and 500 the whole dashboard request.
        result = tracking_service.normalize_gps_position(_raw_ttas(latitude="", longitude="n/a"))
        assert result["lat"] is None and result["lng"] is None

    def test_vehicle_status_stopped_engine_on_vs_off(self):
        on = tracking_service.normalize_gps_position(_raw_ttas(speed="Dừng đỗ", ad3="Nổ"))
        off = tracking_service.normalize_gps_position(_raw_ttas(speed="Dừng đỗ", ad3="Tắt"))
        assert on["vehicle_status"] == "stopped_engine_on"
        assert off["vehicle_status"] == "stopped_engine_off"

    def test_speed_parses_embedded_number(self):
        result = tracking_service.normalize_gps_position(_raw_ttas(speed="Chạy 42km/h"))
        assert result["speed_kmh"] == 42.0

    def test_gps_position_carries_the_parsed_timestamp(self):
        """The field every age computation reads. `last_update` stays raw for
        display; `last_update_iso` is the one arithmetic may touch."""
        result = tracking_service.normalize_gps_position(_raw_ttas(trktime="30/07/2026 10:00:00"))
        assert result["last_update"] == "30/07/2026 10:00:00"
        assert result["last_update_iso"] == "2026-07-30T10:00:00"

    def test_unreadable_timestamp_yields_none_not_a_guess(self):
        result = tracking_service.normalize_gps_position(_raw_ttas(trktime="sometime tuesday"))
        assert result["last_update"] == "sometime tuesday"
        assert result["last_update_iso"] is None


class TestTtasTimestampParsing:
    """TTAS writes dates day-first (`01/08/2026` is 1 August).

    Before this was parsed server-side, `trktime` reached the browser as raw
    text and `new Date()` read it **month-first**, which broke differently
    depending on the day of the month — see `parse_ttas_timestamp`. The
    dashboard reported every vehicle ~205 days stale on the 1st of a month,
    and from the 13th reported nothing at all.

    These fixtures deliberately use TTAS's real format. The pre-existing ones
    used ISO, which is why the suite never caught any of it (audit T-01/T-02
    is the same failure mode: a test asserting a contract production never
    had).
    """

    def test_day_first_is_the_convention(self):
        from app.services.ttas_client import parse_ttas_timestamp
        # 1 August, not 8 January — the exact value behind the "GPS stale
        # 4920h" reports, 4920h being precisely 8 Jan → 1 Aug.
        assert parse_ttas_timestamp("01/08/2026 10:30:00") == "2026-08-01T10:30:00"

    def test_a_day_past_the_twelfth_still_parses(self):
        """The silent case. `13/08/2026` has no month 13, so `new Date()`
        returned Invalid Date and the dashboard's isNaN guard skipped the
        staleness check entirely for two thirds of every month."""
        from app.services.ttas_client import parse_ttas_timestamp
        assert parse_ttas_timestamp("13/08/2026 10:30:00") == "2026-08-13T10:30:00"
        assert parse_ttas_timestamp("31/07/2026 09:00:00") == "2026-07-31T09:00:00"

    def test_a_day_before_the_twelfth_is_not_swapped(self):
        """`12/08/2026` read month-first as 8 December — a date in the
        *future*, giving a negative age and therefore no warning."""
        from app.services.ttas_client import parse_ttas_timestamp
        assert parse_ttas_timestamp("12/08/2026 10:30:00") == "2026-08-12T10:30:00"

    @pytest.mark.parametrize("value,expected", [
        ("01/08/2026 10:30", "2026-08-01T10:30:00"),
        ("01/08/2026", "2026-08-01T00:00:00"),
        ("2026-08-01 10:30:00", "2026-08-01T10:30:00"),
        ("2026-08-01T10:30:00", "2026-08-01T10:30:00"),
        ("  01/08/2026 10:30:00  ", "2026-08-01T10:30:00"),
    ])
    def test_accepted_shapes(self, value, expected):
        from app.services.ttas_client import parse_ttas_timestamp
        assert parse_ttas_timestamp(value) == expected

    @pytest.mark.parametrize("value", ["", None, "   ", "n/a", "32/08/2026", "01-08-2026 10:30"])
    def test_unparseable_values_return_none(self, value):
        """None means "age unknown", which the dashboard shows as its own
        state. Returning a fabricated date here would be the original bug
        with a different author."""
        from app.services.ttas_client import parse_ttas_timestamp
        assert parse_ttas_timestamp(value) is None

    def test_an_unknown_format_is_logged_once_not_per_poll(self, caplog):
        """40 vehicles on a 12s poll would write ~200 lines a minute. One line
        per distinct shape is what makes a format change noticeable rather
        than buried."""
        from app.services import ttas_client
        ttas_client._unparsed_timestamps_seen.discard("08.01.2026 10:30")
        with caplog.at_level(logging.WARNING, logger=ttas_client.__name__):
            for _ in range(5):
                ttas_client.parse_ttas_timestamp("08.01.2026 10:30")
        assert len([r for r in caplog.records if "Unrecognised TTAS timestamp" in r.message]) == 1

    def test_normalize_vehicle_keeps_the_raw_text_alongside(self):
        """static/js/map.js prints `last_update` verbatim in the fleet map
        popup, so it must keep TTAS's own format."""
        from app.services.ttas_client import normalize_vehicle
        v = normalize_vehicle({"biensoxe": "50E-18463", "trktime": "01/08/2026 10:30:00"})
        assert v["last_update"] == "01/08/2026 10:30:00"
        assert v["last_update_iso"] == "2026-08-01T10:30:00"


class TestSpeedPhraseParsing:
    """`_parse_speed_kmh` — TTAS sends no numeric speed field, only a
    Vietnamese phrase, so every km/h figure on the dashboard is an extraction
    from prose.

    These lived in TestTtasTimestampParsing until 2026-08-03, which is not
    what that class is about; they moved here when the parked-duration bug
    below was fixed.
    """

    def test_speed_parses_decimal(self):
        result = tracking_service.normalize_gps_position(_raw_ttas(speed="Chạy 37.5 km/h"))
        assert result["speed_kmh"] == 37.5

    def test_speed_none_when_missing(self):
        result = tracking_service.normalize_gps_position(_raw_ttas(speed=""))
        assert result["speed_kmh"] is None

    def test_speed_never_defaults_to_zero(self):
        # A genuine 0 km/h reading and "we don't know" must stay distinguishable.
        unparseable = tracking_service.normalize_gps_position(_raw_ttas(speed="unknown state"))
        assert unparseable["speed_kmh"] is None
        stopped = tracking_service.normalize_gps_position(_raw_ttas(speed="Chạy 0km/h"))
        assert stopped["speed_kmh"] == 0.0

    # ── A parked truck's phrase counts hours, not km/h ──────────────────
    #
    # Operator-reported 2026-08-03: the dashboard showed a speed for a truck
    # that had been standing still for hours. TTAS writes "Dừng 3h30'" — the
    # duration it has been parked — and reading the first number in the
    # phrase turned that into "3 km/h", growing the longer it sat.

    @pytest.mark.parametrize("phrase,shown", [
        ("Dừng 3h30'", 3),
        ("Dừng 6h4'", 6),
        ("Dừng 7h44'", 7),
        ("Dừng 25 phút", 25),
        ("Dừng 1 giờ 30 phút", 1),
    ])
    def test_a_park_duration_is_never_read_as_a_speed(self, phrase, shown):
        result = tracking_service.normalize_gps_position(_raw_ttas(speed=phrase))
        assert result["speed_kmh"] != shown, \
            f"{phrase!r} reported as {shown} km/h — that number is the parking time"
        assert result["speed_kmh"] == 0.0, "a stopped truck reads 0, not a duration"

    def test_a_stopped_phrase_is_a_known_zero_not_an_unknown(self, ):
        """`None` blanks the reading on the dashboard. TTAS saying "Dừng" is
        positive knowledge that the vehicle is stopped, so it must not be
        rendered as "no data"."""
        result = tracking_service.normalize_gps_position(_raw_ttas(speed="Dừng đỗ"))
        assert result["speed_kmh"] == 0.0

    def test_the_stopped_reading_agrees_with_the_status(self, ):
        """The symptom that gave this away: one payload yielding "stopped"
        and a non-zero speed at the same time."""
        result = tracking_service.normalize_gps_position(
            _raw_ttas(speed="Dừng 3h30'", ad3="Tắt"))
        assert result["vehicle_status"] == "stopped_engine_off"
        assert result["speed_kmh"] == 0.0

    def test_a_number_carrying_the_unit_still_wins(self):
        """Guards the ordering: the unit-anchored match is tried before the
        stopped-phrase shortcut, so a real reading is never flattened to 0."""
        result = tracking_service.normalize_gps_position(_raw_ttas(speed="Dừng 2h10' (5 km/h)"))
        assert result["speed_kmh"] == 5.0

    @pytest.mark.parametrize("phrase,expected", [
        ("Chạy 42km/h", 42.0),
        ("Chạy 42 km/h", 42.0),
        ("Chạy 42km / h", 42.0),
        ("Chạy 42KM/H", 42.0),
    ])
    def test_unit_spacing_and_case_do_not_matter(self, phrase, expected):
        result = tracking_service.normalize_gps_position(_raw_ttas(speed=phrase))
        assert result["speed_kmh"] == expected

    def test_a_decimal_comma_is_read_as_a_decimal(self):
        """TTAS is a Vietnamese-locale system; "37,5" must not become 375."""
        result = tracking_service.normalize_gps_position(_raw_ttas(speed="Chạy 37,5 km/h"))
        assert result["speed_kmh"] == 37.5

    def test_a_moving_phrase_that_lost_its_unit_still_reads(self):
        result = tracking_service.normalize_gps_position(_raw_ttas(speed="Chạy 42"))
        assert result["speed_kmh"] == 42.0

    def test_an_uninterpretable_phrase_stays_unknown(self):
        """Not 0 — the dispatcher must be able to tell "stopped" from
        "we have no reading"."""
        for phrase in ("unknown state", "???", "---"):
            result = tracking_service.normalize_gps_position(_raw_ttas(speed=phrase))
            assert result["speed_kmh"] is None, phrase


class TestLostSignal:
    """TTAS writes `MTH:6h48'` — *mất tín hiệu*, and how long for.

    Operator-reported 2026-08-03. Such a vehicle still carries the last fix
    taken before the signal dropped, so every "has a position?" test treats
    it as tracked — including the dashboard's No GPS filter, which is the one
    list a dispatcher opens to find the trucks they cannot see.
    """

    @pytest.mark.parametrize("phrase", [
        "MTH:6h48'", "MTH: 6h48'", "MTH:6h54'", "mth:1h2'",
        "Mất tín hiệu", "Mất tín hiệu 6h48'",
    ])
    def test_ttas_lost_signal_phrases_are_recognised(self, phrase):
        from app.services.ttas_client import is_lost_signal
        assert is_lost_signal(phrase) is True

    @pytest.mark.parametrize("phrase", [
        "Chạy 42km/h", "Dừng 3h30'", "Dừng đỗ", "", "   ", "unknown state",
    ])
    def test_ordinary_phrases_are_not_lost_signal(self, phrase):
        from app.services.ttas_client import is_lost_signal
        assert is_lost_signal(phrase) is False

    def test_lost_signal_is_its_own_vehicle_status(self):
        """Not "unknown" — that means a phrase we could not read, and the two
        want different responses from the dispatcher."""
        result = tracking_service.normalize_gps_position(_raw_ttas(speed="MTH:6h48'"))
        assert result["vehicle_status"] == "lost_signal"
        assert result["signal_lost"] is True

    def test_a_tracked_vehicle_is_not_flagged(self):
        for phrase in ("Chạy 42km/h", "Dừng 3h30'"):
            result = tracking_service.normalize_gps_position(_raw_ttas(speed=phrase))
            assert result["signal_lost"] is False, phrase

    def test_an_unreadable_phrase_is_not_claimed_as_lost(self):
        """Guessing "lost signal" from a phrase we simply do not understand
        would put healthy trucks in the No GPS list."""
        result = tracking_service.normalize_gps_position(_raw_ttas(speed="unknown state"))
        assert result["vehicle_status"] == "unknown"
        assert result["signal_lost"] is False

    def test_the_last_known_position_is_still_reported(self):
        """The marker stays on the map — where the truck was last seen is the
        most useful thing left. Only the *filter* treats it as unseen."""
        result = tracking_service.normalize_gps_position(_raw_ttas(speed="MTH:6h48'"))
        assert result["lat"] == 10.8
        assert result["lng"] == 106.6

    def test_no_speed_is_invented_for_a_lost_vehicle(self):
        """`MTH:6h48'` would have read as 6 km/h under the pre-2026-08-03
        first-number-wins parse — the same bug as the parked-duration one."""
        result = tracking_service.normalize_gps_position(_raw_ttas(speed="MTH:6h48'"))
        assert result["speed_kmh"] is None


# ===========================================================================
# 2. Stop Progression Tests (advance, skip, cancel)
# ===========================================================================

class TestStopProgression:
    """Tests for execution_service.py: current stop, advance, skip, cancel."""

    def test_current_stop_none(self, db_path):
        plan_id = _create_plan(db_path)
        assignment_id = _create_vehicle_assignment(db_path, plan_id)
        stop = execution_service.get_current_stop(db_path, assignment_id)
        assert stop is None

    def test_advance_planned_to_completed(self, db_path):
        plan_id = _create_plan(db_path)
        assignment_id = _create_vehicle_assignment(db_path, plan_id)
        stop_id = _create_stop(db_path, assignment_id, 1)

        stop = execution_service.get_current_stop(db_path, assignment_id)
        assert stop["id"] == stop_id
        assert stop["execution_status"] == "planned"

        ok, msg = execution_service.advance_stop(db_path, stop_id)
        assert ok
        assert msg == "advanced"

        stop = execution_service.get_stop_execution(db_path, stop_id)
        assert stop["status"] == "arrived"
        assert stop["actual_arrival_at"] is not None

        # Completing needs proof photos; arriving does not.
        _give_proof(db_path, stop_id)
        ok, msg = execution_service.advance_stop(db_path, stop_id)
        assert ok

        stop = execution_service.get_stop_execution(db_path, stop_id)
        assert stop["status"] == "completed"
        assert stop["completed_at"] is not None

    def test_advance_already_completed_fails(self, db_path):
        plan_id = _create_plan(db_path)
        assignment_id = _create_vehicle_assignment(db_path, plan_id)
        stop_id = _create_stop(db_path, assignment_id, 1)

        execution_service.advance_stop(db_path, stop_id)
        _give_proof(db_path, stop_id)
        execution_service.advance_stop(db_path, stop_id)
        ok, msg = execution_service.advance_stop(db_path, stop_id)
        assert not ok
        assert "Cannot advance" in msg

    def test_current_stop_advances_to_next(self, db_path):
        plan_id = _create_plan(db_path)
        assignment_id = _create_vehicle_assignment(db_path, plan_id)
        s1 = _create_stop(db_path, assignment_id, 1, "Stop A")
        s2 = _create_stop(db_path, assignment_id, 2, "Stop B")

        cs = execution_service.get_current_stop(db_path, assignment_id)
        assert cs["id"] == s1

        execution_service.advance_stop(db_path, s1)
        _give_proof(db_path, s1)
        execution_service.advance_stop(db_path, s1)

        cs = execution_service.get_current_stop(db_path, assignment_id)
        assert cs["id"] == s2

    def test_skip_stop(self, db_path):
        plan_id = _create_plan(db_path)
        assignment_id = _create_vehicle_assignment(db_path, plan_id)
        stop_id = _create_stop(db_path, assignment_id, 1)

        ok = execution_service.skip_stop(db_path, stop_id, "Out of stock")
        assert ok

        exec_ = execution_service.get_stop_execution(db_path, stop_id)
        assert exec_["status"] == "skipped"
        assert exec_["skip_reason"] == "Out of stock"

    def test_cancel_stop(self, db_path):
        plan_id = _create_plan(db_path)
        assignment_id = _create_vehicle_assignment(db_path, plan_id)
        stop_id = _create_stop(db_path, assignment_id, 1)

        ok = execution_service.cancel_stop(db_path, stop_id, "Customer cancelled")
        assert ok

        exec_ = execution_service.get_stop_execution(db_path, stop_id)
        assert exec_["status"] == "cancelled"
        assert exec_["cancel_reason"] == "Customer cancelled"

    def test_skip_advances_current_stop(self, db_path):
        plan_id = _create_plan(db_path)
        assignment_id = _create_vehicle_assignment(db_path, plan_id)
        s1 = _create_stop(db_path, assignment_id, 1, "Stop A")
        s2 = _create_stop(db_path, assignment_id, 2, "Stop B")

        execution_service.skip_stop(db_path, s1)
        cs = execution_service.get_current_stop(db_path, assignment_id)
        assert cs["id"] == s2


# ===========================================================================
# 2b. Plan Auto-Completion Tests
# ===========================================================================

class TestPlanAutoCompletion:
    """Tests for execution_service.py: a plan auto-completes once every
    stop across every vehicle assignment under it reaches a terminal
    state (completed/skipped/cancelled) — otherwise nothing ever leaves
    the dashboard's active (confirmed/executing) view."""

    def test_plan_completes_when_all_stops_terminal(self, db_path):
        plan_id = _create_plan(db_path)
        plan_service.update_plan(db_path, plan_id, status="confirmed")
        assignment_id = _create_vehicle_assignment(db_path, plan_id)
        s1 = _create_stop(db_path, assignment_id, 1)
        s2 = _create_stop(db_path, assignment_id, 2)

        execution_service.advance_stop(db_path, s1)  # planned -> arrived
        _give_proof(db_path, s1)
        execution_service.advance_stop(db_path, s1)  # arrived -> completed
        assert plan_service.get_plan(db_path, plan_id)["status"] == "confirmed"

        execution_service.skip_stop(db_path, s2)
        assert plan_service.get_plan(db_path, plan_id)["status"] == "completed"

    def test_plan_not_completed_while_a_stop_remains(self, db_path):
        plan_id = _create_plan(db_path)
        plan_service.update_plan(db_path, plan_id, status="confirmed")
        assignment_id = _create_vehicle_assignment(db_path, plan_id)
        s1 = _create_stop(db_path, assignment_id, 1)
        _create_stop(db_path, assignment_id, 2)

        execution_service.cancel_stop(db_path, s1, "test")
        assert plan_service.get_plan(db_path, plan_id)["status"] == "confirmed"

    def test_plan_requires_every_assignment_terminal(self, db_path):
        plan_id = _create_plan(db_path)
        plan_service.update_plan(db_path, plan_id, status="executing")
        a1 = _create_vehicle_assignment(db_path, plan_id)
        a2 = _create_vehicle_assignment(db_path, plan_id)
        s1 = _create_stop(db_path, a1, 1)
        s2 = _create_stop(db_path, a2, 1)

        execution_service.cancel_stop(db_path, s1, "done")
        assert plan_service.get_plan(db_path, plan_id)["status"] == "executing"

        execution_service.cancel_stop(db_path, s2, "done")
        assert plan_service.get_plan(db_path, plan_id)["status"] == "completed"

    def test_insert_temp_stop_reopens_completed_plan(self, db_path):
        plan_id = _create_plan(db_path)
        plan_service.update_plan(db_path, plan_id, status="executing")
        assignment_id = _create_vehicle_assignment(db_path, plan_id)
        s1 = _create_stop(db_path, assignment_id, 1)
        execution_service.skip_stop(db_path, s1)
        assert plan_service.get_plan(db_path, plan_id)["status"] == "completed"

        execution_service.insert_temp_stop(db_path, assignment_id, after_sequence=1, station_name="New Stop")
        assert plan_service.get_plan(db_path, plan_id)["status"] == "executing"


# ===========================================================================
# 3. Stop Reordering Tests
# ===========================================================================

class TestStopReordering:
    """Tests for execution_service.py: reorder_stops and insert_temp_stop."""

    def test_reorder_stops(self, db_path):
        plan_id = _create_plan(db_path)
        assignment_id = _create_vehicle_assignment(db_path, plan_id)
        s1 = _create_stop(db_path, assignment_id, 1, "First")
        s2 = _create_stop(db_path, assignment_id, 2, "Second")
        s3 = _create_stop(db_path, assignment_id, 3, "Third")

        execution_service.reorder_stops(db_path, assignment_id, [s3, s1, s2])

        cs = execution_service.get_current_stop(db_path, assignment_id)
        assert cs["id"] == s3  # s3 is now first in execution order

    def test_reorder_affects_current_stop(self, db_path):
        plan_id = _create_plan(db_path)
        assignment_id = _create_vehicle_assignment(db_path, plan_id)
        s1 = _create_stop(db_path, assignment_id, 1, "A")
        s2 = _create_stop(db_path, assignment_id, 2, "B")
        s3 = _create_stop(db_path, assignment_id, 3, "C")

        execution_service.reorder_stops(db_path, assignment_id, [s3, s2, s1])
        cs = execution_service.get_current_stop(db_path, assignment_id)
        assert cs["id"] == s3

        execution_service.skip_stop(db_path, s3)
        cs = execution_service.get_current_stop(db_path, assignment_id)
        assert cs["id"] == s2

    def test_insert_temp_stop(self, db_path):
        plan_id = _create_plan(db_path)
        assignment_id = _create_vehicle_assignment(db_path, plan_id)
        s1 = _create_stop(db_path, assignment_id, 1, "A")
        s2 = _create_stop(db_path, assignment_id, 2, "B")

        new_id = execution_service.insert_temp_stop(
            db_path, assignment_id, after_sequence=0,
            station_name="Temp", lat=10.85, lng=106.65,
        )
        assert new_id is not None

        cs = execution_service.get_current_stop(db_path, assignment_id)
        assert cs["id"] == new_id

    def test_insert_temp_stop_after_first(self, db_path):
        plan_id = _create_plan(db_path)
        assignment_id = _create_vehicle_assignment(db_path, plan_id)
        s1 = _create_stop(db_path, assignment_id, 1, "A")
        s2 = _create_stop(db_path, assignment_id, 2, "B")

        execution_service.insert_temp_stop(
            db_path, assignment_id, after_sequence=1,
            station_name="Inserted", lat=10.85, lng=106.65,
        )

        stops = plan_service.list_stops(db_path, assignment_id)
        names = [s["station_name"] for s in stops]
        assert "A" in names
        assert "B" in names
        assert "Inserted" in names

    def test_insert_temp_stop_updates_execution_sequences(self, db_path):
        plan_id = _create_plan(db_path)
        assignment_id = _create_vehicle_assignment(db_path, plan_id)
        s1 = _create_stop(db_path, assignment_id, 1, "A")
        s2 = _create_stop(db_path, assignment_id, 2, "B")

        execution_service.insert_temp_stop(
            db_path, assignment_id, after_sequence=1,
            station_name="Inserted",
        )

        stops = plan_service.list_stops(db_path, assignment_id)
        for s in stops:
            if s["station_name"] == "Inserted":
                assert s["execution_sequence"] == 2
            elif s["station_name"] == "B":
                assert s["execution_sequence"] == 3


# ===========================================================================
# 4. Image Upload Tests
# ===========================================================================

class FakeFileStorage:
    """Mimics Werkzeug's FileStorage for testing.

    Now exposes ``.stream`` because that is what a real FileStorage provides
    and what image_service._validate_upload seeks over to size the upload
    without buffering it. The previous fake had only ``.filename`` and
    ``.save()``, which let it pass tests that a real upload could not.
    """
    def __init__(self, content: bytes, filename: str):
        self.content = content
        self.filename = filename
        self.stream = io.BytesIO(content)

    def save(self, path):
        self.stream.seek(0)
        with open(path, "wb") as f:
            f.write(self.stream.read())


class TestImageService:
    """Tests for image_service.py: upload, list, get, delete."""

    def test_upload_and_list_images(self, db_path):
        plan_id = _create_plan(db_path)
        assignment_id = _create_vehicle_assignment(db_path, plan_id)
        stop_id = _create_stop(db_path, assignment_id, 1)

        fake_file = FakeFileStorage(b"fake_image_data", "test_photo.jpg")

        img_id = image_service.upload_image(
            db_path, stop_id, fake_file,
            category="delivery",
            uploaded_by="Tester",
        )
        assert img_id is not None

        images = image_service.list_images(db_path, stop_id)
        assert len(images) == 1
        assert images[0]["category"] == "delivery"
        assert images[0]["original_filename"] == "test_photo.jpg"

        img = image_service.get_image(db_path, img_id)
        assert img is not None
        assert img["id"] == img_id

    def test_upload_multiple_categories(self, db_path):
        plan_id = _create_plan(db_path)
        assignment_id = _create_vehicle_assignment(db_path, plan_id)
        stop_id = _create_stop(db_path, assignment_id, 1)

        for cat in ("loading", "delivery", "extra"):
            f = FakeFileStorage(b"data", f"{cat}.jpg")
            image_service.upload_image(db_path, stop_id, f, category=cat)

        images = image_service.list_images(db_path, stop_id)
        assert len(images) == 3
        cats = {i["category"] for i in images}
        assert cats == {"loading", "delivery", "extra"}

    def test_delete_image_removes_file(self, db_path):
        plan_id = _create_plan(db_path)
        assignment_id = _create_vehicle_assignment(db_path, plan_id)
        stop_id = _create_stop(db_path, assignment_id, 1)

        f = FakeFileStorage(b"data", "delete_me.jpg")
        img_id = image_service.upload_image(db_path, stop_id, f)

        img = image_service.get_image(db_path, img_id)
        file_path = image_service.DATA_ROOT / img["relative_path"]
        assert file_path.exists()

        ok = image_service.delete_image(db_path, img_id)
        assert ok
        assert not file_path.exists()
        assert image_service.get_image(db_path, img_id) is None

    def test_list_images_empty_stop(self, db_path):
        plan_id = _create_plan(db_path)
        assignment_id = _create_vehicle_assignment(db_path, plan_id)
        stop_id = _create_stop(db_path, assignment_id, 1)

        images = image_service.list_images(db_path, stop_id)
        assert images == []

    def test_upload_to_nonexistent_stop_returns_none(self, db_path):
        f = FakeFileStorage(b"data", "orphan.jpg")
        img_id = image_service.upload_image(db_path, 99999, f)
        assert img_id is None


class TestVideoEvidence:
    """Video evidence, added 2026-08-15.

    Drivers were shooting proof of delivery as video and had nowhere to put it:
    the validator's allow-list was images only and the cap was 10 MB.
    """

    def test_video_is_accepted_and_classified(self, db_path):
        plan_id = _create_plan(db_path)
        assignment_id = _create_vehicle_assignment(db_path, plan_id)
        stop_id = _create_stop(db_path, assignment_id, 1)

        f = FakeFileStorage(b"fake-video-bytes", "unload.mp4")
        img_id = image_service.upload_image(db_path, stop_id, f, category="unload")
        assert img_id is not None

        images = image_service.list_images(db_path, stop_id)
        assert len(images) == 1
        assert images[0]["media_kind"] == "video"
        assert image_service.get_image(db_path, img_id)["media_kind"] == "video"

    def test_photos_are_still_classified_as_images(self, db_path):
        plan_id = _create_plan(db_path)
        assignment_id = _create_vehicle_assignment(db_path, plan_id)
        stop_id = _create_stop(db_path, assignment_id, 1)

        image_service.upload_image(db_path, stop_id,
                                   FakeFileStorage(b"data", "door.jpg"))
        images = image_service.list_images(db_path, stop_id)
        assert images[0]["media_kind"] == "image"

    def test_media_kind_is_derived_not_stored(self):
        """No migration was run, so classification has to come from the name.

        A row written before video existed must still classify, which is only
        true while this is a pure function of the filename.
        """
        assert image_service.media_kind("x.mp4") == "video"
        assert image_service.media_kind("x.MOV") == "video"
        assert image_service.media_kind("x.webm") == "video"
        assert image_service.media_kind("x.jpg") == "image"
        # Unknown and empty fall back to image — an <img> with a bad src shows
        # a broken thumbnail, a <video> with one shows nothing at all.
        assert image_service.media_kind("x.bin") == "image"
        assert image_service.media_kind(None) == "image"

    def test_size_cap_is_per_kind_not_global(self, db_path):
        """The same 11 MB payload: rejected as a photo, accepted as video.

        This is the whole point of splitting the cap. A single limit would have
        to be the video one, which would then let an 11 MB "photo" through.
        """
        plan_id = _create_plan(db_path)
        assignment_id = _create_vehicle_assignment(db_path, plan_id)
        stop_id = _create_stop(db_path, assignment_id, 1)
        payload = b"x" * (11 * 1024 * 1024)

        with pytest.raises(image_service.UploadRejected) as rejected:
            image_service.upload_image(db_path, stop_id,
                                       FakeFileStorage(payload, "big.jpg"))
        # The message has to name the kind, or a driver told "the limit is
        # 10 MB" after picking a video has no idea video is allowed more.
        assert "images" in str(rejected.value)

        assert image_service.upload_image(
            db_path, stop_id, FakeFileStorage(payload, "big.mp4")
        ) is not None

    def test_video_over_its_own_cap_is_rejected(self, db_path, monkeypatch):
        """Patched down rather than allocating 100 MB in the test process."""
        plan_id = _create_plan(db_path)
        assignment_id = _create_vehicle_assignment(db_path, plan_id)
        stop_id = _create_stop(db_path, assignment_id, 1)

        monkeypatch.setattr(image_service, "MAX_VIDEO_BYTES", 1024)
        with pytest.raises(image_service.UploadRejected) as rejected:
            image_service.upload_image(db_path, stop_id,
                                       FakeFileStorage(b"x" * 2048, "long.mp4"))
        assert "Video" in str(rejected.value)

    def test_active_content_types_are_still_rejected(self, db_path):
        """Widening the allow-list must not have widened it past video (S-05)."""
        plan_id = _create_plan(db_path)
        assignment_id = _create_vehicle_assignment(db_path, plan_id)
        stop_id = _create_stop(db_path, assignment_id, 1)

        for name in ("payload.html", "payload.svg", "shell.php", "clip.avi", "clip.mkv"):
            with pytest.raises(image_service.UploadRejected):
                image_service.upload_image(db_path, stop_id,
                                           FakeFileStorage(b"data", name))

    def test_request_cap_stays_above_the_video_cap(self):
        """Cross-module invariant, and the failure mode is silent.

        Werkzeug enforces MAX_CONTENT_LENGTH before the view runs, so if
        MAX_UPLOAD_MB ever drops below MAX_VIDEO_BYTES the driver gets a bare
        413 and image_service's friendly message becomes unreachable.
        """
        from app import config

        assert config.MAX_UPLOAD_MB * 1024 * 1024 > image_service.MAX_VIDEO_BYTES


# ===========================================================================
# 5. Progress & Dashboard Tests
# ===========================================================================

class TestProgress:
    """Tests for execution_service.py: progress calculation."""

    def test_progress_all_planned(self, db_path):
        plan_id = _create_plan(db_path)
        assignment_id = _create_vehicle_assignment(db_path, plan_id)
        _create_stop(db_path, assignment_id, 1)
        _create_stop(db_path, assignment_id, 2)
        _create_stop(db_path, assignment_id, 3)

        prog = execution_service.get_assignment_progress(db_path, assignment_id)
        assert prog["total"] == 3
        assert prog["completed"] == 0
        assert prog["remaining"] == 3
        assert prog["progress_pct"] == 0.0

    def test_progress_partial(self, db_path):
        plan_id = _create_plan(db_path)
        assignment_id = _create_vehicle_assignment(db_path, plan_id)
        s1 = _create_stop(db_path, assignment_id, 1)
        _create_stop(db_path, assignment_id, 2)
        _create_stop(db_path, assignment_id, 3)

        execution_service.advance_stop(db_path, s1)
        _give_proof(db_path, s1)
        execution_service.advance_stop(db_path, s1)

        prog = execution_service.get_assignment_progress(db_path, assignment_id)
        assert prog["completed"] == 1
        assert prog["remaining"] == 2
        assert prog["progress_pct"] == 33.3

    def test_progress_skipped_counts_as_completed(self, db_path):
        plan_id = _create_plan(db_path)
        assignment_id = _create_vehicle_assignment(db_path, plan_id)
        s1 = _create_stop(db_path, assignment_id, 1)
        _create_stop(db_path, assignment_id, 2)

        execution_service.skip_stop(db_path, s1)

        prog = execution_service.get_assignment_progress(db_path, assignment_id)
        assert prog["completed"] == 1
        assert prog["remaining"] == 1

    def test_progress_empty(self, db_path):
        """An assignment with no stops has no stops.

        This test previously asserted `total == 1` with the comment "fallback
        to avoid div-by-zero" — it encoded audit bug C-09 as intended
        behaviour. The `or 1` guard belonged on the division, not the total,
        and the wrong version made the dashboard report "1 remaining" for an
        assignment that had nothing in it.
        """
        plan_id = _create_plan(db_path)
        assignment_id = _create_vehicle_assignment(db_path, plan_id)

        prog = execution_service.get_assignment_progress(db_path, assignment_id)
        assert prog["total"] == 0
        assert prog["completed"] == 0
        assert prog["remaining"] == 0
        assert prog["progress_pct"] == 0.0
        assert prog["breakdown"] == {}

    def test_dashboard_data(self, db_path):
        plan_id = _create_plan(db_path, "Dash Plan")
        plan_service.update_plan(db_path, plan_id, status="executing")
        assignment_id = _create_vehicle_assignment(db_path, plan_id)
        _create_stop(db_path, assignment_id, 1)

        data = execution_service.get_dashboard_data(db_path)
        assert len(data) == 1
        assert data[0]["plan_name"] == "Dash Plan"
        assert data[0]["current_stop"] is not None
        assert data[0]["progress"]["total"] == 1


# ===========================================================================
# 6. Transaction / Rollback Tests
# ===========================================================================

class TestTransactions:
    """Verify multi-table operations roll back on failure."""

    def test_create_stop_rollback_on_failure(self, db_path):
        with pytest.raises(Exception):
            with DatabaseManager(db_path).connect() as conn:
                conn.execute(
                    "INSERT INTO delivery_plan_stops (vehicle_assignment_id, planned_sequence) VALUES (999, 1)"
                )

        with DatabaseManager(db_path).connect() as conn:
            rows = conn.execute(
                "SELECT COUNT(*) as cnt FROM delivery_plan_stops WHERE vehicle_assignment_id = 999"
            ).fetchone()
            assert rows["cnt"] == 0

    def test_delete_plan_cascades(self, db_path):
        plan_id = _create_plan(db_path)
        assignment_id = _create_vehicle_assignment(db_path, plan_id)
        _create_stop(db_path, assignment_id, 1)
        _create_stop(db_path, assignment_id, 2)

        plan_service.delete_plan(db_path, plan_id)

        assert plan_service.get_plan(db_path, plan_id) is None
        assert plan_service.get_assignment(db_path, assignment_id) is None
        assert len(plan_service.list_stops(db_path, assignment_id)) == 0


# ===========================================================================
# 8. Vehicle Identity Service (Phase 2 — audit C-05, L-03, §5)
# ===========================================================================

def _add_vehicle(db_path, plate):
    with DatabaseManager(db_path).connect() as conn:
        conn.execute("INSERT INTO vehicles (plate_number) VALUES (?)", (plate,))
        return conn.execute("SELECT id FROM vehicles WHERE plate_number = ?", (plate,)).fetchone()["id"]


def _count_vehicles(db_path):
    with DatabaseManager(db_path).connect() as conn:
        return conn.execute("SELECT COUNT(*) c FROM vehicles").fetchone()["c"]


class TestVehicleIdentity:
    """services/vehicle_identity.py — the resolver that replaces five
    mutually incompatible plate-matching schemes (audit §5)."""

    @pytest.mark.parametrize("stored,lookup,matched_by", [
        ("50E-18463", "50E-18463", "exact"),
        ("50E-18463", "50E18463", "canonical"),
        ("50E-18463", "50E 18463", "canonical"),
        ("50E-18463", "50e-18463", "canonical"),
        ("50E-18463", "  50E-18463  ", "exact"),
        ("50E-18463", "18463", "serial"),
        ("50E18463", "50E-18463", "canonical"),
    ])
    def test_resolves_every_plate_format(self, db_path, stored, lookup, matched_by):
        vid = _add_vehicle(db_path, stored)
        with DatabaseManager(db_path).connect() as conn:
            ref = vehicle_identity.resolve(conn, lookup)
        assert ref is not None, f"{lookup!r} failed to resolve against stored {stored!r}"
        assert ref.id == vid
        assert ref.matched_by == matched_by

    def test_unknown_plate_returns_none_and_never_creates(self, db_path):
        before = _count_vehicles(db_path)
        with DatabaseManager(db_path).connect() as conn:
            assert vehicle_identity.resolve(conn, "99Z-00000") is None
        assert _count_vehicles(db_path) == before

    @pytest.mark.parametrize("empty", ["", "   ", None])
    def test_empty_identifier_resolves_to_none(self, db_path, empty):
        with DatabaseManager(db_path).connect() as conn:
            assert vehicle_identity.resolve(conn, empty) is None

    def test_full_plate_wins_over_bare_serial_duplicate(self, db_path):
        """The exact duplicate shape merge_duplicate_vehicles.py cleans up:
        a stray '09473' row alongside the real '50H-09473'."""
        full = _add_vehicle(db_path, "50H-09473")
        _add_vehicle(db_path, "09473")
        with DatabaseManager(db_path).connect() as conn:
            ref = vehicle_identity.resolve(conn, "09473")
        assert ref.id == full and ref.plate_number == "50H-09473"

    def test_ambiguous_serial_refuses_to_guess(self, db_path):
        """Two different full plates sharing a 5-digit serial must not be
        silently collapsed — stops would attach to the wrong truck."""
        a = _add_vehicle(db_path, "50H-18463")
        _add_vehicle(db_path, "51C-18463")
        with DatabaseManager(db_path).connect() as conn:
            assert vehicle_identity.resolve(conn, "18463") is None
            # An exact plate is still unambiguous and must still resolve.
            assert vehicle_identity.resolve(conn, "50H-18463").id == a

    def test_module_exposes_no_write_path(self):
        """Adding a vehicle is a Vehicle Management action. This module must
        never grow a create/insert helper — that is how duplicate rows got
        into `vehicles` in the first place."""
        writes = [n for n in dir(vehicle_identity)
                  if any(w in n.lower() for w in ("create", "insert", "add", "save"))
                  and not n.startswith("_")]
        assert writes == [], f"vehicle_identity must stay read-only, found: {writes}"

    @pytest.mark.parametrize("raw,expected", [
        ("50E-18463", "50E18463"),
        ("50e 18463", "50E18463"),
        ("  50E--18463 ", "50E18463"),
        ("", ""),
        (None, ""),
    ])
    def test_canonical_plate(self, raw, expected):
        assert vehicle_identity.canonical_plate(raw) == expected


class TestImportVehicleResolution:
    """confirm_import must resolve plate variants onto existing rows instead
    of silently creating duplicates (audit C-05) and must not split one truck
    across two assignments (audit L-03)."""

    def _rows(self, *vehicle_keys):
        return [
            {"vehicle": v, "sequence": i + 1, "station_code": f"S{i+1}",
             "station_name": f"Stop {i+1}", "lat": 10.8, "lng": 106.6}
            for i, v in enumerate(vehicle_keys)
        ]

    def test_plate_variants_resolve_to_one_existing_vehicle(self, db_path):
        vid = _add_vehicle(db_path, "50E-18463")
        before = _count_vehicles(db_path)
        plan_id = _create_plan(db_path)

        # Four spellings of the same truck in one file.
        summary = plan_service.confirm_import(
            db_path, plan_id,
            self._rows("50E-18463", "50E18463", "50E 18463", "18463"),
        )

        assert _count_vehicles(db_path) == before, "import created duplicate vehicles (C-05)"
        assert summary["assignments_created"] == 1, "one truck split into multiple assignments (L-03)"
        assert summary["stops_created"] == 4

        plan = plan_service.get_plan(db_path, plan_id)
        assert len(plan["assignments"]) == 1
        assert plan["assignments"][0]["vehicle_id"] == vid

    def test_unknown_vehicle_raises_and_writes_nothing(self, db_path):
        _add_vehicle(db_path, "50E-18463")
        before = _count_vehicles(db_path)
        plan_id = _create_plan(db_path)

        with pytest.raises(plan_service.UnknownVehicles) as exc:
            plan_service.confirm_import(db_path, plan_id, self._rows("50E-18463", "99Z-00000"))

        assert "99Z-00000" in exc.value.identifiers
        assert "50E-18463" not in exc.value.identifiers
        # The whole import is one transaction — a partial write would leave
        # the plan half-imported with no way to tell.
        assert _count_vehicles(db_path) == before
        assert plan_service.get_plan(db_path, plan_id)["assignments"] == []
        assert plan_service.get_plan(db_path, plan_id)["status"] == "draft"

    def test_import_never_creates_a_vehicle_under_any_flag(self, db_path):
        """There is no override. An unknown plate always aborts, and no
        keyword argument can turn the import into a vehicle-creation path."""
        before = _count_vehicles(db_path)
        plan_id = _create_plan(db_path)

        with pytest.raises(plan_service.UnknownVehicles):
            plan_service.confirm_import(db_path, plan_id, self._rows("51D-77777"))
        assert _count_vehicles(db_path) == before

        import inspect
        params = inspect.signature(plan_service.confirm_import).parameters
        assert set(params) == {"db_path", "plan_id", "import_data"}, \
            "confirm_import must not accept a vehicle-creation escape hatch"

    def test_error_names_every_unknown_plate_once(self, db_path):
        """Variants of the same unknown plate collapse to one entry, so the
        dispatcher sees one problem to fix rather than three."""
        plan_id = _create_plan(db_path)
        with pytest.raises(plan_service.UnknownVehicles) as exc:
            plan_service.confirm_import(
                db_path, plan_id, self._rows("51D-77777", "51D77777", "77777")
            )
        assert len(exc.value.identifiers) == 1

    def test_plan_marked_confirmed_once(self, db_path):
        _add_vehicle(db_path, "50E-18463")
        _add_vehicle(db_path, "50H-93571")
        plan_id = _create_plan(db_path)

        summary = plan_service.confirm_import(
            db_path, plan_id, self._rows("50E-18463", "50H-93571"),
        )

        assert summary["plan_confirmed"] is True
        plan = plan_service.get_plan(db_path, plan_id)
        assert plan["status"] == "confirmed"
        assert plan["imported_at"] is not None

    def test_empty_import_leaves_plan_in_draft(self, db_path):
        """Used to return success while the plan silently stayed 'draft' and
        never reached the dashboard (audit L-06) — now reported honestly."""
        plan_id = _create_plan(db_path)
        summary = plan_service.confirm_import(db_path, plan_id, [])
        assert summary["plan_confirmed"] is False
        assert summary["assignments_created"] == 0
        assert plan_service.get_plan(db_path, plan_id)["status"] == "draft"


class TestPreviewImportResolution:
    def test_preview_reports_resolution_when_given_a_db(self, db_path):
        _add_vehicle(db_path, "50E-18463")
        rows = [
            {"vehicle": "50E18463", "sequence": 1, "station_code": "S1", "lat": 10.8, "lng": 106.6},
            {"vehicle": "99Z-00000", "sequence": 1, "station_code": "S2", "lat": 10.8, "lng": 106.6},
        ]
        preview = plan_service.preview_import(rows, db_path=db_path)

        assert preview["vehicles_checked"] is True
        assert preview["unknown_vehicles"] == ["99Z-00000"]
        by_id = {a["vehicle_identifier"]: a for a in preview["assignments"]}
        assert by_id["50E18463"]["resolved"] is True
        assert by_id["50E18463"]["resolved_plate"] == "50E-18463"
        assert by_id["50E18463"]["matched_by"] == "canonical"
        assert by_id["99Z-00000"]["resolved"] is False

    def test_preview_without_db_keeps_old_behaviour(self, db_path):
        rows = [{"vehicle": "50E-18463", "sequence": 1, "station_code": "S1"}]
        preview = plan_service.preview_import(rows)
        assert preview["vehicles_checked"] is False
        assert preview["total_assignments"] == 1
        assert preview["unknown_vehicles"] == []


# ===========================================================================
# 9. Execution correctness (Phase 3 — audit C-07, C-09, reorder validation)
# ===========================================================================

class TestAdvanceAtomicity:
    """A stop must not be walked two steps by one accidental double-tap
    (audit C-07). Dispatch is used on phones; a double-tap is routine."""

    def _stop(self, db_path):
        plan_id = _create_plan(db_path)
        assignment_id = _create_vehicle_assignment(db_path, plan_id)
        return _create_stop(db_path, assignment_id, 1)

    def test_double_advance_with_expected_status_is_refused(self, db_path):
        stop_id = self._stop(db_path)

        ok, msg = execution_service.advance_stop(db_path, stop_id, expected_status="planned")
        assert ok and msg == "advanced"
        assert execution_service.get_stop_execution(db_path, stop_id)["status"] == "arrived"

        # The second tap carries the same token the button was rendered with.
        ok, msg = execution_service.advance_stop(db_path, stop_id, expected_status="planned")
        assert ok is False
        assert "already" in msg.lower()
        # Critically: still 'arrived', not skipped through to 'completed'.
        assert execution_service.get_stop_execution(db_path, stop_id)["status"] == "arrived"

    def test_arrival_is_not_erased_by_a_double_tap(self, db_path):
        """The damage wasn't only the status — arrival and departure were
        stamped in the same second, destroying dwell time."""
        stop_id = self._stop(db_path)
        execution_service.advance_stop(db_path, stop_id, expected_status="planned")
        execution_service.advance_stop(db_path, stop_id, expected_status="planned")

        e = execution_service.get_stop_execution(db_path, stop_id)
        assert e["actual_arrival_at"] is not None
        assert e["actual_departure_at"] is None, "stop was completed by the second tap"

    def test_deliberate_two_step_progression_still_works(self, db_path):
        """The guard must not break the normal flow: a dispatcher advancing
        twice, each time from the status actually on screen."""
        stop_id = self._stop(db_path)

        ok, msg = execution_service.advance_stop(db_path, stop_id, expected_status="planned")
        assert (ok, msg) == (True, "advanced")
        _give_proof(db_path, stop_id)
        ok, msg = execution_service.advance_stop(db_path, stop_id, expected_status="arrived")
        assert (ok, msg) == (True, "completed")
        assert execution_service.get_stop_execution(db_path, stop_id)["status"] == "completed"

    def test_advance_without_token_still_supported(self, db_path):
        """expected_status is optional — older callers keep working."""
        stop_id = self._stop(db_path)
        assert execution_service.advance_stop(db_path, stop_id)[0] is True
        assert execution_service.get_stop_execution(db_path, stop_id)["status"] == "arrived"

    def test_cannot_advance_a_terminal_stop(self, db_path):
        stop_id = self._stop(db_path)
        execution_service.skip_stop(db_path, stop_id, "no access")
        ok, msg = execution_service.advance_stop(db_path, stop_id)
        assert ok is False and "skipped" in msg


class TestRevertStop:
    """Advance is one unconfirmed tap sitting beside Skip and Cancel, pressed
    on a phone in a moving vehicle. The double-tap guard (C-07) stops a mis-tap
    landing twice, but nothing walked back the one that did land — the remedy
    was hand-editing stop_executions."""

    def _stop(self, db_path):
        plan_id = _create_plan(db_path)
        assignment_id = _create_vehicle_assignment(db_path, plan_id)
        return _create_stop(db_path, assignment_id, 1)

    def test_arrived_reverts_to_planned_and_drops_the_arrival(self, db_path):
        stop_id = self._stop(db_path)
        execution_service.advance_stop(db_path, stop_id, expected_status="planned")

        ok, target = execution_service.revert_stop(db_path, stop_id, expected_status="arrived")

        assert (ok, target) == (True, "planned")
        e = execution_service.get_stop_execution(db_path, stop_id)
        assert e["status"] == "planned"
        assert e["actual_arrival_at"] is None, (
            "a stop that was never reached kept an arrival time — the same "
            "corruption of dwell time C-07 caused"
        )

    def test_completed_reverts_one_step_to_arrived(self, db_path):
        stop_id = self._stop(db_path)
        execution_service.advance_stop(db_path, stop_id, expected_status="planned")
        _give_proof(db_path, stop_id)
        execution_service.advance_stop(db_path, stop_id, expected_status="arrived")

        ok, target = execution_service.revert_stop(db_path, stop_id)

        assert (ok, target) == (True, "arrived")
        e = execution_service.get_stop_execution(db_path, stop_id)
        assert e["actual_arrival_at"] is not None, "the arrival really happened"
        assert e["actual_departure_at"] is None
        assert e["completed_at"] is None

    def test_skip_reverts_and_forgets_its_reason(self, db_path):
        stop_id = self._stop(db_path)
        execution_service.skip_stop(db_path, stop_id, "wrong button")

        ok, target = execution_service.revert_stop(db_path, stop_id)

        assert (ok, target) == (True, "planned")
        e = execution_service.get_stop_execution(db_path, stop_id)
        assert e["skip_reason"] == ""
        assert e["completed_at"] is None

    def test_cancel_reverts_and_forgets_its_reason(self, db_path):
        stop_id = self._stop(db_path)
        execution_service.cancel_stop(db_path, stop_id, "customer closed")

        ok, target = execution_service.revert_stop(db_path, stop_id)

        assert (ok, target) == (True, "planned")
        assert execution_service.get_stop_execution(db_path, stop_id)["cancel_reason"] == ""

    def test_skip_after_arrival_reverts_to_arrived(self, db_path):
        """Nothing records what a stop was before it was skipped, but an
        arrival timestamp can only have come from an advance — so this one
        goes back to 'arrived' rather than stranding that timestamp on a stop
        the dashboard would call unvisited."""
        stop_id = self._stop(db_path)
        execution_service.advance_stop(db_path, stop_id, expected_status="planned")
        execution_service.skip_stop(db_path, stop_id, "nobody home")

        ok, target = execution_service.revert_stop(db_path, stop_id)

        assert (ok, target) == (True, "arrived")
        assert execution_service.get_stop_execution(db_path, stop_id)["actual_arrival_at"] is not None

    def test_revert_makes_the_stop_current_again(self, db_path):
        plan_id = _create_plan(db_path)
        assignment_id = _create_vehicle_assignment(db_path, plan_id)
        first = _create_stop(db_path, assignment_id, 1)
        second = _create_stop(db_path, assignment_id, 2)
        execution_service.skip_stop(db_path, first, "mis-tap")
        assert execution_service.get_current_stop(db_path, assignment_id)["id"] == second

        execution_service.revert_stop(db_path, first)

        assert execution_service.get_current_stop(db_path, assignment_id)["id"] == first

    def test_revert_reopens_an_auto_completed_plan(self, db_path):
        """The mirror of _maybe_complete_plan. Without this the corrected plan
        stays 'completed' and drops out of the dashboard's active view, so the
        dispatcher can't see the vehicle they just fixed."""
        plan_id = _create_plan(db_path)
        assignment_id = _create_vehicle_assignment(db_path, plan_id)
        stop_id = _create_stop(db_path, assignment_id, 1)
        execution_service.advance_stop(db_path, stop_id)
        _give_proof(db_path, stop_id)
        execution_service.advance_stop(db_path, stop_id)
        assert plan_service.get_plan(db_path, plan_id)["status"] == "completed"

        execution_service.revert_stop(db_path, stop_id)

        assert plan_service.get_plan(db_path, plan_id)["status"] == "executing"

    def test_stale_token_is_refused(self, db_path):
        stop_id = self._stop(db_path)
        execution_service.advance_stop(db_path, stop_id)
        _give_proof(db_path, stop_id)
        execution_service.advance_stop(db_path, stop_id)

        ok, msg = execution_service.revert_stop(db_path, stop_id, expected_status="arrived")

        assert ok is False and "already" in msg
        assert execution_service.get_stop_execution(db_path, stop_id)["status"] == "completed"

    def test_planned_stop_cannot_be_reverted(self, db_path):
        stop_id = self._stop(db_path)
        ok, msg = execution_service.revert_stop(db_path, stop_id)
        assert ok is False and "Cannot revert" in msg

    def test_missing_stop_is_reported(self, db_path):
        ok, msg = execution_service.revert_stop(db_path, 99999)
        assert ok is False and "not found" in msg

    def test_a_closed_days_plan_can_no_longer_be_corrected(self, db_path):
        """Yesterday's route is a finished record. Correcting a stop is
        bookkeeping, and bookkeeping closes at the end of the shift."""
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        plan_id = _create_plan(db_path, plan_date=yesterday)
        assignment_id = _create_vehicle_assignment(db_path, plan_id)
        stop_id = _create_stop(db_path, assignment_id, 1)
        execution_service.advance_stop(db_path, stop_id)

        ok, msg = execution_service.revert_stop(db_path, stop_id)

        assert ok is False and "date has passed" in msg
        assert execution_service.get_stop_execution(db_path, stop_id)["status"] == "arrived"

    def test_a_stop_stays_correctable_all_day_not_for_15_minutes(self, db_path):
        """The rule that replaced the original 15-minute window. An advance
        made hours ago on today's plan is still correctable."""
        stop_id = self._stop(db_path)
        execution_service.advance_stop(db_path, stop_id)
        _backdate(db_path, stop_id, minutes=8 * 60)

        assert execution_service.revert_stop(db_path, stop_id)[0] is True

    def test_a_future_dated_plan_is_correctable(self, db_path):
        """Plans are built ahead. A stop actioned early on tomorrow's route
        must not be frozen for being in the future."""
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        plan_id = _create_plan(db_path, plan_date=tomorrow)
        assignment_id = _create_vehicle_assignment(db_path, plan_id)
        stop_id = _create_stop(db_path, assignment_id, 1)
        execution_service.advance_stop(db_path, stop_id)

        assert execution_service.revert_stop(db_path, stop_id)[0] is True


class TestProofRequired:
    """A stop cannot be marked completed without photographic proof: the
    goods off the truck, and the door shut afterwards.

    The pair is the point — 'delivered' and 'secured' are the two things a
    dispute actually turns on, and either alone leaves half the question
    open.
    """

    def _arrived_stop(self, db_path):
        plan_id = _create_plan(db_path)
        assignment_id = _create_vehicle_assignment(db_path, plan_id)
        stop_id = _create_stop(db_path, assignment_id, 1)
        execution_service.advance_stop(db_path, stop_id)
        return stop_id

    def test_completing_without_photos_is_refused(self, db_path):
        stop_id = self._arrived_stop(db_path)

        ok, msg = execution_service.advance_stop(db_path, stop_id)

        assert (ok, msg) == (False, execution_service.PROOF_REQUIRED)
        assert execution_service.get_stop_execution(db_path, stop_id)["status"] == "arrived"

    def test_arriving_is_not_gated(self, db_path):
        """Arriving somewhere is not a claim about what happened there, so
        there is nothing yet to prove."""
        plan_id = _create_plan(db_path)
        assignment_id = _create_vehicle_assignment(db_path, plan_id)
        stop_id = _create_stop(db_path, assignment_id, 1)

        assert execution_service.advance_stop(db_path, stop_id)[0] is True

    @pytest.mark.parametrize("supplied,missing", [
        (["unload"], ["door"]),
        (["door"], ["unload"]),
        ([], ["unload", "door"]),
    ])
    def test_one_photo_is_not_enough(self, db_path, supplied, missing):
        stop_id = self._arrived_stop(db_path)
        if supplied:
            _give_proof(db_path, stop_id, supplied)

        ok, msg = execution_service.advance_stop(db_path, stop_id)

        assert (ok, msg) == (False, execution_service.PROOF_REQUIRED)
        assert execution_service.missing_proof(db_path, stop_id) == missing

    def test_both_photos_allow_completion(self, db_path):
        stop_id = self._arrived_stop(db_path)
        _give_proof(db_path, stop_id)

        assert execution_service.advance_stop(db_path, stop_id) == (True, "completed")
        assert execution_service.missing_proof(db_path, stop_id) == []

    def test_an_unrelated_category_does_not_satisfy_the_gate(self, db_path):
        """Categories are sanitized rather than whitelisted on upload (audit
        S-04), so a typo produces a category nobody asked for. The safe
        consequence is that it cannot stand in for real proof."""
        stop_id = self._arrived_stop(db_path)
        _give_proof(db_path, stop_id, ["extra", "unloaded", "Door"])

        assert execution_service.advance_stop(db_path, stop_id)[1] == execution_service.PROOF_REQUIRED

    def test_an_override_completes_the_stop(self, db_path):
        stop_id = self._arrived_stop(db_path)

        ok, msg = execution_service.advance_stop(
            db_path, stop_id, override_reason="driver's phone battery died")

        assert (ok, msg) == (True, "completed")

    def test_the_override_reason_is_kept_in_the_history(self, db_path):
        """The only place it lives. Nothing on stop_executions records that a
        completion was waived, so if the log did not hold the reason the
        exception would be invisible a day later."""
        stop_id = self._arrived_stop(db_path)
        execution_service.advance_stop(db_path, stop_id, override_reason="gate shut, no light")

        event = execution_service.list_status_events(db_path, stop_id)[-1]

        assert event["to_status"] == "completed"
        assert event["reason"] == "gate shut, no light"

    def test_a_blank_override_is_not_an_override(self, db_path):
        """Whitespace would record that proof was waived while saying nothing
        about why — the one thing that makes the exception defensible."""
        stop_id = self._arrived_stop(db_path)

        assert execution_service.advance_stop(
            db_path, stop_id, override_reason="   ")[1] == execution_service.PROOF_REQUIRED

    def test_a_normal_completion_records_no_reason(self, db_path):
        stop_id = self._arrived_stop(db_path)
        _give_proof(db_path, stop_id)
        execution_service.advance_stop(db_path, stop_id)

        assert execution_service.list_status_events(db_path, stop_id)[-1]["reason"] == ""

    def test_skip_and_cancel_are_not_gated(self, db_path):
        """They already carry a typed reason, and photographing a delivery
        that never happened is usually impossible."""
        plan_id = _create_plan(db_path)
        assignment_id = _create_vehicle_assignment(db_path, plan_id)
        skipped = _create_stop(db_path, assignment_id, 1)
        cancelled = _create_stop(db_path, assignment_id, 2)

        assert execution_service.skip_stop(db_path, skipped, "gate locked") is True
        assert execution_service.cancel_stop(db_path, cancelled, "closed") is True


class TestExportNaming:
    """Driver folder names, which are the fiddly part of the handover.

    The operator's folders read `HuynhQuocTrong_79791` — accents stripped,
    words run together, then the plate's 5-digit serial.
    """

    def test_vietnamese_accents_are_stripped(self):
        from services.delivery import export_service
        assert export_service.strip_accents("Huỳnh Quốc Trọng") == "HuynhQuocTrong"
        assert export_service.strip_accents("Nguyễn Thành Giang") == "NguyenThanhGiang"
        assert export_service.strip_accents("Lê Tấn Quốc") == "LeTanQuoc"

    def test_the_letter_d_with_stroke_is_handled(self):
        """đ/Đ is a distinct letter, not d-plus-diacritic, so NFD leaves it
        alone — the classic way this kind of function drops characters."""
        from services.delivery import export_service
        assert export_service.strip_accents("Đỗ Đình Đức") == "DoDinhDuc"
        assert export_service.strip_accents("đường") == "duong"

    def test_a_driver_folder_pairs_name_with_the_plate_serial(self):
        from services.delivery import export_service
        assert export_service.driver_folder_name("Huỳnh Quốc Trọng", "50E-79791") \
            == "HuynhQuocTrong_79791"

    @pytest.mark.parametrize("plate", ["50E-79791", "50E79791", "50E 79791", "79791"])
    def test_the_serial_is_stable_across_plate_formats(self, plate):
        """Same reduction the GPS matching uses (audit C-03), so the number
        in the folder is the one the rest of the system agrees on."""
        from services.delivery import export_service
        assert export_service.driver_folder_name("A", plate).endswith("_79791")

    def test_a_nameless_driver_still_produces_a_folder(self):
        from services.delivery import export_service
        folder = export_service.driver_folder_name("", "50E-79791")
        assert folder == "KhongRoTaiXe_79791", "an empty segment would collapse the path"

    def test_punctuation_and_spacing_never_reach_the_path(self):
        from services.delivery import export_service
        assert export_service.strip_accents("Trần  Hoàng-Quân (A)") == "TranHoangQuanA"


class TestStatusHistory:
    """Every phase change is recorded, and revert returns the stop to the
    phase it is recorded as having come from.

    Before this the reverse transition was a static table, which had to
    *infer* where a skipped stop had been. The log makes the answer a matter
    of record instead of deduction.
    """

    def _stop(self, db_path):
        plan_id = _create_plan(db_path)
        assignment_id = _create_vehicle_assignment(db_path, plan_id)
        return _create_stop(db_path, assignment_id, 1)

    def test_advance_is_recorded(self, db_path):
        stop_id = self._stop(db_path)
        execution_service.advance_stop(db_path, stop_id)

        events = execution_service.list_status_events(db_path, stop_id)
        assert len(events) == 1
        assert (events[0]["from_status"], events[0]["to_status"]) == ("planned", "arrived")
        assert events[0]["action"] == "advance"
        assert events[0]["occurred_at"]

    def test_the_log_reads_in_the_order_it_happened(self, db_path):
        stop_id = self._stop(db_path)
        execution_service.advance_stop(db_path, stop_id)
        _give_proof(db_path, stop_id)
        execution_service.advance_stop(db_path, stop_id)
        execution_service.revert_stop(db_path, stop_id)

        events = execution_service.list_status_events(db_path, stop_id)
        assert [(e["from_status"], e["to_status"], e["action"]) for e in events] == [
            ("planned", "arrived", "advance"),
            ("arrived", "completed", "advance"),
            ("completed", "arrived", "revert"),
        ]

    def test_skip_and_cancel_record_their_reason(self, db_path):
        skipped = self._stop(db_path)
        execution_service.skip_stop(db_path, skipped, "gate locked")
        event = execution_service.list_status_events(db_path, skipped)[-1]
        assert (event["action"], event["reason"]) == ("skip", "gate locked")
        assert (event["from_status"], event["to_status"]) == ("planned", "skipped")

    def test_a_refused_transition_records_nothing(self, db_path):
        """The event is written on the same connection as the UPDATE and only
        after it reported a rowcount, so a rejected action leaves no trace
        claiming it happened."""
        stop_id = self._stop(db_path)
        execution_service.advance_stop(db_path, stop_id, expected_status="planned")
        execution_service.advance_stop(db_path, stop_id, expected_status="planned")  # stale, refused

        assert len(execution_service.list_status_events(db_path, stop_id)) == 1

    def test_revert_returns_to_the_recorded_phase(self, db_path):
        stop_id = self._stop(db_path)
        execution_service.advance_stop(db_path, stop_id)          # planned -> arrived
        execution_service.skip_stop(db_path, stop_id, "no access")  # arrived -> skipped

        ok, target = execution_service.revert_stop(db_path, stop_id)

        assert (ok, target) == (True, "arrived")

    def test_a_second_revert_steps_back_again_rather_than_redoing(self, db_path):
        """The subtle one. After advance, advance, revert, the newest event
        landing on 'arrived' is the revert itself — whose from_status is
        'completed'. Reading that would send the next revert *forward*,
        turning a second undo into a redo."""
        stop_id = self._stop(db_path)
        execution_service.advance_stop(db_path, stop_id)   # planned -> arrived
        _give_proof(db_path, stop_id)
        execution_service.advance_stop(db_path, stop_id)   # arrived -> completed
        execution_service.revert_stop(db_path, stop_id)    # -> arrived

        ok, target = execution_service.revert_stop(db_path, stop_id)

        assert (ok, target) == (True, "planned")
        assert execution_service.get_stop_execution(db_path, stop_id)["status"] == "planned"

    def test_advance_after_revert_starts_a_fresh_forward_record(self, db_path):
        stop_id = self._stop(db_path)
        execution_service.advance_stop(db_path, stop_id)
        execution_service.revert_stop(db_path, stop_id)
        execution_service.advance_stop(db_path, stop_id)

        assert execution_service.get_stop_execution(db_path, stop_id)["status"] == "arrived"
        assert execution_service.revert_stop(db_path, stop_id)[1] == "planned"

    def test_a_stop_with_no_log_still_reverts_by_inference(self, db_path):
        """Nothing was backfilled, so every stop touched before the log
        existed has an empty history. Those must keep working."""
        stop_id = self._stop(db_path)
        execution_service.advance_stop(db_path, stop_id)
        execution_service.skip_stop(db_path, stop_id, "x")
        _clear_status_events(db_path, stop_id)

        ok, target = execution_service.revert_stop(db_path, stop_id)

        # Falls back to inferring from actual_arrival_at, as it did before.
        assert (ok, target) == (True, "arrived")
        assert execution_service.list_status_events(db_path, stop_id)[-1]["action"] == "revert"

    def test_history_is_empty_for_an_untouched_stop(self, db_path):
        assert execution_service.list_status_events(db_path, self._stop(db_path)) == []


class TestCanRevert:
    """The predicate the dashboard's Revert button is drawn from. It runs
    server-side so the button and the endpoint enforcing it read one calendar.

    The rule is the plan's own day, not elapsed time — a correction is
    bookkeeping, and bookkeeping is finished at the end of a shift rather
    than within fifteen minutes of the mistake.
    """

    TODAY = date(2026, 8, 1)

    def test_todays_plan_is_correctable_in_every_actioned_status(self):
        for status in ("arrived", "completed", "skipped", "cancelled"):
            assert execution_service.can_revert(status, plan_date="2026-08-01", today=self.TODAY), status

    def test_planned_has_nothing_to_correct(self):
        assert execution_service.can_revert("planned", plan_date="2026-08-01", today=self.TODAY) is False

    def test_a_past_plan_is_closed(self):
        assert execution_service.can_revert("completed", plan_date="2026-07-31", today=self.TODAY) is False

    def test_a_future_plan_is_open(self):
        """Routes are built ahead of the day they run."""
        assert execution_service.can_revert("completed", plan_date="2026-08-02", today=self.TODAY) is True

    def test_elapsed_time_alone_never_closes_the_record(self):
        """The behaviour that replaced the 15-minute window: nothing about
        how long ago the action happened enters into it."""
        assert execution_service.can_revert("arrived", plan_date="2026-08-01", today=self.TODAY) is True

    def test_a_missing_or_unreadable_date_reads_as_closed(self):
        """Unknown is treated as closed rather than open — the same
        conservative choice made everywhere else here."""
        assert execution_service.can_revert("completed", plan_date=None, today=self.TODAY) is False
        assert execution_service.can_revert("completed", plan_date="", today=self.TODAY) is False
        assert execution_service.can_revert("completed", plan_date="not a date", today=self.TODAY) is False

    def test_a_timestamp_valued_plan_date_still_compares_by_day(self):
        assert execution_service.can_revert(
            "completed", plan_date="2026-08-01 00:00:00", today=self.TODAY) is True

    def test_annotate_uses_the_execution_status_alias(self, db_path):
        """list_stops aliases the column to execution_status; reading 'status'
        here would silently mark every stop unrevertible."""
        plan_id = _create_plan(db_path)
        assignment_id = _create_vehicle_assignment(db_path, plan_id)
        first = _create_stop(db_path, assignment_id, 1)
        _create_stop(db_path, assignment_id, 2)
        execution_service.advance_stop(db_path, first)

        stops = execution_service.annotate_revertible(
            plan_service.list_stops(db_path, assignment_id)
        )

        assert stops[0]["can_revert"] is True
        assert stops[1]["can_revert"] is False


class TestReorderValidation:
    """reorder_stops accepted any list and applied it stop-by-stop, so a
    partial list left duplicate execution_sequence values and ids from another
    assignment silently no-opped while reporting success."""

    def _assignment_with_stops(self, db_path, n=3):
        plan_id = _create_plan(db_path)
        assignment_id = _create_vehicle_assignment(db_path, plan_id)
        ids = [_create_stop(db_path, assignment_id, i) for i in range(1, n + 1)]
        return assignment_id, ids

    def test_full_reorder_succeeds(self, db_path):
        aid, ids = self._assignment_with_stops(db_path)
        ok, msg = execution_service.reorder_stops(db_path, aid, [ids[2], ids[0], ids[1]])
        assert ok is True and msg == "reordered"
        assert [s["id"] for s in plan_service.list_stops(db_path, aid)] == [ids[2], ids[0], ids[1]]

    def test_partial_list_is_rejected(self, db_path):
        aid, ids = self._assignment_with_stops(db_path)
        before = [s["id"] for s in plan_service.list_stops(db_path, aid)]

        ok, msg = execution_service.reorder_stops(db_path, aid, [ids[2], ids[1]])
        assert ok is False and "missing" in msg

        # Nothing partially applied — no duplicate sequences left behind.
        assert [s["id"] for s in plan_service.list_stops(db_path, aid)] == before
        seqs = [s["execution_sequence"] for s in plan_service.list_stops(db_path, aid)]
        assert len(seqs) == len(set(seqs)), f"duplicate execution_sequence values: {seqs}"

    def test_foreign_stop_ids_are_rejected(self, db_path):
        aid, ids = self._assignment_with_stops(db_path, n=1)
        other_aid, other_ids = self._assignment_with_stops(db_path, n=1)

        ok, msg = execution_service.reorder_stops(db_path, aid, other_ids)
        assert ok is False
        assert "not in this assignment" in msg

    def test_duplicate_ids_are_rejected(self, db_path):
        aid, ids = self._assignment_with_stops(db_path, n=2)
        ok, msg = execution_service.reorder_stops(db_path, aid, [ids[0], ids[0]])
        assert ok is False and "duplicate" in msg.lower()

    def test_empty_assignment_is_rejected(self, db_path):
        plan_id = _create_plan(db_path)
        aid = _create_vehicle_assignment(db_path, plan_id)
        ok, msg = execution_service.reorder_stops(db_path, aid, [])
        assert ok is False and "no stops" in msg


class TestProgressWithoutStops:
    """audit C-09 — `total = sum(...) or 1` leaked a division guard into the
    reported totals."""

    def test_dashboard_reports_zero_not_one(self, db_path):
        plan_id = _create_plan(db_path, "Empty")
        plan_service.update_plan(db_path, plan_id, status="confirmed")
        _create_vehicle_assignment(db_path, plan_id)

        entry = execution_service.get_dashboard_data(db_path)[0]
        assert entry["progress"]["total"] == 0
        assert entry["progress"]["remaining"] == 0, "dispatcher would chase a stop that doesn't exist"
        assert entry["progress"]["progress_pct"] == 0.0

    def test_percentage_still_correct_with_stops(self, db_path):
        plan_id = _create_plan(db_path)
        aid = _create_vehicle_assignment(db_path, plan_id)
        ids = [_create_stop(db_path, aid, i) for i in range(1, 5)]
        execution_service.skip_stop(db_path, ids[0], "x")

        prog = execution_service.get_assignment_progress(db_path, aid)
        assert (prog["total"], prog["completed"], prog["remaining"]) == (4, 1, 3)
        assert prog["progress_pct"] == 25.0


class TestPlanDriverOverride:
    """The driver typed during plan creation is who drove *that day*.

    Drivers mostly exist as `vehicles.current_driver` text with no `drivers`
    row, so `driver_id` is almost always NULL and every reader used to fall
    back to the vehicle's default — silently discarding a stand-in the
    dispatcher had typed. The name is now stored free-text on the assignment
    and outranks both the linked record and the vehicle default.
    """

    def _confirmed_plan_with_driver(self, db_path, driver_name=None, driver_id=None):
        plan_id = _create_plan(db_path, "Override")
        plan_service.update_plan(db_path, plan_id, status="confirmed")
        aid = plan_service.create_assignment(
            db_path, plan_id, 1, driver_id=driver_id, sequence=1,
            driver_name=driver_name,
        )
        return plan_id, aid

    def test_typed_name_beats_the_vehicle_default_on_the_dashboard(self, db_path):
        self._confirmed_plan_with_driver(db_path, "Nguyen Van Thay")

        entry = execution_service.get_dashboard_data(db_path)[0]
        assert entry["current_driver"] == "Nguyen Van Thay", \
            "dispatcher would be told the wrong man is behind the wheel"

    def test_vehicle_default_still_used_when_nothing_was_typed(self, db_path):
        self._confirmed_plan_with_driver(db_path, None)

        entry = execution_service.get_dashboard_data(db_path)[0]
        assert entry["current_driver"] == "Test Driver"

    def test_a_blank_entry_does_not_blank_the_dashboard(self, db_path):
        """An empty box means "no opinion", not "no driver" — whitespace has
        to reduce to the same thing or the column goes empty."""
        self._confirmed_plan_with_driver(db_path, "   ")

        entry = execution_service.get_dashboard_data(db_path)[0]
        assert entry["current_driver"] == "Test Driver"

    def test_a_linked_driver_record_still_wins_over_the_vehicle(self, db_path):
        did = plan_service.create_driver(db_path, "Registered Driver")
        self._confirmed_plan_with_driver(db_path, None, driver_id=did)

        entry = execution_service.get_dashboard_data(db_path)[0]
        assert entry["current_driver"] == "Registered Driver"

    def test_typed_name_beats_even_a_linked_record(self, db_path):
        """Both set means the dispatcher edited the prefilled name — the
        edit is the newer intent."""
        did = plan_service.create_driver(db_path, "Registered Driver")
        self._confirmed_plan_with_driver(db_path, "Stand In", driver_id=did)

        entry = execution_service.get_dashboard_data(db_path)[0]
        assert entry["current_driver"] == "Stand In"

    def test_no_driver_record_is_created(self, db_path):
        """A one-off stand-in must not accumulate in the drivers list."""
        self._confirmed_plan_with_driver(db_path, "One Off Guy")

        assert [d["name"] for d in plan_service.list_drivers(db_path)] == ["Test Driver"], \
            "list_drivers only synthesises from vehicles; a typed name must not persist"

    def test_reopening_the_plan_shows_the_name_that_was_typed(self, db_path):
        """The look-back case: the plan is a record of that exact day."""
        plan_id, _ = self._confirmed_plan_with_driver(db_path, "Nguyen Van Thay")

        plan = plan_service.get_plan(db_path, plan_id)
        assert plan["assignments"][0]["driver_name"] == "Nguyen Van Thay"

    def test_the_record_survives_the_vehicle_changing_hands(self, db_path):
        """Reassigning the truck must not rewrite last week's plan."""
        plan_id, _ = self._confirmed_plan_with_driver(db_path, "Nguyen Van Thay")

        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE vehicles SET current_driver = 'Somebody Else' WHERE id = 1")
        conn.commit()
        conn.close()

        plan = plan_service.get_plan(db_path, plan_id)
        assert plan["assignments"][0]["driver_name"] == "Nguyen Van Thay"

    def test_listing_assignments_carries_the_name(self, db_path):
        plan_id, _ = self._confirmed_plan_with_driver(db_path, "Nguyen Van Thay")

        rows = plan_service.list_assignments(db_path, plan_id)
        assert rows[0]["driver_name"] == "Nguyen Van Thay"

    def test_get_assignment_carries_the_name(self, db_path):
        _, aid = self._confirmed_plan_with_driver(db_path, "Nguyen Van Thay")

        assert plan_service.get_assignment(db_path, aid)["driver_name"] == "Nguyen Van Thay"

    def test_the_name_can_be_edited_afterwards(self, db_path):
        plan_id, aid = self._confirmed_plan_with_driver(db_path, "First Guess")

        assert plan_service.update_assignment(db_path, aid, driver_name="Second Guess")
        assert plan_service.get_assignment(db_path, aid)["driver_name"] == "Second Guess"

    def test_clearing_the_name_falls_back_to_the_vehicle(self, db_path):
        plan_id, aid = self._confirmed_plan_with_driver(db_path, "First Guess")

        plan_service.update_assignment(db_path, aid, driver_name="")
        entry = execution_service.get_dashboard_data(db_path)[0]
        assert entry["current_driver"] == "Test Driver"

    def test_the_export_folder_uses_the_typed_name(self, db_path):
        """Photo handover folders are named after the driver, so they have to
        agree with the dashboard or the operator gets two answers."""
        from services.delivery import export_service

        _, aid = self._confirmed_plan_with_driver(db_path, "Huỳnh Quốc Trọng")
        _create_stop(db_path, aid, 1)

        summary = export_service.day_summary(db_path, date.today().isoformat())
        assert summary["drivers"][0]["driver_name"] == "Huỳnh Quốc Trọng"
        assert summary["drivers"][0]["folder"].startswith("HuynhQuocTrong_")
