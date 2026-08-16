"""
Manual location file I/O and normalization.

Extracted from app.py. Lives in app/services/ (not one of the report's
named modules) because app/__init__.py's create_app() must call
load_known_locations() to populate state.known_locations at startup —
putting these functions in app.py itself (the remaining core routes file)
would create a circular import between app.py and app/__init__.py.
"""
import json
import math
import os

from app import config


def read_manual_locations():
    if not os.path.exists(config.MANUAL_LOCATIONS_FILE):
        return {}
    try:
        with open(config.MANUAL_LOCATIONS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"Error reading manual locations file: {e}")
        return {}


def write_manual_locations(locations):
    with open(config.MANUAL_LOCATIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(locations, f, indent=2, ensure_ascii=False)


def parse_location_payload(data):
    name = (data.get("name") or "").strip()
    corners = data.get("corners")

    if not name:
        return None, "Location name is required"

    if not corners or not isinstance(corners, list) or len(corners) < 3:
        return None, "At least 3 corners are required"

    try:
        parsed_corners = []
        for corner in corners:
            if not isinstance(corner, list) or len(corner) < 2:
                return None, "Each corner must be [lat, lng]"
            lat = float(corner[0])
            lng = float(corner[1])
            if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
                return None, "Invalid coordinate range"
            parsed_corners.append([lat, lng])
    except (TypeError, ValueError):
        return None, "Invalid corner coordinates"

    return {"name": name, "corners": parsed_corners}, None


def load_known_locations():
    normalized = {}
    for name, location in read_manual_locations().items():
        try:
            # Handle both old format (single corners) and new format (multiple polygons)
            if "polygons" in location and isinstance(location["polygons"], list):
                normalized[name] = {
                    "polygons": [
                        [[float(c[0]), float(c[1])] for c in polygon]
                        for polygon in location["polygons"]
                    ],
                    "type": "multi_polygon"
                }
            elif "corners" in location and len(location["corners"]) >= 3:
                normalized[name] = {
                    "polygons": [
                        [[float(c[0]), float(c[1])] for c in location["corners"]]
                    ],
                    "type": "multi_polygon"
                }
            elif "latitude" in location and "longitude" in location:
                lat = float(location["latitude"])
                lng = float(location["longitude"])
                radius_km = float(location.get("radius_km", config.DEFAULT_RADIUS_KM))
                delta_lat = radius_km / 111
                delta_lng = radius_km / (111 * math.cos(math.radians(lat)))
                normalized[name] = {
                    "polygons": [
                        [[lat + delta_lat, lng - delta_lng],
                         [lat + delta_lat, lng + delta_lng],
                         [lat - delta_lat, lng + delta_lng],
                         [lat - delta_lat, lng - delta_lng]]
                    ],
                    "type": "multi_polygon"
                }
        except (KeyError, TypeError, ValueError):
            continue
    return normalized
