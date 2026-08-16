"""
Mapillary coverage check — throwaway verification script, not part of the app.

Answers the one question the street-view plan rests on: for the stops your
dispatchers actually look at, is there street-level imagery near enough to be
useful, and how old is it?

Mapillary's radius search caps at 50 m. Your stop coordinates come from a
hand-typed Google Sheet via sheet_import_service.py, so a fair number will sit
further out than that. This script runs the same two-pass strategy the service
would use — radius first, then a ~200 m bounding box — and reports which pass
found the image, so the fallback earns its place with numbers rather than a
guess.

Run from the repo root:

    python check_mapillary_coverage.py

Reads MAPILLARY_TOKEN from .env. Never prints the token. Delete this file once
the question is answered.
"""
import json
import math
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

GRAPH = "https://graph.mapillary.com/images"
SAMPLE_SIZE = 25
TIMEOUT_S = 25

# Matches the app's own haversine (app/utils/geo.py), so a distance printed
# here and one computed by the service agree.
EARTH_RADIUS_M = 6371000


def read_token(path=".env"):
    """Pull MAPILLARY_TOKEN out of .env without importing dotenv.

    requirements.txt in this repo is UTF-16, so encoding is not assumed
    anywhere that reads a file by hand.
    """
    try:
        raw = open(path, "rb").read()
    except FileNotFoundError:
        sys.exit(f"No {path} found. Run this from the repo root.")

    text = None
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    if text is None:
        sys.exit(f"Could not decode {path}.")

    m = re.search(r"^\s*MAPILLARY_TOKEN\s*=\s*(.+?)\s*$", text, re.M)
    if not m:
        sys.exit("MAPILLARY_TOKEN is not set in .env.")
    return m.group(1).strip().strip('"').strip("'")


def distance_m(lat1, lng1, lat2, lng2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def query(token, params):
    url = f"{GRAPH}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Authorization": f"OAuth {token}"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        return json.load(resp)


FIELDS = "id,captured_at,is_pano,geometry"


def nearest_image(token, lat, lng):
    """Radius search, then bbox fallback. Returns (image, how, metres) or None."""
    body = query(token, {"fields": FIELDS, "lat": lat, "lng": lng,
                         "radius": 50, "limit": 1})
    data = body.get("data") or []
    if data:
        lng2, lat2 = data[0]["geometry"]["coordinates"]
        return data[0], "radius", distance_m(lat, lng, lat2, lng2)

    # ~200 m box. The API rejects a bbox of 0.01 degrees square or larger, and
    # this is two orders of magnitude inside that.
    dlat = 100 / 111000
    dlng = 100 / (111000 * math.cos(math.radians(lat)))
    body = query(token, {
        "fields": FIELDS,
        "bbox": f"{lng - dlng},{lat - dlat},{lng + dlng},{lat + dlat}",
        "limit": 50,
    })
    data = body.get("data") or []
    if not data:
        return None

    best = None
    for image in data:
        lng2, lat2 = image["geometry"]["coordinates"]
        d = distance_m(lat, lng, lat2, lng2)
        if best is None or d < best[2]:
            best = (image, "bbox", d)
    return best


def load_stops(limit):
    """Distinct stop locations, most-used first — what dispatchers actually see."""
    con = sqlite3.connect("routing_system.db")
    try:
        rows = con.execute(
            """SELECT station_name, lat, lng, COUNT(*) AS uses
                 FROM delivery_plan_stops
                WHERE lat IS NOT NULL AND lng IS NOT NULL
             GROUP BY ROUND(lat, 4), ROUND(lng, 4)
             ORDER BY uses DESC
                LIMIT ?""",
            (limit,),
        ).fetchall()
    finally:
        con.close()
    return rows


def main():
    token = read_token()

    try:
        query(token, {"fields": "id", "lat": 10.7725, "lng": 106.6980,
                      "radius": 50, "limit": 1})
    except urllib.error.HTTPError as e:
        detail = e.read()[:400].decode("utf-8", "replace")
        sys.exit(f"Token rejected by Mapillary (HTTP {e.code}).\n{detail}")
    except Exception as e:  # noqa: BLE001 — surface anything, this is a check
        sys.exit(f"Could not reach Mapillary: {type(e).__name__}: {e}")
    print("Token accepted by Mapillary.\n")

    stops = load_stops(SAMPLE_SIZE)
    if not stops:
        sys.exit("No stops with coordinates in delivery_plan_stops.")

    hits_radius = hits_bbox = misses = 0
    panos = 0
    ages = []

    print(f"{'stop':<36}{'uses':>5}{'found':>8}{'dist':>8}  captured")
    print("-" * 78)

    for name, lat, lng, uses in stops:
        label = (name or "?")[:34]
        try:
            found = nearest_image(token, lat, lng)
        except Exception as e:  # noqa: BLE001
            print(f"{label:<36}{uses:>5}  ERROR {type(e).__name__}: {e}")
            continue

        if not found:
            misses += 1
            print(f"{label:<36}{uses:>5}{'—':>8}{'—':>8}  no imagery within 200 m")
            continue

        image, how, metres = found
        when_s = image["captured_at"] / 1000
        when = time.strftime("%Y-%m", time.gmtime(when_s))
        ages.append((time.time() - when_s) / 31557600)  # years
        if image.get("is_pano"):
            panos += 1
        if how == "radius":
            hits_radius += 1
        else:
            hits_bbox += 1
        pano_tag = " 360°" if image.get("is_pano") else ""
        print(f"{label:<36}{uses:>5}{how:>8}{int(metres):>6} m  {when}{pano_tag}")

    total = len(stops)
    print("-" * 78)
    print(f"within 50 m (radius search): {hits_radius}/{total}")
    print(f"only via ~200 m bbox fallback: {hits_bbox}/{total}")
    print(f"no imagery at all: {misses}/{total}")
    if ages:
        ages.sort()
        median = ages[len(ages) // 2]
        print(f"panoramic (360°): {panos}/{len(ages)} of the images found")
        print(f"median image age: {median:.1f} years  (oldest {max(ages):.1f})")

    print()
    if hits_radius + hits_bbox == 0:
        print("Verdict: no usable coverage. Street view is not worth building.")
    elif misses > total / 2:
        print("Verdict: thin coverage. Worth building, but expect the panel to say")
        print("'no imagery here' more often than it shows a photo.")
    elif hits_bbox > hits_radius:
        print("Verdict: usable, and the bbox fallback is doing the heavy lifting —")
        print("the 50 m radius cap alone would miss most of your stops.")
    else:
        print("Verdict: good coverage. The 50 m radius search carries most stops.")


if __name__ == "__main__":
    main()
