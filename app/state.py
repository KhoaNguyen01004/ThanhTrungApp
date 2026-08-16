"""
Shared mutable runtime state.

Not one of the report's named modules — added because app.py's module-level
globals (route_data_cache, KNOWN_LOCATIONS, fleet_session, the oil-fetch
progress tracker, etc.) are read and mutated across the fleet/fuel/oil/trips
route blueprints and the TTAS service layer. Without a shared home for
this state, those modules would need to import it from each other,
creating circular imports. Mutate via module attribute assignment
(``state.route_data_cache = {...}``), which — unlike a plain module-level
variable rebind via `global` — works correctly from any importing module.
"""
import threading

route_data_cache = {}
cache_lock = threading.Lock()
last_manual_update = 0.0

#: When do_refresh_route_data() last finished writing route_data_cache, as a
#: time.time() float. 0.0 means "never on this worker".
#:
#: The cache is process memory, and under Gunicorn nothing fills it on a cold
#: start: start_route_refresh_thread() is gated behind __main__ in app.py, so
#: it runs in dev only, and no client POSTs /api/refresh-routes. So after every
#: restart /api/route-data answered `[]` until someone advanced or cancelled a
#: trip, and the fleet map's Phase line fell back to "N/A" on each page load
#: (reported 2026-08-10). This timestamp lets that endpoint rebuild on demand.
route_cache_refreshed_at = 0.0

#: When an on-demand rebuild was last *attempted*, successful or not. Tracked
#: separately from route_cache_refreshed_at because the staleness test treats
#: an empty cache as always stale — so with TTAS down, every single request
#: would start its own doomed refresh and block on it. This makes a failed
#: attempt cost one blocked request per interval instead of all of them.
route_refresh_attempted_at = 0.0

#: Held for the whole of an on-demand rebuild so concurrent readers wait for
#: one refresh instead of each starting their own. Separate from cache_lock,
#: which is only ever held for the dict swap: a refresh makes a TTAS call plus
#: one OpenRouteService call per active trip, and holding cache_lock across
#: that would block every reader for the duration.
route_refresh_lock = threading.Lock()

oil_fetch_progress = {}
oil_fetch_lock = threading.Lock()

sync_lock = threading.Lock()

known_locations = {}

# Set once at app startup (create_fleet_session); reassigned by
# ensure_session()/refresh_session() in app.services.ttas_client.
fleet_session = None
