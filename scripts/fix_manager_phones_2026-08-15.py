"""
One-off repair of delivery_plan_stops.manager_phone.

Why
---
The Google Sheet's phone columns are text in some rows and *number-formatted*
in others, and a numeric cell reached the database corrupted twice over:

1. **Sheets drops the leading zero.** ``0939746130`` typed into a numeric cell
   is the integer 939746130.
2. **We welded the float's fraction on.** ``gviz`` reports the cell as
   ``939746130.0``; ``_cell`` stringified it; ``_clean_phone``'s
   ``re.sub(r"[^\\d+]", "", ...)`` deleted the decimal point and left the
   trailing ``0`` attached — ``9397461300``.

Measured on the live database 2026-08-15: of 149 non-empty manager phones,
118 were malformed. 33 were 9 digits (corruption 1 only) and **85 were 10
digits ending in 0 — 85 of 85, no exceptions**. That unanimity is what
identifies the float as the cause; a genuine set of numbers would end in 0
about a tenth of the time. Seven managers had the same number stored in two or
three different forms across their stops, e.g. Nguyễn Minh Sơn as
``0939746130`` (text cell), ``939746130`` and ``9397461300`` (numeric cells)
across 14 stops.

The repair therefore undoes both, in order: drop a trailing ``0`` that a
10-digit value cannot legitimately carry, then restore the leading ``0``.
Prefixing ``0`` alone would turn those 85 rows into 11-digit numbers that
cannot be dialled.

The importer fix that stops this recurring is in
``services/delivery/sheet_import_service._clean_phone``; this script only
repairs rows imported before it.

Idempotent: a value already starting ``0`` is never touched, so re-running
changes nothing.

Usage:
    python scripts/fix_manager_phones_2026-08-15.py --dry-run   # report only
    python scripts/fix_manager_phones_2026-08-15.py             # back up, then apply
"""
import argparse
import os
import re
import shutil
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("DB_PATH") or os.path.join(ROOT, "routing_system.db")

# Vietnamese mobile prefixes, as the digit that follows the leading zero.
# Landlines (024, 028, 0292 ...) also start 02 and are covered by the same
# 10-digit shape, so 2 is included rather than assuming every stop manager
# carries a mobile.
VALID_LEADING = set("2356789")


def repair(stored: str, normalize_spaces: bool = False) -> tuple[str, str]:
    """Return ``(fixed, reason)``. ``reason`` is "" when nothing was wrong."""
    raw = (stored or "").strip()
    if not raw:
        return raw, ""

    digits = re.sub(r"[^\d]", "", raw)

    if raw.startswith("0"):
        # Text cell — arrived intact and is dialable as it stands. Ten rows
        # carry human spacing ("0939 980 584"). Reformatting them is cosmetic
        # and outside this repair, so it is opt-in.
        if normalize_spaces and digits != raw:
            return digits, "normalized (spaces stripped)"
        return raw, ""

    if len(digits) == 10 and digits.endswith("0"):
        return "0" + digits[:-1], "dropped welded .0, restored leading zero"

    if len(digits) == 9:
        return "0" + digits, "restored leading zero"

    return raw, "UNRECOGNIZED — left unchanged, needs a human"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would change without writing")
    ap.add_argument("--db", default=DB_PATH)
    ap.add_argument("--normalize-spaces", action="store_true",
                    help="also strip human spacing from phones that are "
                         "already correct (cosmetic; off by default)")
    args = ap.parse_args()

    if not os.path.exists(args.db):
        print(f"No database at {args.db}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, station_code, manager_name, manager_phone "
            "FROM delivery_plan_stops WHERE manager_phone != '' "
            "ORDER BY manager_name, station_code"
        ).fetchall()

        changes, unchanged, suspect = [], 0, []
        for r in rows:
            fixed, reason = repair(r["manager_phone"], args.normalize_spaces)
            if reason.startswith("UNRECOGNIZED"):
                suspect.append((r, fixed))
            elif fixed != r["manager_phone"]:
                changes.append((r, fixed, reason))
            else:
                unchanged += 1

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = os.path.join(ROOT, f"reports/manager_phone_fix_{stamp}.txt")
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"manager_phone repair — {datetime.now().isoformat(timespec='seconds')}\n")
            f.write(f"database: {args.db}\n")
            f.write(f"{len(rows)} stops with a phone; {len(changes)} to change, "
                    f"{unchanged} already correct, {len(suspect)} unrecognized\n\n")
            f.write(f"{'stop':>5}  {'station':<10} {'before':<14} -> {'after':<12}  "
                    f"reason / manager\n")
            f.write("-" * 100 + "\n")
            for r, fixed, reason in changes:
                f.write(f"{r['id']:>5}  {r['station_code'] or '':<10} "
                        f"{r['manager_phone']:<14} -> {fixed:<12}  "
                        f"{reason} | {r['manager_name'] or ''}\n")
            if suspect:
                f.write("\nUNRECOGNIZED — not touched:\n")
                for r, _ in suspect:
                    f.write(f"{r['id']:>5}  {r['station_code'] or '':<10} "
                            f"{r['manager_phone']} | {r['manager_name'] or ''}\n")

        print(f"{len(rows)} stops with a phone")
        print(f"  {len(changes)} to repair")
        print(f"  {unchanged} already correct")
        print(f"  {len(suspect)} unrecognized (left alone)")
        print(f"report: {report_path}")

        if args.dry_run:
            print("\n--dry-run: nothing written.")
            return 0

        backup = os.path.join(ROOT, f"reports/routing_system_backup_{stamp}.db")
        # sqlite3's own backup API first: an open writer elsewhere cannot leave
        # us with a torn copy the way a file copy could. It needs to create its
        # own journal alongside the destination, which some mounted/network
        # filesystems refuse with "disk I/O error" — fall back to a plain copy
        # there rather than proceeding with no backup at all.
        try:
            with sqlite3.connect(backup) as dest:
                conn.backup(dest)
            print(f"backup: {backup}")
        except sqlite3.OperationalError as exc:
            if os.path.exists(backup):
                os.remove(backup)
            shutil.copy2(args.db, backup)
            print(f"backup: {backup}  (file copy — sqlite backup API "
                  f"unavailable here: {exc})")
        if os.path.getsize(backup) == 0:
            print("backup is empty — refusing to modify the database",
                  file=sys.stderr)
            return 1

        conn.executemany(
            "UPDATE delivery_plan_stops SET manager_phone = ? WHERE id = ?",
            [(fixed, r["id"]) for r, fixed, _ in changes],
        )
        conn.commit()
        print(f"updated {len(changes)} rows")

        # Post-condition: every phone is now a plausible VN number, and no
        # manager is left holding two different ones.
        after = conn.execute(
            "SELECT manager_name, manager_phone FROM delivery_plan_stops "
            "WHERE manager_phone != ''").fetchall()
        # Compare on digits alone — the ten space-formatted values are
        # deliberately left as the dispatcher typed them.
        def _digits(v):
            return re.sub(r"[^\d]", "", v)

        bad_shape = [a["manager_phone"] for a in after
                     if not (len(_digits(a["manager_phone"])) in (10, 11)
                             and _digits(a["manager_phone"]).startswith("0")
                             and _digits(a["manager_phone"])[1] in VALID_LEADING)]
        by_manager = defaultdict(set)
        for a in after:
            by_manager[(a["manager_name"] or "").strip()].add(
                _digits(a["manager_phone"]))
        split = {n: v for n, v in by_manager.items() if len(v) > 1}

        print(f"\nverify: {len(bad_shape)} implausible values, "
              f"{len(split)} managers with more than one number")
        for value in sorted(set(bad_shape)):
            print(f"  implausible: {value}")
        for name, values in sorted(split.items()):
            print(f"  split: {name} -> {sorted(values)}")
        return 0 if not bad_shape else 2
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
