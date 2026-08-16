"""
Application configuration — environment variable reads and constants.

Extracted from the top of app.py (Section 6.4.1, Phase 2). Import-time
behavior is preserved exactly: this module still raises RuntimeError at
import time if a required env var is missing, matching app.py's original
fail-fast startup check.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# Validate required environment variables
required_env_vars = [
    "ORS_API_KEY",
    "ORS_BASE_URL",
    "TTAS_TRACKING_PAGE_URL",
    "TTAS_TRACKING_API",
]
missing_vars = [var for var in required_env_vars if not os.getenv(var)]
if missing_vars:
    raise RuntimeError(f"Missing required environment variables: {', '.join(missing_vars)}. Please set them in .env file!")

# OpenRouteService Configuration (REQUIRED to be set in .env)
ORS_API_KEY = os.getenv("ORS_API_KEY")
ORS_BASE_URL = os.getenv("ORS_BASE_URL")

# Mapillary Configuration (OPTIONAL — street-level imagery on the dashboard).
#
# Deliberately NOT in required_env_vars above. That list raises RuntimeError at
# import time, which means a missing entry stops the whole application from
# booting — correct for ORS and TTAS, which the dispatch board cannot function
# without, and wrong for a stop-photo lookup. Absent token = the street view
# button reports itself unavailable and everything else runs untouched.
#
# This is a *client* token (the "MLY|app_id|secret" form from
# mapillary.com/dashboard/developers), not a user token. It grants read access
# to public imagery and nothing else, so it is a rate-limit credential rather
# than an account one. It still stays server-side: app/services/streetview.py
# is the only reader, and it is never rendered into a template.
MAPILLARY_TOKEN = os.getenv("MAPILLARY_TOKEN")

# TTAS Configuration (REQUIRED to be set in .env)
TTAS_TRACKING_PAGE_URL = os.getenv("TTAS_TRACKING_PAGE_URL")
TTAS_TRACKING_API = os.getenv("TTAS_TRACKING_API")
TTAS_PAYLOAD = {"Running": 1, "Stop": 1, "LostGPRS": 1, "devname": "", "groupxe": "", "maptype": 2}
TTAS_HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/json; charset=UTF-8",
    "Origin": os.getenv("TTAS_TRACKING_PAGE_URL", ""),
    "Referer": TTAS_TRACKING_PAGE_URL,
    "X-Requested-With": "XMLHttpRequest",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
}
TTAS_REPORT_URL = os.getenv("TTAS_REPORT_PAGE_URL", "https://dinhvihopquy.vn/baocao/ttas_baocao_tonghop_theongay.aspx")

# Database & File Paths
DB_PATH = str(BASE_DIR / os.getenv("DB_PATH", "routing_system.db"))
MANUAL_LOCATIONS_FILE = str(BASE_DIR / os.getenv("MANUAL_LOCATIONS_FILE", "manual_locations.json"))

# Application Configuration
DEFAULT_RADIUS_KM = float(os.getenv("DEFAULT_RADIUS_KM", "3"))
MAX_LIVE_FETCH_ATTEMPTS = int(os.getenv("MAX_LIVE_FETCH_ATTEMPTS", "2"))
ROUTE_REFRESH_INTERVAL = int(os.getenv("ROUTE_REFRESH_INTERVAL_SECONDS", "60"))
FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "true").lower() == "true"
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")

# Upper bound on any request body (Flask MAX_CONTENT_LENGTH). Sized for a
# multi-photo proof-of-delivery upload plus an Excel plan import; the
# per-file limits in services/delivery/image_service.py are tighter.
#
# Raised 25 -> 110 on 2026-08-15 when video evidence was accepted. This has to
# stay above image_service.MAX_VIDEO_BYTES (100 MB) plus multipart overhead:
# Werkzeug enforces MAX_CONTENT_LENGTH before the view runs, so a value below
# the per-file cap makes image_service's friendly "the limit for video is
# 100 MB" message unreachable and the driver gets a bare 413 instead.
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "110"))
