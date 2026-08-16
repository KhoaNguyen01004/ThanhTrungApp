#!/usr/bin/env python3
"""Land the 2026-08-06 audit fixes as eight reviewable commits.

Why this is a script and not something already committed
--------------------------------------------------------
The agent session that made these changes reaches the repository through a
mount that does not permit unlinking files. Git creates `index.lock`,
`HEAD.lock` and `refs/heads/<branch>.lock` for every write and removes them
when it finishes — it could create them there but not remove them, so any
`git commit` left a lock behind that blocked the next command. (That is also
where the stray `.git/*.lock.stale*` files came from; they are inert and can
be deleted.) The commits therefore have to be made from Windows, where the
filesystem behaves normally.

What it does
------------
The working tree already holds the final state of every change. This script
splits that into eight commits -- one per phase of docs/BUGFIX_PLAN_2026-08-06.md,
plus a final housekeeping commit --
by staging a chosen subset of each file's diff hunks at each step. Every hunk
is located by its *old-side* context, so subsets apply against the HEAD version
with exact line numbers regardless of which other hunks are or aren't included.

The working tree is never modified. Only the index and refs change. If any
precondition fails the script aborts before creating a single commit.

Usage
-----
    python scripts/commit_audit_fixes.py --check     # verify, change nothing
    python scripts/commit_audit_fixes.py             # create the commits

To undo afterwards:  git reset --soft HEAD~8
"""
import argparse
import ast
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPECTED_HEAD = "569c0fe9553c3ebc103eff0fa3432a8cec66b61f"

# Hunk indices per file, per phase. Sets are cumulative: each entry lists every
# hunk that should be present in the index *after* that commit.
TRIPS_GEOFENCE = [10, 11, 12]
TRIPS_ALL = list(range(15))
FUEL_WRITE_HANDLERS = [12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 26, 27, 28, 29]
FUEL_ALL = list(range(30))

EXPECTED_HUNK_COUNTS = {
    "truck_load_planner/routes.py": 5,
    "app/routes/trips.py": 15,
    "app/routes/fuel.py": 30,
}


def git(*args, check=True):
    r = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)
    if check and r.returncode:
        sys.exit(f"git {' '.join(args)} failed:\n{r.stdout}\n{r.stderr}")
    return r.stdout


def split_hunks(path):
    diff = git("diff", "--", path).split("\n")
    try:
        first = next(i for i, l in enumerate(diff) if l.startswith("@@"))
    except StopIteration:
        sys.exit(f"{path} has no unstaged changes — has this already been run?")
    header, hunks, cur = diff[:first], [], None
    for line in diff[first:]:
        if line.startswith("@@"):
            if cur:
                hunks.append(cur)
            cur = [line]
        elif cur is not None:
            cur.append(line)
    if cur:
        hunks.append(cur)
    # `git diff` output ends with a newline, so splitting on "\n" leaves a
    # trailing empty element on the final hunk. Carried through, it becomes an
    # extra blank context line and `git apply` rejects any patch that includes
    # that hunk — while every subset without it applies cleanly, which is a
    # confusing way to fail. An empty context line in a real hunk is " ", not
    # "", so dropping a trailing "" is unambiguous.
    while hunks and hunks[-1] and hunks[-1][-1] == "":
        hunks[-1].pop()
    return header, hunks


def stage_hunks(path, indices):
    """Stage `path` as its HEAD content plus the selected hunks."""
    header, hunks = split_hunks(path)
    patch = "\n".join(header + [l for i in indices for l in hunks[i]])
    if not patch.endswith("\n"):
        patch += "\n"

    scratch = tempfile.mkdtemp(prefix="commit-audit-")
    try:
        target = os.path.join(scratch, path.replace("/", os.sep))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8", newline="") as fh:
            fh.write(git("show", f"HEAD:{path}"))
        patch_file = os.path.join(scratch, "subset.patch")
        with open(patch_file, "w", encoding="utf-8", newline="") as fh:
            fh.write(patch)

        r = subprocess.run(["git", "apply", "-p1", "--recount", patch_file],
                           cwd=scratch, capture_output=True, text=True)
        if r.returncode:
            sys.exit(f"could not apply hunks {indices} of {path}:\n{r.stderr}")

        text = open(target, encoding="utf-8").read()
        if path.endswith(".py"):
            ast.parse(text)          # a commit must never stage unparseable code
        sha = git("hash-object", "-w", "--", target).strip()
        git("update-index", "--add", "--cacheinfo", f"100644,{sha},{path}")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def stage_text(path, text):
    if path.endswith(".py"):
        ast.parse(text)
    scratch = tempfile.mkdtemp(prefix="commit-audit-")
    try:
        target = os.path.join(scratch, "blob")
        with open(target, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        sha = git("hash-object", "-w", "--", target).strip()
        git("update-index", "--add", "--cacheinfo", f"100644,{sha},{path}")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def stage_whole(*paths):
    git("add", "--", *paths)


def stage_deletion(*paths):
    """Record files that have been moved out of the tree as deleted."""
    git("add", "-A", "--", *paths)


def stage_untrack(*paths):
    """Stop tracking a path without removing it from disk.

    Used for the generated graphify artifacts: they stay on disk (the cache
    makes rebuilds cheap) but leave git history, where they were ~20 MB.
    """
    git("rm", "-r", "--cached", "--quiet", "--ignore-unmatch", "--", *paths)


def tlp_test_file_without_arrange_tests():
    """tests/test_tlp_routes.py as it should look in commit 1.

    The file arrives with the delete_package cascade; the auto-arrange
    regression tests land with their own fix in commit 2. Splitting it keeps
    each commit self-contained and green on its own.
    """
    src = open(os.path.join(REPO, "tests", "test_tlp_routes.py"), encoding="utf-8").read()
    start = src.index("class TestArrangeByShipment:")
    end = src.index("class TestDeletePackageCascade:")
    trimmed = src[:start] + src[end:]
    return trimmed.replace(
        "That is exactly where the 2026-08-06 audit found one:", "The first of those is",
    )


COMMITS = [
    # (subject, body, staging callable)
    (
        "fix(tlp): delete_package leaves orphaned placements and shipment items",
        """It deleted only tlp_packages, while the sibling clear_all_packages also
clears tlp_placements and tlp_shipment_items. This schema runs with
enable_fk=False and has no ON DELETE CASCADE -- both deliberate, see the note
at the top of the module -- so nothing else caught it. Orphaned placements
reload through the LEFT JOIN in list_plans with a null name and zero
dimensions: invisible boxes in a saved load plan.

Children are deleted first, so the rowcount deciding the 404 is still the
package row's own.

Adds tests/test_tlp_routes.py, the Truck Load Planner's first route-layer
test file.""",
        lambda: (stage_hunks("truck_load_planner/routes.py", [2]),
                 stage_text("tests/test_tlp_routes.py",
                            tlp_test_file_without_arrange_tests())),
    ),
    (
        "fix(tlp): auto-arrange by shipment_id returned an unhandled 500",
        """_get_packages_from_request selected `p.name AS package_name` and handed the
row to LegacyPackage.from_row, which reads row["name"]. tlp_shipment_items has
no `name` column, so the key did not exist and the handler -- which has no
try/except -- answered 500. Not an API-only corner: truck-load-planner.js:1403
sends shipment_id whenever a shipment is selected, so "select a shipment then
Auto Arrange" was dead. It went unnoticed because the table currently holds
zero shipment items.

A second defect sat behind it: `si.*` put the shipment *item's* id in
row["id"], so fixing only the KeyError would have produced placements carrying
the wrong package_id -- a loud crash traded for silent bad data. Both are
fixed together by replacing `si.*` with an explicit aliased column list.

Package.from_row is deliberately unchanged. Its other caller
(validate_placement) passes a genuine tlp_packages row and is correct today;
the query was what lied about its columns.

An item whose package no longer exists is now skipped with a warning rather
than arranged as a zero-dimension package.""",
        lambda: (stage_hunks("truck_load_planner/routes.py", [0, 1, 2, 3, 4]),
                 stage_whole("tests/test_tlp_routes.py")),
    ),
    (
        "fix(trips): geofence advance never ran past the first active trip",
        """do_refresh_route_data opened an explicit conn.execute('BEGIN') inside its
per-trip loop. That cannot work, in two independent ways:

1. Python's sqlite3 opens a transaction implicitly before the driver-name
   UPDATE immediately above it, so the explicit BEGIN raised "cannot start a
   transaction within a transaction";
2. on the normal path -- vehicle not yet at its stop -- neither commit branch
   ran, so the transaction stayed open and the next iteration's BEGIN raised
   the same error.

The per-trip except printed and moved on, so there was no error anybody saw.
The symptom was trips that quietly stopped advancing phase and never
auto-completed.

The BEGIN is removed and each iteration now ends in exactly one commit or
rollback, with the driver-name UPDATE moved inside so it rolls back with the
rest. This matches what api_advance_trip and api_cancel_trip already did.

This also closes a "database is locked" window: the uncommitted driver-name
write held a RESERVED lock from the top of the loop until the first commit in
the second half of the function, which is after N serial OpenRouteService
calls. Independent of the WAL / --workers decision, which is untouched.

Adds tests/test_trips_geofence.py, the first coverage of any kind for
app/routes/trips.py.""",
        lambda: (stage_hunks("app/routes/trips.py", TRIPS_GEOFENCE),
                 stage_whole("tests/test_trips_geofence.py")),
    ),
    (
        "fix(tlp): escape operator-supplied text before innerHTML",
        """The 2026-07-29 refactor moved every page onto UI.escapeHtml(). This file was
missed: it had zero calls, against 28 in delivery-plan-builder.js and 27 in
map.js, while interpolating package names, customer names, plate numbers,
container names and driver names straight into innerHTML. utils.js was already
loaded by the template, so the function was there and simply never used.

Thirteen interpolations across seven sites are now escaped, with `||` defaults
inside the call so a null never reaches escapeHtml. Numeric and boolean
interpolations are left alone.

With no authentication on any endpoint (deliberate, see CLAUDE.md), anything
that could reach the network could persist a payload via a package name and
have it execute in every dispatcher's browser on the TLP page.

tests/js/tlp-escaping.test.js is deliberately dependency-free -- no jsdom -- so
it still runs in a checkout with no node_modules. What it guards against would
recur years from now, and a test that needs setup is a test that stops being
run.""",
        lambda: stage_whole("static/js/truck-load-planner.js",
                            "tests/js/tlp-escaping.test.js"),
    ),
    (
        "fix(routes): close the connection on the exception path in write handlers",
        """fleet.py, fuel.py, oil.py and trips.py all followed

    try:
        conn = sqlite3.connect(...)
        ...
        conn.close()
        return jsonify(...)
    except Exception as e:
        return jsonify({...}), 500

so an exception skipped the close. On a read handler that is a standards
violation and little more. On a write handler it is not: if the exception
lands after a write but before the commit, SQLite holds a RESERVED lock until
garbage collection, and production is a single synchronous Gunicorn worker
with no WAL, so a concurrent request meets "database is locked". Same failure
mode as the geofence bug, one size down.

All 22 write handlers now close in a finally. Read-only handlers are
deliberately left alone. Raw sqlite3.connect() stays -- the DB-access-pattern
split is deliberate and was not migrated.

tests/test_write_handler_connections.py swaps sqlite3.connect for a wrapper
whose cursor() raises, which forces the exception at exactly the point the
finally exists to cover, uniformly across all 18 reachable endpoints.""",
        lambda: (stage_whole("app/routes/fleet.py", "app/routes/oil.py"),
                 stage_hunks("app/routes/trips.py", TRIPS_ALL),
                 stage_hunks("app/routes/fuel.py", FUEL_WRITE_HANDLERS),
                 stage_whole("tests/test_write_handler_connections.py")),
    ),
    (
        "perf(fuel): GET /api/fuel-log opened 1,900 connections per request",
        """api_fuel_log_list called four helpers per row, each opening its own
connection and two of them opening a second. Measured against the live
database: 1,900 connections and 591 ms for 323 rows, all serialised behind the
single synchronous worker.

The helpers now take an optional conn, and the two loops (list and export)
pass their open connection down. Same request: 1 connection, 31 ms. The
parameter is optional so the create and update handlers, which compute a
single entry, are untouched.

The payload is unchanged, and that is the whole safety argument, so
test_response_is_unchanged_by_connection_reuse asserts it directly by
reproducing the old per-helper behaviour and diffing the two responses.

Adds tests/test_fuel_routes.py, the first route-layer coverage for
app/routes/fuel.py.""",
        lambda: (stage_hunks("app/routes/fuel.py", FUEL_ALL),
                 stage_whole("tests/test_fuel_routes.py")),
    ),
    (
        "docs: audit report, plan, changelog, and corrections to CLAUDE.md",
        """Adds docs/AUDIT_2026-08-06.md (findings, each reproduced against live code
or data) and docs/BUGFIX_PLAN_2026-08-06.md (the phased plan the preceding
commits implement), plus the dated CHANGELOG entry.

Corrects three claims in CLAUDE.md that had drifted from the code:

- render.yaml *does* declare a 20 GB persistent disk at /var/data, so the
  database and the delivery photos survive a redeploy. The note said the
  opposite and told the reader to go check the dashboard.
- playwright is pinned in requirements.txt. The note called it a missing
  dependency. requirements.txt is UTF-16, so grep finds nothing and tells you
  the opposite -- now recorded.
- test counts, the new route-layer suites, and the rebuilt graph
  (3,104 nodes / 5,957 edges / 200 communities).

services/plate_utils.py's docstring claimed the 5-digit serial was "globally
unique". It is not -- it carries no province code, so 50H-09473 and 51C-09473
collapse to the same key. No behaviour change: VehicleIndex._ambiguous_serials
and _gps_by_plate_key already handle collisions, and this fleet has none
today. The docstring now says so and names both guards.

The rest of the reference set is brought in line: test counts and the new
route-layer suites in README.md and DELIVERY_MODULE.md; both auto-arrange
payload shapes, the manual-cascade delete rule and the escaping rule in
TRUCK_LOAD_PLANNER.md; addendum 2026-08-06b in CODEBASE_ANALYSIS_REPORT.md with
items 23 and 27 corrected. DELIVERY_AUDIT_2026-07-31.md **closes D-10** -- its
only "verify this first" Critical -- because render.yaml does declare the
persistent disk; D-09's reasoning is corrected in place with a dated note
rather than edited away.

Note README.md and DELIVERY_MODULE.md also carried uncommitted edits that
predate this work; they are included here rather than split out.""",
        lambda: stage_whole("docs/AUDIT_2026-08-06.md",
                            "docs/BUGFIX_PLAN_2026-08-06.md",
                            "docs/CONCURRENCY_PLAN_2026-08-06.md",
                            "docs/CHANGELOG.md",
                            "docs/TRUCK_LOAD_PLANNER.md",
                            "docs/CODEBASE_ANALYSIS_REPORT.md",
                            "docs/DELIVERY_AUDIT_2026-07-31.md",
                            "docs/DELIVERY_MODULE.md",
                            "README.md",
                            "CLAUDE.md",
                            "services/plate_utils.py",
                            "graphify-out",
                            "scripts/commit_audit_fixes.py"),
    ),
    (
        "chore: drop stale generated docs, stop tracking graphify artifacts",
        """Removed:

- project_tree.txt -- 274 KB, UTF-16, generated 2026-07-30 by `tree` *without*
  /F, so it lists directories and no filenames at all. 3,225 of its 3,685 lines
  are directory names and 453 are graphify cache folders. Nothing referenced
  it, and graphify plus the actual filesystem answer the question it was
  trying to.
- INSTRUCTIONS.md -- the prompt that commissioned the delivery audit ("Perform
  a complete architectural investigation... Do not modify any files"). That
  audit shipped as docs/DELIVERY_AUDIT_2026-07-31.md on 2026-07-31; the brief
  has been spent since.
- reports/*.txt -- four benchmark and diagnostic outputs from 2026-07-29.
  tests/test_all.py regenerates them on demand and creates the directory
  itself, so both the files and the tracking were disposable.

Untracked but kept on disk: graphify-out/cache/ (~9 MB AST extraction cache,
rebuilt by `graphify update .`) and the rotating dated backup directories
(~2-3 MB each). Together they were roughly 20 MB of generated artifacts in git
history. graph.json, graph.html and GRAPH_REPORT.md stay tracked -- they are
what the standing "query the graph before grepping" instruction reads.

.gitignore gains rules for all of the above plus node_modules/, so none of it
comes back.

Kept deliberately: graphify-cli-reference.txt, despite looking like a
candidate. CLAUDE.md records that graphify has no per-subcommand --help and
that asking for one returns real-looking noise, so a full CLI dump is load
bearing. The two Vietnamese report files at the repo root are unrelated to the
app but they are not redundant, and they are not this commit's business.""",
        lambda: (stage_deletion("project_tree.txt", "INSTRUCTIONS.md", "reports"),
                 stage_untrack("graphify-out/cache",
                               "graphify-out/2026-07-30",
                               "graphify-out/2026-07-31",
                               "graphify-out/2026-08-02",
                               "graphify-out/2026-08-06"),
                 stage_whole(".gitignore")),
    ),
]


def preflight():
    problems = []

    head = git("rev-parse", "HEAD").strip()
    if head != EXPECTED_HEAD:
        problems.append(
            f"HEAD is {head[:8]}, expected {EXPECTED_HEAD[:8]}. These commits were "
            "prepared against that revision; the hunk indices may not fit yours.")

    for path, expected in EXPECTED_HUNK_COUNTS.items():
        _, hunks = split_hunks(path)
        if len(hunks) != expected:
            problems.append(
                f"{path} has {len(hunks)} diff hunks, expected {expected}. The file "
                "has changed since the split was worked out; aborting rather than "
                "guessing which hunk is which.")

    for path in ("project_tree.txt", "INSTRUCTIONS.md"):
        if os.path.exists(os.path.join(REPO, path)):
            problems.append(
                f"{path} still exists — it was moved to _trash_2026-08-06/ as part of "
                "the cleanup commit. Restore that move or drop the last commit.")

    for path in ("tests/test_tlp_routes.py", "tests/test_trips_geofence.py",
                 "tests/test_fuel_routes.py",
                 "tests/test_write_handler_connections.py",
                 "tests/js/tlp-escaping.test.js",
                 "docs/AUDIT_2026-08-06.md", "docs/BUGFIX_PLAN_2026-08-06.md"):
        if not os.path.exists(os.path.join(REPO, path)):
            problems.append(f"missing expected new file: {path}")

    if git("diff", "--cached", "--name-only").strip():
        problems.append("the index is not empty — run `git reset` first")

    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="verify preconditions and print the plan, commit nothing")
    args = ap.parse_args()

    problems = preflight()
    if problems:
        print("Refusing to run:\n")
        for p in problems:
            print("  - " + p)
        sys.exit(1)

    print("Preconditions OK. Plan:\n")
    for i, (subject, _, _) in enumerate(COMMITS, 1):
        print(f"  {i}. {subject}")
    print()

    if args.check:
        print("--check given; nothing was committed.")
        return

    for i, (subject, body, stage) in enumerate(COMMITS, 1):
        stage()
        git("commit", "-m", f"{subject}\n\n{body}")
        sha = git("rev-parse", "--short", "HEAD").strip()
        print(f"  [{sha}] {subject}")

    print("\nDone. Verify with:")
    print("  git log --oneline -8")
    print("  git status --porcelain          # only the pre-existing CRLF churn should remain")
    print("  git diff HEAD                   # should be empty for the files above")
    print("\nTo undo:  git reset --soft HEAD~8")


if __name__ == "__main__":
    main()
