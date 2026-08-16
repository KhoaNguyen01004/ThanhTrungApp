# Fleet Logistics Platform

Flask-based logistics system for a working trucking fleet — **36 vehicles**, deployed and
used daily by dispatchers. It covers the whole operating day:
live GPS tracking, fuel and oil monitoring, 3D truck-load planning, next-day delivery
planning, stop-by-stop dispatch execution with photo proof of delivery, and end-of-day
reporting.

It began as fuel-log tracking, which is where the old title came from. That is now one
module out of seven.

**At a glance**

| | |
|---|---|
| HTTP endpoints | **130** across 7 Flask blueprints |
| Pages | 11 routes over 9 templates |
| Fleet in `routing_system.db` | 32 box trucks (1.5–10 t) + 4 container vehicles |
| Tests | **737** pytest, plus **242** jsdom drives of the real frontend |
| Storage | SQLite, no ORM, raw SQL throughout |
| Frontend | Vanilla JS, no build step |
| Deployment | Render, `gunicorn wsgi:app`, 20 GB persistent disk |
| External services | TTAS (GPS), OpenRouteService (routing/ETA), Google Sheets (fuel log + delivery plan) |

> **No authentication.** Every endpoint, including the destructive ones, is open to anyone
> who can reach the host — a deliberate 2026-07-31 decision for an internal-network
> deployment, made after a shared dispatcher password cost real time at every shift change.
> See `docs/DELIVERY_MODULE.md` § Key Design Decisions before exposing this publicly.

---

## Modules

**GPS & trip tracking** — Live vehicle positions from TTAS, geofence entry/exit detection
by ray casting, road-aware route lines from OpenRouteService, and a background refresher
that keeps them warm. Manual location CRUD for the places TTAS does not know about.

**Fuel** — Refuel log with per-vehicle efficiency KPIs and charts, separate handling for
container vehicles (partial-tank refuels), CSV export, and an ingest that syncs a Google
Sheet fuel log into `fuel_log`.

**Oil maintenance** — Oil-change tracking against scraped TTAS kilometre logs, so the
interval is measured on real odometer movement rather than dates.

**Fleet & vehicle data** — Vehicle CRUD over the master `vehicles` table that every other
module keys off, the physical envelope (gross weight, height, width, length, axle load)
with per-type defaults, an interactive 3D container diagram, and the envelope-derived ORS
restriction options behind vehicle-constrained routing.

**Truck Load Planner** — 3D/2D cargo loader: multi-vehicle distribution and vehicle
selection, single-vehicle placement with scoring, stacking rules with a depth cap,
door-aware access validation, clearance handling, and step-by-step placement animation.
Two engines (internal, plus an experimental `py3dbp`).

**Delivery planning** — Build the next day's plan in a 5-step wizard, or import it. Two
import paths: an `.xlsx` upload, and a read-only pull straight from the manager's Google
Sheet (see below). Per-assignment driver naming overrides the vehicle's usual driver for
that plan only.

**Dispatch execution** — The board dispatchers watch all day: stop-level execution
tracking, road-aware ETA and distance, attention indicators (stuck / GPS-stale /
reported-stopped), a **No GPS** filter covering both unmatched plates and TTAS lost-signal
(`MTH`) vehicles, a pinned current-stop card with click-to-call, inline skip/cancel reason
editing, per-stop phase history with undo, single and batch photo upload with a read-only
gallery, follow-vehicle map mode, live stop reordering, click-a-stop-to-locate-it, a
straight-line distance ruler (right-click the map), Mapillary street-level imagery for a
selected stop, and a switchable basemap (satellite / streets / muted) with Esri imagery
capture dates.

**Reporting** — Per-day delivery summary, day-level image attachments, and a packaged
`day.zip` download.

## Pages

| Route | Page |
|---|---|
| `/` | Map — GPS trip tracking with geofencing |
| `/locations` | Manual location management |
| `/fuel-efficiency` | Fuel dashboard — KPIs, chart, refuel log |
| `/fuel-container` | Same page in container mode (partial-tank support) |
| `/oil-change` | Oil change tracking |
| `/vehicle-management` | Vehicle CRUD + interactive 3D container diagram (Three.js) |
| `/truck-load-planner` | 3D/2D cargo loader with auto-arrange, stacking, step animation |
| `/delivery/new` | Delivery plan builder — wizard, Excel import, Google Sheet import |
| `/delivery/edit/<plan_id>` | Reopens a saved plan in the builder; confirmed plans stay editable |
| `/delivery/dashboard` | Dispatch board |
| `/delivery/export` | End-of-day export |

Endpoints by blueprint: `delivery` 44 · `tlp` 28 · `fuel` 18 · `core` 15 · `fleet` 12 ·
`oil` 9 · `trips` 4. `core` gained `/api/streetview` on 2026-08-16.

## Google Sheet plan import

The next day's dispatch plan is filled in by hand in the operator's manager's Google Sheet
(one tab per month). `/delivery/new` reads it directly: pick a date, review what would be
written, commit.

**It is read-only by construction** — the only thing touched is Google's `gviz/tq` query
endpoint, which has no write path, on a link-shared document this system does not own. No
credential is involved, which is why it does not reuse the fuel log's service account.

That sheet is hand-typed prose, and the parser is defensive because it has to be: the date
column is text with no year (`21-Jul`, `2-Aug`, `01-th8`), continuation rows leave it
blank, and the coordinate columns hold three incompatible formats — including
`9.585.868` / `1.059.744`, where a thousands separator has replaced the decimal point.
Coordinates are recovered by digit placement inside a Vietnam bounding box, and a cell that
cannot be placed is **never guessed at**: the stop imports without coordinates and says so.
Read `services/delivery/sheet_import_service.py`'s module docstring before changing any of
it, and `docs/CHANGELOG.md` (2026-08-09) for the reasoning.

---

## How to Run

```bash
python app.py            # dev server
gunicorn wsgi:app        # production (see render.yaml)
```

Two virtualenvs exist in the repo (`venv/`, `.venv/`) — check which one actually has
packages installed before running `pip` or `python`.

`.env` and `credentials.json` hold real TTAS and Google credentials and are gitignored.

---

## Running Tests

### Delivery Management Tests (502 tests)
```bash
python -m pytest tests/test_delivery.py -v              # 230 — service layer
python -m pytest tests/test_delivery_routes.py -v       # 157 — route layer, real HTTP with TTAS mocked
python -m pytest tests/test_sheet_import.py -v          # 89  — Google Sheet parser (fixtures, no network)
python -m pytest tests/test_sheet_import_routes.py -v   # 26  — Google Sheet import endpoints
```

`test_delivery.py` imports the service modules directly; `test_delivery_routes.py` drives
`app.test_client()` end to end, which is the only suite that sees bugs living inside a
request handler or in an assembled response. Run both for any delivery change.

The two `test_sheet_import*` suites cover the read-only Google Sheet plan import added
2026-08-09. Neither touches the network: the fetch is patched with
`tests/fixtures/huwei_plan_th08.json`, a `gviz` payload built from real sheet rows,
defects included. See `docs/CHANGELOG.md` for what those defects are — the coordinate
formatting in particular is not something to guess at.

`pytest tests/` runs everything — **737 tests**, measured 2026-08-16.

> **`test_delivery_routes.py` needs `playwright` importable** even though it never drives a
> browser: it imports the app through `main.py`, which imports `playwright` at module
> level. Without it all 157 tests error out with `ModuleNotFoundError: No module named
> 'playwright'` rather than failing on anything real. It **is** pinned in
> `requirements.txt` (`playwright==1.61.0`), so this means your environment is behind —
> `pip install -r requirements.txt` fixes it. The browser binaries
> (`playwright install`) are not needed. Note `requirements.txt` is UTF-16, so
> `grep playwright requirements.txt` finds nothing and will tell you the opposite.

### Route-layer Tests (113 tests)

```bash
python -m pytest tests/test_write_handler_connections.py -v  # 36 — write handlers, all four route modules
python -m pytest tests/test_streetview_routes.py -v          # 30 — /api/streetview (Mapillary proxy)
python -m pytest tests/test_trips_geofence.py -v             # 14 — route refresher + lazy /api/route-data
python -m pytest tests/test_fleet_routes.py -v               # 11 — fleet CRUD
python -m pytest tests/test_tlp_routes.py -v                 # 8  — truck load planner
python -m pytest tests/test_wsgi_routes.py -v                # 8  — what gunicorn serves == what app.py serves
python -m pytest tests/test_fuel_routes.py -v                # 6  — fuel log
```

Added 2026-08-06 (see `docs/AUDIT_2026-08-06.md`), except `test_fleet_routes.py`,
`test_wsgi_routes.py` and `test_streetview_routes.py` (2026-08-16). Before them the truck load planner, `app/routes/trips.py` and
`app/routes/fuel.py` had **no** coverage that issued a request — and the audit's two
Critical findings both lived inside a request handler, where a service-level suite is
structurally blind. `test_tlp_routes.py` and `test_trips_geofence.py` each fail against
the pre-fix code, which is the property that makes them worth keeping.

`test_write_handler_connections.py` is parametrised over all 18 reachable write endpoints:
it swaps `sqlite3.connect` for a wrapper whose `cursor()` raises, forcing an exception at
exactly the point each handler's `finally` exists to cover.

`test_wsgi_routes.py` (2026-08-07) asserts that `gunicorn wsgi:app` and `python app.py`
serve the same routes. Every other suite builds its client from `create_app()`, so all 548
tests at the time were blind to a route registered *outside* the factory — which is how
production ran for a while with no `/`.

### Frontend Tests (242 drives, non-pytest)

```bash
npm install jsdom                    # once, at the repo root; dev-only, not vendored
node tests/js/dashboard.test.js      # 131 — dispatch dashboard      (needs jsdom)
node tests/js/measure.test.js        # 35  — map distance ruler      (needs jsdom)
node tests/js/streetview.test.js     # 33  — Mapillary street view panel (needs jsdom)
node tests/js/sheet-import.test.js   # 16  — Google Sheet import button (needs jsdom)
node tests/js/export.test.js         # 12  — end-of-day export page  (needs jsdom)
node tests/js/plan-builder.test.js   # 10  — delivery plan builder   (needs jsdom)
node tests/js/tlp-escaping.test.js   # 5   — truck load planner escaping (no deps)
# jsdom installed elsewhere? NODE_PATH=/path/to/node_modules node tests/js/dashboard.test.js
```

All seven were run individually on 2026-08-16; every suite passed in full except the one
time-of-day case noted at the end of this section. Each jsdom boot takes tens of seconds
on a slow filesystem, so run them one file at a time rather than in a single loop with a
short timeout.

`node_modules/` is gitignored. Node resolves it by walking up from the test file, so a
single `npm install jsdom` at the repo root is enough — no `NODE_PATH` needed.

`tlp-escaping.test.js` is deliberately dependency-free so it runs in a checkout with no
`node_modules` at all. It guards `truck-load-planner.js` against losing its HTML escaping
again (it had none until 2026-08-06), and that is the kind of regression that recurs years
later — a test that needs setup is a test that stops being run.

Frontend changes get no pytest coverage at all, so these are the only real verification
those pages get. All six jsdom suites drive the actual `static/js/` modules against the actual template
(loaded from disk with its `<script>` tags stripped), with only the parts that reach
outside the page stubbed — the API and the Leaflet map for the dashboard, `fetch` for the
builder. An element id renamed in a template but not in the JS fails here.

`plan-builder.test.js` additionally records every stubbed request, so a test can assert on
the exact payload the server would have received. That is how it catches the class of bug
where a field is captured and rendered correctly and then simply left out of the POST.
`export.test.js` (2026-08-10) uses the same recording harness on the end-of-day page, and
carries one trap worth reading before you copy it: **do not dispatch `DOMContentLoaded`
by hand.** `new JSDOM(html)` leaves `readyState` at `loading` and fires its own a tick
later, so a manual dispatch boots the page twice — two listeners, two `loadSummary()`
calls, every upload counted double — which reads as a duplicate-request bug in the page
and is not one. `await` a turn of the event loop instead.

`sheet-import.test.js` does the same for the Google Sheet import button, and needs one
extra trick worth knowing before you write another suite that asserts on a redirect:
**jsdom 30 seals `Location` completely** — `window.location` is non-configurable and each
of its properties is non-writable *and* non-configurable, so it cannot be replaced by
assignment, `defineProperty`, or overriding `assign`. That suite therefore loads the
builder inside a function whose `window` parameter shadows the global one, via a `Proxy`
that forwards everything to the real window except `location`. Bare `document` references
still resolve to the real document, so only the navigation is intercepted. Do not reshape
production code to make a redirect observable.

Run the matching suite for any change under `static/js/`, alongside `node --check` on the
touched files.

**One dashboard ETA case is time-of-day dependent** — `a route running past midnight is
marked, not shown as already late` feeds `UI.etaClock()` a 36-hour ETA and asserts the
result ends in `+1d`. `etaClock` counts *calendar days* crossed, so from 12:00 onwards
36 hours lands two dates away and it renders `+2d` instead. The suite reports
**131/131 before noon and 130/131 after**. Known, unrelated to whatever you are changing;
the fix is an injectable clock.

> **`TZ=UTC` is not a fix, and this README used to say it was.** The threshold is noon *in
> whatever zone the test runs in*, so `TZ=UTC` only helps while UTC itself is before noon.
> Verified 2026-08-16 at 22:30 +07 — that is 15:30 UTC, and
> `TZ=UTC node tests/js/dashboard.test.js` still reported 130/131 with exactly this test
> failing. From UTC+7 the useful window is roughly 07:00–19:00 local; outside it, pick a
> zone where the local hour is under 12 (`TZ=Pacific/Auckland`, `TZ=Asia/Tokyo`, … depending
> on when you are reading this) or just expect the one failure.

### Truck Load Planner Tests (39 tests)

```bash
python -m pytest tests/test_scorer.py tests/test_auto_arrange_e2e.py tests/test_tlp_routes.py -v
```

`test_scorer.py` (26) covers scoring/candidate-generation units; `test_auto_arrange_e2e.py`
(5) runs realistic-sized shipments through the real production entry points and asserts
on utilization, stacking behavior, the stack-depth cap, and multi-vehicle truck-count
minimization — see `docs/TRUCK_LOAD_PLANNER.md` for the algorithm these exercise.
`test_tlp_routes.py` (8) is the only one of the three that issues an HTTP request, and so
the only one that could have caught the `shipment_id` 500 fixed on 2026-08-06.

Note `tests/test_all.py` is a **script**, not a pytest module — it defines zero `def test_`
and is collected by `pytest tests/` without contributing any tests. Its subcommands are
below.

### TLP Benchmarks, Diagnostics & Manual Debugging (non-pytest)

```bash
# ── Benchmarks ─────────────────────────────────────────────
python tests/test_all.py benchmark --mode distribution   # Single distribution run (46 pkgs, 32 vehicles)
python tests/test_all.py benchmark --mode floor_contact  # Compare floor_contact weight 25 vs 5 (60 trials)
python tests/test_all.py benchmark --mode real_data      # End-to-end with real DB data

# ── Diagnostics ────────────────────────────────────────────
python tests/test_all.py diagnose --scenario general     # KBF 280R + 3x LC 900 placement debug
python tests/test_all.py diagnose --scenario kbf_lc900   # Same scenario, focused output
python tests/test_all.py diagnose --scenario candidates  # Candidate generation & scoring breakdown
python tests/test_all.py diagnose --scenario stacking    # Floor vs stack decision analysis (15 pkgs)
python tests/test_all.py diagnose --scenario stacking --full  # Detailed breakdown

# ── Debug ──────────────────────────────────────────────────
python tests/test_all.py debug --mode py3dbp      # Run py3dbp engine on first vehicle
python tests/test_all.py debug --mode stats       # Statistics from py3dbp engine
python tests/test_all.py debug --mode validation  # Validate first package through pipeline
python tests/test_all.py debug --mode vehicles    # List all vehicles with dimensions

# ── Database Queries ───────────────────────────────────────
python tests/test_all.py query --mode vehicles   # Vehicles sorted by capacity
python tests/test_all.py query --mode tables     # Row counts per table
python tests/test_all.py query --mode db         # Full database overview
python tests/test_all.py query --mode shipments  # Shipments with package details

# ── Instrumentation ────────────────────────────────────────
python tests/test_all.py instrument --mode trace      # Read instrument_trace.jsonl
python tests/test_all.py instrument --mode bug-trace  # Support integrity trace (10 pkgs)

# ── Standalone Debugger ────────────────────────────────────
python tests/debug_arrange.py kbf_lc900          # Auto-arrange debug per scenario
python tests/debug_arrange.py real --full        # Full 46-pkg real shipment debug

# ── Manual Test (full pipeline) ────────────────────────────
python manual_test.py                            # Internal engine (default)
python manual_test.py --engine py3dbp            # py3dbp engine (experimental, not wired into the web app)
python manual_test.py --compare                  # Side-by-side comparison
```

Note: `test_all.py` matches pytest's `test_*.py` discovery but contains no `test_*`
functions (everything is `cmd_*`/argparse-CLI-only) — running it via the commands above
is the only way any of this logic executes; `pytest` collects the file but asserts
nothing from it.

---

## Reference Documents

| Document | What it covers |
|---|---|
| `CLAUDE.md` | Architecture, conventions and hard-won gotchas — the densest overview of the codebase |
| `docs/CHANGELOG.md` | Dated entries on what changed and why. Newest first |
| `docs/CODEBASE_ANALYSIS_REPORT.md` | Whole-codebase audit, roadmap, Priority Action Items (§9) |
| `docs/DELIVERY_MODULE.md` | Delivery module design, entities, API |
| `docs/TRUCK_LOAD_PLANNER.md` | TLP algorithm, scoring, API, frontend reference |
| `docs/AUDIT_2026-08-06.md` | Whole-workspace audit; §6 lists what was checked and found clean |
| `docs/BUGFIX_PLAN_2026-08-06.md` | The phased plan those fixes were made under |
| `docs/CONCURRENCY_PLAN_2026-08-06.md` | WAL and `--workers`, measured. **Recommendation only — nothing changed** |
| `docs/DELIVERY_AUDIT_2026-07-31.md` | Delivery-specific audit that drove Phases 1–5 |
| `docs/DISPATCH_UX_PLAN.md` | Dispatch board UX research; Phase 0 shipped, 1–2 proposed |
| `docs/VEHICLE_ROUTING_PLAN.md` | Vehicle-constrained routing; Phases A–C shipped |

The `*_PLAN` and `*_AUDIT` documents are historical records as much as references — status
headers are current, bodies preserve what was proposed versus what shipped.

---

## Project Structure

```
app.py                          # Entry point: create_app() + dev server; registers no routes itself
wsgi.py                         # Gunicorn entry point (`gunicorn wsgi:app`) — see note below
main.py                         # Standalone TTAS GPS tracking tool
manual_test.py                  # Manual pipeline test with instrumentation
routing_system.db               # The live SQLite database
database.sql                    # Full `sqlite3 .dump` backup of the above, committed to git.
                                 #   UTF-16LE — grep/head fail on it silently. NOT the schema
                                 #   of record; that's app/database/schema.py +
                                 #   services/delivery/database.py
graphify-out/                   # Knowledge graph (graph.json, GRAPH_REPORT.md, graph.html).
                                 #   Rebuild with `graphify update .` — see CLAUDE.md § graphify
app/                            # Flask application package (see app/__init__.py's create_app())
  __init__.py                   # App factory: config, init_db(), blueprint registration
  config.py                     # Env vars, constants
  state.py                      # Shared mutable runtime state (route cache, locks, TTAS session)
  db.py                         # DatabaseManager — context-managed SQLite, PRAGMA foreign_keys=ON
  database/
    schema.py                   # CREATE TABLE statements
    migrations.py               # Column migrations, data backfill
  utils/
    geo.py                      # Distance/polygon/centroid helpers
    export.py                   # Shared CSV-response helper
  services/
    ttas_client.py               # TTAS session, live vehicle fetch, report scraping,
                                 #   speed-phrase parsing and MTH lost-signal detection
    routing.py                   # OpenRouteService routing helpers
    locations.py                 # Manual-location file I/O
    vehicle_specs.py             # Vehicle envelope (weight/height/width/length/axle-load):
                                 #   validation, per-type defaults, ORS restriction options
  routes/                       # Flask Blueprints
    core.py                      # Pages (/, /locations, /delivery/*), /api/vehicles,
                                 #   /api/geocode, /api/streetview, manual-location CRUD —
                                 #   moved out of app.py 2026-08-07, because Gunicorn never
                                 #   executed app.py
    fleet.py                     # Vehicle CRUD
    fuel.py                      # Fuel log CRUD, profiles, CSV export, Google Sheet sync
    oil.py                       # Oil maintenance CRUD, TTAS KM-log scraping
    trips.py                     # Main-map route lines + advance/cancel, background route-refresh,
                                 #   and a single-flight lazy rebuild on GET /api/route-data —
                                 #   under Gunicorn the background thread never runs, so without
                                 #   it the cache was empty on every cold start
                                 # (Trip Management / Trip History pages removed 2026-07-31 —
                                 #  superseded by the Dispatch dashboard)
services/                       # Application services (not to be confused with app/services/)
  plate_utils.py                # normalize_plate() — the one canonical plate normalizer
  vehicle_identity.py           # Canonical-plate index; resolves a plate/serial to one vehicle
  google_sheet_service.py       # Google Sheets fuel-log ingest (service account, parsing + sync)
  delivery/                     # Delivery plan management
    database.py                 # Schema DDL, table initialization
    plan_service.py             # Plans, assignments, stops CRUD + Excel import pipeline
    sheet_import_service.py     # Read-only Google Sheet plan extraction (gviz, no credential):
                                 #   coordinate repair, year-less date parsing, layout guard
    execution_service.py        # Current stop derivation, advance, skip, cancel, revert, reorder
    tracking_service.py         # TTAS GPS wrapper, vehicle lookup
    eta_service.py              # ORS-based ETA calculation (Haversine fallback)
    image_service.py            # Stop image upload, serve, delete
    export_service.py           # End-of-day summary, day-level images, day.zip packaging
    routes.py                   # Flask Blueprint (44 endpoints under /api, none authenticated)
truck_load_planner/             # 3D bin-packing package
  routes.py                     # Flask routes / API endpoints (28, under /api/tlp)
  session.py                    # Load planning session
  db.py                         # Database initialization
  engine/                       # Packing algorithms (21 modules — see docs/TRUCK_LOAD_PLANNER.md §13)
  engines/                      # Packing engine abstraction (internal + py3dbp)
  geometry/                     # Canonical AABB, grid, coordinate transforms
  optimization/                 # vehicle_cost.py — cost model, kept out of the geometry engine
  models/                       # Data models
  logistics/                    # Legacy validation helpers — adapters.py delegates check_boundary/
                                 # calculate_total_weight/check_weight to engine/; volume.py and
                                 # constraints.py::get_door_status have no engine equivalent and
                                 # remain self-contained
static/                         # Frontend assets (JS, CSS)
  js/utils.js                   # ApiClient (fetch wrapper) + UI (toast, escapeHtml, etaClock)
                                 #   namespace, shared by all pages
  js/delivery-plan-builder.js   # Plan wizard, Excel import, Google Sheet import panel
  js/delivery-export.js         # End-of-day export page
  js/truck-load-planner.js      # 3D/2D loader UI
  js/dashboard/                 # Dispatch dashboard, split by panel — the only multi-file page
    main.js                     # Orchestrator: state, filters, selection, detail loading, plans
    api.js                      # Every dashboard fetch, with a 20s client timeout
    polling.js                  # 12s poll cycle, refresh coalescing, pause while the tab is hidden
    vehicle-list.js             # Left panel
    map.js                      # Leaflet: basemap switcher, markers, route line, Esri identify
    measure.js                  # Straight-line ruler; own layer group, untouched by the poll
    timeline.js                 # Right panel: stop list, actions, reordering, locate-on-map
templates/                      # HTML templates (9 files, 11 routes)
tests/                          # All test, debug, and diagnostic files
  conftest.py                   # Points DB_PATH at a throwaway file before any test module
                                 #   imports app/ — without it the suite migrates the real DB
  fixtures/                     # Recorded upstream payloads (huwei_plan_th08.json — real
                                 #   Google Sheet rows, defects included)
  test_all.py                   # Unified debug/benchmark harness (5 subcommands, 17 modes;
                                 #   no pytest tests)
  test_delivery.py              # Delivery services (230)
  test_delivery_routes.py       # Delivery HTTP API (157)
  test_sheet_import.py          # Google Sheet parser (89)
  test_vehicle_specs.py         # Envelope validation/defaults (40)
  test_write_handler_connections.py  # Write-handler connection cleanup, all route modules (36)
  test_vehicle_core_data.py     # Guards on the master vehicles table (36)
  test_streetview_routes.py     # /api/streetview Mapillary proxy (30)
  test_sheet_import_routes.py   # Google Sheet import endpoints (26)
  test_scorer.py                # TLP scoring units (26)
  test_routing.py               # ORS options, restrictions (15)
  test_trips_geofence.py        # Route refresher + lazy /api/route-data (14)
  test_fleet_routes.py          # Fleet HTTP API (11)
  test_tlp_routes.py            # TLP HTTP API (8)
  test_wsgi_routes.py           # gunicorn-vs-dev route parity (8)
  test_fuel_routes.py           # Fuel log HTTP API (6)
  test_auto_arrange_e2e.py      # TLP end-to-end (5)
  js/                           # jsdom drives of the real frontend modules, run with plain node
    dashboard.test.js           # Dispatch dashboard (131)
    measure.test.js             # Map distance ruler (35)
    streetview.test.js          # Mapillary street view panel (33)
    sheet-import.test.js        # Google Sheet import button (16)
    export.test.js              # End-of-day export page (12)
    plan-builder.test.js        # Delivery plan builder (10)
    tlp-escaping.test.js        # TLP HTML escaping, dependency-free (5)
  debug_arrange.py              # Per-package auto-arrange debugger
  merge_duplicate_vehicles.py   # One-time DB dedup utility
scripts/
  migrate_to_delivery.py        # Idempotent migration from legacy vehicle_trips
  fill_vehicle_gvw_2026-07-31.sql  # One-off backfill of gross vehicle weights
reports/                        # Test and debug output files
docs/                           # Reference documents — see the table above
```

**Why both `app.py` and `wsgi.py`?** `app.py` (file) and `app/` (package) share the name
`app`, and Python's import system always resolves `import app` to the package over the
file. Gunicorn's `app:app` target therefore can't reach `app.py`'s Flask instance —
`wsgi.py` gives it an unambiguous one (`gunicorn wsgi:app`, see `render.yaml`). `python
app.py` for local dev is unaffected, since running a script directly doesn't register it
under the package's name. **Every route must be registered inside `create_app()`**;
`tests/test_wsgi_routes.py` fails if anything is attached outside the factory.

## Tech Stack

- **Backend**: Python, Flask 3.1, SQLite3
- **Frontend**: Vanilla JS (`ApiClient`/`UI` shared namespace in `static/js/utils.js`),
  Chart.js 4.4.7, Konva.js 9 (canvas), Three.js (3D), Leaflet 1.9.4 (maps)
- **No ORM** — raw SQL for full control, via `DatabaseManager` (`app/db.py`)
  context-managed connections. Two access patterns coexist deliberately; see
  `CLAUDE.md` § Architecture before "fixing" one
- **No build step** — every script is loaded directly by a `<script>` tag
- **No CI** — running the suites yourself is the only verification there is. Every count
  in this file was measured on 2026-08-16; re-measure rather than trusting them

### Third-party hosts the browser must reach

Beyond the app itself, the dispatch dashboard loads from these at runtime. If a driver
tablet or office network filters them, the map degrades rather than failing loudly, so
they are worth allow-listing explicitly:

| Host | Used for |
|------|----------|
| `unpkg.com` | Leaflet JS/CSS |
| `server.arcgisonline.com` | Esri World Imagery tiles **and** the imagery capture-date `identify` query |
| `basemaps.cartocdn.com` | CARTO Positron / Voyager tiles and the satellite label overlay |
| `cdnjs.cloudflare.com` | Chart.js, Konva, Three.js on the other pages |
| `docs.google.com` | Not browser-side — the server reads the delivery plan sheet from here |

Server-side the app also calls OpenRouteService (routing/ETA), TTAS (GPS), and Google
Sheets (fuel log via service account, delivery plan via public `gviz` read).
