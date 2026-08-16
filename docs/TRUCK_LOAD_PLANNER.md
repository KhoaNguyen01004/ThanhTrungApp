# Truck Load Planner — Algorithm, API & Frontend Reference

Flask-based 3D/2D bin-packing planner: multi-vehicle distribution, single-vehicle
placement/scoring/stacking, door-access validation, and step-by-step 3D placement
animation. This is the canonical reference for the TLP subsystem — it replaces the
former separate `SORTING_STRATEGY.md` and `SYSTEM.md` (merged 2026-07-30; their content
had drifted into three overlapping, partly-contradictory copies across
`SORTING_STRATEGY.md`, `SYSTEM.md`, and `README.md`'s old "Algorithm Reference" section).

## 1. Package Sort Order (Pre-Processing)

All packages are sorted by **non-stackable first, then descending width, then descending length, then descending volume, then descending weight** before any placement logic runs. The same sort is used in both single-vehicle and multi-vehicle paths.

**Source**: `engine/auto_arrange.py` → `LargestFirstStrategy`, `engine/distribution.py` → `distribute_across_vehicles()`

```python
sorted_packages = sorted(
    packages,
    key=lambda p: (
        0 if not p.stackable else 1,                        # non-stackable first
        -p.width_mm,                                        # width desc
        -p.length_mm,                                       # length desc
        -(p.length_mm * p.width_mm * p.height_mm),          # volume desc
        -p.weight_kg,                                       # weight desc
    ),
)
```

### Rationale

Non-stackable packages must go on the floor — placing them first ensures they get floor space before stackable packages consume it. After that, the widest packages come first so the X-slice filling heuristic can pack the full container width as early as possible, reducing blocking. Length, volume, and weight are secondary tie-breakers.

---

## 2. Vehicle Selection (Multi-Vehicle Distribution)

When no single `vehicle_id` is specified, packages are distributed via
`distribute_across_vehicles()` (`engine/distribution.py`), which delegates candidate
*ordering* to a pluggable `VehicleSelectionStrategy`
(`engine/vehicle_selection.py`). The default is **`SmallestVehicleThatFitsStrategy`**,
which minimizes fleet size/cost:

```
Input:  packages[], vehicle_sessions[]
Output: { placed, failed, unplaced, vehicle_map }

1. Sort packages by width DESC, length DESC, volume DESC, weight DESC (non-stackable first)
2. Vehicle selection (SmallestVehicleThatFitsStrategy.select_vehicles):
     Sort vehicles by capacity (volume × payload) ASCENDING
     For each vehicle, smallest first:
       Cheap prefilter (_cheap_could_fit_all): total volume/weight vs. capacity,
         each package's footprint vs. cargo cross-section (with rotation) —
         reject obviously-infeasible vehicles with no arrangement attempt
       If it passes: probe with a single fast pass (strategy="largest_first"),
         not the 15-pass "optimized" strategy
       If everything placed: reset to empty, re-run "optimized" once on just
         this vehicle to refine the layout, use it alone, done
     If no single vehicle fits everything: fall back to DESCENDING (largest-
     first) order for the incremental multi-vehicle loop below — filling big
     vehicles first uses fewer trucks overall than filling small ones first
3. For each selected vehicle (in the order chosen above):
     Delegate to the same per-package placement pipeline the single-vehicle
     path uses (auto_arrange.py::_run_ordered_pass), not a separate
     hand-written copy — see Section 3
4. Return { placed, failed, unplaced, vehicle_map }
```

Notes/tradeoffs:
- The cheap prefilter is a *necessary, not sufficient* condition (it can't predict real
  packing efficiency/clearance losses), so some vehicles that pass it still fail the
  real single-vehicle probe. This means the single-vehicle-fits-all search costs more
  than a naive "always largest-first" approach when nothing fits alone — that cost buys
  the ability to use one smaller (cheaper) truck instead of a larger one when a shipment
  genuinely fits, which a pure largest-first approach can't discover.
- `LargestVehicleFirstStrategy` (`vehicle_selection.py`) is available as an explicit
  alternative (`StrategyRegistry.get("largest_first")`) for callers that want to skip
  the single-vehicle search entirely.

---

## 3. Intra-Vehicle Placement (Single Vehicle)

Once a vehicle is selected, a `StrategyRegistry`-registered strategy places packages
one at a time. The route default (`routes.py`) is **`optimized`**
(`OptimizedStrategy`), not `LargestFirstStrategy` — `LargestFirstStrategy` is a
simpler, faster single-pass strategy still registered and available, but not the
default entry point.

**Source**: `engine/auto_arrange.py` → `LargestFirstStrategy.arrange()` /
`OptimizedStrategy.arrange()`

### `LargestFirstStrategy` — single-pass algorithm

```
For each package p in sorted_packages:

  // Step 1 — Generate candidate points
  candidates = {(0, 0, 0)}
  for each placed package pl:
    candidates.add((pl.x + pl.length + 2×clearance, pl.y, pl.z))  // right face
    candidates.add((pl.x, pl.y + pl.width + 2×clearance, pl.z))   // front face
    candidates.add((pl.x, pl.y, pl.z + pl.height))                // top face

  // Step 2 — Expand with rotations
  expanded = []
  for each (x,y,z) in candidates:
    expanded.add({x, y, z, rotation=0})
    if p.allow_rotation:
      expanded.add({x, y, z, rotation=90})

  // Step 3 — Score (see Section 4 for the real term list/weights) and pick best
  best = null
  for each pos in expanded:
    if validate(p, pos) is valid:
      score = evaluate(p, pos)
      if score > best.score:
        best = {score, pos}

  // Step 4 — Commit
  if best found: place_package(p, best.pos)
  else: mark as unplaced
```

No post-processing, no repair, no gap-filling, no compaction. The first valid placement
is the final one.

**Tighten Position**: `tighten_position()` (`candidate_points.py`) snaps a generated
candidate back toward the nearest valid extreme point after initial generation, closing
small gaps left by the corner-based candidate set.

### `OptimizedStrategy` — the actual live default

Runs the `LargestFirstStrategy`-style pass repeatedly: **5 package orderings × 3
scoring-weight profiles = 15 full arrangement passes** per call
(`auto_arrange.py:272-328`), keeping whichever trial placed the most packages at the
best utilization/score, and early-exits the sweep only once a trial places every
package. This is the primary identified cause of "auto-arrange is slow" for realistic
package counts — the 15x multiplier itself is unchanged (early-exit tuning was
attempted then reverted — see `CHANGELOG.md`'s Phase 3 entry for why). It respects a
caller-configured `candidate_limit` (see §9) rather than discarding it every trial.

---

## 4. Scoring Strategy

**Source**: `engine/scorer.py` → `score_placement()`, `SCORING_WEIGHTS`

Each candidate position gets a `raw_score × weight` per term, summed into `total`.
Terms are **not** on a consistent 0-1 scale — some (`contact_area`, `x_position`) are
ratios multiplied by a large weight; others (`usable_space`, `stack_level`,
`tower_height`) are already large raw numbers with weight `1`. This mixed convention is
a known readability wart, not a bug in itself.

### Terms & Weights

| Term | Weight | Raw range | Calculation | Why |
|------|--------|-----------|--------------|-----|
| `contact_area` | 1000 | 0–1 | Sum of coincident-face overlap areas ÷ max possible | Maximise contact density |
| `x_position` | 200 | 0–1 | Row/slice completion at the deepest X reached so far, within the candidate's own height band (`_score_x_position`) — higher = closes out the current row instead of skipping ahead into fresh depth | Reduces blocking behavior |
| `weight_balance` | 50 | 0–1 | `1 − \|y_cog − container.width/2\| / (container.width/2)` | Even weight distribution across width |
| `usable_space` | 3 | -500 to 500 | Gap-awareness: rewards positions that don't leave a dead strip too narrow for any remaining package (see `_score_usable_space`) | The only real gap-filling term — weighted high enough that a bad gap can't be outweighed by a merely-good `contact_area` score |
| `stack_level` | 1 | -500 to 200 | Floor=200, layer1=150, layer2=50, layer3+=-500 | Prefer floor, but not overwhelmingly — kept intentionally close between floor and layer1 so `contact_area`/`usable_space` can tip a genuinely-better stack into winning |
| `tower_height` | 1 | -800 to 100 | Based on the tallest stack anywhere in the candidate's XY neighbourhood (not just directly below) | Discourage building next to/on top of an already-tall tower |

`OptimizedStrategy`'s `dense`/`stack_friendly` weight-profile trials
(`auto_arrange.py::_weight_profiles`) override `usable_space` to `2.0`/`2.5` and
`x_position` to `350.0`/`300.0` — these are **independently pre-tuned absolute values**,
not multipliers relative to the base weights above. Don't scale them proportionally if
the base weights change again — doing so during development caused a measurable
regression in aggregate placement rate (a 36-scenario sweep dropped from ~75% to ~70%
placed under `OptimizedStrategy`) before being caught and reverted.

---

## 5. Stacking Strategy

**Source**: `engine/support.py` → `check_support()`

### Combined-Support Model (Capacity-Based)

```
For a candidate at z > 0:

1. Collect packages directly below (zmax match)
2. Hard column-depth cap: how many packages deep is the tallest column
   among the below packages? If placing the candidate would reach
   _SYSTEM_MAX_STACK_LAYERS (3) packages in that single-file column →
   reject, regardless of any per-package max_stack_layers setting
   (_tower_depth() in engine/support.py)
3. For each below package:
   - Check stacking mode: NONE → reject, LIGHT_ONLY → enforce max_top_weight_kg
   - Must not exceed max_stack_layers already stacked directly on IT
     specifically (XY-overlap-scoped, not just any placement sharing its
     height) — if the package's own `max_stack_layers` is 0 ("no explicit
     per-package limit," the DB/UI default), the same system-wide
     `_SYSTEM_MAX_STACK_LAYERS` applies as a breadth fallback (how many
     separate packages can share this one base's top surface)
   - Must be heavier than candidate
4. The candidate itself must be stackable (stacking_mode ≠ NONE)
5. Footprint area: candidate ≤ every below package's footprint
6. Compute union coverage: grid-sample (20×20), require ≥ 50%
7. Centre-of-mass: XY centre inside at least one below AABB
```

Step 2 (depth) and step 3's `max_stack_layers` check (breadth) are genuinely different
constraints — a linear single-file column never has more than one package directly on
any given package, so the breadth check alone can't limit how many layers deep a tower
goes. Both the depth cap and the breadth check's XY-overlap scoping (it previously
matched *any* placement sharing a Z-height anywhere in the container, not just ones
actually on the specific base) were added/fixed together, since a real end-to-end test
was the first thing to exercise this path under the common case (no explicit
`max_stack_layers` set).

### Stacking Modes

| Mode | Meaning |
|------|---------|
| `NONE` | Nothing allowed above |
| `LIGHT_ONLY` | Only packages ≤ `max_top_weight_kg` |
| `NORMAL` | Stacking allowed subject to all rules |

`stackable=False` auto-derives `stacking_mode=NONE`.

---

## 6. Door Access Strategy

**Source**: `engine/access.py` → `check_door_access()`

```
Try:  rear_door  →  side_door(right)  →  side_door(left)
```

- **Rear door**: cross-section fits opening, sweep from position to rear clear
- **Side door**: cross-section fits opening, X-range overlaps door, sweep clear
- Default: full-width/full-height rear door when no features configured

The `door_used` value is stored in `Placement` and used by the 3D animation for entry point selection (§10).

#### Rear Door Check
```
1. Package cross-section (width × height) fits within rear door dimensions
2. Sweep volume: AABB from package position (x, y, z) to rear wall (container.length, y+w, z+h)
3. Sweep must not intersect any already-placed package (using their inflated AABBs)
```
The sweep represents the straight-line path a forklift would take from the rear door straight into the container.

#### Side Door Check
```
1. Package cross-section (length × height) fits within side door dimensions
2. Package X-range [x, x+l] overlaps door X-range [position_from_front, position_from_front + width]
3. Sweep volume: from position to side wall (y=0 or y=container.width)
4. Sweep must not intersect any placed package
```
The side door is positioned at `position_from_front_mm` from the front wall.

---

## 7. Clearance Strategy

10mm clearance bubble on every side of every package. Implementation per subsystem:

| Subsystem | AABB Used | Behaviour |
|-----------|-----------|-----------|
| Spatial index | Inflated (+clearance) | Extreme points offset by +2×clearance |
| Collision | Inflated | 20mm gap between packages |
| Boundary | Actual | Packages can touch walls |
| Support | Actual | Physical footprint |
| Door access | Inflated | Sweep with safety bubble |

---

## 8. Full Pipeline Summary

```
Packages (unsorted)
    ▼
Sort: non-stackable first, width DESC, length DESC, volume DESC, weight DESC
    ▼
Multi-vehicle: SmallestVehicleThatFitsStrategy (Section 2)
    ▼
For each selected vehicle:
    └─► For each remaining package:
            ├─► Generate candidates (origin + box corners + rotations)
            ├─► Score (6 terms: contact_area, x_position, weight_balance,
            │         usable_space, stack_level, tower_height — Section 4)
            ├─► Validate (boundary, weight, collision, support, door)
            └─► Place if valid, else unplaced → next vehicle
    ▼
Done — no post-processing passes
```

---

## 9. Configuration Points

| Parameter | Location | Default | Description |
|-----------|----------|---------|-------------|
| `SCORING_WEIGHTS` | `engine/scorer.py` | `{contact_area:1000, x_position:200, weight_balance:50, usable_space:3, stack_level:1, tower_height:1}` | 6-term scoring, see Section 4 |
| `_SYSTEM_MAX_STACK_LAYERS` | `engine/support.py` | 3 | Hard cap applied when a package's own `max_stack_layers` is 0 |
| `horizontal_clearance_mm` | `engine/package.py` | 10.0 | Safety gap (mm) |
| `vertical_clearance_mm` | `engine/package.py` | 0.0 | Vertical safety gap (mm) |
| `max_top_weight_kg` | `engine/package.py` | 0.0 | Max weight above (0=unlimited) |
| `max_stack_layers` | `engine/package.py` | 0 | Per-package stack-layer override (0 = no override, falls back to `_SYSTEM_MAX_STACK_LAYERS`) |
| `support_threshold` | `engine/support.py` | 0.50 | Min footprint fraction for support |
| `_GRID_SAMPLES` | `engine/support.py` | 20 | Grid resolution |
| `candidate_limit` | `engine/profile.py` (`PlannerProfile`) | `None` (balanced) / 15 (fast) | Max candidates — only matters when `profile=fast` is explicitly requested alongside `strategy=optimized`, since `balanced` (the default) never sets a limit to begin with |
| `tighten_step_mm` | `engine/profile.py` (`PlannerProfile`) | 200.0 | Defined but **dead** — `tighten_position()` (`candidate_points.py:70`) hardcodes its own step (`max(50.0, h_clr*2)`) and never reads this value |

---

## 10. Step Animation & 3D Controls

After auto-arrange completes, the frontend sorts placements by `load_sequence` and plays them one-by-one in the Three.js 3D view.

```
1. Sort placements by load_sequence ASC
2. For each step:
   a. Read door_used field from placement
   b. Choose start position based on door:
      - "rear":       (container.length + pkg_length, y, z)  — outside rear wall
      - "side_right": (x, y, container.width + pkg_width)     — outside right wall
      - "side_left":  (x, y, -pkg_width)                      — outside left wall
   c. Create a mesh at start position
   d. Tween to final position over 500ms with cubic ease-out (1 − (1−t)³)
   e. On completion, convert to permanent mesh
3. Auto-play advances every 700ms (500ms tween + 200ms pause)
```

**Source**: `static/js/truck-load-planner.js` `_stepNext()` reads `placement.door_used` and computes the correct entry point. The backend stores `door_used` in `Placement.door_used` (default `"rear"`).

The animation is driven by `requestAnimationFrame` inside the existing `_animate3D()` loop. Step meshes are tracked separately from the main scene to avoid conflicts with normal `update3DScene()` calls.

Package rotation (`rotation` field, 0/90/180/270°) swaps which axis length/width occupy
for 90°/270° — both the 2D views (`_drawPackages`) and the 3D mesh loop
(`update3DScene`) apply this swap consistently as of 2026-07-30 (previously 3D ignored
rotation, rendering rotated packages with the wrong box extents).

### 3D Toolbar Controls

| Control | ID | Behaviour |
|---------|----|-----------|
| ◀ Prev | `tlp-3d-btn-prev` | Go back one step, re-show previous packages |
| 0/15 | `tlp-3d-step-counter` | Current step / total |
| ▶ Next | `tlp-3d-btn-next` | Advance one step with fly-in animation |
| ▶▶ Play | `tlp-3d-btn-play` | Toggle auto-play; icon changes to ⏸ when playing |
| ⏭ End | `tlp-3d-btn-end` | Show all packages immediately |
| ⛶ / ❌ | `tlp-3d-btn-fullscreen` | Toggle fullscreen mode (CSS fixed overlay, not native API) |

**Visibility**: toolbar is `opacity: 0` by default, `opacity: 1` on hover or when `.fullscreen` class is active.

**Persistence**: after animation completes or user clicks "Show all", the buttons remain visible (step mode stays active). Only switching vehicles or closing the 3D view hides them.

**Keyboard**: `F` toggles fullscreen, `Escape` exits.

Each package in the 3D view also renders a text sprite showing its name above the top face (`_makeTextSprite()`).

---

## 11. Frontend: Arrange Results & Validation

After auto-arrange, the left sidebar shows an **Arrange Results** section. Each row represents a vehicle that received packages:

```
┌─ Arrange Results ────────────────────┐
│  51C-123.45          24 pkgs         │  ← clickable, switches viewer
│  51C-678.90          18 pkgs         │
└──────────────────────────────────────┘
```

Clicking a vehicle: `_selectVehicle(vehicle_id)` loads its container config, filters
`_arrangePlacements` to that vehicle's packages, re-renders the 2D/3D views, starts
step animation, and highlights the active row.

### Validation panel

The right sidebar's validation checklist (`updateValidationUI()`) recomputes boundary,
collision, weight, volume, and door checks client-side on every status refresh — these
are simple enough formulas to be exactly equivalent to the backend's, so no round-trip
is needed for them. There is **no client-side support/stacking check** at all (Section 5's
rules aren't client-reproducible), so after a manual drag/rotate,
`_validateAllPlacements()` calls the real backend endpoint (`POST
/api/tlp/session/validate`, single-placement) for the moved package against the rest of
the plan, and folds a rejection's reason into the panel/status-bar text. This is the
only point where backend-only rules (support, stacking, capacity) get enforced on a
manual edit — auto-arrange itself never needs this since every placement it makes
already passed full backend validation.

---

### Escaping — every operator-supplied string goes through `UI.escapeHtml()`

`static/js/truck-load-planner.js` builds most of its UI with `innerHTML` and template
literals. Package names, customer names, reference numbers, plate numbers, container
names, driver names and plan names are all operator-entered and all reach a sink, so
each is wrapped:

```js
`<div class="tlp-pkg-name">${UI.escapeHtml(pkg.name)} ${stackingLabel}</div>`
```

The `||` default goes **inside** the call, so a `null` never reaches `escapeHtml`.
Numeric and boolean interpolations (`${pkg.length}`, `${item.quantity}`, `${p.id}`) are
deliberately left bare — escaping them would be noise.

This file had **zero** escaping until 2026-08-06; the 2026-07-29 refactor that moved
every other page onto `UI.escapeHtml()` missed it. With no authentication on any
endpoint (deliberate — see `CLAUDE.md`), anything that could reach the network could
persist a payload via a package name and have it run in every dispatcher's browser.
`tests/js/tlp-escaping.test.js` guards against it being dropped again and is
deliberately dependency-free so it runs without `node_modules`.

---

## 12. 2D Canvas View Coordinates

The frontend renders three orthogonal views of the container using Konva.js. Each view maps two container axes onto the canvas:

| View | Canvas X | Canvas Y | Ruler X Label | Ruler Y Label |
|------|----------|----------|---------------|---------------|
| **Top** | Container length (front→rear) | Container width (left→right) | X | Y |
| **Side** | Container length (front→rear) | Container height (floor→ceiling) | X | Z |
| **Back** | Container width | Container height | W | Z |

### Back View (Rear Perspective)

The back view renders the cargo area as seen from the rear door looking toward the front. Since the viewer faces forward (same direction as the truck), **the left wall (Y=0) appears on the right side of the canvas** and the right wall (Y=width) appears on the left.

Coordinate flips are applied consistently across rendering (`_drawPackages`, `_focusOnPackage`), drag-and-drop, preview, validation, and placement (`_onDrop`). The generic `_mmToStage` / `_stageToMm` converters remain unflipped — all view-specific logic is handled at the call site.

---

## 13. Engine Architecture (`truck_load_planner/engine/`)

21 modules plus `__init__.py`.

| Module | Responsibility |
|--------|---------------|
| `planner.py` | Orchestrates all planning operations |
| `auto_arrange.py` | Strategy-based auto-arrange (`LargestFirstStrategy`, `OptimizedStrategy`) |
| `distribution.py` | Multi-vehicle fleet distribution |
| `vehicle_selection.py` | Pluggable vehicle-selection strategies (`SmallestVehicleThatFitsStrategy`, `LargestVehicleFirstStrategy`) |
| `candidate_points.py` | Candidate position generation (origin + package corners) + `tighten_position()` |
| `scorer.py` | 6-term placement quality scoring |
| `validation.py` | All rule checks: boundary, collision, weight, support, door access |
| `access.py` | Door access validation (rear + side sweep checks) |
| `support.py` | Stacking validation with combined-support model + hard column-depth cap |
| `state.py` | Planner state: spatial index, extreme points, placement mutations |
| `spatial.py` | Spatial hash grid for fast AABB queries |
| `geometry.py` | Re-exports the canonical `AABB` (clearance-aware `from_dimensions`, overlap/intersection) and coordinate transforms from `truck_load_planner/geometry/` |
| `collision.py` | AABB collision detection |
| `boundary.py` | Container boundary containment |
| `statistics.py` | Utilization, weight, and package counts |
| `weight.py` | Total weight vs payload calculation |
| `container.py` | Container dataclass (dimensions, features, payload) |
| `package.py` | Package dataclass (dimensions, stackable, rotation, clearance) + `EnginePackage.from_legacy()` factory (converts legacy dict/object shapes) |
| `placement.py` | Placement dataclass (position, rotation, sequence, door_used) |
| `profile.py` | Solver profile configuration (name, candidate_limit, tighten_step) |
| `trace_mutations.py` | Debug-only placement mutation tracer. Assigns every `Placement` a `_uid` and logs every change to x/y/z/rotation plus insertion and removal; provides `M.check_integrity()` and `M.dump_for()`. Written for support-integrity bugs — disable with `M.enabled = False` |

### Related packages outside `engine/`

| Package | Responsibility |
|---------|---------------|
| `geometry/` | `aabb.py` — the single canonical AABB class (`engine/geometry.py` re-exports it); `grid.py`, `transform.py` |
| `optimization/vehicle_cost.py` | Estimated transport cost per vehicle — fuel, empty-volume and empty-floor penalties, fixed cost. Deliberately outside `engine/` so business factors stay independent of packing geometry |
| `logistics/` | Legacy validation helpers. `adapters.py` delegates `check_boundary` / `calculate_total_weight` / `check_weight` to `engine/`; `volume.py` and `constraints.py::get_door_status` have no engine equivalent and remain the live implementation |

### Experimental: py3dbp Packing Engine

An experimental integration of the [py3dbp](https://pypi.org/project/py3dbp/) 3D
bin-packing library is available in `truck_load_planner/engines/py3dbp/` as an
alternative packing engine for benchmarking (`manual_test.py --engine py3dbp`), but is
**not wired into the live web app** — reachable only from CLI/manual-test scripts, never
from any Flask route. `truck_load_planner/engines/internal/engine.py` is a thin
adapter that just wraps `distribute_across_vehicles()`. Both implement the
`PackingEngine` interface (`truck_load_planner/engines/base.py`).

---

## 14. Database

### TLP Tables

| Table | Purpose | Key Columns |
|-------|---------|--------------|
| `tlp_packages` | Package definitions | `id`, `name`, `length`, `width`, `height`, `weight_kg`, `color`, `allow_rotation`, `allow_stacking`, `default_qty` |
| `tlp_shipments` | Customer orders | `id`, `customer_name`, `reference`, `notes` |
| `tlp_shipment_items` | Package-quantity links | `id`, `shipment_id` (FK), `package_id` (FK), `quantity` |
| `tlp_load_plans` | Saved plans | `id`, `name`, `vehicle_id` (FK), `shipment_id` (FK), `status`, `planner`, `notes` |
| `tlp_placements` | Individual placements | `id`, `load_plan_id` (FK), `package_id` (FK), `x`, `y`, `z`, `rotation`, `load_sequence` |
| `container_configs` | Container/trailer dimensions | `id`, `name`, `cargo_length_mm`, `cargo_width_mm`, `cargo_height_mm`, `payload_kg` |
| `container_features` | Doors, lift gates | `id`, `container_config_id` (FK), `feature_type`, `geometry_json` |

### Delete semantics — the cascade is manual

`truck_load_planner/routes.py` connects with `enable_fk=False` and the TLP schema uses
plain `REFERENCES` with no `ON DELETE CASCADE`. **Both are deliberate**, and the
consequence is that every delete route must clean up its own children:

| route | also deletes |
|---|---|
| `DELETE /packages/<id>` | `tlp_placements`, `tlp_shipment_items` for that package |
| `DELETE /packages/clear` | all `tlp_placements`, all `tlp_shipment_items` |
| `DELETE /shipments/<id>` | `tlp_shipment_items` for that shipment |
| `DELETE /container-configs/<id>` | `container_features` for that config |

`delete_package` did not do this until 2026-08-06 — it removed only the package row,
leaving placements pointing at an id that no longer existed. Those reload through the
`LEFT JOIN` in `list_plans` with a null name and zero dimensions, i.e. as invisible
boxes in a saved load plan. If you add a delete route here, add its cascade with it;
turning FK enforcement on instead would break the other three.

Note the children are deleted **before** the parent, so the `rowcount` deciding the 404
is still the parent row's own.

### Feature Geometry Schema

**Rear door** `geometry_json`:
```json
{ "width_mm": 1800, "height_mm": 1900 }
```

**Side door** `geometry_json`:
```json
{ "width_mm": 1200, "height_mm": 1800, "position_from_front_mm": 2400 }
```

---

## 15. API: Auto-Arrange Endpoint

```
POST /api/tlp/auto-arrange
```

**Body** (omit `vehicle_id` for multi-vehicle distribution):
```json
{
  "vehicle_id": 1,
  "strategy": "optimized",
  "profile": "balanced",
  "shipment_id": 1,
  "debug": false
}
```

**Cargo arrives one of two ways, and the frontend picks between them.**
`truck-load-planner.js:1403` sends `shipment_id` when a shipment is selected, and an
inline `packages` array otherwise. Both go through `_get_packages_from_request`:

| field | source | shape |
|---|---|---|
| `shipment_id` | `tlp_shipment_items` joined to `tlp_packages`, expanded by `quantity` | server-side |
| `packages` | array of `{package_id, name, length, width, height, weight_kg, color, allow_stacking}` | client-side, already expanded |

`shipment_id` wins if both are present. A shipment item whose package has been deleted
is **skipped with a warning**, not arranged — the `LEFT JOIN` is kept so the orphan
surfaces, but a package with a null name and 0 mm sides would otherwise be packed as an
invisible box.

> **Fixed 2026-08-06.** The `shipment_id` path returned an unhandled 500 for the whole
> life of the endpoint: the query aliased `p.name AS package_name` while
> `Package.from_row` reads `row["name"]`, so it raised `KeyError: 'name'`. Behind that,
> `si.*` exposed the *shipment item's* id as `row["id"]`, which would have given every
> placement the wrong `package_id` once the crash was fixed. Both were corrected
> together — see `docs/AUDIT_2026-08-06.md` §1. `tests/test_tlp_routes.py` pins the two
> payload shapes to produce identical placements, so they cannot drift apart again.

**Response** (single-vehicle shape; multi-vehicle adds `per_vehicle`):
```json
{
  "multi_vehicle": false,
  "success": true,
  "summary": {
    "placed_packages": 42,
    "failed_packages": 0,
    "utilization": 78.3,
    "total_score": 15234.5,
    "warnings": [],
    "unplaced_packages": []
  },
  "placements": [
    { "package_id": 5, "x": 0, "y": 0, "z": 0, "rotation": 0, "load_sequence": 1, "_name": "Widget A" }
  ],
  "statistics": { "volume_used_pct": 78.3 }
}
```

Single-placement validation (used by drag/drop and the manual-edit re-validation
described in Section 11) is a separate endpoint:

```
POST /api/tlp/session/validate
Body: { vehicle_id, package_id, x, y, z, rotation, existing_placements }
Response: { accepted: bool, placement?: {...}, errors?: [...] }
```
