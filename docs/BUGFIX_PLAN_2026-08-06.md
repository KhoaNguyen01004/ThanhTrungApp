# Bug-fix plan — findings of `docs/AUDIT_2026-08-06.md`

**Status: approved and fully implemented, 2026-08-06.** All seven phases landed;
`pytest tests/` is 548 passing. Each fix was mutation-checked — reverted, the new tests
confirmed failing, restored. See `docs/CHANGELOG.md` for what shipped.

This document is kept as the historical record of what was *planned*. The body below is
unedited; three things it says turned out to be wrong, corrected here rather than in place:

- **"Full suite must be 491+ passing"** — the final figure is 548 (491 + 57 new).
- **"`playwright` … is a missing dev dependency … should go into `requirements.txt`"** —
  it was already there (`playwright==1.61.0`). `requirements.txt` is UTF-16, so `grep`
  finds nothing and reports the opposite. Nothing was added.
- **"§5 plate collision guard"** — `services/vehicle_identity.py` already had one
  (`VehicleIndex._ambiguous_serials`). That item shrank from a code change to a docstring
  correction.

Two estimates were also off: the connection-close work was **22 handlers, not ~14**, and
Phase 3 was **13 interpolations across 7 sites**, not a whole-file rewrite.

Scope agreed with the operator on 2026-08-06:

| Audit finding | In scope | Note |
|---|---|---|
| §1 shipment auto-arrange 500 | ✅ Phase 1 | |
| §2 `trips.py` geofence transaction | ✅ Phase 2 | |
| §3 TLP XSS | ✅ Phase 3 | |
| §4 connection close | ✅ Phase 4 | **write handlers only** — read-only handlers keep the current pattern |
| §4 N+1 fuel connections | ✅ Phase 5 | |
| §5 `delete_package` orphans | ✅ Phase 6 | |
| §5 plate collision guard | ✅ Phase 6 | **shrunk — see below** |
| §5 TTAS case-tolerance | ❌ deferred | latent only; no current phrase triggers it |
| §5 `zoomToAll` dead code, `0.0` coordinate check | ❌ deferred | cosmetic |

**Correction to the audit, found while planning:** `services/vehicle_identity.py` **already has** the collision guard — `VehicleIndex._ambiguous_serials` detects two full plates sharing a serial, logs a warning, and refuses to resolve rather than guessing. §5's "plate collision guard" therefore shrinks from a code change to a docstring correction in `plate_utils.py`. Phase 6 is smaller than the audit implied.

Phases 1 and 2 are independent and can be approved separately. Phase 6's `delete_package` fix should land **before or with** Phase 1, because it changes how many orphaned shipment items Phase 1's query has to tolerate.

---

## Phase 1 — Shipment auto-arrange returns 500

**Files:** `truck_load_planner/routes.py` (`_get_packages_from_request`, ~lines 702-719) · new `tests/test_tlp_routes.py`

### Approach

Fix the **query**, not `Package.from_row`. `from_row` has two callers: `routes.py:626` passes a genuine `tlp_packages` row and works correctly today. Loosening `from_row` to tolerate aliased columns would make it lie about its contract for both callers to accommodate one bad query. The query is what's wrong.

Replace `si.*` with an explicit column list aliased to what `from_row` expects:

```sql
SELECT si.quantity, si.notes,
       p.id AS id, p.name AS name,
       p.length, p.width, p.height, p.weight_kg,
       p.allow_stacking, p.allow_rotation, p.fragile, p.color,
       p.max_top_weight_kg, p.max_stack_layers
FROM tlp_shipment_items si
LEFT JOIN tlp_packages p ON p.id = si.package_id
WHERE si.shipment_id = ?
```

Dropping `si.*` fixes **both** defects in one change: `name` now exists (the `KeyError`), and `id` is the package id rather than the shipment-item id (the silently-wrong `package_id` hiding behind it). Fixing only the first would convert a loud 500 into quiet data corruption, so they must land together.

**Orphaned shipment items.** The `LEFT JOIN` stays, but rows where `p.id IS NULL` get skipped with a `logger.warning` naming the shipment and missing `package_id`, rather than being arranged as a zero-dimension package. This matches the loud-degradation pattern `_gps_by_plate_key` already uses in `services/delivery/routes.py:69-80` — no new convention introduced. Phase 6 stops new orphans being created; this handles any that already exist.

**Noted, deliberately not changed:** the `for _ in range(qty)` loop appends the *same* `EnginePackage` instance `qty` times. `Package` is a mutable dataclass, but no mutation of package instances was found in `engine/planner.py` or `engine/state.py`, so this is safe today. The frontend's `packages` path doesn't share instances. I'll re-verify during implementation and report it rather than change it — out of scope per Scope Control.

### Tests

`truck_load_planner` has **no route-layer tests at all**. `test_all.py` is a script (0 `def test_`), `test_auto_arrange_e2e.py` and `test_scorer.py` drive `Planner.auto_arrange()` directly — none of them can see a bug inside a request handler. That is exactly the gap `tests/test_delivery_routes.py` was written to close for delivery, and this bug is the same shape.

New `tests/test_tlp_routes.py`, modelled on `test_delivery_routes.py`'s fixtures (temp DB via `DB_PATH` before importing `app`, real `app.test_client()`):

1. `POST /api/tlp/auto-arrange` with `{shipment_id}` returns 200, not 500 — the regression test.
2. Every returned placement's `package_id` matches a real `tlp_packages.id`, and equals the shipment item's `package_id` — catches the second defect.
3. `{shipment_id}` and the equivalent `{packages}` payload produce the same placement count and the same package ids — pins the two paths together so they can't diverge again.
4. A shipment item pointing at a deleted package is skipped, not arranged as a zero-size box.

### Acceptance criteria

- Selecting a shipment in the TLP UI and clicking Auto Arrange returns placements instead of a 500.
- **Mutation check:** revert the query change, confirm tests 1 and 2 both fail, restore.
- `pytest tests/` still 491 + new tests, 0 failures.

---

## Phase 2 — `trips.py` geofence transaction

**Files:** `app/routes/trips.py` (lines ~299-358) · new `tests/test_trips_geofence.py`

### Approach

Remove the explicit `conn.execute('BEGIN')` at line 304 and let Python's implicit transaction stand, with exactly one `commit()` or `rollback()` per loop iteration. This is not a new pattern — it is the pattern the rest of the file already uses (`api_advance_trip`, `api_cancel_trip` both do plain `c.execute(...)` → `conn.commit()` with no explicit `BEGIN`). The explicit `BEGIN` is the odd one out, and it is what breaks.

Target structure:

```python
try:
    if driver_name and driver_name != active_trip.get('driver_name', ''):
        c.execute('UPDATE vehicle_trips SET driver_name = ? ...', (driver_name, trip_id))

    target_lat, target_lng, target_name, target_type = get_target_for_phase(db_phase)
    if target_name and target_lat and target_lng:
        target_location = state.known_locations.get(target_name)
        if target_location and is_point_in_location(...):
            ...geofence inserts/updates, unchanged...
    conn.commit()
except Exception:
    conn.rollback()
    raise
```

Three things this has to get right:

- The **driver-name `UPDATE` moves inside** the same try/commit. Today it sits outside and is what opens the transaction that the `BEGIN` then collides with.
- The `continue` at line 344 currently returns to the loop having already committed. Under the new structure it must not skip the commit — restructured so the commit precedes it, or replaced with a flag.
- The blanket `except Exception` per trip at line 357 **stays**. One bad trip should not abort the refresh for the others. It should keep printing, but it will stop being the thing that hides this bug because the bug will be gone.

**Knock-on this resolves:** the uncommitted driver-name write currently holds a `RESERVED` lock from line 301 until the first commit in the *second* half of the function — which is after N serial `get_route_coords()` ORS calls. Committing per iteration closes that window. This reduces `database is locked` pressure independently of the WAL / `--workers` decision, which stays untouched and unaddressed here.

### Tests

`trips.py` has no tests. New `tests/test_trips_geofence.py` drives `do_refresh_route_data()` directly with `fetch_vehicle_data` patched to return fixed positions:

1. Three active trips, none at their target, driver names changed → all three process without `OperationalError`, and `conn.in_transaction` is `False` afterwards. **This test fails against current code** (reproduced during the audit: all three raise `cannot start a transaction within a transaction`).
2. Three active trips, the *third* inside its geofence → that trip's phase advances. Currently it cannot, because iterations 2 and 3 never reach the geofence check.
3. A trip arriving at its final stop completes and activates the next queued trip — pins the `continue` path that the restructure touches.
4. An exception mid-iteration rolls back that trip's writes and leaves the other trips' work committed.

### Acceptance criteria

- Tests 1-4 pass; **mutation check:** restore the `BEGIN`, confirm 1 and 2 fail, remove it again.
- Manual: with two or more active trips, watch a phase advance on the second one — the behaviour that is currently silently dead.
- `pytest tests/` green.

---

## Phase 3 — XSS in `static/js/truck-load-planner.js`

**Files:** `static/js/truck-load-planner.js` (13 lines)

### Approach

Wrap the 13 string-field interpolations in `UI.escapeHtml()`. `utils.js` is already loaded by `templates/truck-load-planner.html:1581`, so nothing new is imported and no new pattern is introduced — this brings the file in line with the other 11 JS files.

The exact 13 sites, confirmed by scan:

| Line | Expression |
|---|---|
| 1552 | `${r.plate_number}` |
| 1930 | `${p._name \|\| "Unknown"}` |
| 2282 | `${pkg.name}` |
| 2474 | `${v.plate_number}` |
| 2475 | `${v.vehicle_type \|\| ""}`, `${v.container_name \|\| ""}`, `${v.current_driver \|\| "No driver"}` |
| 2549 | `${s.customer_name}` |
| 2550 | `${s.reference_number \|\| "No ref"}` |
| 2667 | `${item.package_name}` |
| 2719 | `${p.name \|\| "Unnamed"}` |
| 2720 | `${p.plate_number \|\| "?"}`, `${p.status \|\| "draft"}` |

The `||` default goes **inside** the call — `${UI.escapeHtml(v.vehicle_type || "")}` — so a `null` never reaches `escapeHtml`. Numeric and boolean interpolations (`${pkg.length}`, `${item.quantity}`, `${p.id}`, `${color}`) are left alone; escaping them would be noise.

### Tests

No automated coverage is possible from my sandbox — `tests/js/` needs `jsdom` and there's no npm registry access here. Verification is yours to run:

1. `node --check static/js/truck-load-planner.js`
2. `NODE_PATH=<your node_modules> node tests/js/dashboard.test.js` (122; expect 121 after local noon, or use `TZ=UTC`) and `tests/js/plan-builder.test.js` (10) — these don't cover this file, but confirm nothing else regressed.
3. Manual: create a package named `<img src=x onerror=alert(1)>`, confirm it renders as literal text in the package list, the shipment modal and the saved-plans list. Delete it afterwards.

### Acceptance criteria

- All 13 sites escaped; a scripted payload in a package or customer name renders as text.
- No behaviour change for ordinary names, including ones with `&` or accented Vietnamese characters.

---

## Phase 4 — Connection close on write handlers

**Files:** `app/routes/fleet.py`, `app/routes/fuel.py`, `app/routes/oil.py`, `app/routes/trips.py`

### Approach

**21 handlers, 22 `connect()` sites** — slightly more than the "~14" I estimated when we scoped this; the exact list is below. Read-only handlers are deliberately left alone per your decision.

| File | Handlers |
|---|---|
| `fleet.py` | `api_vehicles_create`, `api_vehicle_set_container`, `api_vehicles_update`, `api_vehicles_delete`, `api_vehicles_bulk_delete`, `api_vehicle_types_create`, `api_vehicle_types_delete` |
| `fuel.py` | `api_fuel_log_create` (2 sites), `api_fuel_log_update`, `api_fuel_log_delete`, `api_fuel_log_profile_update`, `api_fuel_log_profile_delete`, `api_fuel_sync` |
| `oil.py` | `_store_km_log`, `api_oil_maintenance_create`, `api_oil_maintenance_update`, `api_oil_maintenance_delete`, `api_oil_maintenance_mark_done`, `api_oil_maintenance_fetch_km` |
| `trips.py` | `api_advance_trip`, `api_cancel_trip` |

Each becomes:

```python
conn = None
try:
    conn = sqlite3.connect(config.DB_PATH)
    ...
finally:
    if conn is not None:
        conn.close()
```

Two details:

- Several handlers already call `conn.close()` before an early `return` (e.g. `fuel.py:753`, `trips.py:75`). `sqlite3.Connection.close()` is idempotent, so a `finally` on top is harmless — but the inner calls get removed anyway so there's one exit path, not two.
- `api_fuel_sync` already has a `finally` on its first connection (line 818). Only its second (839) needs changing.

Raw `sqlite3.connect()` stays — the DB-access-pattern split is deliberate per `CLAUDE.md` and is not being migrated to `DatabaseManager` here.

### Tests

`fleet.py` has 11 route tests (`tests/test_fleet_routes.py`). **`fuel.py` and `oil.py` have zero** — no test in the repo touches `/api/fuel-log` or `/oil-change`. Rather than build two full suites (the option you declined), each edited handler gets one targeted test: force an exception mid-handler via `monkeypatch`, assert the response is still a 500 JSON **and** that the connection was closed (tracked with a `sqlite3.connect` wrapper). That's ~21 small tests that directly pin the thing being changed, without inventing coverage for behaviour nobody is touching.

### Acceptance criteria

- Every listed handler closes its connection on both the success and the exception path.
- `pytest tests/test_fleet_routes.py` still 11/11 — the handlers' happy-path behaviour is unchanged.
- **Mutation check:** remove one `finally`, confirm its test fails.

---

## Phase 5 — N+1 connections in `/api/fuel-log`

**Files:** `app/routes/fuel.py`

### Approach

`api_fuel_log_list` opens one connection, then per row calls `_compute_fuel_entry`, `_enrich_fuel_entry`, `_compute_baseline` (which calls `_get_normal_l_per_100km`, and may open a second for its fallback) and `_get_anomaly_multiplier` — each opening its own. At 323 rows that's on the order of 1,300 connections for one request, blocking your single synchronous worker throughout.

Give each helper an optional connection parameter, defaulting to `None`:

```python
def _compute_fuel_entry(row: dict, conn=None) -> dict:
    own = conn is None
    if own:
        conn = sqlite3.connect(config.DB_PATH)
    try:
        ...
    finally:
        if own:
            conn.close()
```

Then `api_fuel_log_list` (and `api_fuel_log_export`, which has the same loop) passes its already-open connection down. Every other caller keeps working unchanged because the parameter is optional — no call site outside this file has to know.

This is deliberately the smallest change that removes the connection churn. It does **not** restructure the queries into a join or add caching; that would be a rewrite of the fuel entry pipeline, which Long-Term Maintainability says to avoid for a problem this one solves.

### Tests

New `tests/test_fuel_routes.py` (first route coverage for this file):

1. `GET /api/fuel-log` returns byte-identical JSON before and after the change, against a seeded fixture — this is the whole safety argument, so it's the test that matters.
2. Connection count for one `GET /api/fuel-log` over N rows is O(1), not O(N) — counted with a `sqlite3.connect` wrapper. Pins the fix against regression.
3. Each helper still works when called with no connection, so the optional parameter didn't break the standalone path.

### Acceptance criteria

- Identical response payload before/after on the same data.
- Connection count for an unfiltered `GET /api/fuel-log` drops from ~1,300 to single digits.
- Page load time measured before and after, reported in the summary.

---

## Phase 6 — Small fixes

**Files:** `truck_load_planner/routes.py` (~line 262) · `services/plate_utils.py` (docstring)

1. **`delete_package` cascade.** Mirror what `clear_all_packages` (lines 271-278) already does, scoped to one package:

   ```python
   c.execute("DELETE FROM tlp_placements WHERE package_id = ?", (pkg_id,))
   c.execute("DELETE FROM tlp_shipment_items WHERE package_id = ?", (pkg_id,))
   c.execute("DELETE FROM tlp_packages WHERE id = ?", (pkg_id,))
   ```

   `enable_fk=False` and the missing `ON DELETE CASCADE` both stay as they are — deliberate per `CLAUDE.md`, and changing either would break the three other delete routes. Test: create a package, place it, delete it, assert no orphan rows remain.

2. **`plate_utils.normalize_plate` docstring.** Drop the "globally unique" claim — Vietnamese plates carry a province prefix, so `50H-09473` and `51C-09473` collapse to the same key. Document that the caller is responsible for collisions, and point at `VehicleIndex._ambiguous_serials` and `_gps_by_plate_key`, which both already handle it. Also document that trailing digits in a device name (`"51C-12345 (xe 2)"`) produce the wrong key.

   **No behaviour change** — the function is correct for this fleet's data (verified: 36 vehicles, 0 collisions, all 31 `fuel_log` plates resolve). Only the comment is wrong.

3. **`docs/CHANGELOG.md`** — one dated entry covering Phases 1, 2 and 3, in the style of the 2026-07-29 entry. Phases 4-6 are self-contained fixes and don't warrant their own entries.

---

## Execution order and checkpoints

```
Phase 6.1 (delete_package)  ──┐
                              ├──> Phase 1 (shipment 500)   ──> checkpoint
Phase 2 (geofence)  ──────────────────────────────────────  ──> checkpoint
Phase 3 (XSS)  ────────────────────────────────────────────  ──> you verify in browser + node
Phase 4 (conn close)  ─────────────────────────────────────  ──> checkpoint
Phase 5 (N+1 fuel)  ───────────────────────────────────────  ──> checkpoint
Phase 6.2/6.3 (docstring, changelog)
```

One phase at a time, verified before the next starts, per the Large Feature Workflow. At each checkpoint: relevant suite green, mutation check done, and a 2-3 sentence summary.

**Full suite must be 491+ passing and 0 failing at every checkpoint.** `tests/test_delivery_routes.py` needs `playwright` installed to run at all — that's a missing dev dependency, not a regression, and it should go into `requirements.txt` (or a dev-requirements file) as part of Phase 1 so the next person doesn't lose an afternoon to 135 phantom errors.

**Things I will not touch**, restating so it's on the record: authentication stays absent; the DB-access-pattern split stays; the frontend toast/escape split stays; `app/routes/trips.py:403`'s legacy speed regex stays; `database.sql` stays exactly as it is; the WAL / `--workers` pair stays unaddressed; root-level non-app files stay ignored.

---

## What I need from you

Approve per phase or as a whole. Two specific calls worth making explicitly:

1. **Phase 1's new `tests/test_tlp_routes.py`** is the first route-layer test file for the truck load planner. It's the main reason this phase is more than a two-line fix, and it's what stops the same class of bug recurring. Worth it, or do you want the fix alone for now?
2. **Phase 4's ~21 targeted tests** — same question. The alternative is fixing the handlers with no test, which for `fuel.py` and `oil.py` means nothing catches a mistake but you, in production.
