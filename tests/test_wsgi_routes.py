"""Guards that the production entry point serves the same routes as dev.

Why this file exists
--------------------
On 2026-08-07 the deployed service returned 404 for ``/`` — and for
``/locations``, all four ``/delivery/*`` pages, ``/api/vehicles``,
``/api/geocode`` and the entire manual-location CRUD — while every blueprint
route answered 200 and ``python app.py`` worked perfectly on the developer's
machine.

The cause was structural, not a typo. ``app.py`` called ``create_app()`` and
then registered ~15 routes on the returned object with ``@app.route``.
``wsgi.py`` — the Gunicorn target, and the only thing production runs — calls
``create_app()`` and nothing else. Python never executes ``app.py`` in that
path, so those decorators never ran. Dev and prod were serving two different
applications, and nothing in the 548-test suite could tell, because every
existing route test builds its client from ``create_app()`` and therefore
shared the blind spot exactly.

So the assertion that matters is not "does ``/`` work" but "is anything
registered outside ``create_app()``". The two tests below are the narrow and
the general form of that:

``test_core_routes_registered`` pins the specific 14 routes that went missing,
by rule *and* endpoint name — a rename that silently drops one is the same
outage.

``test_no_routes_registered_outside_create_app`` is the one that generalises.
It imports ``app.py`` as a module and diffs its URL map against a fresh
``create_app()``. Any future ``@app.route`` added to ``app.py`` — the habit
that caused this — fails here rather than in production. Note that it must
load ``app.py`` by file path: the ``app/`` package shadows the name, so
``import app`` resolves to the package. That collision is the root of the
whole episode, and reproducing it here is deliberate.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from app import create_app  # noqa: E402


# Rule -> endpoint. Every one of these 404'd in production on 2026-08-07.
CORE_ROUTES = {
    "/": "core.index",
    "/locations": "core.locations",
    "/delivery/new": "core.delivery_plan_builder",
    "/delivery/edit/<int:plan_id>": "core.edit_delivery_plan",
    "/delivery/dashboard": "core.delivery_dashboard",
    "/delivery/export": "core.delivery_export",
    "/api/vehicles": "core.api_vehicles",
    "/api/known-locations": "core.api_known_locations",
    "/api/manual-locations": "core.api_manual_locations",
    "/api/save-location": "core.api_save_location",
    "/api/update-location": "core.api_update_location",
    "/api/delete-location": "core.api_delete_location",
    "/api/clear-all-locations": "core.api_clear_all_locations",
    "/api/geocode": "core.api_geocode",
    # Added 2026-08-16 with the street view panel. Not one of the original 14 —
    # it postdates the outage — but it lives in the same blueprint and would
    # fail in production the same way if it ever drifted out of create_app().
    "/api/streetview": "core.api_streetview",
}

# Pages that render a template with no query parameters, so a bare GET is a
# fair smoke test. The API routes are excluded: they hit TTAS, Nominatim or
# the locations file, and are covered elsewhere.
CORE_PAGES = [
    "/",
    "/locations",
    "/delivery/new",
    "/delivery/edit/1",
    "/delivery/dashboard",
    "/delivery/export",
]


@pytest.fixture(scope="module")
def app():
    """Built the way wsgi.py builds it — create_app() and nothing more."""
    return create_app()


def _rule_map(flask_app):
    return {str(r.rule): r.endpoint for r in flask_app.url_map.iter_rules()}


def test_core_routes_registered(app):
    """All 14 formerly-missing routes are reachable from create_app() alone."""
    registered = _rule_map(app)
    missing = {
        rule: (endpoint, registered.get(rule))
        for rule, endpoint in CORE_ROUTES.items()
        if registered.get(rule) != endpoint
    }
    assert not missing, (
        "routes absent or renamed in create_app() — production will 404 on "
        f"these even though `python app.py` serves them: {missing}"
    )


@pytest.mark.parametrize("path", CORE_PAGES)
def test_core_pages_render(app, path):
    """The 404s the operator actually saw. 200, not just 'in the url_map'."""
    response = app.test_client().get(path)
    assert response.status_code == 200, (
        f"GET {path} returned {response.status_code} from a create_app()-only "
        "application, which is exactly what Gunicorn serves"
    )


def test_no_routes_registered_outside_create_app(app):
    """app.py must add no routes of its own — it is a dev runner, not a router.

    This is the regression guard proper. It fails on the *next* ``@app.route``
    added to app.py, before that route can go missing in production.
    """
    spec = importlib.util.spec_from_file_location(
        "_app_py_entry", _REPO_ROOT / "app.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["_app_py_entry"] = module
    try:
        spec.loader.exec_module(module)
        extra = set(_rule_map(module.app)) - set(_rule_map(app))
    finally:
        sys.modules.pop("_app_py_entry", None)

    assert not extra, (
        "app.py registers routes that create_app() does not, so `gunicorn "
        f"wsgi:app` will not serve them: {sorted(extra)}. Move them into a "
        "blueprint registered inside create_app() (see app/routes/core.py)."
    )
