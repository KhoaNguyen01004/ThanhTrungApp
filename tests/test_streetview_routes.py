"""Route- and service-layer tests for /api/streetview (Mapillary lookup).

Why this file exists
--------------------
``/api/streetview`` proxies a third-party API the test environment cannot
reach, and the one distinction the whole feature rests on is invisible from a
happy-path test: **"there is no imagery here" and "Mapillary could not be
asked" must not look the same to the dashboard.**

If those two collapse into one response, an expired token or a Mapillary
outage renders as "this address has no street view" on every stop at once, the
panel looks like it is working, and nobody finds out until a dispatcher
mentions months later that street view "never has anything". So the split —
200 ``found: false`` versus 503 — is asserted from both directions here, and
is the reason the service raises for one and returns ``None`` for the other
rather than returning a falsy value for both.

The second thing under test is the two-pass search. Mapillary caps its radius
search at 50 m; this fleet's stop coordinates are hand-typed into the
manager's Google Sheet, so a meaningful share of stops sit further out than
that from the nearest photo. The bbox fallback is what makes the feature
useful rather than a button that usually says no, and
``test_falls_back_to_bbox_and_picks_the_nearest`` pins both that it runs and
that it picks the closest candidate rather than the first one returned.

Every Mapillary call is stubbed at ``requests.get``. Nothing here touches the
network, and no test needs a real MAPILLARY_TOKEN.
"""
import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app                          # noqa: E402
from app.services import streetview                 # noqa: E402


# Ho Chi Minh City, Ben Thanh market — the coordinate the coverage check uses.
LAT, LNG = 10.7725, 106.6980


@pytest.fixture(scope="module")
def app():
    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def token(monkeypatch):
    """A configured token by default; the un-configured case opts out."""
    monkeypatch.setattr(streetview.config, "MAPILLARY_TOKEN", "MLY|test|token")


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.ok = 200 <= status < 400

    def json(self):
        if self._payload is _UNREADABLE:
            raise ValueError("not json")
        return self._payload


_UNREADABLE = object()


def image(image_id, lat, lng, captured_at=1700000000000, is_pano=False):
    """A Graph API image entity. Note coordinates are [lng, lat], as GeoJSON."""
    return {
        "id": image_id,
        "captured_at": captured_at,
        "is_pano": is_pano,
        "compass_angle": 90,
        "geometry": {"type": "Point", "coordinates": [lng, lat]},
    }


def stub_get(monkeypatch, *responses):
    """Queue one FakeResponse per call, and record the params each call used."""
    calls = []
    queue = list(responses)

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append({"url": url, "params": params or {}, "headers": headers or {}})
        if not queue:
            raise AssertionError(f"unexpected extra Mapillary call: {params}")
        result = queue.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(streetview.requests, "get", fake_get)
    return calls


# --- Parameter validation ------------------------------------------------

@pytest.mark.parametrize("query", [
    "",
    "?lat=10.77",
    "?lng=106.69",
    "?lat=abc&lng=106.69",
    "?lat=10.77&lng=",
    "?lat=nan&lng=106.69",
    "?lat=inf&lng=106.69",
    "?lat=91&lng=106.69",
    "?lat=10.77&lng=181",
])
def test_bad_parameters_are_rejected(client, query):
    """400 before any Mapillary call — a malformed request is not an outage.

    NaN and infinity are in here because ``float("nan")`` succeeds. Without the
    isfinite check they reach the API as the literal string "nan" and come back
    as an opaque upstream error, which the endpoint would then report as a 503
    and blame on Mapillary.
    """
    response = client.get(f"/api/streetview{query}")
    assert response.status_code == 400
    assert response.get_json()["found"] is False


def test_valid_parameters_are_not_rejected(client, monkeypatch):
    """Guards the validation above against becoming too strict."""
    stub_get(monkeypatch, FakeResponse({"data": [image("1", LAT, LNG)]}))
    assert client.get(f"/api/streetview?lat={LAT}&lng={LNG}").status_code == 200


# --- Configuration -------------------------------------------------------

def test_missing_token_is_503_not_a_crash(client, monkeypatch):
    """A deployment with no MAPILLARY_TOKEN degrades; it does not 500."""
    monkeypatch.setattr(streetview.config, "MAPILLARY_TOKEN", None)
    response = client.get(f"/api/streetview?lat={LAT}&lng={LNG}")
    assert response.status_code == 503
    assert response.get_json()["found"] is False


def test_missing_token_does_not_stop_the_app_booting():
    """The whole reason MAPILLARY_TOKEN is not in config.required_env_vars.

    That list raises RuntimeError at import time. Street view is a convenience;
    the dispatch board must still boot without it.
    """
    from app import config
    assert "MAPILLARY_TOKEN" not in config.required_env_vars


def test_token_is_never_echoed_to_the_client(client, monkeypatch):
    """The token is a server-side credential and must not leak into a response.

    It is sent as an Authorization header rather than a query parameter partly
    so it stays out of logs; a response body carrying it would undo that.
    """
    stub_get(monkeypatch, FakeResponse({"data": [image("1", LAT, LNG)]}))
    body = client.get(f"/api/streetview?lat={LAT}&lng={LNG}").get_data(as_text=True)
    assert "MLY|" not in body
    assert "test|token" not in body


def test_token_is_sent_as_an_authorization_header(monkeypatch):
    stub_calls = stub_get(monkeypatch, FakeResponse({"data": [image("1", LAT, LNG)]}))
    streetview.find_nearest_image(LAT, LNG)
    assert stub_calls[0]["headers"]["Authorization"] == "OAuth MLY|test|token"
    assert "access_token" not in stub_calls[0]["params"]


# --- The two-pass search -------------------------------------------------

def test_radius_hit_returns_immediately(client, monkeypatch):
    """One call, not two — the bbox pass must not run when the first succeeds."""
    calls = stub_get(monkeypatch, FakeResponse({"data": [image("777", LAT, LNG)]}))
    body = client.get(f"/api/streetview?lat={LAT}&lng={LNG}").get_json()

    assert len(calls) == 1
    assert calls[0]["params"]["radius"] == streetview.RADIUS_CAP_M
    assert body["found"] is True
    assert body["image"]["image_id"] == "777"
    assert body["image"]["found_by"] == "radius"


def test_falls_back_to_bbox_and_picks_the_nearest(client, monkeypatch):
    """The pass that makes the feature usable on hand-typed coordinates.

    Mapillary returns bbox results in its own order, so the nearest one is
    deliberately *not* first here — returning ``data[0]`` would pass a weaker
    version of this test and show the dispatcher a photo 90 m away when one
    sits 20 m away.
    """
    far = image("far", LAT + 0.0008, LNG)      # ~89 m north
    near = image("near", LAT + 0.00018, LNG)   # ~20 m north
    calls = stub_get(
        monkeypatch,
        FakeResponse({"data": []}),                  # radius: nothing
        FakeResponse({"data": [far, near]}),         # bbox: near is second
    )

    body = client.get(f"/api/streetview?lat={LAT}&lng={LNG}").get_json()

    assert len(calls) == 2
    assert "bbox" in calls[1]["params"]
    assert "radius" not in calls[1]["params"]
    assert body["image"]["image_id"] == "near"
    assert body["image"]["found_by"] == "bbox"
    assert 15 < body["image"]["distance_m"] < 25


def test_widens_to_a_second_box_before_giving_up(client, monkeypatch):
    """The pass added 2026-08-16, and the reason it exists.

    Most of this fleet's stops are down lanes and yards no Mapillary driver
    entered. The nearest imagery is on the arterial road the lane comes off,
    typically a few hundred metres away — which is exactly the image a
    dispatcher wants, because it is how the driver approaches. The original
    150 m ceiling discarded it.
    """
    calls = stub_get(
        monkeypatch,
        FakeResponse({"data": []}),                                   # radius 50 m
        FakeResponse({"data": []}),                                   # bbox 100 m
        FakeResponse({"data": [image("arterial", LAT + 0.003, LNG)]}),  # ~333 m
    )

    body = client.get(f"/api/streetview?lat={LAT}&lng={LNG}").get_json()

    assert len(calls) == 3
    assert body["found"] is True
    assert body["image"]["image_id"] == "arterial"
    assert body["image"]["found_by"] == "bbox_wide"
    assert 300 < body["image"]["distance_m"] < 360


def test_the_narrow_box_wins_before_the_wide_one_is_tried(client, monkeypatch):
    """A hit at 100 m must not cost a second, larger query."""
    calls = stub_get(
        monkeypatch,
        FakeResponse({"data": []}),
        FakeResponse({"data": [image("near", LAT + 0.0005, LNG)]}),
    )
    body = client.get(f"/api/streetview?lat={LAT}&lng={LNG}").get_json()

    assert len(calls) == 2
    assert body["image"]["found_by"] == "bbox"


def test_every_bbox_is_within_mapillarys_size_limit(monkeypatch):
    """Mapillary rejects a bbox of 0.01 degrees square or larger.

    The wide pass sits deliberately close to that ceiling, so this asserts both
    boxes rather than only the first — widening it any further silently breaks
    every lookup that reaches the second pass.
    """
    calls = stub_get(
        monkeypatch,
        FakeResponse({"data": []}),
        FakeResponse({"data": []}),
        FakeResponse({"data": []}),
    )
    streetview.find_nearest_image(LAT, LNG)

    boxes = [c["params"]["bbox"] for c in calls if "bbox" in c["params"]]
    assert len(boxes) == 2
    for box in boxes:
        west, south, east, north = (float(v) for v in box.split(","))
        assert (east - west) < 0.01, f"bbox too wide: {box}"
        assert (north - south) < 0.01, f"bbox too tall: {box}"
        assert west < LNG < east
        assert south < LAT < north


def test_no_imagery_is_a_200_not_an_error(client, monkeypatch):
    """An uncovered alley is a finding, not a failure.

    404 here would make DASH.api's fetch wrapper throw, and the panel would
    report a broken server for what is an ordinary and expected answer in a
    city mapped by volunteer drivers.
    """
    stub_get(
        monkeypatch,
        FakeResponse({"data": []}),
        FakeResponse({"data": []}),
        FakeResponse({"data": []}),
    )
    response = client.get(f"/api/streetview?lat={LAT}&lng={LNG}")

    assert response.status_code == 200
    body = response.get_json()
    assert body["found"] is False
    assert body["reason"] == "no_imagery"
    assert "error" not in body


def test_imagery_beyond_the_ceiling_is_treated_as_no_imagery(client, monkeypatch):
    """A photo a kilometre away answers a question nobody asked.

    The ceiling is generous (600 m) because a lane's arterial road is genuinely
    useful, but it is still a ceiling: a click that lands in open country
    should say so rather than open a highway somewhere else.
    """
    stub_get(
        monkeypatch,
        FakeResponse({"data": []}),
        FakeResponse({"data": []}),
        FakeResponse({"data": [image("far", LAT + 0.0085, LNG)]}),  # ~945 m
    )
    body = client.get(f"/api/streetview?lat={LAT}&lng={LNG}").get_json()
    assert body["found"] is False
    assert body["reason"] == "no_imagery"


# --- Upstream failure ----------------------------------------------------

@pytest.mark.parametrize("failure", [
    requests.Timeout("timed out"),
    requests.ConnectionError("dns failure"),
])
def test_transport_failure_is_503(client, monkeypatch, failure):
    stub_get(monkeypatch, failure)
    response = client.get(f"/api/streetview?lat={LAT}&lng={LNG}")
    assert response.status_code == 503
    assert response.get_json()["found"] is False


def test_mapillary_error_object_is_503(client, monkeypatch):
    """Mapillary reports throttling as a 4xx carrying an `error` object.

    The message is the only thing separating "rate limited" from "bad token",
    so it is surfaced rather than flattened into a generic failure.
    """
    stub_get(monkeypatch, FakeResponse({
        "error": {"message": "Application request limit reached", "code": 4},
    }, status=429))

    response = client.get(f"/api/streetview?lat={LAT}&lng={LNG}")
    assert response.status_code == 503
    assert "limit reached" in response.get_json()["error"]


def test_http_error_without_a_body_is_503(client, monkeypatch):
    stub_get(monkeypatch, FakeResponse(_UNREADABLE, status=500))
    assert client.get(f"/api/streetview?lat={LAT}&lng={LNG}").status_code == 503


def test_expired_token_does_not_read_as_no_imagery(client, monkeypatch):
    """The failure mode this whole file exists for.

    A 401 must not render as "this address has no street view" — that is the
    version of the bug nobody reports, because the panel looks like it is
    working correctly on every stop.
    """
    stub_get(monkeypatch, FakeResponse({
        "error": {"message": "Invalid OAuth access token", "type": "OAuthException"},
    }, status=401))

    response = client.get(f"/api/streetview?lat={LAT}&lng={LNG}")
    body = response.get_json()

    assert response.status_code == 503
    assert body.get("reason") != "no_imagery"
    assert "error" in body


# --- Response shape ------------------------------------------------------

def test_geojson_coordinates_are_read_lng_lat(client, monkeypatch):
    """[lng, lat], not [lat, lng].

    Both orderings are valid floats and neither raises, so reversing them fails
    silently — the distance would come out in the thousands of kilometres and
    every stop would report no imagery.
    """
    stub_get(monkeypatch, FakeResponse({"data": [image("1", LAT + 0.0009, LNG)]}))
    body = client.get(f"/api/streetview?lat={LAT}&lng={LNG}").get_json()

    assert abs(body["image"]["lat"] - (LAT + 0.0009)) < 1e-9
    assert abs(body["image"]["lng"] - LNG) < 1e-9
    assert body["image"]["distance_m"] < 200


def test_response_carries_what_the_panel_renders(client, monkeypatch):
    stub_get(monkeypatch, FakeResponse({
        "data": [image("550092599700936", LAT, LNG,
                       captured_at=1709164800000, is_pano=True)],
    }))
    img = client.get(f"/api/streetview?lat={LAT}&lng={LNG}").get_json()["image"]

    assert img["image_id"] == "550092599700936"
    assert img["captured_at"] == 1709164800000  # ms since epoch, unformatted
    assert img["is_pano"] is True
    assert "550092599700936" in img["embed_url"]
    assert "style=photo" in img["embed_url"]
    assert img["page_url"]


def test_malformed_geometry_does_not_crash(client, monkeypatch):
    """Defensive: a scraped-then-processed feed can always surprise you."""
    stub_get(monkeypatch, FakeResponse({"data": [{
        "id": "1", "captured_at": None, "geometry": {"coordinates": []},
    }]}))
    body = client.get(f"/api/streetview?lat={LAT}&lng={LNG}").get_json()

    assert body["found"] is True
    assert body["image"]["distance_m"] is None
    assert body["image"]["captured_at"] is None


def test_route_is_registered_inside_create_app(app):
    """The 2026-08-07 lesson: a route outside create_app() is a production 404."""
    rules = {str(r.rule): r.endpoint for r in app.url_map.iter_rules()}
    assert rules.get("/api/streetview") == "core.api_streetview"
