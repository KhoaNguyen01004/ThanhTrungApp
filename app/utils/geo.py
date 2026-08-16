"""
Geo utility functions — distance, polygon centroid/containment, safe parsing.

Extracted from app.py (Section 6.4.1, Phase 6).
"""
import math


def get_distance_meters(lat1, lon1, lat2, lon2):
    """Calculate distance between two points in meters using Haversine formula."""
    R = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def calculate_polygon_centroid(polygon):
    """Calculate centroid (center) of a polygon given as list of [lat, lng] points.
    Uses the formula for centroid of a planar polygon: average of vertices weighted by the area of each sub-triangle."""
    if not polygon or len(polygon) < 3:
        return None

    # Ensure polygon is closed
    closed_polygon = polygon + [polygon[0]]
    signed_area = 0.0
    sum_lat = 0.0
    sum_lng = 0.0

    for i in range(len(closed_polygon) - 1):
        lat_i, lng_i = closed_polygon[i]
        lat_j, lng_j = closed_polygon[i + 1]

        term = (lat_i * lng_j) - (lat_j * lng_i)
        signed_area += term
        sum_lat += (lat_i + lat_j) * term
        sum_lng += (lng_i + lng_j) * term

    signed_area = signed_area / 2.0

    if abs(signed_area) < 1e-10:  # Degenerate polygon, just return average of vertices
        avg_lat = sum(p[0] for p in polygon) / len(polygon)
        avg_lng = sum(p[1] for p in polygon) / len(polygon)
        return [avg_lat, avg_lng]

    centroid_lat = sum_lat / (6 * signed_area)
    centroid_lng = sum_lng / (6 * signed_area)
    return [centroid_lat, centroid_lng]


def calculate_multi_polygon_centroid(polygons):
    """Calculate centroid of a multi-polygon (multiple polygons), returns weighted average of all polygon centroids."""
    if not polygons or not isinstance(polygons, list) or len(polygons) == 0:
        return None

    centroids = []
    areas = []

    for polygon in polygons:
        centroid = calculate_polygon_centroid(polygon)
        if centroid:
            centroids.append(centroid)
            # Calculate area for weighting
            closed_poly = polygon + [polygon[0]]
            area = 0.0
            for i in range(len(closed_poly) - 1):
                lat_i, lng_i = closed_poly[i]
                lat_j, lng_j = closed_poly[i + 1]
                area += (lat_i * lng_j) - (lat_j * lng_i)
            areas.append(abs(area / 2.0))

    if len(centroids) == 0:
        return None

    total_area = sum(areas)
    if total_area < 1e-10:  # All degenerate, average the centroids
        avg_lat = sum(c[0] for c in centroids) / len(centroids)
        avg_lng = sum(c[1] for c in centroids) / len(centroids)
        return [avg_lat, avg_lng]

    weighted_lat = 0.0
    weighted_lng = 0.0
    for i in range(len(centroids)):
        weight = areas[i] / total_area
        weighted_lat += centroids[i][0] * weight
        weighted_lng += centroids[i][1] * weight
    return [weighted_lat, weighted_lng]


def is_point_in_polygon(lat, lng, polygon):
    """Check if point (lat, lng) is inside polygon using Ray Casting algorithm."""
    if not polygon or len(polygon) < 3:
        return False

    inside = False
    n = len(polygon)
    x = lng
    y = lat

    for i in range(n):
        j = (i - 1) % n
        xi, yi = polygon[i][1], polygon[i][0]
        xj, yj = polygon[j][1], polygon[j][0]

        intersect = ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi)
        if intersect:
            inside = not inside
    return inside


def is_point_in_location(lat, lng, location):
    """Check if point (lat, lng) is inside any polygon of a location."""
    if not location:
        return False

    polygons_to_check = []
    if location.get("polygons") and isinstance(location.get("polygons"), list):
        polygons_to_check = location["polygons"]
    elif location.get("corners") and isinstance(location.get("corners"), list):
        polygons_to_check = [location["corners"]]
    else:
        return False

    for polygon in polygons_to_check:
        if is_point_in_polygon(lat, lng, polygon):
            return True
    return False


def get_location_centroid(location):
    """Get centroid from a location object, handling single polygon, multi-polygon, or point."""
    if not location:
        return None
    if "polygons" in location and isinstance(location["polygons"], list):
        centroid = calculate_multi_polygon_centroid(location["polygons"])
        if centroid:
            return {"lat": centroid[0], "lng": centroid[1]}
    if "corners" in location:
        centroid = calculate_polygon_centroid(location["corners"])
        if centroid:
            return {"lat": centroid[0], "lng": centroid[1]}
    if "latitude" in location and "longitude" in location:
        return {"lat": location["latitude"], "lng": location["longitude"]}
    return None


def safe_float(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def clean_text(value):
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    try:
        return text.encode("latin1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text
