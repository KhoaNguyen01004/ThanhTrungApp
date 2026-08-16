"""
Core page routes and the leftovers that never got a domain of their own:
the index page, the main /api/vehicles list, manual-location management,
geocoding, and the delivery page shells.

Extracted from app.py (Section 6.4.1, final phase) on 2026-08-07. These
handlers previously hung off the app object in app.py, *after* create_app()
returned — which meant `gunicorn wsgi:app` never registered them, because
Gunicorn imports wsgi.py and never executes app.py. Production 404'd on
every route in this file, including "/", while `python app.py` worked
locally. Registering them inside create_app() is what makes the two entry
points serve the same application.

Note the split with services/delivery/routes.py: that blueprint owns the
delivery *API* under /api; the four /delivery/* routes here only render
templates, and stay with the other page routes.
"""
import logging
import math

from flask import Blueprint, jsonify, render_template, request

from app import config, state
from app.services import streetview
from app.services.locations import (
    parse_location_payload,
    read_manual_locations,
    write_manual_locations,
)
from app.services.ttas_client import fetch_vehicle_data, normalize_vehicle

bp = Blueprint("core", __name__)
logger = logging.getLogger(__name__)


# --- Pages ---------------------------------------------------------------

@bp.route("/")
def index():
    return render_template("index.html")


@bp.route("/locations")
def locations():
    return render_template("locations.html")


@bp.route("/delivery/new")
def delivery_plan_builder():
    return render_template("delivery-plan-builder.html", edit_plan_id=None)


@bp.route("/delivery/edit/<int:plan_id>")
def edit_delivery_plan(plan_id):
    return render_template("delivery-plan-builder.html", edit_plan_id=plan_id)


@bp.route("/delivery/dashboard")
def delivery_dashboard():
    # The Mapillary token reaches the browser on this page only.
    #
    # This is a deliberate exception to keeping it server-side, and it is
    # forced by two things that cannot be proxied usefully: the coverage vector
    # tiles (Mapillary's own docs name the query-parameter form the preferred
    # method for tiles) and MapillaryJS, which authenticates its own image
    # requests. Proxying either through Flask would put dozens of tile requests
    # per pan behind render.yaml's single synchronous Gunicorn worker, in front
    # of the dispatcher actions that actually matter.
    #
    # What is exposed is a *client* token: read access to public imagery,
    # nothing else. It is not the TTAS or Google credential class of secret.
    # The real cost of a leak is someone spending the tile quota (50k/day), so
    # if street view starts reporting quota errors, rotate it at
    # mapillary.com/dashboard/developers rather than hunting for a bug.
    #
    # /api/streetview still exists and still keeps the token server-side — the
    # nearest-image lookup runs there, and only the viewer and tiles are
    # client-authenticated.
    return render_template(
        "delivery-dashboard.html",
        mapillary_token=config.MAPILLARY_TOKEN or "",
    )


@bp.route("/delivery/export")
def delivery_export():
    return render_template("delivery-export.html")


# --- Vehicles ------------------------------------------------------------

@bp.route("/api/vehicles")
def api_vehicles():
    raw_vehicles, source, error = fetch_vehicle_data()
    cleaned = [normalize_vehicle(item) for item in raw_vehicles]
    return jsonify({
        "vehicles": cleaned,
        "source": source,
        "source_url": config.TTAS_TRACKING_PAGE_URL,
        "error": error,
    })


# --- Manual locations ----------------------------------------------------

@bp.route("/api/known-locations")
def api_known_locations():
    return jsonify(state.known_locations)


@bp.route("/api/manual-locations")
def api_manual_locations():
    return jsonify(read_manual_locations())


@bp.route("/api/save-location", methods=["POST"])
def api_save_location():
    try:
        data = request.json or {}
        parsed, error = parse_location_payload(data)
        if error:
            return jsonify({"success": False, "message": error}), 400

        name = parsed["name"]
        new_polygon = parsed["corners"]

        manual_locs = read_manual_locations()

        if name in state.known_locations:
            # Add to existing location
            existing = state.known_locations[name]
            polygons = existing.get("polygons", [])
            polygons.append(new_polygon)

            # Update both known_locations and manual_locs
            updated_loc = {"polygons": polygons, "type": "multi_polygon"}
            state.known_locations[name] = updated_loc
            manual_locs[name] = updated_loc
        else:
            # Create new location
            new_loc = {"polygons": [new_polygon], "type": "multi_polygon"}
            state.known_locations[name] = new_loc
            manual_locs[name] = new_loc

        write_manual_locations(manual_locs)

        return jsonify({"success": True, "message": f"Location '{name}' saved"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route("/api/update-location", methods=["POST"])
def api_update_location():
    try:
        data = request.json or {}
        original_name = (data.get("original_name") or "").strip()
        parsed, error = parse_location_payload(data)
        if error:
            return jsonify({"success": False, "message": error}), 400
        if not original_name:
            return jsonify({"success": False, "message": "Original name required"}), 400

        manual_locs = read_manual_locations()
        if original_name not in state.known_locations and original_name not in manual_locs:
            return jsonify({"success": False, "message": "Not found"}), 404

        name = parsed["name"]
        new_polygon = parsed["corners"]

        # Handle renaming if needed
        if name != original_name:
            if name in state.known_locations or name in manual_locs:
                return jsonify({"success": False, "message": "Name exists"}), 409

            # Move location to new name
            if original_name in manual_locs:
                manual_locs[name] = manual_locs.pop(original_name)
            if original_name in state.known_locations:
                state.known_locations[name] = state.known_locations.pop(original_name)

        # Update the polygons (replace all polygons with new one for edit mode)
        updated_loc = {"polygons": [new_polygon], "type": "multi_polygon"}
        manual_locs[name] = updated_loc
        state.known_locations[name] = updated_loc
        write_manual_locations(manual_locs)

        return jsonify({"success": True, "name": name, "location": updated_loc})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route("/api/delete-location", methods=["POST"])
def api_delete_location():
    try:
        data = request.json or {}
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"success": False, "message": "Name required"}), 400

        manual_locs = read_manual_locations()
        if name not in state.known_locations and name not in manual_locs:
            return jsonify({"success": False, "message": "Not found"}), 404

        state.known_locations.pop(name, None)
        manual_locs.pop(name, None)
        write_manual_locations(manual_locs)

        return jsonify({"success": True, "message": f"Location '{name}' deleted"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route("/api/clear-all-locations", methods=["POST"])
def api_clear_all_locations():
    try:
        state.known_locations = {}
        write_manual_locations({})

        return jsonify({"success": True, "message": "All locations cleared"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# --- Geocoding -----------------------------------------------------------

@bp.route("/api/geocode", methods=["GET"])
def api_geocode():
    query = request.args.get('q', '')
    if not query:
        return jsonify({'success': False, 'error': 'No query provided'}), 400

    try:
        import requests
        # Use Nominatim (OpenStreetMap) for free geocoding
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            'q': query,
            'format': 'json',
            'addressdetails': 1,
            'limit': 5
        }
        headers = {
            'User-Agent': 'ChiTuyen-Fleet-Management/1.0'
        }

        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()

        results = []
        for place in response.json():
            results.append({
                'name': place.get('display_name', ''),
                'lat': float(place.get('lat')),
                'lng': float(place.get('lon'))
            })

        return jsonify({'success': True, 'results': results})
    except Exception as e:
        print(f"Geocoding error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# --- Street-level imagery ------------------------------------------------

@bp.route("/api/streetview", methods=["GET"])
def api_streetview():
    """Nearest Mapillary image to a point, for the dashboard street view panel.

    Lives here for the same reason /api/geocode does: a thin proxy to a
    third-party lookup that belongs to no domain in particular. Proxied rather
    than called from the browser so MAPILLARY_TOKEN stays server-side.

    Three outcomes the caller must be able to tell apart, hence three statuses:
      200 {found: true,  image: {...}}  — imagery exists near the point
      200 {found: false, reason: ...}   — Mapillary answered, nothing is there
      503 {found: false, error: ...}    — Mapillary could not be asked

    "Nothing is there" is a 200 because it is a successful answer to a
    reasonable question. Returning 404 would make the dashboard's fetch wrapper
    throw, and an uncovered alley is not a client error.
    """
    lat_raw = request.args.get('lat')
    lng_raw = request.args.get('lng')
    if lat_raw is None or lng_raw is None:
        return jsonify({'found': False, 'error': 'lat and lng are required'}), 400

    try:
        lat = float(lat_raw)
        lng = float(lng_raw)
    except (TypeError, ValueError):
        return jsonify({'found': False, 'error': 'lat and lng must be numbers'}), 400

    # NaN and infinity survive float() and would be serialised into the URL as
    # literal "nan", which Mapillary answers with an opaque error.
    if not (math.isfinite(lat) and math.isfinite(lng)):
        return jsonify({'found': False, 'error': 'lat and lng must be finite'}), 400
    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        return jsonify({'found': False, 'error': 'lat or lng out of range'}), 400

    if not streetview.is_configured():
        # 503 rather than 500: the deployment is missing a setting, which is a
        # fixable state and not a bug in the request.
        return jsonify({
            'found': False,
            'error': 'Street view is not configured on this server',
        }), 503

    try:
        image = streetview.find_nearest_image(lat, lng)
    except streetview.StreetViewUnavailable as e:
        logger.warning("Street view lookup failed at %s,%s: %s", lat, lng, e)
        return jsonify({'found': False, 'error': str(e)}), 503

    if image is None:
        return jsonify({
            'found': False,
            'reason': 'no_imagery',
        })

    return jsonify({'found': True, 'image': image})
