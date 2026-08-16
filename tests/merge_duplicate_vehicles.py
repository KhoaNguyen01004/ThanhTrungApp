"""
One-time utility to merge duplicate vehicles created by Google Sheet sync.

Problem
-------
The Google Sheet stores only the last 5 digits of the license plate
(e.g. ``09473``), while the fleet database stores the full plate
(e.g. ``50H-09473``).  Previous syncs created separate vehicle records
for each format, resulting in duplicates.

What this script does
---------------------
1. Finds every vehicle whose ``plate_number`` consists only of digits.
2. For each, locates the vehicle with the corresponding full plate.
3. Moves all foreign-key references from the duplicate to the original.
4. Deletes the duplicate vehicle.

Safety
------
Everything runs inside a single database transaction.  If **any** step
fails the entire operation is rolled back and the database is left
unchanged.

The script is safe to run multiple times (idempotent).
"""

import os
import sys
import sqlite3
from typing import Any

# Ensure the project root is on sys.path so we can import from services
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from services.plate_utils import normalize_plate


# ---------------------------------------------------------------------------
# Database path resolution (mirrors app.py logic)
# ---------------------------------------------------------------------------
def _get_db_path() -> str:
    """Resolve the path to the SQLite database."""
    from dotenv import load_dotenv

    load_dotenv()
    return os.path.join(
        PROJECT_ROOT, os.getenv("DB_PATH", "routing_system.db")
    )


# ---------------------------------------------------------------------------
# Reference table descriptors – used in place of ORM metadata
# ---------------------------------------------------------------------------
# Tables whose rows reference a vehicle via vehicles.id (integer FK).
# Each entry: (table_name, fk_column)
INTEGER_FK_TABLES: list[tuple[str, str]] = [
    ("fuel_log", "vehicle_id"),
    ("tlp_load_plans", "vehicle_id"),
    # Added 2026-07-31. The delivery module shipped after this script was
    # written, so vehicle_assignments was missing from the list: merging a
    # duplicate would either abort on the vehicles DELETE (PRAGMA
    # foreign_keys=ON, since vehicle_assignments.vehicle_id has no ON DELETE
    # action) or, with FK enforcement off, leave every assignment pointing at
    # a vehicle row that no longer exists (audit T-12).
    ("vehicle_assignments", "vehicle_id"),
]

# Tables whose rows reference a vehicle via license_plate (text).
# Each entry: (table_name, plate_column)
TEXT_PLATE_TABLES: list[tuple[str, str]] = [
    ("fuel_log", "license_plate"),
    ("fuel_vehicle_profile", "license_plate"),
    ("oil_maintenance", "license_plate"),
    ("oil_km_log", "license_plate"),
]


# ---------------------------------------------------------------------------
# Merge logic
# ---------------------------------------------------------------------------
def merge_duplicate_vehicles(db_path: str) -> dict[str, Any]:
    """Find and merge duplicate vehicle records.

    Returns a summary dictionary with keys:

    * ``duplicate_count`` – total duplicate vehicles found
    * ``merged`` – list of ``(dup_plate → orig_plate)`` strings
    * ``skipped`` – list of plates that could not be matched
    * ``updated_counts`` – per-table count of rows updated
    * ``vehicles_removed`` – number of duplicate vehicles deleted
    * ``success`` – ``True`` if the transaction was committed
    """
    summary: dict[str, Any] = {
        "duplicate_count": 0,
        "merged": [],
        "skipped": [],
        "updated_counts": {},
        "vehicles_removed": 0,
        "success": False,
    }

    conn = sqlite3.connect(db_path)
    conn.execute("BEGIN")

    try:
        cur = conn.cursor()

        # ---- Step 1: Identify duplicates ----
        cur.execute(
            "SELECT id, plate_number FROM vehicles "
            "WHERE plate_number GLOB '[0-9][0-9][0-9][0-9][0-9]'"
        )
        numeric_vehicles = cur.fetchall()

        # Filter to only those that are purely numeric (exactly 5 digits)
        # GLOB above catches any row with 5 digits anywhere – refine here.
        numeric_vehicles = [
            (vid, plate)
            for vid, plate in numeric_vehicles
            if plate.isdigit() and len(plate) == 5
        ]

        summary["duplicate_count"] = len(numeric_vehicles)

        if not numeric_vehicles:
            conn.commit()
            summary["success"] = True
            return summary

        # Cache all non-duplicate vehicles for matching
        cur.execute("SELECT id, plate_number FROM vehicles")
        all_vehicles = cur.fetchall()

        # Build a suffix lookup: normalize_plate(plate) → (id, plate)
        # Prefer vehicles that are NOT purely numeric (i.e. the full plate)
        suffix_map: dict[str, tuple[int, str]] = {}
        for vid, plate in all_vehicles:
            is_numeric = plate.isdigit() and len(plate) == 5
            suffix = normalize_plate(plate)
            if not suffix:
                continue
            # Only add non-numeric vehicles to the map (these are the originals)
            if not is_numeric:
                suffix_map[suffix] = (vid, plate)

        # ---- Step 2: Process each duplicate ----
        for dup_id, dup_plate in numeric_vehicles:
            suffix = normalize_plate(dup_plate)
            match = suffix_map.get(suffix)

            if match is None:
                summary["skipped"].append(dup_plate)
                continue

            orig_id, orig_plate = match
            summary["merged"].append(f"{dup_plate} -> {orig_plate}")

            # --- 2a. Update integer FK references ---
            for table, column in INTEGER_FK_TABLES:
                cur.execute(
                    f"UPDATE {table} SET {column} = ? WHERE {column} = ?",
                    (orig_id, dup_id),
                )
                summary["updated_counts"].setdefault(table, 0)
                summary["updated_counts"][table] += cur.rowcount

            # --- 2b. Update text plate references ---
            for table, column in TEXT_PLATE_TABLES:
                # Check for UNIQUE/PK constraint violations before updating
                if table == "fuel_vehicle_profile":
                    # PRIMARY KEY on license_plate – if original already has a
                    # profile, delete the duplicate's profile (data already exists)
                    existing = cur.execute(
                        "SELECT 1 FROM fuel_vehicle_profile WHERE license_plate = ?",
                        (orig_plate,),
                    ).fetchone()
                    if existing:
                        cur.execute(
                            "DELETE FROM fuel_vehicle_profile WHERE license_plate = ?",
                            (dup_plate,),
                        )
                    else:
                        cur.execute(
                            f"UPDATE {table} SET {column} = ? WHERE {column} = ?",
                            (orig_plate, dup_plate),
                        )
                        summary["updated_counts"].setdefault(table, 0)
                        summary["updated_counts"][table] += cur.rowcount

                elif table == "oil_maintenance":
                    # UNIQUE on license_plate – same strategy
                    existing = cur.execute(
                        "SELECT 1 FROM oil_maintenance WHERE license_plate = ?",
                        (orig_plate,),
                    ).fetchone()
                    if existing:
                        cur.execute(
                            "DELETE FROM oil_maintenance WHERE license_plate = ?",
                            (dup_plate,),
                        )
                    else:
                        cur.execute(
                            f"UPDATE {table} SET {column} = ? WHERE {column} = ?",
                            (orig_plate, dup_plate),
                        )
                        summary["updated_counts"].setdefault(table, 0)
                        summary["updated_counts"][table] += cur.rowcount

                elif table == "oil_km_log":
                    # UNIQUE(license_plate, log_date) – cannot blindly UPDATE.
                    # For each row on the duplicate plate, try to UPDATE.
                    # If a conflict would arise (row with same plate+date exists),
                    # delete the duplicate's row since the data is already present.
                    rows = cur.execute(
                        "SELECT rowid, log_date FROM oil_km_log WHERE license_plate = ?",
                        (dup_plate,),
                    ).fetchall()
                    for rowid, log_date in rows:
                        conflict = cur.execute(
                            "SELECT 1 FROM oil_km_log WHERE license_plate = ? AND log_date = ? AND rowid != ?",
                            (orig_plate, log_date, rowid),
                        ).fetchone()
                        if conflict:
                            cur.execute(
                                "DELETE FROM oil_km_log WHERE rowid = ?",
                                (rowid,),
                            )
                        else:
                            cur.execute(
                                "UPDATE oil_km_log SET license_plate = ? WHERE rowid = ?",
                                (orig_plate, rowid),
                            )
                    summary["updated_counts"].setdefault(table, 0)
                    # Count any row that was updated or deleted
                    summary["updated_counts"][table] += len(rows)

                else:
                    # No UNIQUE concerns – direct UPDATE
                    cur.execute(
                        f"UPDATE {table} SET {column} = ? WHERE {column} = ?",
                        (orig_plate, dup_plate),
                    )
                    summary["updated_counts"].setdefault(table, 0)
                    summary["updated_counts"][table] += cur.rowcount

            # --- 2c. Delete duplicate vehicle ---
            cur.execute("DELETE FROM vehicles WHERE id = ?", (dup_id,))
            summary["vehicles_removed"] += 1

        conn.commit()
        summary["success"] = True

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return summary


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def print_report(summary: dict[str, Any]) -> None:
    """Print a human-readable merge report."""
    print()
    print("=" * 45)
    print("  Vehicle Merge Utility")
    print("=" * 45)
    print()

    if not summary["success"]:
        print("  FAILED – transaction rolled back.")
        return

    print(f"  Duplicate vehicles found:  {summary['duplicate_count']}")
    print()

    if summary["merged"]:
        print("  Merged:")
        for entry in summary["merged"]:
            print(f"    {entry}")
        print()

    if summary["skipped"]:
        print("  WARNING")
        print()
        print("  Could not find matching vehicle for:")
        for plate in summary["skipped"]:
            print(f"    {plate}")
        print("  Skipped.")
        print()

    sorted_tables = sorted(summary["updated_counts"].items())
    for table, count in sorted_tables:
        label = table.replace("_", " ").title()
        print(f"  {label} updated:          {count}")

    print(f"  Duplicate vehicles removed: {summary['vehicles_removed']}")
    print()

    if summary["skipped"]:
        print("  Completed with warnings (see above).")
    else:
        print("  Completed successfully.")


def main() -> None:
    db_path = _get_db_path()
    if not os.path.exists(db_path):
        print(f"Database not found: {db_path}")
        sys.exit(1)

    summary = merge_duplicate_vehicles(db_path)
    print_report(summary)

    if not summary["success"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
