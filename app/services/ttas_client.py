"""
TTAS session management, live vehicle fetching, and report scraping.

Extracted from app.py (Section 6.4.1, Phase 8). Shared across the core
/api/vehicles route, trips.py (set_destination looks up driver name), and
oil.py (fetch-km uses ensure_session/refresh_session).

fleet_session is mutable shared state — ensure_session()/refresh_session()
reassign it via `state.fleet_session = ...` (module attribute assignment),
which is visible to every module that does `import app.state as state`,
the same way the original `global fleet_session` was visible to every
function within the single app.py module.
"""
import json
import logging
import os
import re
import time
from datetime import datetime as _dt

import requests
from bs4 import BeautifulSoup

from app import config, state
from app.utils.geo import safe_float, clean_text

logger = logging.getLogger(__name__)


class LiveVehicleFetchError(Exception):
    pass


#: Accepted shapes for a TTAS position timestamp, tried in order.
#:
#: TTAS is day-first (``01/08/2026`` is 1 August), the same convention the
#: report scraper below already parses with ``%d/%m/%Y``. The ISO forms are
#: kept as a defensive fallback — they cost nothing and the test fixtures
#: have always used them.
_TTAS_TIME_FORMATS = (
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
)

#: Distinct unparseable values already logged. Bounded, because the fleet is
#: 40 vehicles polled every 12 seconds — logging each failure as it happens
#: would write ~200 lines a minute and bury everything else. One line per
#: shape is enough to identify a format change.
_unparsed_timestamps_seen = set()
_UNPARSED_LOG_LIMIT = 20


def parse_ttas_timestamp(value):
    """Parse a TTAS position timestamp into an ISO 8601 string.

    Returns ``None`` when the value is empty or in no recognised format —
    "I cannot tell how old this is", which callers must render as its own
    state rather than folding into either "fresh" or "no position".

    This exists because ``trktime`` used to be handed to the browser as raw
    text and parsed there by ``new Date()``, whose non-ISO fallback is
    **month-first**. On a day-first value that silently swapped the date:

      - on the 1st of August, ``01/08/2026`` read as 8 January, so every
        vehicle reported its GPS ~205 days stale (4920h);
      - on the 12th, ``12/08/2026`` read as 8 December — a date in the
        *future*, giving a negative age and therefore no warning at all;
      - from the 13th, ``13/08/2026`` has no month 13 and parsed as Invalid
        Date, which the dashboard's ``isNaN`` guard skipped in silence — so
        for two thirds of every month **staleness detection was simply off**,
        and a dead tracker raised nothing.

    Parsing server-side means one implementation, one calendar convention,
    and a log line when TTAS sends something new — instead of every consumer
    re-deriving it from a locale-dependent browser default.
    """
    text = clean_text(value or "")
    if not text:
        return None

    for fmt in _TTAS_TIME_FORMATS:
        try:
            return _dt.strptime(text, fmt).isoformat()
        except ValueError:
            continue

    if len(_unparsed_timestamps_seen) < _UNPARSED_LOG_LIMIT and text not in _unparsed_timestamps_seen:
        _unparsed_timestamps_seen.add(text)
        logger.warning(
            "Unrecognised TTAS timestamp format: %r — GPS age cannot be computed "
            "for vehicles reporting it. Add the format to _TTAS_TIME_FORMATS.",
            text,
        )
    return None


def create_fleet_session():
    session = requests.Session()
    session.headers.update(config.TTAS_HEADERS)
    return session


def get_session_cookies():
    from main import get_session_cookies as _get_session_cookies
    return _get_session_cookies()


def ensure_session():
    if not state.fleet_session.cookies.get_dict():
        cookies = get_session_cookies()
        if not cookies:
            raise LiveVehicleFetchError("TTAS login failed - no cookies")
        state.fleet_session.cookies.update(cookies)
    return state.fleet_session


def refresh_session():
    cookies = get_session_cookies()
    if not cookies:
        raise LiveVehicleFetchError("TTAS login failed - no cookies")
    state.fleet_session = create_fleet_session()
    state.fleet_session.cookies.update(cookies)
    return state.fleet_session


def load_last_json_document(content):
    decoder = json.JSONDecoder()
    index = 0
    last_document = None
    length = len(content)
    while index < length:
        while index < length and content[index].isspace():
            index += 1
        if index >= length:
            break
        try:
            document, next_index = decoder.raw_decode(content, index)
        except json.JSONDecodeError:
            break
        last_document = document
        index = next_index
    return last_document


def load_sample_data():
    sample_path = config.BASE_DIR / "log.json"
    if not os.path.exists(sample_path):
        return []
    try:
        with open(sample_path, encoding="utf-8") as f:
            content = f.read().strip()
    except Exception as e:
        print(f"Error reading sample: {e}")
        return []
    if not content:
        return []
    try:
        doc = json.loads(content)
    except json.JSONDecodeError:
        doc = load_last_json_document(content)
    return doc.get("d", {}).get("DevList", []) or []


def fetch_live_vehicle_data():
    last_error = None
    for attempt in range(config.MAX_LIVE_FETCH_ATTEMPTS):
        try:
            session = refresh_session() if attempt else ensure_session()
            response = session.post(config.TTAS_TRACKING_API, json=config.TTAS_PAYLOAD, timeout=15, allow_redirects=False)

            if response.status_code in (301, 302, 401, 403):
                raise LiveVehicleFetchError(f"TTAS HTTP {response.status_code}")

            response.raise_for_status()

            if "ttas_login" in response.text.lower():
                raise LiveVehicleFetchError("TTAS returned login page")

            data = response.json()
            raw_vehicles = data.get("d", {}).get("DevList", [])
            if not isinstance(raw_vehicles, list):
                raise LiveVehicleFetchError("TTAS response invalid")
            return raw_vehicles
        except Exception as e:
            last_error = e
            state.fleet_session.cookies.clear()
            time.sleep(0.5)
    raise LiveVehicleFetchError(f"{type(last_error).__name__}: {last_error}")


def fetch_vehicle_data():
    try:
        return fetch_live_vehicle_data(), "live", None
    except Exception as e:
        print(f"Live fetch failed: {type(e).__name__}: {e}")
        return load_sample_data(), "sample", str(e)


def is_lost_signal(speed_status) -> bool:
    """True when TTAS is reporting the tracker as having lost signal.

    Written `MTH:6h48'` on the tracking page — *mất tín hiệu* abbreviated,
    followed by how long it has been out. Accepts the unabbreviated form and
    tolerates the spacing/case variants, since this string is scraped rather
    than contracted.

    This is TTAS *stating* the device is unreachable, which is a stronger and
    earlier fact than inferring it from the age of the last fix — the two can
    disagree when a tracker reports late but is fine.
    """
    text = (speed_status or "").strip()
    if not text:
        return False
    upper = text.upper()
    return upper.startswith("MTH") or "MẤT TÍN HIỆU" in upper


def normalize_vehicle(raw):
    speed = clean_text(raw.get("speed", ""))
    ad3 = clean_text(raw.get("ad3", ""))
    status = clean_text(raw.get("status", ""))

    vehicle_status = "unknown"
    if speed.startswith("Chạy"):
        vehicle_status = "running"
    elif speed.startswith("Dừng"):
        vehicle_status = "stopped_engine_on" if ad3 == "Nổ" else "stopped_engine_off"
    elif is_lost_signal(speed):
        # TTAS's own declaration that the tracker has gone quiet, written
        # "MTH:6h48'" — mất tín hiệu, and how long for. Distinct from
        # "unknown", which means a phrase we could not read at all.
        vehicle_status = "lost_signal"

    license_plate = (
        clean_text(raw.get("biensoxe", ""))
        or clean_text(raw.get("plate", ""))
        or clean_text(raw.get("license_plate", ""))
        or clean_text(raw.get("car_number", ""))
        or clean_text(raw.get("vehicle_number", ""))
        or clean_text(raw.get("devicename", ""))
    )

    return {
        "id": raw.get("id", raw.get("devimei", "")),
        "device_name": license_plate,
        "driver_name": clean_text(raw.get("driver") or "Unknown"),
        "latitude": safe_float(raw.get("latitude")),
        "longitude": safe_float(raw.get("longitude")),
        "speed_status": speed,
        # last_update stays exactly as TTAS wrote it — static/js/map.js prints
        # it verbatim in the fleet map popup, and swapping the operator's
        # familiar format for ISO there is not this fix's business. Anything
        # doing *arithmetic* on the time reads last_update_iso instead, which
        # is None when the value could not be understood.
        "last_update": clean_text(raw.get("trktime", raw.get("time", ""))),
        "last_update_iso": parse_ttas_timestamp(raw.get("trktime", raw.get("time", ""))),
        "car_type": clean_text(raw.get("car_type", raw.get("tenloaihinh", ""))),
        "position": clean_text(raw.get("position", "")),
        "status": status,
        "vehicle_type": clean_text(raw.get("tenloaihinh", "")),
        "tracking_url": clean_text(raw.get("link", "")),
        "engine_status": ad3,
        "vehicle_status": vehicle_status,
    }


# ── TTAS daily-report scraping (used by oil-change KM tracker) ──────────

def _fetch_ttas_report_page(session, plate: str, from_date_ddmmyyyy: str, to_date_ddmmyyyy: str) -> str:
    """Fetch the TTAS report page for a specific vehicle and date range."""
    try:
        get_resp = session.get(config.TTAS_REPORT_URL, timeout=20)
        get_resp.raise_for_status()
        soup = BeautifulSoup(get_resp.text, "html.parser")

        def _hidden(name):
            tag = soup.find("input", {"name": name})
            return tag["value"] if tag and tag.get("value") else ""

        viewstate           = _hidden("__VIEWSTATE")
        viewstate_gen       = _hidden("__VIEWSTATEGENERATOR")
        event_validation    = _hidden("__EVENTVALIDATION")

        drp_input = soup.find("select", {"id": lambda x: x and "drpchonxe" in x.lower()})
        drp_name = drp_input["name"] if drp_input else "ctl00$ttasbaocao$drpchonxe"

        drp_value = ""
        if drp_input:
            clean_plate = re.sub(r'[^a-zA-Z0-9]', '', plate).upper()
            for opt in drp_input.find_all("option"):
                opt_text_clean = re.sub(r'[^a-zA-Z0-9]', '', opt.text).upper()
                opt_val_clean = re.sub(r'[^a-zA-Z0-9]', '', opt.get("value", "")).upper()
                if opt_text_clean == clean_plate or opt_val_clean == clean_plate:
                    drp_value = opt.get("value", "")
                    break
            if not drp_value:
                drp_value = plate
        else:
            drp_value = plate

        date_from_input = soup.find("input", {"id": lambda x: x and "txttungay" in x.lower()})
        date_to_input   = soup.find("input", {"id": lambda x: x and "txtdenngay" in x.lower()})
        btn_input       = soup.find("input", {"id": lambda x: x and "btndealscreen" in x.lower()})

        date_from_name = date_from_input["name"] if date_from_input else "ctl00$ttasbaocao$txttungay"
        date_to_name   = date_to_input["name"]   if date_to_input   else "ctl00$ttasbaocao$txtdenngay"
        btn_name       = btn_input["name"]        if btn_input       else "ctl00$ttashtkt$btndealscreen"
        btn_value      = btn_input["value"]       if btn_input       else "Xem BC"

        post_data = {
            "__VIEWSTATE":          viewstate,
            "__VIEWSTATEGENERATOR": viewstate_gen,
            "__EVENTVALIDATION":    event_validation,
            drp_name:               drp_value,
            date_from_name:         from_date_ddmmyyyy,
            date_to_name:           to_date_ddmmyyyy,
            btn_name:               btn_value,
        }
        post_resp = session.post(config.TTAS_REPORT_URL, data=post_data, timeout=30)
        post_resp.raise_for_status()
        return post_resp.text
    except Exception as e:
        print(f"[OilTracker] TTAS report fetch failed for {plate} ({from_date_ddmmyyyy} to {to_date_ddmmyyyy}): {e}")
        return ""


def _parse_ttas_report_html(html: str, target_plate: str) -> list:
    """Parse tData tbody from the TTAS daily summary report.
    Returns: [{"license_plate": str, "log_date": str, "daily_km": int}, ...]"""
    if not html:
        return []
    try:
        from datetime import datetime as _datetime
        soup = BeautifulSoup(html, "html.parser")
        tbody = soup.find(id="tData")
        if not tbody:
            return []

        rows = tbody.find_all("tr")
        results = []

        clean_target = re.sub(r'[^a-zA-Z0-9]', '', target_plate).upper()
        current_match = True

        for row in rows:
            tds = row.find_all("td")
            if not tds:
                continue

            if len(tds) == 1 and "Biển số xe" in tds[0].get_text():
                raw = tds[0].get_text(strip=True)
                parsed_plate = raw.split(":")[-1].strip()
                clean_parsed = re.sub(r'[^a-zA-Z0-9]', '', parsed_plate).upper()
                current_match = (clean_parsed == clean_target)
                continue

            first_text = tds[0].get_text(strip=True)
            combined_first = (tds[0].get_text(strip=True) + (tds[1].get_text(strip=True) if len(tds) > 1 else ""))
            if "Tổng cộng" in first_text or "Tổng cộng" in combined_first:
                continue

            if current_match and len(tds) >= 4:
                idx_text = tds[0].get_text(strip=True)
                if idx_text.isdigit():
                    date_str = tds[1].get_text(strip=True)
                    km_text = tds[3].get_text(strip=True)

                    try:
                        dt_obj = _datetime.strptime(date_str, "%d/%m/%Y").date()
                        log_date_iso = dt_obj.strftime("%Y-%m-%d")

                        km_match = re.search(r"(\d+)", km_text)
                        km = int(km_match.group(1)) if km_match else 0

                        results.append({
                            "license_plate": target_plate,
                            "log_date": log_date_iso,
                            "daily_km": km
                        })
                    except Exception as ex:
                        print(f"[OilTracker] Row parsing error: {ex}")
                        pass

        return results
    except Exception as e:
        print(f"[OilTracker] HTML parse error: {e}")
        return []


def _parse_ttas_total_km(table_html: str, plate: str, to_date_str: str) -> list:
    """Parse the full #tData table HTML and return total KM for the target plate.
    Finds the 'Biển số xe: {plate}' header, then the 'Tổng cộng' row for that
    vehicle, and extracts the KM value. Falls back to summing daily rows.
    Returns a single entry with total KM logged on to_date.
    """
    from datetime import date as _date, datetime as _datetime

    if not table_html:
        print(f"[OilTracker] Empty table HTML for {plate}")
        return []
    try:
        soup = BeautifulSoup(f"<table><tbody>{table_html}</tbody></table>", "html.parser")
        tbody = soup.find("tbody")
        if not tbody:
            print(f"[OilTracker] No tbody in table HTML for {plate}")
            return []

        clean_target = re.sub(r'[^a-zA-Z0-9]', '', plate).upper()
        in_target = True  # assume single-vehicle report unless a plate header says otherwise
        total_km = 0

        for row in tbody.find_all("tr"):
            tds = row.find_all("td")
            if not tds:
                continue

            if len(tds) == 1 and "Biển số xe" in tds[0].get_text():
                raw = tds[0].get_text(strip=True)
                parsed_plate = raw.split(":")[-1].strip()
                clean_parsed = re.sub(r'[^a-zA-Z0-9]', '', parsed_plate).upper()
                in_target = (clean_parsed == clean_target)
                continue

            if not in_target:
                continue

            first_text = tds[0].get_text(strip=True)
            combined = first_text + (tds[1].get_text(strip=True) if len(tds) > 1 else "")
            if "Tổng cộng" in first_text or "Tổng cộng" in combined:
                for td in tds:
                    text = td.get_text(strip=True).replace(".", "")
                    m = re.search(r"([\d]+)\s*km", text, re.IGNORECASE)
                    if m:
                        total_km = int(m.group(1))
                        break
                break  # stop after processing the total row for this vehicle

            idx_text = tds[0].get_text(strip=True)
            if idx_text.isdigit() and len(tds) >= 4:
                km_text = tds[3].get_text(strip=True)
                km_match = re.search(r"(\d+)", km_text.replace(".", ""))
                if km_match:
                    total_km += int(km_match.group(1))

        print(f"[OilTracker] Parsed {plate}: total_km={total_km}, in_target={in_target}")
        if total_km == 0:
            return []
        try:
            end_dt = _datetime.strptime(to_date_str, "%d/%m/%Y").date()
            log_date_iso = end_dt.strftime("%Y-%m-%d")
        except Exception:
            log_date_iso = _date.today().strftime("%Y-%m-%d")
        return [{"license_plate": plate, "log_date": log_date_iso, "daily_km": total_km}]
    except Exception as e:
        print(f"[OilTracker] Table total parse error: {e}")
        return []
