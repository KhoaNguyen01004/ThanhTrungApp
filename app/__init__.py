"""
Flask app factory (Section 6.4.1, Phase 1).

app.py (the project's entry point, run via `python app.py`) calls
create_app() to build the Flask application, then runs it. This keeps
`python app.py` working exactly as before while the actual app
construction — config, database init, blueprint registration — lives
here where it can be imported and tested independently of the dev-server
bootstrap code.
"""
import logging

from flask import Flask

logger = logging.getLogger(__name__)


def create_app():
    from app import config, state

    # Run once per process at app-construction time (matches the original
    # app.py, which ran this at module level so it executes once per
    # Gunicorn worker on import).
    from app.database import init_db
    try:
        init_db(config.DB_PATH)
    except Exception:
        logger.exception("Fatal error during database initialization — aborting startup")
        raise

    app = Flask(__name__, static_folder="../static", template_folder="../templates")
    app.secret_key = config.SECRET_KEY

    # Session cookie hardening. Kept even though no route reads the session
    # today (the dispatcher login was removed 2026-07-31): these are defaults
    # for the whole app, and re-deriving them later is easy to get wrong.
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=not config.FLASK_DEBUG,
        # Hard ceiling on request bodies — Werkzeug rejects anything larger
        # before it reaches a view, so an oversized upload can't exhaust
        # memory or disk. image_service enforces its own tighter per-file
        # limit with a friendlier error.
        MAX_CONTENT_LENGTH=config.MAX_UPLOAD_MB * 1024 * 1024,
    )

    # Shared runtime state
    from app.services.locations import load_known_locations
    from app.services.ttas_client import create_fleet_session
    state.known_locations = load_known_locations()
    state.fleet_session = create_fleet_session()

    # Inject DB path into TLP routes module (legacy module-level config pattern)
    import truck_load_planner.routes as tlp_routes
    tlp_routes.DB_PATH = config.DB_PATH
    app.config["DB_PATH"] = config.DB_PATH

    # Register TLP Blueprint
    app.register_blueprint(tlp_routes.tlp_bp)

    # Register Delivery Blueprint
    from services.delivery.routes import bp as delivery_bp
    app.register_blueprint(delivery_bp)

    # Initialize delivery tables
    from services.delivery.database import init_delivery_tables
    init_delivery_tables(config.DB_PATH)

    # Register the 4 extracted domain blueprints
    from app.routes.fleet import bp as fleet_bp
    from app.routes.fuel import bp as fuel_bp
    from app.routes.oil import bp as oil_bp
    from app.routes.trips import bp as trips_bp
    app.register_blueprint(fleet_bp)
    app.register_blueprint(fuel_bp)
    app.register_blueprint(oil_bp)
    app.register_blueprint(trips_bp)

    # Core routes: index, /api/vehicles, manual-location management,
    # geocoding, delivery page shells.
    #
    # These lived in app.py until 2026-08-07, registered on the app object
    # *after* create_app() returned. That worked for `python app.py` and
    # silently did not for `gunicorn wsgi:app`, which imports wsgi.py and
    # never executes app.py — so production 404'd on "/" and everything
    # else in that file. Anything registered here is served by both entry
    # points; nothing should be attached to the app outside this function.
    from app.routes.core import bp as core_bp
    app.register_blueprint(core_bp)

    return app
