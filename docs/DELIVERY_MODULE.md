# Delivery Module — Documentation

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                   Flask Application                      │
│  ┌───────────────────────────────────────────────────┐  │
│  │        app/__init__.py :: create_app()              │  │
│  │  Registers 7 blueprints: core, fleet, fuel, oil,    │  │
│  │  trips, tlp, delivery                               │  │
│  │  core owns the /delivery/* page shells               │  │
│  └──────────┬────────────────────────────────────────┘  │
│             │                                            │
│  ┌──────────▼────────────────────────────────────────┐  │
│  │           delivery Blueprint (routes.py)           │  │
│  │  Prefix: /api                                      │  │
│  │  Endpoints: /plans, /assignments, /stops, /exec,   │  │
│  │             /eta, /drivers, /images                │  │
│  └──────────┬────────────────────────────────────────┘  │
│             │                                            │
│  ┌──────────▼────────────────────────────────────────┐  │
│  │              Service Layer                          │  │
│  │  ┌────────────┐ ┌──────────────┐ ┌─────────────┐  │  │
│  │  │plan_service│ │execution_svc │ │  eta_svc    │  │  │
│  │  │  CRUD ops  │ │adv/skip/cancel│ │  ORS calc   │  │  │
│  │  └────────────┘ └──────────────┘ └─────────────┘  │  │
│  │  ┌────────────┐ ┌──────────────┐ ┌─────────────┐  │  │
│  │  │image_svc   │ │tracking_svc  │ │ database.py │  │  │
│  │  │file upload │ │ GPS normalize│ │  table init │  │  │
│  │  └────────────┘ └──────────────┘ └─────────────┘  │  │
│  └────────────────────────────────────────────────────┘  │
│             │                                            │
│  ┌──────────▼────────────────────────────────────────┐  │
│  │              SQLite Database                       │  │
│  │  routing_system.db (delivery_* tables + legacy)    │  │
│  └────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
         ▲                          ▲
         │ HTML templates           │ Static assets
         ▼                          ▼
┌────────────────────┐  ┌───────────────────────────┐
│   Jinja2 Templates │  │  JS / CSS / Images        │
│  delivery-*.html    │  │  dashboard/* (modular)    │
│                     │  │  delivery-plan-builder.js │
└────────────────────┘  └───────────────────────────┘
```

> `manage-trips.html` and its route were removed on 2026-07-31 — the Dispatch dashboard
> superseded them.

---

## Frontend Structure

```
templates/
├── delivery-plan-builder.html     Plan creation / editing wizard
├── delivery-dashboard.html        Operational dispatch dashboard
└── delivery-export.html           End-of-day export page

static/css/
├── delivery-plan-builder.css      Wizard styles, modals, responsive
├── delivery-dashboard.css         3-panel layout, vehicle cards, timeline
└── delivery-export.css            Export page layout

static/js/
├── delivery-plan-builder.js       Single-file wizard (state machine, 5 steps)
├── delivery-export.js             Export page — sequential uploads, day.zip download
└── dashboard/
    ├── main.js                    Orchestrator, state, filters, detail loading, plan mgmt
    ├── api.js                     All API calls (20s client-side timeout)
    ├── polling.js                 12-second poll cycle, refresh coalescing, tab-visibility
    ├── vehicle-list.js            Left panel rendering
    ├── map.js                     Leaflet: basemap switcher, markers, route, imagery identify
    ├── measure.js                 Straight-line ruler, own layer group (added 2026-08-13)
    └── timeline.js                Right panel, stop list, actions, reorder, locate-on-map
```

`main.js` loads last and owns `DASH.state`. Modules talk to each other only through the
`DASH.state` / `DASH.map` / `DASH.timeline` surfaces, never by reaching into internals.

### Plan Builder Flow

| Step | Panel | Key Actions |
|------|-------|-------------|
| 1 | Plan Info | Enter name, date, description |
| 2 | Vehicles | Add/edit/duplicate/remove assignments |
| 3 | Stops | Add/edit/delete/reorder (drag) stops per assignment |
| 4 | Review | Validate, save draft, or confirm |
| 5 | Success | View plan ID, open/edit, create another |

All steps share a single state object. Auto-save runs every 30s while the plan is dirty,
not saving, and already has a `planId`.

Reopening a plan at `/delivery/edit/<plan_id>` runs the same wizard. Since 2026-08-06 a
**confirmed** plan reopens editable rather than read-only — see Key Design Decisions #1.

### Dashboard Panels

| Panel | Content | Update |
|-------|---------|--------|
| Left (280px) | Vehicle cards with progress, status, GPS time, attention indicator (stuck / GPS-stale / GPS-age-unknown / no-GPS / reported-stopped), and quick filters including **No GPS** — which covers both an unmatched plate and a TTAS lost-signal (`MTH`) vehicle | Every 12s poll |
| Center (flex) | Leaflet map: vehicle markers, stop pins, road-following route, basemap switcher, imagery capture-date popup | On selection + every poll |
| Right (300px) | Pinned current-stop card (contact, `tel:` link, primary actions incl. Revert) + stop timeline with photo gallery, single-shot **and** batch photo upload, per-stop phase history, inline skip/cancel reason editing, and per-stop reorder controls | Progressively on selection, then every poll |

All three panels use incremental DOM diffing (not full rebuilds) — see `CHANGELOG.md`'s Phase 1 entry for why.

#### Selecting a vehicle

Selection fires three requests at once and paints each as it lands, rather than awaiting
all three. `/api/stops` and `/api/execution/progress` are local SQLite reads; `/api/eta`
issues one OpenRouteService call per remaining stop, serially, each with a 30-second
server-side timeout. A `Promise.all` here made the whole panel as slow as routing.

Selection also clears the previous vehicle's timeline, stop pins, route line and info bar
immediately and shows "Loading stops…" — otherwise the panel silently keeps displaying
the *previous* truck's stops until new data arrives.

#### Map behaviour

| Concern | Behaviour |
|---------|-----------|
| Basemaps | Satellite (Esri World Imagery + CARTO label overlay), Streets (CARTO Voyager), Muted (CARTO Positron). Choice persists in `localStorage` under `dashboard_basemap`. |
| Imagery date | Clicking the map while Satellite is active queries Esri's `World_Imagery/MapServer/identify` and shows capture date, source, sensor, resolution and accuracy. |
| Automatic panning | Only Follow mode. Leaflet's popup autoPan is suppressed for background updates (`withoutAutoPan()` in `map.js`), or a moving truck's popup drags the view back every poll. |
| Locating a stop | Clicking a timeline row or the current-stop card centres the map on it, raising zoom to 15 only if further out, and turns Follow off. |
| Reordering | Up/down controls per stop, optimistic, POSTed in click order. Terminal stops can't move and nothing moves across one. |

---

## Database Schema

### `delivery_plans`

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| plan_name | TEXT | Required |
| plan_date | TEXT | ISO date |
| description | TEXT | Optional |
| status | TEXT | `draft` → `confirmed` → `executing` → `completed`/`cancelled` |
| created_by | TEXT | Dispatcher name |
| created_at | TIMESTAMP | Auto |
| updated_at | TIMESTAMP | Auto |
| imported_at | TIMESTAMP | Set on Excel import |

### `vehicle_assignments`

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| plan_id | INTEGER FK → delivery_plans | Cascade delete |
| vehicle_id | INTEGER → vehicles | From master vehicle table |
| driver_id | INTEGER → drivers | FK to drivers. **Usually NULL** — see below |
| driver_name_override | TEXT | Free-text driver for this plan only |
| sequence | INTEGER | Order within plan |
| notes | TEXT | Optional |
| created_at | TIMESTAMP | Auto |

**Which driver is shown.** Precedence is `driver_name_override` →
`drivers.name` via `driver_id` → `vehicles.current_driver`, expressed once as
`plan_service.DRIVER_NAME_SQL` for the plan-facing queries and inline in
`execution_service.get_dashboard_data` / `export_service.day_summary`, whose
fallback chains differ slightly.

Most drivers have no `drivers` row at all — `plan_service.list_drivers`
synthesises the rest from `DISTINCT vehicles.current_driver` with `id: None`,
so the plan builder's autocomplete offers names that cannot be stored as an id
and `driver_id` is NULL in the ordinary case. Before 2026-08-02 that meant a
driver typed during plan creation was discarded and dispatch showed the
vehicle's usual driver instead.

The typed name deliberately outranks a linked `drivers` row: both being set
means the dispatcher edited a prefilled value, and the edit is the newer
intent. It also deliberately **does not create a `drivers` record** — these
are stand-ins for one day, and the plan stays a snapshot, so reassigning a
truck next week does not rewrite who drove it today.

> The column list above ended with a stray `| updated_at | TIMESTAMP | Auto |` row,
> orphaned outside the table by an earlier edit. Removed 2026-08-06 — **there is no
> `updated_at` column on `vehicle_assignments`**, in `database.py`'s `CREATE TABLE`
> or in the live database. It was documentation of a column that never existed.

### `delivery_plan_stops`

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| vehicle_assignment_id | INTEGER FK → vehicle_assignments | Cascade delete |
| planned_sequence | INTEGER | Original planned order |
| station_code | TEXT | Client-defined code |
| station_name | TEXT | Required |
| address | TEXT | |
| lat | REAL | Latitude |
| lng | REAL | Longitude |
| manager_name | TEXT | |
| manager_phone | TEXT | |
| product_description | TEXT | |
| note | TEXT | |
| created_at | TIMESTAMP | Auto |
| updated_at | TIMESTAMP | Auto |

### `stop_executions`

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| stop_id | INTEGER FK → delivery_plan_stops | Unique, cascade delete |
| execution_sequence | INTEGER | 1-based during execution |
| status | TEXT | `planned` → `enroute` → `arrived` → `completed` (or `skipped`/`cancelled`) |
| skip_reason | TEXT | |
| cancel_reason | TEXT | |
| actual_arrival_at | TIMESTAMP | |
| actual_departure_at | TIMESTAMP | |
| completed_at | TIMESTAMP | |
| created_at | TIMESTAMP | Auto |
| updated_at | TIMESTAMP | Auto |

### `drivers`

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | |
| name | TEXT | |
| phone | TEXT | |
| license_number | TEXT | |

### `delivery_stop_images`

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | |
| stop_id | INTEGER FK → delivery_plan_stops | |
| relative_path | TEXT | File path |
| category | TEXT | `arrival`, `delivery`, `damage`, `departure`, `extra` |
| gps_lat | REAL | |
| gps_lng | REAL | |
| captured_at | TIMESTAMP | |
| uploaded_by | TEXT | |

### Status Lifecycle

```
planned ──► enroute ──► arrived ──► completed
  │                        │
  ├──► skipped              └──► cancelled
  └──► cancelled
```

---

## API Endpoints

**None of these require authentication** — reads or writes, including
`POST /api/plans/clear`, which cascade-deletes every plan, assignment, stop, execution
record and image row. That is a deliberate decision, not an oversight; see
[Key Design Decisions](#key-design-decisions) below. The `Auth` column is retained on the
Plans table as a reminder of what it would look like if that ever changes.

### Plans

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/api/plans` | List plans (filter: `?status=`) | None |
| POST | `/api/plans` | Create plan | None |
| GET | `/api/plans/<id>` | Get plan + assignments + stops | None |
| PUT | `/api/plans/<id>` | Update plan fields | None |
| DELETE | `/api/plans/<id>` | Delete plan (cascades) | None |
| POST | `/api/plans/<id>/confirm` | Set status → confirmed | None |
| POST | `/api/plans/batch-delete` | Delete several plans (`plan_ids[]`) | None |
| POST | `/api/plans/clear` | **Delete every plan and everything under it** | None |
| POST | `/api/plans/import/parse` | Parse an uploaded Excel file into a preview, without writing | None |
| POST | `/api/plans/import/save` | Commit a parsed import to plans/assignments/stops | None |

### Assignments

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/assignments` | List (`?plan_id=`) |
| POST | `/api/assignments` | Create (`plan_id`, `vehicle_id`, `driver_id`, `driver_name`, `sequence`, `notes`) |
| GET | `/api/assignments/<id>` | Get single |
| PUT | `/api/assignments/<id>` | Update |
| DELETE | `/api/assignments/<id>` | Delete (cascades stops) |

### Stops

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/stops?assignment_id=X` | List stops with execution status |
| POST | `/api/stops` | Create stop + execution record |
| GET | `/api/stops/<id>` | Get stop with images |
| PUT | `/api/stops/<id>` | Update stop fields |
| DELETE | `/api/stops/<id>` | Delete stop + execution |
| POST | `/api/stops/<id>/skip` | Mark skipped |
| POST | `/api/stops/<id>/cancel` | Mark cancelled |
| POST | `/api/stops/reorder` | Reorder stops (`assignment_id`, `stop_ids[]` — must name **every** stop of the assignment exactly once) |
| POST | `/api/stops/insert` | Insert temp stop between existing stops |
| GET | `/api/stops/<id>/history` | Phase-change log for the stop, oldest first; reverts are labelled as such |

### Execution

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/execution/current?assignment_id=X` | Current active stop |
| POST | `/api/execution/advance` | Advance stop (`planned→arrived→completed`) |
| POST | `/api/execution/revert` | Undo the last phase change; guarded by an expected-status check so a stale board cannot revert the wrong transition |
| GET | `/api/execution/dashboard` | All assignments + GPS + progress |
| GET | `/api/execution/progress?assignment_id=X` | Progress stats per assignment |

### ETA

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/eta?assignment_id=X` | ETAs for remaining stops via ORS |

### Drivers

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/drivers` | List all |
| POST | `/api/drivers` | Create |

### Images

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/stops/<id>/images` | List images for stop |
| POST | `/api/stops/<id>/images` | Upload image |
| GET | `/api/images/<id>/file` | Serve image file |
| DELETE | `/api/images/<id>` | Delete image |

### End-of-Day Export

Backed by `export_service.py`; the page is `/delivery/export`.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/export/summary?day=YYYY-MM-DD` | Per-day rollup: assignments, stops, phase outcomes, photo counts |
| GET | `/api/export/day.zip?day=YYYY-MM-DD` | Packaged download — stop photos foldered per driver, plus a manifest CSV |
| GET | `/api/export/day-images` | List day-level (not stop-level) images (`?day=`, optional `?category=`) |
| POST | `/api/export/day-images` | Upload a day-level image |
| DELETE | `/api/export/day-images/<id>` | Delete a day-level image |

Driver folder names inside the zip are accent-stripped (`strip_accents`) and fall back to
the plate, so a Vietnamese driver name never produces an unopenable path on a Windows
machine downstream.

### Owned by other blueprints

| Method | Path | Blueprint | Description |
|--------|------|-----------|-------------|
| GET | `/api/fleet/vehicles` | `fleet` (`app/routes/fleet.py`) | List all vehicles (`?q=`) |
| GET | `/api/vehicles` | `core` (`app/routes/core.py`) | Live vehicle data from TTAS |

Both lived in `app.py` until 2026-08-07, when everything registered outside
`create_app()` was moved into blueprints — Gunicorn never executes `app.py`, so those
routes 404'd in production while dev worked.

---

## Service Responsibilities

| Service | File | Responsibility |
|---------|------|----------------|
| `plan_service` | `plan_service.py` | CRUD for plans, assignments, stops. Excel parse/validate. |
| `execution_service` | `execution_service.py` | Stop progression (advance/skip/cancel/revert), phase history, reordering, dashboard data, progress calculation. |
| `eta_service` | `eta_service.py` | ETA calculation using OpenRouteService API, with vehicle envelope restrictions and a Haversine fallback. |
| `image_service` | `image_service.py` | Image upload/serve/delete for delivery stops. |
| `export_service` | `export_service.py` | End-of-day summary, day-level images, `day.zip` packaging, accent-stripped driver folder names. |
| `tracking_service` | `tracking_service.py` | Normalize GPS positions from TTAS, including speed-phrase parsing and `MTH` lost-signal state. |
| `database` | `database.py` | Create delivery tables (idempotent migrations). |

`services/vehicle_identity.py` and `services/plate_utils.py` sit one level up, outside
`delivery/`, because fuel, oil and TLP resolve plates too — plate normalization is a
fleet-wide concern, not a delivery one.

---

## Key Design Decisions

1. **A confirmed plan is editable; execution history is not.** *(Changed 2026-08-06 —
   this decision previously read "Plan tables are immutable after import".)* Reopening a
   confirmed plan at `/delivery/edit/<plan_id>` gives a fully editable builder: the
   read-only banner is suppressed, autosave keeps running, and saving no longer demotes
   the plan back to `draft`. The original rule made confirming a one-way door, with no
   route back into a plan whose stop needed fixing.

   The half that did **not** change is the one that matters: what happened during a run
   is still owned by the execution layer (advance / skip / cancel / revert) and its
   `stop_status_events` log. Editing a confirmed plan rewrites the plan; it does not
   rewrite the record of the run.

2. **Current stop is derived** — No `is_current` column. The current stop is the first stop with status `planned`, `enroute`, or `arrived` (ordered by execution_sequence).

3. **`stop_executions` has no `vehicle_assignment_id`** — The link is through `delivery_plan_stops.vehicle_assignment_id`. This avoids duplication.

4. **Excel import pipeline** — The `confirm_import` function in `plan_service.py` handles the Excel flow by parsing, validating, previewing, and persisting in one transaction per vehicle group.

5. **Dashboard polls every 12s** — The dashboard endpoint returns all data in one call (`/api/execution/dashboard`). Detailed data (stops, ETA) is fetched per-selection only, and each of the three detail requests paints as it arrives rather than being awaited together — `/api/eta` is an order of magnitude slower than the other two and used to gate the whole panel.

6. **Plans auto-complete, they're never auto-archived** — `execution_service.py` transitions a plan's status to `completed` once every stop across every vehicle assignment under it is terminal (completed/skipped/cancelled), so finished plans stop appearing on the active dashboard on their own. There's deliberately no automatic archival/deletion of old or abandoned plans (e.g. test data whose stops were never touched) — that's a manual, explicit dispatcher action, left as a future addition pending observed need.

7. **No authentication — anyone who can reach the host can change or delete anything.**
   A shared dispatcher password (`DISPATCH_PASSWORD`, session cookie, `login_required` on
   22 mutating endpoints) existed briefly on 2026-07-31 and was removed the same day at
   the operator's request: this is an internal-network tool and the login step cost time
   at every shift change. The trade accepted is that the destructive endpoints are again
   reachable by anyone who can resolve the host, and the app binds `0.0.0.0`.

   `tests/test_delivery_routes.py::TestOpenAccess` is the inverse regression guard. It
   fails if any of the 27 endpoints it covers — 23 mutating, 4 read — starts returning
   401/403/503 again, so a gate cannot be reintroduced silently without the frontend
   being taught about it. It also asserts `/login` still 404s. **Revisit this
   before the deployment becomes publicly reachable**, not after. The removed
   implementation is described in full in `CHANGELOG.md` if it needs rebuilding.

8. **Reordering is optimistic and stops carry two sequence numbers** — `planned_sequence`
   is fixed when the plan is built; `execution_sequence` (on `stop_executions`) is what
   everything orders by and what a reorder rewrites. Display the latter, falling back to
   the former. The dashboard paints a move before the server confirms it and POSTs moves
   in click order, because the server rewrites every sequence on each call and two racing
   requests would settle on whichever finished last. Terminal stops are immovable and
   nothing moves across one — their position is a record of what happened.

9. **The driver on a plan is free text, not a `drivers` record** — see
   [`vehicle_assignments`](#vehicle_assignments). A dispatcher typing a stand-in is
   recording who drove that day, not registering an employee, so nothing is promoted to
   the `drivers` table and the plan keeps a snapshot that a later truck reassignment
   cannot rewrite.

10. **TTAS telemetry is prose, and is parsed by meaning rather than by digits** —
    TTAS sends no numeric speed field. Its `speed` key is a Vietnamese status phrase:
    `Chạy 42km/h` (running), `Dừng 3h30'` (stopped, and for how long), `MTH:6h48'`
    (*mất tín hiệu* — signal lost, and for how long). Only the running phrase's number
    is a speed; taking the first number in any phrase reported a truck parked 7h44' as
    doing 7 km/h, which is how this was found. `_parse_speed_kmh` therefore requires the
    km/h unit, reads `Dừng` as a known `0.0`, and strips durations before any fallback.

    `speed_kmh` distinguishes `None` ("no reading we can interpret") from `0.0`
    ("stopped"); the dashboard renders the first as a blank, not a speed.

    `vehicle_status` has four values — `running`, `stopped_engine_on` /
    `stopped_engine_off`, `lost_signal`, `unknown`. `lost_signal` comes from TTAS
    *declaring* the tracker unreachable, which is deliberately preferred over inferring
    it from a stale timestamp: a tracker reporting late is not a tracker that is gone.
    The computed `gps_stale` chip is kept alongside it — two independent paths to the
    same conclusion is what identified the bug.

    A lost-signal vehicle **still has a position** (the last fix before the drop), so it
    passes every "does this have GPS?" test. That is why the dashboard's **No GPS**
    filter keys off `gps.signal_lost` as well as a missing position — it is asked "which
    trucks can I not see?", not "which have no coordinates?".

---

## Configuration

All configuration is via `.env` file:

```
# Required
ORS_API_KEY=           OpenRouteService API key
ORS_BASE_URL=          ORS API base URL

# TTAS tracking (vehicle GPS)
TTAS_LOGIN_URL=        TTAS login page
TTAS_TRACKING_PAGE_URL=TTAS tracking page
TTAS_TRACKING_API=     TTAS realtime tracking endpoint
TTAS_USERNAME=         TTAS login username
TTAS_PASSWORD=         TTAS login password

# Optional
DB_PATH=               SQLite database path (default: routing_system.db)
FLASK_HOST=            Server host (default: 0.0.0.0)
FLASK_PORT=            Server port (default: 5000)
FLASK_DEBUG=           Debug mode (default: true)
DEFAULT_RADIUS_KM=     Geofence radius (default: 3)
ROUTE_REFRESH_INTERVAL=Route cache refresh seconds (default: 60)
```

---

## Testing

### Running Tests

```bash
# Everything — 676 tests
pytest tests/

# Delivery — run BOTH for any delivery change
pytest tests/test_delivery.py -v         # 223 — service layer
pytest tests/test_delivery_routes.py -v  # 143 — route layer

# Google Sheet plan import — run these too if you touch it
pytest tests/test_sheet_import.py -v        # 79 — parser
pytest tests/test_sheet_import_routes.py -v # 26 — endpoints

# Single test class
pytest tests/test_delivery.py::TestStopProgression -v

# With coverage
pytest tests/test_delivery.py --cov=services/delivery --cov-report=term
```

### Two suites, and why both are needed

`test_delivery.py` imports the service modules directly. That is structurally incapable
of catching a bug that lives inside a request handler or in an assembled response — which
is where every Critical finding in `DELIVERY_AUDIT_2026-07-31.md` lived. `test_delivery_routes.py`
drives real HTTP through `app.test_client()` with TTAS mocked. Neither substitutes for the
other.

Frontend code gets no pytest coverage. Six jsdom suites stand in — **194 drives** in
total, run with plain `node`. The four that touch this module are
`tests/js/dashboard.test.js` (122), `tests/js/measure.test.js` (31),
`tests/js/plan-builder.test.js` (10) and `tests/js/export.test.js` (10). See `CLAUDE.md`
§ Definition of Done — including the one dashboard ETA case that fails from 12:00 local
onwards for reasons unrelated to your change.

`test_delivery_routes.py` needs `playwright` installed (it reaches the app via `main.py`,
which imports it at module level). Without it all 143 error out on import rather than
failing on anything real.

### Test Coverage — services (`test_delivery.py`)

223 tests. Largest classes first; the long tail is listed for completeness
because a class missing from here is how coverage silently stops being run.

| Test Class | Tests | Coverage |
|-----------|-------|----------|
| TestEtaService | 27 | ETA calculation, ORS fallback, road geometry, route cache hit/invalidation, travelled distance |
| TestVehicleIdentity | 19 | Plate normalization and the canonical-vehicle index |
| TestSpeedPhraseParsing | 18 | TTAS sends a phrase, not a number — unit-anchored extraction, `Dừng` as a known 0, park durations never read as speeds |
| TestLostSignal | 17 | `MTH:6h48'` recognised as `lost_signal`; last position still reported; no speed invented |
| TestTtasTimestampParsing | 16 | Day-first dates, and the raw text kept alongside the ISO parse |
| TestTrackingService | 14 | Raw-TTAS field names, `device_name`/`plate_key` emission, 0,0 as no-fix |
| TestRevertStop | 13 | Reverting a stop to the phase it came from |
| TestPlanDriverOverride | 13 | The driver typed in the plan outranks the vehicle default, survives a truck changing hands, and creates no `drivers` row |
| TestProofRequired | 12 | Completion gated on both proof photo categories |
| TestStatusHistory | 9 | Every phase change recorded |
| TestExportNaming | 9 | Driver folder names, accent stripping, plate serials |
| TestCanRevert | 8 | Correctability decided per plan-day |
| TestStopProgression | 7 | Advance, skip, cancel, current stop |
| TestImportVehicleResolution | 6 | Plate variants resolving to one vehicle on import |
| TestStopReordering | 5 | Reorder, insert temp stop, sequence update |
| TestReorderValidation | 5 | Full/partial/foreign-id reorder rejection |
| TestProgress | 5 | Progress calculation, breakdown |
| TestImageService | 5 | Upload, list, delete, edge cases |
| TestAdvanceAtomicity | 5 | Concurrent advance leaves no half-applied state |
| TestPlanAutoCompletion | 4 | Plan auto-completes when all stops/assignments terminal, reopens on new stop |
| TestTransactions | 2 | Rollback on failure, cascade delete |
| TestProgressWithoutStops | 2 | An empty assignment reports 0, not 1 |
| TestPreviewImportResolution | 2 | Import preview resolves plates the same way the import does |

### Test Coverage — routes (`test_delivery_routes.py`)

143 tests.

| Area | Coverage |
|------|----------|
| GPS pipeline | GPS reaching the dashboard, telemetry parsed from raw TTAS keys, all five plate formats matching, 0,0 treated as no-fix, malformed coordinates not 500-ing |
| Assignment driver | A name POSTed by the plan builder reaches the dashboard, comes back on reopen, is editable by PUT, and never becomes a `drivers` row. Route-layer on purpose — the field was being dropped in the request handler, which the service suite cannot see |
| Open access | 23 mutating and 4 read endpoints asserted **reachable** — fails if authentication is reintroduced; `/login` asserted to 404 |
| Execution lifecycle | Full progression, the double-tap 409, skip/cancel with reasons, plan auto-completion, temp-stop insertion |
| Reorder validation | Full/partial/foreign-id cases, and that no duplicate `execution_sequence` is left behind |
| Excel import | Plate variants collapsing to one assignment, unknown plates rejected with nothing written |
| Uploads | Accepted image types, rejected `.html`/`.svg`/`.php`, oversized/empty, traversal confined to the upload root |

### Manual Test Checklist

- [ ] Create plan with 2+ assignments, 3+ stops each
- [ ] Edit draft plan — verify all stops load correctly
- [ ] Confirm plan — verify status changes to `confirmed`
- [ ] Open dashboard — verify vehicle appears
- [ ] Select vehicle — verify map shows stops + route
- [ ] Advance stop — verify timeline updates
- [ ] Skip stop — verify status becomes `skipped`
- [ ] Cancel stop — verify status becomes `cancelled`
- [ ] Verify execution persists after page refresh
- [ ] Add duplicate assignment — verify stops copy correctly
- [ ] Reorder stops via drag-and-drop (plan builder, Step 3)
- [ ] Reorder stops via the ▲/▼ controls (dashboard timeline) — confirm a completed stop can't move and nothing moves across it
- [ ] Click a stop in the timeline — verify the map centres on it and Follow switches off
- [ ] Switch basemap (Satellite / Streets / Muted) — verify the choice survives a reload
- [ ] Click the satellite map — verify a capture date appears; switch to Streets and verify clicking does nothing
- [ ] Select a different vehicle — verify the right panel clears immediately and the stop list appears well before ETAs do
- [ ] Use station search — verify auto-fill
- [ ] Use map picker — verify lat/lng populated
- [ ] Test responsive layout at 768px width
- [ ] Test filters (plan, date, vehicle, driver, status)

---

## Deployment

### Requirements

- Python 3.10+
- Flask 3.x
- SQLite 3
- OpenRouteService API key
- TTAS tracking credentials

### Install

```bash
pip install -r requirements.txt
```

### Run

```bash
# Development
python app.py

# Production (Gunicorn) — this is what render.yaml runs
gunicorn wsgi:app
```

**The target is `wsgi:app`, not `app:app`.** `app.py` (file) and `app/` (package) share
the name `app`, and Python resolves `import app` to the package, so `app:app` cannot reach
the Flask instance. An earlier revision of this document specified `-w 4 ... app:app`;
both halves were wrong.

Note that `render.yaml` passes no `--workers`/`--threads`, so production runs a **single
synchronous worker** — see Known Limitations.

### Environment

Create `.env` from `.env.example` with all required keys. There is no authentication
variable; `DISPATCH_PASSWORD` was removed on 2026-07-31 and is ignored if still present.

---

## Known Limitations

1. **ETA requires live GPS** — If TTAS is unreachable, ETA shows "Vehicle GPS not available". The dashboard gracefully handles this.
2. **Single SQLite database** — No connection pooling. Not suitable for high-concurrency production use without a pooler.
3. **No real-time push** — The dashboard uses polling (12s interval). For sub-second updates, WebSocket or SSE would be needed.
4. **N+1 in get_plan** — Loading a plan with N assignments issues N+1 queries (1 for plan, 1 for assignments list, N for each assignment's stops). Acceptable for typical plan sizes (< 20 assignments).
5. **Page refresh loses unsaved auto-save timer** — The `beforeunload` handler warns users, but a crash during auto-save could lose the current save operation.
6. **TTAS session expires** — The fleet session cookie expires periodically. The app retries with a fresh session on failure.

7. **Requests are serialised in production** — `render.yaml` runs `gunicorn wsgi:app` with no `--workers`/`--threads`, i.e. one synchronous worker, and `/api/execution/dashboard` performs a blocking TTAS HTTP fetch inside the request. A dispatcher action landing mid-poll waits behind that fetch no matter what the frontend does. The obvious fix is worker/thread flags, but this SQLite database has no `PRAGMA journal_mode=WAL` — adding concurrency without WAL trades the latency for "database is locked" errors. Treat WAL and concurrency as one decision.

8. **No authentication** — see Key Design Decisions #7. Deliberate, and a real exposure if this ever leaves the internal network.

9. **The map depends on three third-party hosts** — `unpkg.com` (Leaflet), `server.arcgisonline.com` (satellite tiles *and* the imagery capture-date query) and `basemaps.cartocdn.com` (street/muted tiles, satellite labels). On a filtered network the map degrades quietly rather than erroring, so allow-list them explicitly. Satellite tiles are also heavier than vector-styled street tiles on a slow link.

10. **A stop with no coordinates can't be located or routed** — it still appears in the timeline and counts toward progress, but has no map marker, is skipped by the route line, and clicking it reports that it isn't on the map.

11. **`.vehicle-list` / `.vehicle-card` has an unfixed flex bug** — the same defect fixed in `.timeline-item` on 2026-07-31 (a flex-column child with no `flex-shrink: 0`, so cards squash instead of the container scrolling). More visible there because the card has no `overflow: hidden`, so text spills between cards. Left alone under scope control; a one-line CSS fix.
