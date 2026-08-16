"""
Local development entry point — `python app.py`.

Route registration lives entirely in app.create_app() (see app/__init__.py);
this file only builds the app and runs Flask's dev server. It deliberately
defines no routes: until 2026-08-07 it registered ~15 of them on the app
object after create_app() returned, which meant Gunicorn — which imports
wsgi.py and never executes this file — served an application missing "/",
/locations, /delivery/*, /api/vehicles and /api/geocode. They now live in
app/routes/core.py so both entry points serve the same routes.

Production uses `gunicorn wsgi:app` (see render.yaml). The two entry points
differ in exactly one way, below: the background route-refresh thread.
"""
from app import create_app, config
from app.routes.trips import start_route_refresh_thread

app = create_app()


if __name__ == "__main__":
    # Background route polling thread — local development only.
    #
    # Under Gunicorn this is intentionally NOT started because:
    #   - Multiple workers would each spawn their own polling thread,
    #     causing duplicate ORS API calls and cache conflicts.
    #   - The shared route_data_cache would suffer race conditions.
    #
    # Production alternatives:
    #   a) Run Gunicorn with --workers=1 --threads=N if background
    #      polling is essential (single-process, concurrent requests).
    #   b) Use an external scheduler (cron, Celery beat, APScheduler)
    #      that calls POST /api/refresh-routes periodically.
    start_route_refresh_thread()
    app.run(host=config.FLASK_HOST, port=config.FLASK_PORT, debug=config.FLASK_DEBUG, use_reloader=False)
