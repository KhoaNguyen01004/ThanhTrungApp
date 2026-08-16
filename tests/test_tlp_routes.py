"""Route-layer tests for the Truck Load Planner HTTP API.

Why this file exists
--------------------
Before 2026-08-06 the TLP had **no route-layer coverage at all**.
``test_all.py`` is a script (zero ``def test_``), and ``test_scorer.py`` (26)
and ``test_auto_arrange_e2e.py`` (5) drive ``Planner.auto_arrange()``
directly. None of them can see a bug that lives inside a request handler.

That is exactly where the 2026-08-06 audit found one: ``POST /auto-arrange``
with a ``shipment_id`` raised ``KeyError: 'name'`` and returned an unhandled
500, on the path the frontend takes whenever a shipment is selected
(``truck-load-planner.js:1403``). A second defect sat behind it — ``si.*``
put the shipment-item id in ``row["id"]``, so fixing only the crash would
have produced placements carrying the wrong ``package_id``. A loud failure
traded for silent bad data is not a fix, so ``test_placements_carry_the_real_package_id``
matters as much as ``test_arrange_by_shipment_does_not_500``.

This is the same lesson ``tests/test_delivery_routes.py`` records for the
delivery module, and the fixtures below follow its shape: a temp DB wired in
before the app package is imported, and real HTTP through
``app.test_client()``.
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# app/config.py reads DB_PATH at import time and app/__init__.py runs init_db()
# against it, so it must point somewhere disposable before `app` is imported.
_BOOT_FD, _BOOT_DB = tempfile.mkstemp(suffix="-tlp-boot.db")
os.close(_BOOT_FD)
os.environ["DB_PATH"] = _BOOT_DB

from app import create_app                                  # noqa: E402
from app.database import init_db                            # noqa: E402
from truck_load_planner import routes as tlp_routes         # noqa: E402
from truck_load_planner.db import init_tlp_tables           # noqa: E402


@pytest.fixture(scope="module")
def app():
    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture
def db(app, monkeypatch):
    """A fresh TLP database per test, with one vehicle that has a container.

    ``truck_load_planner.routes`` reads a module-level ``DB_PATH`` that
    ``app/__init__.py`` assigns at startup, so the patch has to go there
    rather than into app.config.
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(path)
    init_tlp_tables(path)

    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO container_configs (name, cargo_length_mm, cargo_width_mm, "
        "cargo_height_mm, payload_kg) VALUES ('Test Box', 6000, 2400, 2400, 5000)"
    )
    cc_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO vehicles (plate_number, vehicle_type, current_driver, "
        "container_config_id) VALUES ('50E-18463', '5 Tons', 'Driver A', ?)",
        (cc_id,),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(tlp_routes, "DB_PATH", path)
    yield path
    os.unlink(path)


@pytest.fixture
def client(app, db):
    """HTTP client. Every endpoint is open by design — see CLAUDE.md."""
    with app.test_client() as c:
        yield c


def _vehicle_id(db):
    conn = sqlite3.connect(db)
    vid = conn.execute("SELECT id FROM vehicles LIMIT 1").fetchone()[0]
    conn.close()
    return vid


def _add_package(db, name="Crate", length=1000, width=800, height=700, weight=50):
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO tlp_packages (name, length, width, height, weight_kg, "
        "allow_stacking, allow_rotation, fragile, color) "
        "VALUES (?, ?, ?, ?, ?, 1, 1, 0, '#3b82f6')",
        (name, length, width, height, weight),
    )
    pkg_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return pkg_id


def _add_shipment(db, items):
    """items: list of (package_id, quantity)."""
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO tlp_shipments (customer_name, reference_number) "
        "VALUES ('ACME', 'REF-1')"
    )
    shipment_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    for pkg_id, qty in items:
        conn.execute(
            "INSERT INTO tlp_shipment_items (shipment_id, package_id, quantity) "
            "VALUES (?, ?, ?)",
            (shipment_id, pkg_id, qty),
        )
    conn.commit()
    conn.close()
    return shipment_id


class TestArrangeByShipment:
    """The audit's Critical #1. Every test here fails against the pre-fix query."""

    def test_arrange_by_shipment_does_not_500(self, client, db):
        pkg_id = _add_package(db)
        shipment_id = _add_shipment(db, [(pkg_id, 2)])

        resp = client.post("/api/tlp/auto-arrange", json={
            "vehicle_id": _vehicle_id(db),
            "shipment_id": shipment_id,
        })

        assert resp.status_code == 200, resp.get_data(as_text=True)
        assert resp.get_json()["summary"]["placed_packages"] == 2

    def test_placements_carry_the_real_package_id(self, client, db):
        """The defect hiding behind the KeyError.

        ``si.*`` exposed the shipment *item* id as ``row["id"]``. With one
        package and one item their ids can coincide by accident, so a second
        package is inserted first to push the item ids out of alignment —
        otherwise this test would pass against the broken code.
        """
        _add_package(db, name="Decoy")
        _add_package(db, name="Decoy 2")
        pkg_id = _add_package(db, name="Real")
        shipment_id = _add_shipment(db, [(pkg_id, 2)])

        resp = client.post("/api/tlp/auto-arrange", json={
            "vehicle_id": _vehicle_id(db),
            "shipment_id": shipment_id,
        })
        assert resp.status_code == 200

        placements = resp.get_json()["placements"]
        assert placements, "expected at least one placement"
        assert {p["package_id"] for p in placements} == {pkg_id}
        assert all(p["_name"] == "Real" for p in placements)

    def test_shipment_and_inline_packages_agree(self, client, db):
        """The two payload shapes must not drift apart again.

        The frontend picks between them on whether a shipment is selected, so
        the same cargo has to arrange the same way either way.
        """
        pkg_id = _add_package(db)
        shipment_id = _add_shipment(db, [(pkg_id, 3)])
        vehicle_id = _vehicle_id(db)

        by_shipment = client.post("/api/tlp/auto-arrange", json={
            "vehicle_id": vehicle_id, "shipment_id": shipment_id,
        }).get_json()

        inline = client.post("/api/tlp/auto-arrange", json={
            "vehicle_id": vehicle_id,
            "packages": [{
                "package_id": pkg_id, "name": "Crate",
                "length": 1000, "width": 800, "height": 700,
                "weight_kg": 50, "color": "#3b82f6", "allow_stacking": True,
            }] * 3,
        }).get_json()

        assert (by_shipment["summary"]["placed_packages"]
                == inline["summary"]["placed_packages"] == 3)
        assert ([p["package_id"] for p in by_shipment["placements"]]
                == [p["package_id"] for p in inline["placements"]])

    def test_orphaned_shipment_item_is_skipped_not_arranged(self, client, db):
        """A LEFT JOIN miss must not become a zero-dimension package.

        Without the guard, from_row builds a package with a null name and 0mm
        sides and the planner packs it happily — an invisible box in the load
        plan, which is worse than the row simply not being there.
        """
        pkg_id = _add_package(db)
        shipment_id = _add_shipment(db, [(pkg_id, 1), (999_999, 1)])

        resp = client.post("/api/tlp/auto-arrange", json={
            "vehicle_id": _vehicle_id(db),
            "shipment_id": shipment_id,
        })

        assert resp.status_code == 200
        assert resp.get_json()["summary"]["placed_packages"] == 1

    def test_shipment_with_no_resolvable_items_is_a_400_not_a_crash(self, client, db):
        shipment_id = _add_shipment(db, [(999_999, 1)])

        resp = client.post("/api/tlp/auto-arrange", json={
            "vehicle_id": _vehicle_id(db),
            "shipment_id": shipment_id,
        })

        assert resp.status_code == 400
        assert "No packages" in resp.get_json()["error"]


class TestDeletePackageCascade:
    """The audit's §5 orphan finding.

    This schema runs with ``enable_fk=False`` and has no ON DELETE CASCADE
    (both deliberate — see the note at the top of truck_load_planner/routes.py),
    so the children have to be cleaned up in the handler.
    """

    def test_delete_package_removes_its_placements_and_shipment_items(self, client, db):
        pkg_id = _add_package(db)
        _add_shipment(db, [(pkg_id, 1)])

        conn = sqlite3.connect(db)
        conn.execute(
            "INSERT INTO tlp_load_plans (name, vehicle_id, status) "
            "VALUES ('P', ?, 'draft')", (_vehicle_id(db),)
        )
        plan_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO tlp_placements (load_plan_id, package_id, x, y, z, "
            "rotation, stack_level, load_sequence) VALUES (?, ?, 0, 0, 0, 0, 0, 1)",
            (plan_id, pkg_id),
        )
        conn.commit()
        conn.close()

        assert client.delete(f"/api/tlp/packages/{pkg_id}").status_code == 200

        conn = sqlite3.connect(db)
        try:
            assert conn.execute(
                "SELECT COUNT(*) FROM tlp_placements WHERE package_id = ?",
                (pkg_id,)).fetchone()[0] == 0
            assert conn.execute(
                "SELECT COUNT(*) FROM tlp_shipment_items WHERE package_id = ?",
                (pkg_id,)).fetchone()[0] == 0
            assert conn.execute(
                "SELECT COUNT(*) FROM tlp_packages WHERE id = ?",
                (pkg_id,)).fetchone()[0] == 0
        finally:
            conn.close()

    def test_deleting_a_missing_package_still_404s(self, client, db):
        """The cascade added three DELETEs before the package's own, so the
        rowcount that decides this had to stop being the last statement's."""
        assert client.delete("/api/tlp/packages/999999").status_code == 404

    def test_delete_leaves_other_packages_untouched(self, client, db):
        keep_id = _add_package(db, name="Keep")
        drop_id = _add_package(db, name="Drop")
        _add_shipment(db, [(keep_id, 1), (drop_id, 1)])

        assert client.delete(f"/api/tlp/packages/{drop_id}").status_code == 200

        conn = sqlite3.connect(db)
        try:
            assert conn.execute(
                "SELECT COUNT(*) FROM tlp_shipment_items WHERE package_id = ?",
                (keep_id,)).fetchone()[0] == 1
            assert conn.execute(
                "SELECT COUNT(*) FROM tlp_packages WHERE id = ?",
                (keep_id,)).fetchone()[0] == 1
        finally:
            conn.close()
