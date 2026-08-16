"""Core fleet data is never created or altered in the background.

`vehicles` — plate numbers, vehicle type, dimensions, current driver — is
maintained by a human through Vehicle Management. Operational data flowing
into the system (fuel logs, delivery plan imports, Google Sheet syncs, boot
migrations) may *read* it and *link* to it, but must never insert a row or
edit one, and must never do either without telling the user.

These tests exist because the codebase repeatedly did the opposite:
  - fuel logging upserted the vehicle and overwrote `current_driver` from
    whatever name was typed on the fuel form;
  - the boot migration re-ran that upsert against all of fuel history on
    every startup;
  - the delivery Excel import created a vehicle for any unmatched plate;
  - all three matched on the exact plate string, so a formatting difference
    ("50E18463" vs "50E-18463") produced duplicate trucks rather than a
    match — see tests/merge_duplicate_vehicles.py, which exists to clean up
    the resulting mess.

See docs/DELIVERY_AUDIT_2026-07-31.md (C-05, §5) and the 2026-07-31 entries
in docs/CHANGELOG.md.
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

VEHICLES_DDL = """
CREATE TABLE vehicles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plate_number TEXT NOT NULL UNIQUE,
    vehicle_type TEXT NOT NULL DEFAULT '',
    current_driver TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    container_config_id INTEGER DEFAULT NULL
)
"""

FUEL_LOG_DDL = """
CREATE TABLE fuel_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    license_plate TEXT NOT NULL,
    log_date TEXT NOT NULL,
    log_time TEXT NOT NULL,
    gas_store TEXT NOT NULL DEFAULT '',
    old_km INTEGER NOT NULL DEFAULT 0,
    new_km INTEGER NOT NULL DEFAULT 0,
    liters REAL NOT NULL DEFAULT 0,
    driver_name TEXT NOT NULL DEFAULT '',
    unit_price REAL DEFAULT NULL,
    notes TEXT DEFAULT '',
    is_full_tank INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    vehicle_id INTEGER DEFAULT NULL
)
"""


@pytest.fixture
def fleet_db():
    """A database with one registered vehicle, fully specified."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.execute(VEHICLES_DDL)
    conn.execute(FUEL_LOG_DDL)
    conn.execute(
        "INSERT INTO vehicles (plate_number, vehicle_type, current_driver, container_config_id) "
        "VALUES ('50E-18463', 'Box Truck', 'Original Driver', 7)"
    )
    conn.commit()
    conn.close()
    yield path
    os.unlink(path)


def _update_vehicles_statements(lowered_source: str) -> list[str]:
    """Every `UPDATE vehicles SET ...` statement in a module, up to its WHERE
    or the end of the string literal — enough to see which columns are set."""
    import re
    return re.findall(r"update vehicles set (.*?)(?:where|\"|')", lowered_source, re.S)


def core_data(db_path):
    """Everything this project considers core vehicle data."""
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            "SELECT id, plate_number, vehicle_type, current_driver, container_config_id "
            "FROM vehicles ORDER BY id"
        ).fetchall()
    finally:
        conn.close()


class TestBootMigrationNeverWritesCoreData:
    """app/database/migrations.py runs on every startup."""

    def test_links_fuel_history_without_touching_vehicles(self, fleet_db):
        from app.database.migrations import backfill_vehicles_from_fuel_log

        conn = sqlite3.connect(fleet_db)
        # A fuel row referring to the known truck by bare serial, and one for
        # a plate belonging to no registered vehicle.
        conn.execute(
            "INSERT INTO fuel_log (license_plate, log_date, log_time, driver_name) "
            "VALUES ('18463', '2026-07-01', '08:00', 'Someone Else')"
        )
        conn.execute(
            "INSERT INTO fuel_log (license_plate, log_date, log_time, driver_name) "
            "VALUES ('77Z-00000', '2026-07-01', '08:00', 'Nobody')"
        )
        conn.commit()

        before = core_data(fleet_db)
        backfill_vehicles_from_fuel_log(conn)

        assert core_data(fleet_db) == before, "startup migration modified core vehicle data"

        rows = dict(conn.execute(
            "SELECT license_plate, vehicle_id FROM fuel_log ORDER BY id"
        ).fetchall())
        conn.close()

        # Known plate: linked and normalised onto the fleet's canonical form.
        assert rows["50E-18463"] is not None
        # Unknown plate: left exactly as it was, not invented into existence.
        assert rows["77Z-00000"] is None

    def test_does_not_overwrite_current_driver(self, fleet_db):
        from app.database.migrations import backfill_vehicles_from_fuel_log

        conn = sqlite3.connect(fleet_db)
        conn.execute(
            "INSERT INTO fuel_log (license_plate, log_date, log_time, driver_name) "
            "VALUES ('50E-18463', '2026-07-01', '08:00', 'Temporary Relief Driver')"
        )
        conn.commit()
        backfill_vehicles_from_fuel_log(conn)
        conn.close()

        driver = core_data(fleet_db)[0][3]
        assert driver == "Original Driver", (
            f"a name typed on a fuel form replaced the vehicle's driver: {driver!r}"
        )


class TestNoModuleCreatesVehicles:
    """Static guarantee, so a future edit can't quietly reintroduce this."""

    # app/routes/fleet.py is the legitimate owner: Vehicle Management, where
    # creating a vehicle is the explicit point of the request.
    ALLOWED = {"app/routes/fleet.py"}

    SCANNED = [
        "app/routes/fuel.py",
        "app/routes/oil.py",
        "app/routes/trips.py",
        "app/database/migrations.py",
        "services/vehicle_identity.py",
        "services/google_sheet_service.py",
        "services/delivery/plan_service.py",
        "services/delivery/routes.py",
        "services/delivery/execution_service.py",
        "truck_load_planner/routes.py",
    ]

    @pytest.mark.parametrize("relpath", SCANNED)
    def test_module_does_not_insert_into_vehicles(self, relpath):
        root = Path(__file__).resolve().parent.parent
        source = (root / relpath).read_text(encoding="utf-8").lower()
        assert "into vehicles" not in source, (
            f"{relpath} writes to the vehicles table. Vehicle creation belongs "
            f"in Vehicle Management (app/routes/fleet.py) only."
        )

    @pytest.mark.parametrize("relpath", SCANNED)
    def test_module_does_not_update_vehicle_identity_columns(self, relpath):
        """plate_number / vehicle_type / current_driver identify a vehicle and
        describe it. Nothing outside Vehicle Management may write them."""
        root = Path(__file__).resolve().parent.parent
        source = (root / relpath).read_text(encoding="utf-8").lower()
        for statement in _update_vehicles_statements(source):
            for column in ("plate_number", "vehicle_type", "current_driver"):
                assert column not in statement, (
                    f"{relpath} writes vehicles.{column}: {statement.strip()[:120]!r}. "
                    f"Core fields change only through manual entry."
                )

    def test_only_the_one_time_tlp_migration_touches_dimensions(self):
        """container_config_id (the vehicle's dimensions) is written in exactly
        one place: the guarded, logged, one-time tlp_trucks migration."""
        root = Path(__file__).resolve().parent.parent
        offenders = []
        for relpath in self.SCANNED:
            source = (root / relpath).read_text(encoding="utf-8").lower()
            if any("container_config_id" in s for s in _update_vehicles_statements(source)):
                offenders.append(relpath)
        assert offenders == ["app/database/migrations.py"], (
            f"unexpected writers of vehicle dimensions: {offenders}"
        )

    def test_vehicle_identity_has_no_write_helpers(self):
        from services import vehicle_identity

        writes = [
            name for name in dir(vehicle_identity)
            if not name.startswith("_")
            and any(w in name.lower() for w in ("create", "insert", "add", "save", "upsert"))
        ]
        assert writes == [], f"vehicle_identity must stay read-only, found: {writes}"


class TestLooseMatchingPreventsFalseAlarms:
    """The unknown-vehicle prompt must only fire for genuinely new trucks —
    never because a plate was written in a different format."""

    @pytest.mark.parametrize("entered", [
        "50E-18463", "50E18463", "50E 18463", "50e-18463", "18463", " 18463 ",
    ])
    def test_known_truck_is_recognised_in_any_format(self, fleet_db, entered):
        from app.db import DatabaseManager
        from services import vehicle_identity

        with DatabaseManager(fleet_db).connect() as conn:
            ref = vehicle_identity.resolve(conn, entered)
        assert ref is not None, f"{entered!r} would have triggered a false 'new vehicle' prompt"
        assert ref.plate_number == "50E-18463"

    @pytest.mark.parametrize("entered,expected", [
        ("51D99999", "51D-99999"),
        ("51d 99999", "51D-99999"),
        ("51D-99999", "51D-99999"),
        ("99999", "99999"),      # bare serial: can't infer a province/series
        ("", ""),
    ])
    def test_plate_suggestion_for_the_prefilled_form(self, entered, expected):
        from services import vehicle_identity
        assert vehicle_identity.suggest_plate_format(entered) == expected

    def test_unknown_vehicle_response_carries_prefill(self):
        from services import vehicle_identity

        body = vehicle_identity.unknown_vehicle_response("51D99999", "New Driver")
        assert body["success"] is False
        assert body["error_code"] == "unknown_vehicle"
        assert body["unknown_vehicle"]["suggested_plate"] == "51D-99999"
        assert body["unknown_vehicle"]["current_driver"] == "New Driver"
        assert body["redirect_to"].startswith("/vehicle-management?")
        assert "51D-99999" in body["redirect_to"]
