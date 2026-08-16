"""
Route-layer tests for the vehicle envelope fields on /api/fleet/vehicles.

The service-layer suite (tests/test_vehicle_specs.py) is structurally blind to
a validator that is never called, or to a column that is never written — which
is where a "validated" form that silently drops its values would live. These
drive real HTTP.
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_BOOT_FD, _BOOT_DB = tempfile.mkstemp(suffix="-fleet-boot.db")
os.close(_BOOT_FD)
os.environ.setdefault("DB_PATH", _BOOT_DB)

from app import config                                    # noqa: E402
from app.database.migrations import add_vehicle_envelope_columns  # noqa: E402
from app.routes import fleet as fleet_routes              # noqa: E402

from flask import Flask                                   # noqa: E402


@pytest.fixture
def db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix="-fleet.db")
    os.close(fd)

    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE vehicles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plate_number TEXT NOT NULL UNIQUE,
            vehicle_type TEXT NOT NULL DEFAULT '',
            current_driver TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            container_config_id INTEGER DEFAULT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE container_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL DEFAULT '',
            cargo_length_mm REAL NOT NULL,
            cargo_width_mm REAL NOT NULL,
            cargo_height_mm REAL NOT NULL,
            payload_kg REAL NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE container_features (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            container_config_id INTEGER NOT NULL,
            feature_type TEXT NOT NULL,
            label TEXT NOT NULL DEFAULT '',
            geometry_json TEXT NOT NULL DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    # The migration under test, run the way startup runs it.
    add_vehicle_envelope_columns(conn)
    conn.close()

    # fleet.py reads config.DB_PATH at call time, not app.config.
    monkeypatch.setattr(config, "DB_PATH", path)
    yield path
    os.unlink(path)


@pytest.fixture
def client(db):
    application = Flask(__name__, template_folder=str(Path(__file__).resolve().parent.parent / "templates"))
    application.config["TESTING"] = True
    application.register_blueprint(fleet_routes.bp)
    with application.test_client() as c:
        yield c


VALID = {
    "plate_number": "50H-36908",
    "vehicle_type": "2.5 Tons",
    "current_driver": "Test Driver",
    "cargo_length_mm": 4285,
    "cargo_width_mm": 1850,
    "cargo_height_mm": 1810,
    "payload_kg": 1600,
    "overall_length_mm": 6200,
    "overall_width_mm": 2000,
    "overall_height_mm": 2900,
    "gross_weight_kg": 4990,
}


def _row(db_path, plate="50H-36908"):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM vehicles WHERE plate_number = ?", (plate,)).fetchone()
    conn.close()
    return dict(row) if row else None


class TestCreate:
    def test_envelope_values_are_persisted(self, client, db):
        resp = client.post("/api/fleet/vehicles", json=VALID)
        assert resp.status_code == 200, resp.get_json()
        assert resp.get_json()["success"] is True

        row = _row(db)
        assert row["overall_height_mm"] == 2900
        assert row["gross_weight_kg"] == 4990
        assert row["overall_length_mm"] == 6200

    def test_blank_envelope_fields_are_stored_as_null_not_zero(self, client, db):
        body = {k: v for k, v in VALID.items() if not k.startswith(("overall_", "gross_", "axle_"))}
        body["overall_height_mm"] = ""
        resp = client.post("/api/fleet/vehicles", json=body)
        assert resp.status_code == 200

        row = _row(db)
        # A 0 would reach ORS as a genuine restriction rather than as "unknown".
        assert row["overall_height_mm"] is None
        assert row["gross_weight_kg"] is None

    def test_cargo_figures_in_envelope_fields_are_rejected(self, client, db):
        body = {
            **VALID,
            "overall_height_mm": VALID["cargo_height_mm"],
            "overall_length_mm": VALID["cargo_length_mm"],
            "gross_weight_kg": VALID["payload_kg"],
        }
        resp = client.post("/api/fleet/vehicles", json=body)
        assert resp.status_code == 400
        payload = resp.get_json()
        assert payload["success"] is False
        assert len(payload["errors"]) == 3
        # And nothing was written.
        assert _row(db) is None

    def test_implausible_values_warn_but_still_save(self, client, db):
        # 4.5 m clears the QCVN 09:2024 truck limit and 45 t clears anything on
        # the road here. Note the bounds are fleet-wide, not per-type: a 39 t
        # "2.5 Tons" truck is nonsense but passes, and tightening that would
        # mean per-type ranges, which is more machinery than the check is worth.
        resp = client.post("/api/fleet/vehicles", json={**VALID, "overall_height_mm": 4500,
                                                        "gross_weight_kg": 45000})
        assert resp.status_code == 200
        warnings = resp.get_json()["warnings"]
        assert any("gross_weight_kg" in w for w in warnings)
        assert any("overall_height_mm" in w for w in warnings)
        # Saved regardless — blocking would get the field left empty, which
        # falls back to an estimate.
        assert _row(db)["gross_weight_kg"] == 45000

    def test_a_vehicle_with_no_envelope_at_all_is_still_creatable(self, client, db):
        body = {"plate_number": "51C-00001", "vehicle_type": "2.5 Tons"}
        assert client.post("/api/fleet/vehicles", json=body).status_code == 200
        assert _row(db, "51C-00001")["overall_height_mm"] is None


class TestUpdate:
    def test_envelope_values_are_updated(self, client, db):
        client.post("/api/fleet/vehicles", json=VALID)
        vehicle_id = _row(db)["id"]

        resp = client.put(f"/api/fleet/vehicles/{vehicle_id}",
                          json={**VALID, "overall_height_mm": 3050})
        assert resp.status_code == 200
        assert _row(db)["overall_height_mm"] == 3050

    def test_clearing_a_field_writes_null_rather_than_leaving_the_old_value(self, client, db):
        client.post("/api/fleet/vehicles", json=VALID)
        vehicle_id = _row(db)["id"]

        resp = client.put(f"/api/fleet/vehicles/{vehicle_id}",
                          json={**VALID, "gross_weight_kg": ""})
        assert resp.status_code == 200
        # A stale value silently surviving a deliberate clear would be worse
        # than the blank: it would keep routing on a number nobody stands behind.
        assert _row(db)["gross_weight_kg"] is None

    def test_update_rejects_cargo_figures_too(self, client, db):
        client.post("/api/fleet/vehicles", json=VALID)
        vehicle_id = _row(db)["id"]

        resp = client.put(f"/api/fleet/vehicles/{vehicle_id}",
                          json={**VALID, "overall_height_mm": VALID["cargo_height_mm"]})
        assert resp.status_code == 400
        assert _row(db)["overall_height_mm"] == 2900   # unchanged


class TestList:
    def test_envelope_source_marks_a_fully_specified_vehicle(self, client, db):
        client.post("/api/fleet/vehicles", json=VALID)
        rows = client.get("/api/fleet/vehicles").get_json()["data"]
        assert rows[0]["envelope_source"] == "vehicle"

    def test_envelope_source_marks_a_vehicle_running_on_estimates(self, client, db):
        client.post("/api/fleet/vehicles", json={"plate_number": "51C-00002",
                                                 "vehicle_type": "10 Tons"})
        rows = client.get("/api/fleet/vehicles").get_json()["data"]
        assert rows[0]["envelope_source"] == "type_default"

    def test_envelope_source_marks_a_vehicle_with_nothing_to_fall_back_on(self, client, db):
        client.post("/api/fleet/vehicles", json={"plate_number": "51C-00003",
                                                 "vehicle_type": "Hovercraft"})
        rows = client.get("/api/fleet/vehicles").get_json()["data"]
        assert rows[0]["envelope_source"] == "none"
