"""
WSGI entry point for production servers (Gunicorn, etc.).

Needed because `app.py` (the local-dev entry point run via `python app.py`)
and the `app/` package (containing create_app()) share the name `app` —
`import app` always resolves to the package, so `gunicorn app:app` cannot
reach app.py's Flask instance. This module gives Gunicorn an unambiguous
target: `gunicorn wsgi:app`.
"""
from app import create_app

app = create_app()
