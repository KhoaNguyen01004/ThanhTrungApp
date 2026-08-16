"""
Tests for app/services/routing.py — the shared ORS transport.

Covers the two things phase A of docs/VEHICLE_ROUTING_PLAN.md is responsible
for: every directions request is a POST carrying avoid_borders, and "no route
exists" is never reported as "ORS is broken".
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import routing


def _ok_response(mock_post, distance=15000, duration=900,
                 coordinates=((106.6, 10.8), (106.7, 10.9))):
    mock_post.return_value.status_code = 200
    mock_post.return_value.ok = True
    mock_post.return_value.json.return_value = {
        "features": [{
            "geometry": {"coordinates": [list(c) for c in coordinates]},
            "properties": {"segments": [{"distance": distance, "duration": duration}]},
        }]
    }
    return mock_post


def _error_response(mock_post, status, code=None, message="", text=""):
    mock_post.return_value.status_code = status
    mock_post.return_value.ok = 200 <= status < 400
    mock_post.return_value.text = text
    if code is None:
        mock_post.return_value.json.return_value = {}
    else:
        mock_post.return_value.json.return_value = {"error": {"code": code, "message": message}}
    return mock_post


class TestRequestDirections:
    @patch("app.services.routing.requests.post")
    def test_posts_to_the_geojson_endpoint(self, mock_post):
        _ok_response(mock_post)
        routing.request_directions("k", "https://api.ors/v2/directions",
                                   [[106.6, 10.8], [106.7, 10.9]])
        args, kwargs = mock_post.call_args
        # GET cannot carry an options body at all — this must be a POST, and it
        # must be the /geojson result type, whose features carry the same
        # `segments` both call sites have always parsed.
        assert args[0] == "https://api.ors/v2/directions/driving-hgv/geojson"
        assert kwargs["headers"]["Authorization"] == "k"

    @patch("app.services.routing.requests.post")
    def test_avoid_borders_is_sent_on_every_request(self, mock_post):
        _ok_response(mock_post)
        routing.request_directions("k", "https://api.ors/v2/directions",
                                   [[106.6, 10.8], [106.7, 10.9]])
        assert mock_post.call_args.kwargs["json"]["options"]["avoid_borders"] == "all"

    @patch("app.services.routing.requests.post")
    def test_caller_options_are_merged_but_cannot_drop_avoid_borders(self, mock_post):
        _ok_response(mock_post)
        routing.request_directions(
            "k", "https://api.ors/v2/directions", [[106.6, 10.8], [106.7, 10.9]],
            options={"avoid_borders": "controlled",
                     "profile_params": {"restrictions": {"height": 3.2}}},
        )
        options = mock_post.call_args.kwargs["json"]["options"]
        # The border rule is absolute: a caller relaxing restrictions (phase
        # C's degraded retry) must not be able to relax this one with them.
        assert options["avoid_borders"] == "all"
        assert options["profile_params"]["restrictions"]["height"] == 3.2

    @patch("app.services.routing.requests.post")
    def test_returns_distance_duration_and_coordinates(self, mock_post):
        _ok_response(mock_post, distance=15000, duration=900)
        result = routing.request_directions("k", "https://api.ors/v2/directions",
                                            [[106.6, 10.8], [106.7, 10.9]])
        assert result["distance_m"] == 15000
        assert result["duration_s"] == 900
        # Left in ORS [lng, lat] order — flipping for Leaflet is the caller's job.
        assert result["coordinates"] == [[106.6, 10.8], [106.7, 10.9]]

    def test_missing_configuration_is_unavailable_not_a_crash(self):
        with pytest.raises(routing.OrsUnavailableError):
            routing.request_directions("", "https://api.ors/v2/directions", [[1, 2], [3, 4]])
        with pytest.raises(routing.OrsUnavailableError):
            routing.request_directions("k", "", [[1, 2], [3, 4]])

    @patch("app.services.routing.requests.post")
    def test_2009_raises_no_route_despite_the_404(self, mock_post):
        _error_response(mock_post, 404, code=2009,
                        message="Route could not be found between locations.")
        with pytest.raises(routing.OrsNoRouteError) as excinfo:
            routing.request_directions("k", "https://api.ors/v2/directions", [[1, 2], [3, 4]])
        assert excinfo.value.code == 2009

    @patch("app.services.routing.requests.post")
    def test_2010_point_not_found_also_raises_no_route(self, mock_post):
        _error_response(mock_post, 404, code=2010, message="Point was not found.")
        with pytest.raises(routing.OrsNoRouteError):
            routing.request_directions("k", "https://api.ors/v2/directions", [[1, 2], [3, 4]])

    @patch("app.services.routing.requests.post")
    def test_other_internal_errors_are_unavailable(self, mock_post):
        _error_response(mock_post, 500, code=2099, message="Unknown internal error.")
        with pytest.raises(routing.OrsUnavailableError):
            routing.request_directions("k", "https://api.ors/v2/directions", [[1, 2], [3, 4]])

    @patch("app.services.routing.requests.post")
    def test_transport_failure_is_unavailable(self, mock_post):
        mock_post.side_effect = requests.RequestException("connection reset")
        with pytest.raises(routing.OrsUnavailableError):
            routing.request_directions("k", "https://api.ors/v2/directions", [[1, 2], [3, 4]])

    @patch("app.services.routing.requests.post")
    def test_200_with_no_features_is_no_route_not_a_crash(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.ok = True
        mock_post.return_value.json.return_value = {"features": []}
        with pytest.raises(routing.OrsNoRouteError):
            routing.request_directions("k", "https://api.ors/v2/directions", [[1, 2], [3, 4]])

    @patch("app.services.routing.requests.post")
    def test_unparseable_body_is_unavailable(self, mock_post):
        mock_post.return_value.status_code = 502
        mock_post.return_value.ok = False
        mock_post.return_value.text = "<html>Bad Gateway</html>"
        mock_post.return_value.json.side_effect = ValueError("not json")
        with pytest.raises(routing.OrsUnavailableError):
            routing.request_directions("k", "https://api.ors/v2/directions", [[1, 2], [3, 4]])


class TestGetRouteCoords:
    """The trips.py entry point. Its three original keys must not change
    shape — a background thread depends on them — but it now says which of the
    four outcomes produced them."""

    @patch("app.services.routing.config")
    @patch("app.services.routing.requests.post")
    def test_success_reports_ok_and_converts_to_km(self, mock_post, mock_config):
        mock_config.ORS_API_KEY = "k"
        mock_config.ORS_BASE_URL = "https://api.ors/v2/directions"
        _ok_response(mock_post, distance=15000, duration=900)
        route = routing.get_route_coords(106.6, 10.8, 106.7, 10.9)
        assert route["status"] == "ok"
        assert route["distance"] == 15.0
        assert route["duration"] == 900
        assert route["coordinates"] == [[106.6, 10.8], [106.7, 10.9]]

    @patch("app.services.routing.config")
    def test_no_api_key_falls_back_to_a_straight_line(self, mock_config):
        mock_config.ORS_API_KEY = None
        route = routing.get_route_coords(106.6, 10.8, 106.7, 10.9)
        assert route["status"] == "not_configured"
        assert route["duration"] is None
        assert route["coordinates"] == [[106.6, 10.8], [106.7, 10.9]]

    @patch("app.services.routing.config")
    @patch("app.services.routing.requests.post")
    def test_no_route_is_distinguishable_from_ors_being_down(self, mock_post, mock_config):
        mock_config.ORS_API_KEY = "k"
        mock_config.ORS_BASE_URL = "https://api.ors/v2/directions"

        _error_response(mock_post, 404, code=2009, message="no route")
        assert routing.get_route_coords(106.6, 10.8, 106.7, 10.9)["status"] == "no_route"

        mock_post.side_effect = requests.RequestException("down")
        assert routing.get_route_coords(106.6, 10.8, 106.7, 10.9)["status"] == "unavailable"

    @patch("app.services.routing.config")
    @patch("app.services.routing.requests.post")
    def test_failure_still_returns_the_keys_trips_py_reads(self, mock_post, mock_config):
        mock_config.ORS_API_KEY = "k"
        mock_config.ORS_BASE_URL = "https://api.ors/v2/directions"
        mock_post.side_effect = requests.RequestException("down")
        route = routing.get_route_coords(106.6, 10.8, 106.7, 10.9)
        # app/routes/trips.py indexes these three directly, from a background
        # thread, with no guard.
        assert set(["coordinates", "distance", "duration"]).issubset(route)
        assert route["distance"] > 0
