# Changelog

## 2026-08-16 — Documentation pass: every test and endpoint count re-measured

> **Documentation only.** No source file changed. Every figure below was produced by
> running the thing, on 2026-08-16, not by reading a previous doc.

`README.md` and `CLAUDE.md` both carried a test inventory frozen around 2026-08-10. Three
suites had grown since, one whole suite (`test_streetview_routes.py`, and its jsdom
counterpart) had been added on 2026-08-16 and appeared in neither file, and one endpoint
had been added to `core`. A count that is only slightly wrong is worse than no count: it
reads as authoritative and nobody re-checks it.

### What moved

| Figure | Was | Now | How measured |
|---|---|---|---|
| pytest total | 676 | **737** | `python3 -m pytest tests/ -q` → `737 passed in 71.21s` |
| `test_delivery.py` | 223 | 230 | per-file `pytest -q` |
| `test_delivery_routes.py` | 143 | 157 | per-file `pytest -q` |
| `test_sheet_import.py` | 79 | 89 | per-file `pytest -q` |
| `test_streetview_routes.py` | *(absent)* | 30 | per-file `pytest -q` |
| jsdom total | 194 over 6 suites | **242 over 7** | each file run individually with `node` |
| `dashboard.test.js` | 122 | 131 | `node tests/js/dashboard.test.js` |
| `measure.test.js` | 31 | 35 | ditto |
| `export.test.js` | 10 | 12 | ditto |
| `streetview.test.js` | *(absent)* | 33 | ditto |
| HTTP endpoints | 129 | **130** | `grep -cE "\.route\(" ` over the 7 route modules |
| `core` blueprint | 14 | 15 | `/api/streetview`, added 2026-08-16 |

Suite totals in `README.md` § Running Tests move with them: delivery 471 → **502**,
route-layer 83 → **113**, TLP unchanged at 39. Those three blocks sum to 654 rather than
737 because they only cover the suites they name, and `test_tlp_routes.py` (8) is
deliberately listed under both route-layer and TLP. The full inventory in § Project
Structure adds to 737 exactly.

### Two entries were wrong, not merely stale

Worth separating from the arithmetic above, because a stale number is a maintenance debt
and a wrong instruction sends the next person down a dead end.

**1. `TZ=UTC` was documented as a workaround for the time-dependent dashboard test. It is
not one.** Both files said `TZ=UTC node tests/js/dashboard.test.js` "gives a clean run from
a UTC+7 afternoon". The failing assertion is `a route running past midnight is marked, not
shown as already late`: it feeds `UI.etaClock()` a 36-hour ETA and expects `+1d`, and
`etaClock` counts calendar days crossed, so `now + 36h` lands one date away only while the
local hour is under 12. That threshold applies **in whichever zone the process runs in**.
Forcing `TZ=UTC` does not remove the threshold, it just moves it seven hours.

Reproduced on 2026-08-16 at 22:30 +07, which is 15:30 UTC:

```
$ TZ=UTC node tests/js/dashboard.test.js
  ✗ a route running past midnight is marked, not shown as already late
130/131 passed
```

From UTC+7 the window in which `TZ=UTC` helps is roughly 07:00–19:00 local — i.e. it works
in the morning, which is when whoever wrote the note presumably tried it, and stops working
in exactly the "mid-afternoon" case it was written for. Both files now say to pick a zone
whose local hour is under 12, or accept the single failure. The real fix is still an
injectable clock in `etaClock`.

**2. "Six suites exist" in `CLAUDE.md` § Definition of Done.** There are seven;
`streetview.test.js` was added the same day as the entry above it and the count was not
touched.

### Also corrected

- `README.md` § Modules did not mention the Mapillary street-view panel in the dispatch
  board's feature list, though the CHANGELOG entry above it describes the feature in full.
- `README.md` § Project Structure listed `core.py` without `/api/streetview`.
- The jsdom block in both files now records that each boot costs tens of seconds on a slow
  filesystem, so the suites want running one file at a time. Running all seven behind a
  single short timeout is how this pass initially failed to measure any of them.

### What was checked and found already correct

So the same ground is not re-walked:

- Fleet composition — `SELECT vehicle_type, COUNT(*) FROM vehicles GROUP BY vehicle_type`
  still gives 32 box trucks (1.5–10 t) + 4 container vehicles, 36 total.
- Blueprint split for `delivery` (44), `tlp` (28), `fuel` (18), `fleet` (12), `oil` (9) and
  `trips` (4) — unchanged.
- TLP suite total (39 = 26 + 5 + 8) — unchanged.
- `test_vehicle_specs.py` (40), `test_vehicle_core_data.py` (36),
  `test_write_handler_connections.py` (36), `test_scorer.py` (26),
  `test_sheet_import_routes.py` (26), `test_routing.py` (15), `test_trips_geofence.py` (14),
  `test_fleet_routes.py` (11), `test_tlp_routes.py` (8), `test_wsgi_routes.py` (8),
  `test_fuel_routes.py` (6), `test_auto_arrange_e2e.py` (5) — all unchanged.
- `plan-builder.test.js` (10), `sheet-import.test.js` (16), `tlp-escaping.test.js` (5) —
  unchanged.
- `tests/test_all.py` still contributes zero pytest tests despite matching `test_*.py`
  discovery.
- Pages: 11 routes over 9 templates. Street view is a panel on the existing dispatch board,
  not a new page.

### Note for the next pass

`docs/CODEBASE_ANALYSIS_REPORT.md`, `docs/DELIVERY_MODULE.md` and
`docs/TRUCK_LOAD_PLANNER.md` were **not** audited here and may carry their own stale
figures. `AGENTS.md`'s graphify statistics (3,131 nodes / 5,997 edges / 200 communities
over 137 files) were also left alone — verifying them means running `graphify update .`
first, which is a separate job.

## 2026-08-16 — Street view on the dispatch board (Mapillary)

> **Uncommitted at the time of writing.** Not yet verified against live Mapillary —
> see "What is unproven" below before trusting it in production.

A dispatcher whose driver cannot find an address had nothing to look at. The satellite
basemap shows a roof; the stop record shows text typed into a spreadsheet. Neither answers
"what does the front of this place look like". This adds a panel that does.

### Why Mapillary

Free, with no paid tier — Meta-owned, imagery under CC BY-SA 4.0, search API capped at
10,000 requests per minute against an expected few hundred per day. Vietnamese coverage is
better than it sounds: ride-hailing company Be Group contributed ~9M images / 27,000 km
across Ho Chi Minh City and Hanoi. Google Street View returned to Vietnam in June 2025 and
is better imagery, but Street View Static is a Pro SKU with 5,000 free calls/month since
Google replaced the flat $200 credit with per-SKU caps in March 2025, and it would be a
metered dependency inside a workflow used all day.

Vantor (ex-Maxar) Vivid was evaluated first and rejected: enterprise-priced satellite
foundation data, no street level, and nothing in it that changes an ETA or finds a gate.

### How it is reached

- **Street view button** on every timeline stop that has coordinates, including completed,
  skipped and cancelled ones — "where was that place again?" is asked about yesterday's
  stops as often as today's. `buildActionsHtml`'s early return for non-actionable stops is
  gone for that reason; those rows previously rendered no action bar at all.
- **Shift+right-click** anywhere on the map, for a point that is not a stop.

Plain right-click still arms the measure ruler. Both handlers sit on the same Leaflet
`contextmenu` event, so `measure.js` returns early when `shiftKey` is set — checked
*before* its `active` branch, or the gesture would discard a half-finished measurement on
its way to opening the panel.

### Architecture

- `MAPILLARY_TOKEN` is **not** in `config.required_env_vars`. That list raises at import
  time; street view is a convenience and must not be able to stop the dispatch board
  booting. Absent token = the panel says it is unconfigured, nothing else changes.
- `app/services/streetview.py` runs two passes. Mapillary's radius search caps at **50 m**,
  and this fleet's stop coordinates are hand-typed into the manager's Google Sheet, so a
  meaningful share of stops sit further out than that from the nearest photo. A ~200 m
  bounding box (well inside the API's 0.01-degree-square limit) catches those,
  nearest-wins. Beyond 150 m the result is discarded — a photo of somewhere else captioned
  as the stop is worse than an honest "nothing here".
- `GET /api/streetview` proxies it so the token stays server-side, and lives in
  `core.py` next to `/api/geocode` for the same reason: a thin third-party lookup with no
  domain of its own.

### The distinction the whole feature rests on

**"No imagery here" and "the lookup failed" must never render the same.** If they collapse,
an expired token or a Mapillary outage shows as empty coverage on every stop at once, the
panel looks like it is working correctly, and nobody finds out for months.

So the service *returns None* for one and *raises* for the other; the endpoint answers 200
`{found:false, reason:'no_imagery'}` versus 503; and the panel styles them differently.
Asserted from both sides — `test_expired_token_does_not_read_as_no_imagery` and
`a failed lookup reads as a failure, not as empty coverage`.

### Dashboard conventions honoured

The panel contains no `setView`, `panTo`, `flyTo`, `fitBounds` or `setZoom`, and a test
greps the source to keep it that way. Opening street view for stop #7 while watching a
truck approach stop #3 must not move the view — the 2026-07-31 map rules. It owns its own
DOM, so the 12-second poll cannot disturb it, the same property `measure.js` gets from its
own layer group. Every async continuation checks a request token, so a slow lookup cannot
repaint a panel that has since been closed or reopened somewhere else.

The embed is sandboxed **without** `allow-same-origin` and carries
`referrerpolicy="no-referrer"`: third-party content inside an operations tool gets scripts
for the viewer and no access to this page's origin.

Capture date is always shown, and flagged amber past three years. Mapillary's Vietnamese
coverage came largely from a 2022-24 mapping push, so old photos are common, and a
four-year-old shopfront is useful for finding the turning and misleading for identifying
the shop.

### Revised the same day: walkable coverage, not per-stop photos

The operator's correction, and it was right: **most of this fleet's stops are down lanes
and yards no Mapillary driver ever entered**, so a lookup pinned to the stop coordinate
usually finds nothing. The useful imagery is on the arterial road the lane comes off —
which is how a driver actually approaches — and the original 150 m ceiling discarded
exactly those results.

Three changes follow from that:

- **Search widened.** A third pass at a ~500 m box (just inside the API's hard
  0.01-degree-square bbox limit), ceiling raised 150 m → 600 m. Distance is reported and
  flagged amber past 150 m, so "this is the main road, not your gate" is visible rather
  than implied. There is no fourth pass: past half a kilometre the honest answer is that
  the point is not covered.
- **MapillaryJS replaces the embed iframe**, so the dispatcher can walk the road — arrows,
  arrow keys, click-into-the-distance — instead of looking at one fixed frame. A position
  marker with a facing cone tracks the viewer on the Leaflet map, because a photo of a
  street with no idea which street it is answers half the question. The iframe survives as
  a fallback when the CDN is unreachable.
- **Coverage overlay**, green lines in the layer control, off by default and remembered.
  Vector tiles rather than the search API because coverage is a whole-city question and
  the search bbox caps at ~1 km. Clicking a line enters the viewer at that image, with no
  lookup — the dispatcher already pointed at one.

**This moved the token into the browser**, reversing the earlier decision in this entry.
Coverage tiles and MapillaryJS both authenticate their own requests, and proxying them
would put dozens of tile requests per pan behind render.yaml's single synchronous Gunicorn
worker, ahead of the dispatcher actions that matter. `/api/streetview` still exists and
still keeps the token server-side for the nearest-image lookup. What is exposed is a
client token — read access to public imagery, quota 50k tiles/day — so the cost of a leak
is someone spending the quota. If street view starts reporting quota errors, rotate it
rather than hunting for a bug. Both CDN libraries are optional at runtime: neither missing
takes the dispatch board down.

### Tests

`tests/test_streetview_routes.py` (30) and `tests/js/streetview.test.js` (33) are both new;
`tests/js/measure.test.js` gained 4 cases for the right-click split and is now 35.
`/api/streetview` was added to `test_wsgi_routes.py`'s pinned route map.

Mutation-checked, four ways: swapping the GeoJSON `[lng, lat]` order fails 2 backend
cases; collapsing 503 into `no_imagery` fails 5; dropping the panel's stale-response guard
fails the two-stop race; rendering a lookup failure as "no imagery" fails the case named
for it.

jsdom has no WebGL, so MapillaryJS cannot run under test. That is not a coverage gap — it
is the fallback path, exercised exactly as a CDN outage would trigger it. A stubbed
`window.mapillary` covers the real-viewer wiring: construction with the token, `moveTo` on
open, the position marker following the `image` event, and Follow gating the only permitted
map movement.

`pytest tests/` is **737, all passing**. `tests/js/dashboard.test.js` is 130/131 — the one
failure is the documented time-of-day `etaClock()` case, which fails from noon local
onward and is unrelated.

### What is unproven

**No call has ever been made to Mapillary from this codebase.** Every test stubs
`requests.get`. The token in `.env` is well-formed (`MLY|`, three segments) but has not
been exercised against the live API, and no real coverage figure for these stops exists
yet — the development sandbox blocks `graph.mapillary.com`.

`check_mapillary_coverage.py` at the repo root answers both questions in one run: it
confirms the token and reports, over the 25 most-used stop locations, how many are served
by the 50 m radius search, how many need the bbox fallback, and how old the imagery is.
Run it before relying on any of this. If the fallback turns out to carry most stops, the
50 m cap is doing real damage and widening the box is the next lever; if almost nothing is
found, the honest conclusion is that this feature does not suit this fleet's stops.

## 2026-08-15 — Stop manager phone numbers were unusable in 118 of 149 stops

> **Uncommitted at the time of writing.**

The operator reported that stop manager phone numbers should start with `0` and many did
not. They were right, and the cause turned out to produce a second, less visible
corruption on top of the missing zero — one that a naive "prefix a 0" repair would have
baked in permanently.

### What was wrong

The manager's planning sheet stores column R as text in some rows and **number-formatted**
in others. A numeric cell lost information twice on its way into `delivery_plan_stops`:

1. **Sheets drops the leading zero.** `0939746130` in a numeric cell is the integer
   939746130.
2. **We welded the float's fraction onto the end.** `gviz` reports the cell as
   `939746130.0`; `_cell` stringifies it; `_clean_phone`'s `re.sub(r"[^\d+]", "", ...)`
   deleted the decimal point and kept the `0` after it — `9397461300`.

Of 149 stops with a phone, 118 were malformed: 33 nine-digit (corruption 1 alone) and
**85 ten-digit ending in `0` — 85 of 85, no exceptions.** That unanimity is what
identified the float as the cause rather than dispatcher typing; a real set of numbers
ends in `0` about a tenth of the time.

The confirming evidence was seven managers whose one number was stored two or three ways.
Nguyễn Minh Sơn appeared across 14 stops as `0939746130` (text cell), `939746130` and
`9397461300` (numeric cells). Same person, same number, three spellings.

**Prefixing `0` alone would have been wrong** — it turns those 85 rows into 11-digit
numbers that cannot be dialled, and leaves them differing from the same manager's rows
that happened to come from a text cell.

### The fix

- `services/delivery/sheet_import_service._clean_phone` now strips an all-zero decimal
  fraction *before* the digit strip, and restores the leading `0` on a 9-digit result.
  Values already starting `0`, and `+84…` forms, are untouched. Only an all-zero fraction
  is treated as the artifact; anything else falls through to the previous behaviour.
- `scripts/fix_manager_phones_2026-08-15.py` repairs rows imported before that. It backs
  up the database, writes a full before/after mapping to `reports/`, applies, then asserts
  the post-condition: every phone plausible, and no manager holding two different numbers.
  Idempotent — a value starting `0` is never touched.
- Ten already-correct numbers carry human spacing (`0939 980 584`). Reformatting them is
  cosmetic and outside this repair, so it sits behind `--normalize-spaces`, off by default.

Applied to `routing_system.db`: 118 rows updated, 31 already correct, 0 unrecognized. All
149 are now 10 digits starting `0`, and the 7 split managers collapsed to one number each.

`tests/test_sheet_import.py::TestCleanPhone` (10 cases) covers both corruptions and the
text cells that always worked. Mutation-checked: reverting `_clean_phone` fails exactly
the 4 cases aimed at the bug and leaves the 6 regression guards green. Suite is 89, was
79; `test_delivery.py` (345 with the import suites) and `test_delivery_routes.py` (157)
both pass.

**Note for whoever runs this next:** the sandbox mount cannot do SQLite journaling —
`conn.backup()` and `conn.commit()` both raise `disk I/O error`, and a failed commit left
a hot journal that the next open rolled back. The script was run against a copy on local
disk and the finished file copied back. Run it directly on the machine that owns the
database.

## 2026-08-15 — Video evidence, and a way to undo a mis-upload

> **Uncommitted at the time of writing.**

Two operator-reported problems, one code path. Drivers were shooting proof of delivery as
video and had nowhere to put it — the validator's allow-list was images only and the cap
was 10 MB. Separately, dispatch runs many vehicles at once, evidence regularly landed on
the wrong stop, and there was no way at all to correct that from the dashboard.

### Video is accepted alongside photos

`services/delivery/image_service.py` was the single choke point: both the per-stop proof
upload and the end-of-day loading/empty-container upload validate through
`_validate_upload`, so widening it once covered both.

- `ALLOWED_EXTENSIONS` is now the union of `IMAGE_EXTENSIONS` (unchanged) and
  `VIDEO_EXTENSIONS` = `.mp4`, `.mov`, `.webm` — Android, iPhone and desktop respectively.
  `.avi`, `.mkv` and `.3gp` are deliberately out, and the S-05 reasoning is unchanged:
  `serve_image` hands the file to `send_file`, which infers Content-Type from the
  **extension**, so the allow-list is what stops an upload being served as active content.
  The browser-supplied Content-Type on a multipart part is attacker-controlled and is still
  never consulted.
- **The size cap is per kind, not global**: 10 MB images, 100 MB video. A single cap would
  have had to be the video one, which would then have let a 100 MB "photo" through. The
  rejection message names the kind, because a driver told "the limit is 10 MB" after
  picking a video has no way to learn that video is allowed ten times that.
- `media_kind` is **derived from the stored extension, not a column**. No migration, and
  rows written before today classify correctly for free. Unknown extensions read as
  `image`: an `<img>` with a bad source shows a broken thumbnail the dispatcher can report,
  a `<video>` with one shows nothing at all.
- `app/config.py`: `MAX_UPLOAD_MB` **25 → 110**. Werkzeug enforces `MAX_CONTENT_LENGTH`
  before the view runs, so leaving it at 25 would have made `image_service`'s friendly
  message unreachable and handed the driver a bare 413. `test_request_cap_stays_above_the_video_cap`
  asserts the invariant, since the failure is silent.
- `serve_image` needed no change — `send_file` defaults to `conditional=True` for a path,
  which is what makes Range requests work, and a `<video>` seeking against a plain 200 is
  unseekable. Now commented, and covered by a Range test, so it does not get "simplified".

### The evidence gallery is no longer read-only

`DELETE /api/images/<id>` had existed since the delivery module shipped and **had no
caller** — `DASH.api` never got a delete method and `bindPhotosToggle` rendered bare
anchors. That is why a mis-upload was uncorrectable.

- `static/js/dashboard/api.js` gains `deleteStopImage`; the gallery gains a per-item remove
  control, delegated to the container because `load()` replaces its `innerHTML` wholesale.
- **Confirmed, unlike the equivalent remove on `delivery-export.js`.** That page drops a
  photo uploaded seconds earlier in the same session; this one deletes proof of delivery
  for a truck that has already left, the file is unlinked immediately, and there is no undo.
- The correction workflow is delete-then-reupload. **Nothing is enforced in code** — a
  move/reassign endpoint was considered and rejected, and one-file-per-category was
  considered and rejected because multiple files per category is existing, tested,
  in-use behaviour that the batch input depends on.
- **No audit trail, by the operator's decision.** Worth knowing rather than rediscovering:
  with no authentication (also by decision, 2026-07-31), any user on the internal network
  can delete a delivery photo and leave no record of it. If the deployment ever becomes
  publicly reachable, this compounds the auth conversation rather than being separate
  from it.

### Frontend

`timeline.js` now renders three upload inputs, not two. `capture` and `multiple` remain
mutually exclusive, and `accept="image/*,video/*"` **with** `capture` makes the browser
pick — and it picks stills, so a combined button would have been a photo button wearing a
video label. Hence a separate "Record video" input. The batch input takes both types.
Video thumbnails render as `<video preload="metadata">` — a stop with three 100 MB clips
would otherwise pull 300 MB the moment the panel opened, over the mobile connection
dispatch is on — with a badge, since a metadata-preloaded video is just a still frame.

### Tests

676 → **697** pytest (`test_delivery.py` 223 → 230, `test_delivery_routes.py` 143 → 157),
194 → **205** jsdom (`dashboard.test.js` 122 → 131). Ten mutations were run and all ten
were caught: collapsing the caps, emptying `VIDEO_EXTENSIONS`, dropping the `media_kind`
stamp, reverting `MAX_UPLOAD_MB`, `conditional=False`, rendering video through the `<img>`
path, removing the confirm, skipping the post-delete repaint, leaving the button disabled
after a failure, and deleting the video input.

### Known, not addressed

`build_day_zip` assembles the handover ZIP entirely in memory (`BytesIO`) on the single
synchronous production worker. With photos that was fine; a day with a dozen 100 MB videos
is a >1 GB buffer and will likely OOM the Render instance. Related: the 20 GB persistent
disk holds roughly 200 videos at this cap, against tens of thousands of photos, and there
is no retention policy. Neither is caused by this change and both are made materially more
likely by it. Flagged to the operator, left unimplemented per scope control.

## 2026-08-15 — Documentation pass: every figure re-measured

> **Uncommitted at the time of writing.** No source file was touched — this entry is about
> `README.md`, `CLAUDE.md`, `AGENTS.md` and `docs/`.

Counts in the reference documents had drifted behind the 2026-08-10 and 2026-08-13 work.
Everything below was re-derived from the working tree rather than carried forward: route
totals from `create_app().url_map`, test counts from `pytest --collect-only`, fleet and
dump figures from `routing_system.db` and `database.sql`, graph figures from
`graph.json`.

### Corrected

- **`README.md`** — jsdom drives 163 → **194** in the At-a-glance table (the section
  heading below it already said 194); route-layer suite total 76 → **83**;
  `test_delivery_routes.py` 135 → **143** and `test_trips_geofence.py` 7 → **14** in the
  project tree; `test_all.py` "16 subcommands" → **5 subcommands over 17 modes**;
  `measure.test.js` (31) and `export.test.js` (10) added to the tree listing;
  `measure.js` added to the `dashboard/` listing; the plan builder is a **5**-step wizard,
  not 4 (`templates/delivery-plan-builder.html` has five step indicators).
- **`CLAUDE.md`** — `database.sql` is **25** tables, not 24, and no longer mirrors the
  live database: schema and `vehicles`/`fuel_log` still match, but `delivery_plan_stops`
  holds 52 rows in the dump against several hundred live, and climbing daily — so the
  entry now says to re-derive that count rather than quoting one. Graph figures
  3,104/5,957/138 files →
  **3,131/5,997/137**. `trips.py:403` → `:410`.
- **`docs/DELIVERY_MODULE.md`** — the architecture diagram still showed routes hanging off
  `app.py`, which stopped being true on 2026-08-07; the "Legacy (in app.py)" table now
  names the blueprints that actually own those two endpoints. Suite totals 548 → 676 and
  135 → 143. `TestOpenAccess` covers **27** endpoints (23 mutating, 4 read), not 22 — the
  22 was the count the removed login gate wrapped, which is a different number. jsdom
  suites 2 → 6.
- **`docs/CODEBASE_ANALYSIS_REPORT.md`** — addendum 2026-08-15 appended, per this
  document's own rule that corrections are added rather than edited in.
- **`docs/DISPATCH_UX_PLAN.md`** and **`docs/VEHICLE_ROUTING_PLAN.md`** — verification
  dates refreshed. Both re-checked and both still accurate: `planned_arrival_at` and
  `service_minutes` appear nowhere, and the envelope table is unchanged (32/36 on
  `gross_weight_kg`, 0/36 on all four dimension columns).

### Documented for the first time

The lazy route-cache rebuild on `GET /api/route-data` had shipped into the working tree
without reaching any reference document. `CLAUDE.md` § Concurrency now carries it, because
that is where the reason lives: `start_route_refresh_thread()` is gated behind `__main__`
in `app.py`, so under Gunicorn nothing fills `state.route_data_cache` on a cold start.
`state.route_refresh_lock` also joins `sync_lock` and `oil_fetch_lock` in the list of
things a second worker would silently break.

### `AGENTS.md` kept, not deleted

Claude Code and Cowork read `CLAUDE.md` and ignore `AGENTS.md`, so it looked removable.
OpenCode reads it, and `.opencode/opencode.json` is present and configured with the
graphify plugin — deleting the file would have stripped OpenCode's instructions without
any visible failure. Kept, refreshed, and it now states which tool reads which file so the
question does not come up again.

## 2026-08-13 — Distance measure tool on the dispatch map

> **Uncommitted at the time of writing.** This entry documents the working tree, not
> `HEAD`.

### Added — a ruler on the dashboard map

The dashboard could report distance only along a *planned* route: `/api/eta` returns
`travelled_distance_km` and `remaining_distance_km` for the selected assignment, and the
info bar renders them. There was no way to ask how far apart two arbitrary points are — a
yard and a gate, a proposed detour, a customer not yet in any plan. Dispatchers were
switching to Google Maps for it.

`static/js/dashboard/measure.js` is a 7th `DASH` module, loaded after `map.js` (it reads
the Leaflet instance out of `DASH.map.getMap()`) and before `timeline.js`. Gestures follow
Google Maps, which is what the operator asked for and already knows: **right-click** drops
the first pin and arms the tool, **left-click** extends the path, pins **drag** to adjust
with the total updating live, **Backspace** undoes the last pin, and **Escape**, the
toolbar button or a second right-click clears. A top-centre readout carries the running
total and leg count. A `#measureBtn` control arms it without a right-click, which is the
only way in on the phones these pages get used on.

**Straight-line geodesic, computed in the browser.** No new endpoint, no ORS call, no
backend change at all. Road distance would mean one OpenRouteService request per
measurement, and the question this answers — "how far apart are those two points" — is not
the question the ETA panel already answers. The haversine mirrors
`app/utils/geo.py:get_distance_meters` (same R = 6371000), so a figure read off the map and
one computed server-side agree.

Formatting is whole metres below 1 km, two decimals from 1–10 km, one decimal above: at one
decimal the step between 1.0 and 1.1 km hides 100 m, which is the distance between two
adjacent depots.

### Changed — three small edits to make room for it

- `map.js`'s map-click handler returns early while the ruler is armed. Without it every
  measuring click on the satellite basemap would also fire an Esri identify and open an
  imagery-date popup over the point just measured.
- `main.js` clears the measurement in `selectAssignment()`, which is guarded by that
  function's existing same-id early return — so switching trucks wipes the pins (the call
  zooms the map elsewhere and would otherwise strand them off-screen), while re-clicking
  the already-selected truck leaves them alone. That distinction matters because vehicle
  markers stay clickable during measurement, which was a deliberate choice: pins simply
  don't land on top of a truck icon.
- `main.js`'s Escape handler checks the ruler before the filter panel and the selection,
  ordered explicitly there rather than left to listener-registration order.

Nothing in the module moves the map view, so the Follow-mode rule holds. It owns its own
layer group and is never touched by `updateVehicles`/`updateStops`/`updateRoute`, so a
measurement survives the 12-second poll.

### Tests

`tests/js/measure.test.js` (31) — a 6th JS suite. It needs its own harness rather than
joining `dashboard.test.js`, which *stubs* `DASH.map` precisely because `map.js` is the one
module that reaches Leaflet; `measure.js` is built on Leaflet too, so it gets a minimal fake
`L` and the real template from disk. The distance assertions are checked against a spherical
law-of-cosines reference and two analytic ground truths (a degree of longitude at the
equator, a quarter meridian) rather than against a copy of the haversine under test, which
would have proved nothing. Mutation-checked: collapsing the total to first-to-last, dropping
the `map.js` guard, and no-op'ing the vehicle-change clear each fail exactly one test.

JS suite total is now **194**. `tests/js/dashboard.test.js` re-run at 122/122 under
`TZ=UTC` to cover the `main.js` and `map.js` edits. No Python touched, so no pytest.

## 2026-08-10 — Loading photos split per driver; trip phase is a dispatcher decision only

> **Uncommitted at the time of writing.** This entry documents the working tree, not
> `HEAD`.

Two unrelated operator reports, fixed together.

### Changed — the ZIP now matches the operator's own folder tree

The end-of-day ZIP filed every loading photo into one flat `HinhNhanHang_<dd_mm>/` at the
top level. That was a deliberate call when the export was built — the operator's hand-made
tree nested them per driver, and it did not seem worth the taps. With a real day's volume
in it, a single folder of pallet shots gives no way to tell whose truck they came off.

The operator then supplied a `tree` listing of the shape they actually hand over, which is
driver-first with **both** photo folders inside it:

```
8_8/
  TranHoangQuan_79107/
    HinhNhanHang_07_08/        loading, loose — not split by stop
    HinhGiaoHang_08_08/
      CTVT88/                  one folder per stop
      CTBTX0/
  NguyenThanhGiang_94819/
    ...
  HinhThungTrong/              empty containers, one flat folder
  manifest.xlsx
```

`HinhGiaoHang` is split by stop; `HinhNhanHang` is not, at the operator's call — loading
happens in one pass as the truck is filled, and a station picker on every shot would be a
tap for a distinction nobody reads afterwards.

The plumbing already existed: `delivery_day_images.label` is how `empty_container` has
always tagged a driver. Loading uploads simply passed an empty one. So the change is a
driver `<select>` on the upload row (`templates/delivery-export.html`,
`static/js/delivery-export.js`) and a nesting change in `build_day_zip`
(`services/delivery/export_service.py`).

### Added — every folder is created, photographed or not

A stop with no photos previously had no folder, so in the handover a missed stop and a
stop that does not exist looked identical. The stop folders are a checklist: an empty
`CTBTX0/` is how the operator sees that nobody photographed CTBTX0. `build_day_zip` now
emits a directory entry for every driver, both of their photo folders, and every stop on
the plan, whether or not anything is filed inside.

A ZIP directory is a zero-length entry whose name ends in `/` **and** whose
`external_attr` carries the directory bit. Both bits are set — the Unix mode and the
MS-DOS `0x10` flag — because Windows Explorer reads the latter and would otherwise unpack
these as zero-byte files named after each stop.

Note for anyone asserting on a ZIP from here on: `namelist()` now includes folder entries.
`TestDayExport._files()` exists to filter them out, and three existing tests were counting
`namelist()` directly.

### Changed — `manifest.csv` → `manifest.xlsx`

Vietnamese in the manifest arrived in Excel as mojibake — `Huỳnh Quốc Trọng` as
`Huá»³nh Quá»‘c Trá»ng`. Nothing was wrong with the file: ZIP entries were written UTF-8,
but Excel opens a `.csv` in the machine's ANSI codepage unless the bytes start with a BOM,
and on a Vietnamese Windows that is CP1258. A BOM would have fixed this instance; `.xlsx`
is proof against the whole class, since the encoding is declared inside the format rather
than guessed at by the reader. Bold header row, frozen top row, and column widths sized to
the longest value — Vietnamese names are long, and a column of `#####` is its own kind of
unreadable. `openpyxl` was already a dependency (the plan importer reads `.xlsx`).

**The two pickers store different things, deliberately.** `HinhThungTrong` puts its label
in a *filename*, so it stores the human name — `Huỳnh Quốc Trọng` → `HuynhQuocTrong_…jpg`.
`HinhNhanHang` puts its label in a *folder* that has to match the same driver's
`HinhGiaoHang` folder exactly, so it stores the already-built folder name
(`HuynhQuocTrong_79791`). Deriving one from the other at export time is ambiguous the
moment a driver runs two trucks: two folders, one name.

Every `loading` row written before today has a blank label. Those land in
`KhongRoTaiXe/` rather than being dropped — historical dates still export.

### Removed — geofence auto-advance of `vehicle_trips.phase`

`do_refresh_route_data()` advanced a trip's phase, and completed it, whenever TTAS put the
truck inside its current target's fence. **Deleted at the operator's request**: phase is a
dispatcher decision, and a refresh that moved it on its own meant the board disagreed with
the person responsible for it. `/api/advance-trip` and `/api/cancel-trip` are now the only
writers of `phase`. The `geofence_events` table stays — it holds real history — but
nothing writes to it any more.

Everything else the refresher does is unchanged: vehicle positions, status, driver names
and the route geometry drawn to the current phase's target are still rebuilt on every
call. They read `phase`; they no longer write it.

`is_point_in_location` is now unused in `app/routes/trips.py` and dropped from its imports.
It remains in `app/utils/geo.py`.

### Fixed — the Phase line reset to "N/A" on every page refresh

The report that started the above, and a different bug underneath it. `/api/route-data`
returns `state.route_data_cache`, which is process memory, and **under Gunicorn nothing
filled it**:

- `start_route_refresh_thread()` is gated behind `if __name__ == "__main__"` in `app.py`,
  so it runs under `python app.py` and never in production;
- nothing in `static/js/` posts `/api/refresh-routes` — `app.py`'s own comment names an
  external scheduler as the intended trigger, and none was ever set up.

So the cache was written only by advance/cancel-trip and was empty after every restart.
`map.js` paints route data from `localStorage` first and then overwrites it with this
endpoint's response, which is why the symptom was the Phase line *resetting* rather than
simply being absent. Geofence auto-advance had not been running in production either,
for the same reason — worth knowing, because it means deleting it above changed nothing
about what production actually did.

`/api/route-data` now rebuilds on demand when the cache is empty or older than
`ROUTE_REFRESH_INTERVAL`, behind `state.route_refresh_lock` so concurrent readers wait for
one rebuild instead of each starting their own. Two new timestamps in `app/state.py`:
`route_cache_refreshed_at`, and `route_refresh_attempted_at` — the second because an empty
cache reads as stale forever, so without it a TTAS outage would have every single request
start its own doomed refresh and block on it.

A refresh is one TTAS call plus one ORS call per active trip, inside a GET, on a single
synchronous worker. That is the cost of this approach and it is a real one; the
alternatives are starting the thread in `create_app()` or an external cron, both of which
`docs/CONCURRENCY_PLAN_2026-08-06.md` is the right place to read before revisiting.

### Tests

- `tests/test_trips_geofence.py` rewritten: 7 → 14. The five auto-advance tests are gone,
  replaced by `TestPhaseIsNeverWritten` — five cases that put a truck squarely inside its
  target's fence and assert nothing moved. All five fail against the pre-deletion code
  (mutation-checked). `TestLazyRouteRefresh` adds five for the endpoint, including that a
  failing refresh still answers 200 and is not retried on every request.
  The per-trip isolation tests are kept but had to change how they induce a failure: the
  old trigger was a malformed waypoint raising inside the geofence block, which no longer
  exists, so they now wrap `sqlite3.connect` in a proxy that raises on one chosen trip's
  UPDATE. `sqlite3.Cursor` is a C type and cannot be monkeypatched, hence the wrapper.
- `tests/test_delivery_routes.py` 135 → 143: `test_loading_photos_land_in_one_flat_folder`
  replaced by four covering the driver-first nesting and the blank-label fallback
  (`KhongRoTaiXe/`), three for the empty folders — including that the MS-DOS directory
  flag is set — and three for the manifest, one of which round-trips
  `Huỳnh Quốc Trọng` through the workbook.
- `tests/js/export.test.js` is new — 10 jsdom drives of the export page. See README for
  the `DOMContentLoaded` trap it documents.
- Full suite 676 pytest + 163 node, all passing. Both changes mutation-checked: disabling
  `add_dir` and reverting the manifest to CSV bytes fails exactly the seven tests written
  for them.

## 2026-08-09 — Dispatch plans import directly from the operator's Google Sheet

> **Uncommitted at the time of writing.** This entry documents the working tree, not
> `HEAD`.

### Added — one-button import of the next day's plan

The next day's dispatch plan is filled in by hand in the manager's Google Sheet ("Kế hoạch
Giao hàng Huwei", one tab per month: `TH07`, `TH08`, …). Until now it reached this system
by being exported to `.xlsx` and uploaded through the existing import pipeline. The plan
builder (`/delivery/new`) now has an **Import from Google Sheet** panel: pick a dispatch
date (defaults to tomorrow), click *Read sheet*, review what would be written, click
*Create plan*.

The read is two-step by design, not by accident. The sheet is hand-typed prose maintained
outside this system, and its defects have to be visible before the plan goes live rather
than discovered on the dashboard at 6am.

**The sheet is never written to.** It belongs to the operator's manager, is shared
link-editable, and this system only ever GETs Google's `gviz/tq` query endpoint, which has
no write path. There is no credential involved either — a service account cannot be added
to a document we do not own, which is why this does not reuse
`services/google_sheet_service.py`'s auth (that sheet is ours; this one is not).

New module `services/delivery/sheet_import_service.py` does fetch → parse → warn, and
emits rows in the shape `plan_service.preview_import` / `confirm_import` already consume,
so the Excel path is untouched. Two endpoints on `delivery_bp`:
`GET /api/plans/import/sheet/preview` and `POST /api/plans/import/sheet/commit`.

### What the sheet actually contains, and why the parser is shaped this way

Every item below was observed in the live document on 2026-08-09, not anticipated:

- **The date column is text.** `21-Jul`, `2-Aug` (no leading zero), `10-Aug`, and one
  `01-th8` — a Vietnamese *tháng 8* slip. None carry a year.
- **Continuation rows leave the date blank** and belong to the day above, so the date is
  forward-filled before any date match. Two rows in `TH08` are like this.
- **The coordinate columns are text in three incompatible formats**, sometimes within one
  day: `9,636058` (comma decimal), `9.60967` (clean), and `9.585.868` / `1.059.744` —
  where a thousands separator has *replaced* the decimal point. All of 10-Aug's rows are
  the third kind. A bare `float()` either raises or silently returns 1.06 for a longitude
  that should be 105.9744, which reads as real data on the dashboard.
- **Only the first row of a vehicle block carries the plate, driver and vehicle type.**
- **Plates are written inconsistently** — `50H 19793`, `50H-197.93` and `51D08660` all
  appear, sometimes for one truck.
- **Driver names carry typos** (`TRẦN` vs `TRẬN`) and one row holds a note where the name
  should be.

Coordinates are therefore repaired by reducing the cell to its digits and asking which
single decimal placement lands inside Vietnam (lat 8–24, lng 102–110). Those windows do
not overlap, so within a column the placement is provably unique — asserted directly in
`tests/test_sheet_import.py`, not left implicit. **A cell that cannot be placed inside the
window is never guessed at:** the stop is imported with empty coordinates and a warning
saying it will have no map marker or ETA until someone fills it in. A half-valid pair
(good latitude, junk longitude) drops both, because keeping one puts the stop on the prime
meridian, where it looks like real data.

Years are inferred from the requested date by choosing the nearest of the reference year
and its neighbours — and then **validated**: a reading landing more than 120 days from the
requested date still parses but is reported, because a year-less cell four months away is
more likely a typo than a plan. 120 is deliberately narrower than the 183 days at which
every month/day would trivially qualify, and wider than the ~1 month a tab spans.

Plate resolution is unchanged — it goes through `services/vehicle_identity.py`, which
matches on the 5-digit serial. Note this means the sheet's `50H-197.93` resolves to the
fleet's `50E-19793`: the serial matches, the prefix does not. That was the operator's
explicit choice; the preview shows both forms so a genuine plate error stays visible.

Driver names go to `vehicle_assignments.driver_name_override` and **never create `drivers`
rows** — the same rule `UnknownVehicles` enforces for vehicles. `confirm_import` gained
this one field; the Excel importer does not set `driver_name`, so its behaviour is
unchanged and `DRIVER_NAME_SQL` still falls back to `drivers.name`.

### Guarded — re-importing a date cannot silently destroy delivery progress

Re-running the import replaces that date's plan, which cascades to its stops and their
`stop_executions`. For a plan a driver has already started, that would delete the record
of what was delivered. `plan_service.plans_for_date` reports how many stops have left
`planned`; commit refuses with **409 `in_progress`** and writes nothing unless
`override_in_progress` is sent, and the preview surfaces the same fact *before* the
dispatcher commits. Replacing a plan nobody has touched needs no override.

An unresolvable plate also aborts (**409 `unknown_vehicles`**) and the empty plan shell is
rolled back — without that, the previous plan would be deleted and replaced by nothing.

### Two failure modes that are easy to get wrong, and are now tested

- **A layout change is not an empty day.** If the manager inserts or reorders a column,
  every mapping in this importer silently shifts and coordinates start coming out of the
  address column. `validate_layout` anchors nine columns by header text and refuses the
  import (**502 `layout_changed`**), which is deliberately distinct from "the sheet isn't
  filled in yet" (**404 `date_not_found`**) because the two demand opposite responses.
- **A network outage is not an empty day either.** The tab search tolerates a month tab
  that does not exist yet (normal on the 1st), and the first version of that loop caught
  `SheetFetchError` to do it — which reported "no plan for that date" whenever Google was
  unreachable, pointing the dispatcher at a sheet that was fine. `SheetTabMissing` now
  splits the two; a real outage propagates as **502 `fetch_failed`**. The route suite
  caught this, not review.

### Tests

`pytest tests/` is now **661** (was 556).

- `tests/test_sheet_import.py` (79) — parser, against
  `tests/fixtures/huwei_plan_th08.json`, a `gviz` payload built from real `TH08` rows
  including every defect listed above. No network.
- `tests/test_sheet_import_routes.py` (26) — the endpoints: the tomorrow default, each
  sheet failure's status, the replace refusal and its override, the unknown-plate
  rollback, and that repaired coordinates and the driver override actually reach SQLite.
- `tests/js/sheet-import.test.js` (16) — jsdom drives the real button through the real
  template: read-then-commit, the override appearing only for `in_progress`, the commit
  button disabled on an unknown plate, and sheet text escaped before it reaches the DOM.

Every safeguard above was mutation-checked — bounding-box guard, year-inference
validation, half-coordinate drop, escaping, and the `in_progress`-only override each
reverted in turn to confirm the tests fail without them.

Two bugs were found by these tests rather than by inspection: `_strip_accents` did not
fold `Đ` (a distinct Vietnamese letter, not a base plus a combining mark, so NFD leaves it
alone), which made the `ĐỊA CHỈ GIAO HÀNG` header check fail; and the outage-vs-empty-day
conflation described above.

> **Not verified end to end.** Every layer is tested against fixtures, but the live HTTP
> call to `docs.google.com` has not been exercised — it was developed in a sandbox with no
> route to Google. Run `python app.py`, open `/delivery/new` and click *Read sheet* once
> before relying on it.

`HUWEI_PLAN_SHEET_ID`, `HUWEI_PLAN_TAB_PREFIX` and `HUWEI_PLAN_FETCH_TIMEOUT` override the
defaults via environment variable, following `google_sheet_service.py`'s pattern rather
than `app/config.py` — the parser must stay importable without a `.env`.

## 2026-08-07 — Production served no core routes: app.py's handlers extracted to a blueprint

> **Uncommitted at the time of writing.** This entry documents the working tree, not
> `HEAD`.

### Fixed — `gunicorn wsgi:app` 404'd on `/` and 13 other routes

The deployed service returned 404 for `/`, `/locations`, all four `/delivery/*` pages,
`/api/vehicles`, `/api/geocode` and the whole manual-location CRUD, while every blueprint
route answered 200 and `python app.py` worked correctly in development.

The cause was structural. `app.py` called `create_app()` and then registered ~15 routes on
the returned object with `@app.route`. `wsgi.py` — the Gunicorn target, and the only thing
production runs — calls `create_app()` and returns. Python never executes `app.py` on that
path, so those decorators never ran. Dev and prod were serving two different applications.

`wsgi.py` was introduced (2026-07-29) to solve the `app.py`-vs-`app/` name collision, and
it does solve it; what it could not do was pick up routes attached to the app *after* the
factory returned. The comment at the end of `create_app()` recorded the arrangement as
intentional ("registered by app.py itself"), which is presumably why it survived — it read
as a documented split rather than a production gap.

Fix: the handlers moved verbatim into `app/routes/core.py` as a `core` Blueprint,
registered inside `create_app()` alongside the other six. `app.py` is now a dev runner
that defines no routes; its only remaining difference from `wsgi.py` is
`start_route_refresh_thread()` under `if __name__ == "__main__"`, which stays
dev-only for the reasons already documented there. `wsgi.py` is unchanged.

This completes the `docs/CODEBASE_ANALYSIS_REPORT.md` §6.4.1 extraction, which had left
these routes as the last un-extracted group.

**Endpoint names changed** from `index` to `core.index`, and so on for all 14. Nothing in
the repository calls `url_for` — templates use hardcoded paths — so no call site needed
updating. Worth knowing before adding one.

The `/delivery/*` routes here render templates only. The delivery **API** stays in
`services/delivery/routes.py` under its `/api` prefix; the split is unchanged.

### Added — `tests/test_wsgi_routes.py` (8)

No existing test could see this bug: every route suite builds its client from
`create_app()`, so all 548 shared the blind spot precisely. The new file pins the 14 routes
by rule and endpoint, smoke-tests the six page routes for 200, and — the general guard —
loads `app.py` by file path and diffs its URL map against `create_app()`, so the *next*
`@app.route` added to `app.py` fails a test instead of going missing in production. Suite
total is now 556.

Mutation-checked: with `register_blueprint(core_bp)` removed and a probe route added to
`app.py`, all 8 fail; restored, all 8 pass.

### Still open — Render is not applying `render.yaml`

Separate from the above, and not fixed here. The deploy logs show `gunicorn app:app` and
Python 3.14, against a `render.yaml` specifying `gunicorn wsgi:app` and 3.12, so the
service was created manually in the dashboard rather than as a Blueprint and the YAML is
ignored in full. That includes the `fleetfuel-data` disk and `DB_PATH`, so
`routing_system.db` is being recreated empty on ephemeral storage at every boot —
`/api/fleet/vehicles` returned `{"data": []}` against a fleet of 36. Operator action:
create the service from the Blueprint, or replicate the disk and env vars by hand.

## 2026-08-06 — Audit fixes: TLP shipment arrange, geofence transactions, TLP escaping

> **Uncommitted at the time of writing.** This entry documents the working tree, not
> `HEAD`.

Findings and reproduction are in `docs/AUDIT_2026-08-06.md`; the phased plan they were
fixed under is `docs/BUGFIX_PLAN_2026-08-06.md`. Every fix below was mutation-checked —
the fix reverted, the new tests confirmed failing, the fix restored.

### Fixed — `POST /api/tlp/auto-arrange` with a `shipment_id` returned 500

`_get_packages_from_request` selected `p.name AS package_name` and then handed the row to
`LegacyPackage.from_row`, which reads `row["name"]`. `tlp_shipment_items` has no `name`
column, so the key did not exist and the handler — which has no try/except — answered an
unhandled 500. This was not an API-only corner: `truck-load-planner.js:1403` sends
`shipment_id` whenever a shipment is selected, so "select a shipment → Auto Arrange" was
dead. It went unnoticed because the table currently holds zero shipment items.

A second defect sat behind the first. `si.*` put the **shipment item's** id in
`row["id"]`, so once the `KeyError` was fixed every placement would have carried the
wrong `package_id` — a loud crash traded for silent bad data. Both are fixed together by
replacing `si.*` with an explicit aliased column list:

```sql
SELECT si.quantity AS quantity, si.package_id AS package_id,
       p.id AS id, p.name AS name, ...
```

`Package.from_row` is deliberately **not** changed. Its other caller
(`validate_placement`) passes a genuine `tlp_packages` row and is correct today;
loosening it to tolerate aliases would make it lie about its contract for both callers to
accommodate one bad query.

An item whose package no longer exists is now skipped with a `logger.warning` rather than
arranged. The `LEFT JOIN` is kept so the row still surfaces — without the guard,
`from_row` builds a package with a null name and 0mm sides and the planner packs it
happily, i.e. an invisible box in the load plan.

### Fixed — the background trip refresher's geofence advance never ran past the first trip

`app/routes/trips.py` opened an explicit `conn.execute('BEGIN')` inside its per-trip loop.
That cannot work, in two independent ways:

1. Python's `sqlite3` opens a transaction implicitly before the driver-name `UPDATE`
   immediately above it, so the explicit `BEGIN` raised
   `cannot start a transaction within a transaction`;
2. on the normal path — vehicle not yet at its stop — neither `commit()` branch ran, so
   the transaction stayed open and the *next* iteration's `BEGIN` raised the same error.

The per-trip `except` printed and moved on, so there was no error anybody saw. The symptom
was trips that quietly stopped advancing phase and never auto-completed.

The `BEGIN` is removed and each iteration now ends in exactly one `commit()` or
`rollback()`, with the driver-name `UPDATE` moved inside that transaction so it rolls back
with the rest. This matches what every other write path in the file (`api_advance_trip`,
`api_cancel_trip`) already did; the explicit `BEGIN` was the outlier.

**This also closes a `database is locked` window.** The uncommitted driver-name write held
a `RESERVED` lock from the top of the loop until the first commit in the *second* half of
the function — which is after N serial `get_route_coords()` calls to OpenRouteService. A
write lock was held across those network round trips on every refresh cycle. Note this is
independent of the WAL / `--workers` decision, which is untouched.

### Fixed — `static/js/truck-load-planner.js` had no HTML escaping at all

The 2026-07-29 refactor moved every page onto `UI.escapeHtml()`. This file was missed: as
of the audit it had **zero** calls, against 28 in `delivery-plan-builder.js` and 27 in
`map.js` — while interpolating package names, customer names, plate numbers, container
names and driver names straight into `innerHTML`. `utils.js` was already loaded by the
template, so the function was there and simply never used.

Thirteen interpolations across seven sites are now escaped, with `||` defaults inside the
call so a `null` never reaches `escapeHtml`. Numeric and boolean interpolations are left
alone. With no authentication on any endpoint (deliberate, see `CLAUDE.md`), anything that
could reach the network could persist a payload via a package name and have it execute in
every dispatcher's browser on the TLP page.

### Fixed — 22 write handlers leaked their connection on the exception path

`fleet.py`, `fuel.py`, `oil.py` and `trips.py` all followed `conn = sqlite3.connect(...)`
… `conn.close()` … `except: return 500`, so an exception skipped the close. On a write
path an uncommitted connection holds a `RESERVED` lock until garbage collection — the same
failure mode as the geofence bug, one size down. All 22 now close in a `finally`.

Read-only handlers are deliberately unchanged (operator's scope call): there the cost is a
standards violation, not a lock. Raw `sqlite3.connect()` stays — the DB-access-pattern
split is deliberate and was not migrated.

### Changed — `GET /api/fuel-log` opened 1,900 connections per request

`api_fuel_log_list` called four helpers per row, each opening its own connection (two of
them opening a second). Measured against the live database: **1,900 connections and 591 ms
for 323 rows**, all serialised behind `render.yaml`'s single synchronous worker.

The helpers now take an optional `conn`, and the two loops (`list` and `export`) pass
their open connection down. Same request: **1 connection, 31 ms** — 19× faster, with a
payload proven byte-identical by `test_response_is_unchanged_by_connection_reuse`. The
parameter is optional so the create/update handlers, which compute a single entry, are
untouched.

### Fixed — `DELETE /api/tlp/packages/<id>` left orphaned rows

It deleted only `tlp_packages`, while the sibling `clear_all_packages` also clears
`tlp_placements` and `tlp_shipment_items`. This schema runs `enable_fk=False` with no
`ON DELETE CASCADE` (both deliberate), so nothing else caught it. The children are now
removed first, which also means the `rowcount` deciding the 404 is the package row's own.

### Added — three test files, covering three modules that had none

| File | Tests | Module |
|---|---|---|
| `tests/test_tlp_routes.py` | 8 | first route-layer coverage for the Truck Load Planner |
| `tests/test_trips_geofence.py` | 7 | first coverage of any kind for `app/routes/trips.py` |
| `tests/test_write_handler_connections.py` | 36 | write handlers across all four route modules |
| `tests/test_fuel_routes.py` | 6 | first route-layer coverage for `app/routes/fuel.py` |
| `tests/js/tlp-escaping.test.js` | 5 | dependency-free, no jsdom needed |

`test_all.py` is a script (zero `def test_`) and `test_scorer.py` / `test_auto_arrange_e2e.py`
drive the planner directly, so nothing could see a bug inside a TLP request handler — which
is exactly where this one lived. Same lesson `tests/test_delivery_routes.py` records for the
delivery module.

### Measured — WAL and `--workers`, and a correction to two documents

`CLAUDE.md` carried this as one open decision: "adding workers without enabling WAL first
trades that latency for lock errors; treat the pair as one decision." Measured against a
copy of the live database, that is wrong in a way that matters:

- **A held write lock does not block readers.** Four readers arriving during a 7-second
  write hold all completed in under 5 ms, in both journal modes.
- **`database is locked` is writer-vs-writer, and WAL does not fix it.** SQLite serialises
  writers either way. It fires when a write is held past the busy timeout — which is
  Python's 5-second default, set by accident rather than decision.
- So the fix for the lock errors was **the geofence transaction fix above**, not WAL. The
  hold went from N serial ORS round trips to one loop iteration.
- WAL is still worth enabling, on throughput grounds: 2.3× read throughput, read p95
  81 ms → 29.5 ms, write p50 24 ms → 0.8 ms. `journal_mode` persists in the database file,
  so it is one line in `init_db()`.
- The real blocker on `--workers` is not the database: `app/state.py` is process-global, so
  a second worker means two route caches, two TTAS sessions, and `state.sync_lock` /
  `state.oil_fetch_lock` silently ceasing to be mutual exclusion.

Written up in `docs/CONCURRENCY_PLAN_2026-08-06.md`. **Recommendation only — nothing in
`render.yaml`, `app/db.py` or `app/database/` was changed.** The corresponding claims in
`docs/AUDIT_2026-08-06.md` §2 and `docs/DELIVERY_AUDIT_2026-07-31.md` D-09 were corrected
in place with dated notes rather than edited away.

### Documentation

`services/plate_utils.py`'s docstring claimed the 5-digit serial was "globally unique". It
is not — it carries no province code, so `50H-09473` and `51C-09473` collapse to the same
key. No behaviour change: `VehicleIndex._ambiguous_serials` and `_gps_by_plate_key` already
handle collisions, and the fleet has none today (36 vehicles, verified). The docstring now
says so and names both guards.

A documentation pass brought the rest of the reference set in line:

| Document | Change |
|---|---|
| `README.md` | test counts 491 → 548, new Route-layer Tests section, frontend drives 132 → 137, TLP 31 → 39, playwright note corrected, `test_all.py` flagged as a script |
| `CLAUDE.md` | concurrency entry rewritten around the measurements; `render.yaml` disk claim corrected; playwright claim corrected; graph counts refreshed; new docs added to Reference Documents |
| `docs/TRUCK_LOAD_PLANNER.md` | §15 documents both auto-arrange payload shapes and the `shipment_id` fix; §14 gains a "delete semantics — the cascade is manual" table; §11 gains the escaping rule |
| `docs/CODEBASE_ANALYSIS_REPORT.md` | addendum 2026-08-06b; items 23 and 27 corrected (WAL premise; no live SQL injection) |
| `docs/DELIVERY_AUDIT_2026-07-31.md` | **D-10 closed** — the Render persistent disk exists, so the "verify this first" Critical is discharged; D-09's reasoning corrected |
| `docs/DELIVERY_MODULE.md` | test count |

**`docs/DELIVERY_AUDIT_2026-07-31.md` D-10 deserves its own line.** It was the audit's only
"verify this first" Critical — if no disk were attached, `routing_system.db` and every
proof-of-delivery photo would be destroyed on each redeploy. A disk **is** attached
(20 GB at `/var/data`, with `DB_PATH` and `DATA_DIR` pointed at it). Both `CLAUDE.md` and
that audit had said otherwise for as long as the disk has existed.

### Removed — stale generated docs, and ~20 MB of graphify artifacts out of git

| Removed | Why |
|---|---|
| `project_tree.txt` | 274 KB, UTF-16, generated 2026-07-30 by `tree` **without** `/F` — so it lists directories and no filenames at all. 3,225 of its 3,685 lines are directory names, 453 of them graphify cache folders. Nothing referenced it. |
| `INSTRUCTIONS.md` | The prompt that commissioned the delivery audit ("Perform a complete architectural investigation… Do not modify any files"). That audit shipped as `docs/DELIVERY_AUDIT_2026-07-31.md`; the brief has been spent since. |
| `reports/*.txt` | Four benchmark/diagnostic outputs from 2026-07-29. `tests/test_all.py` regenerates them and creates the directory itself (`os.makedirs(exist_ok=True)`), so both the files and the tracking were disposable. |

**Untracked but kept on disk:** `graphify-out/cache/` (~9 MB AST extraction cache, rebuilt
by `graphify update .`) and the rotating dated backup directories (~2-3 MB each, four of
them). Together roughly **20 MB of generated artifacts that were tracked in git**.
`graph.json`, `graph.html` and `GRAPH_REPORT.md` stay tracked — they are what the standing
"query the graph before grepping" instruction actually reads. `.gitignore` gained rules for
all of it, plus `node_modules/`.

**Kept deliberately.** `graphify-cli-reference.txt` looks like a candidate at 25 KB, but
`CLAUDE.md` records that graphify has no per-subcommand `--help` and that asking for one
returns real-looking noise — so a full CLI dump is load-bearing. The two Vietnamese report
files at the repo root are unrelated to the app, which is not the same as redundant.

## 2026-08-06 — A confirmed plan is editable, and reachable from the board

> **Uncommitted at the time of writing.** This entry documents the working tree, not
> `HEAD`. The changes live in `static/js/delivery-plan-builder.js` and
> `static/js/dashboard/main.js` and have not been committed.

Confirming a plan used to be a one-way door. `loadExistingPlan()` set
`state.readOnly = plan.status === 'confirmed'`, which raised the read-only banner and
called `stopAutoSave()`; step 4 then hid both **Save draft** and **Confirm**. A
dispatcher who confirmed a plan and then needed to fix a stop had no route back into it
from the UI at all.

### Changed — `readOnly` is no longer derived from `confirmed`

```js
state.readOnly = false;
state._confirmedStatus = plan.status === 'confirmed';
```

The banner is explicitly hidden, autosave keeps running, and step 4 shows its buttons
whatever the status. `_confirmedStatus` carries the fact that used to be conflated with
editability, and is now used for two narrower things:

- **Saving no longer demotes the plan to `draft`.** `saveDraft()` set
  `state.planInfo.status = 'draft'` unconditionally — harmless while confirmed plans
  could not be saved, and a silent status regression the moment they can. Only a plan
  with no backend record yet starts as a draft.
- **The toast reads "Changes saved" rather than "Draft saved successfully"** when
  editing a confirmed plan, because the latter would now be a lie about what happened.

### Added — plan names in the dashboard's Plans panel link to the editor

`main.js` renders each plan name as `<a href="/delivery/edit/${p.id}">` instead of a
`<span>`. The route already existed; nothing on the board pointed at it. The anchor sits
inside the `<label>` that wraps the selection checkbox, so a click on the name navigates
while a click anywhere else in the row still toggles selection.

### The design decision this reverses

`docs/DELIVERY_MODULE.md` § Key Design Decisions #1 read *"Plan tables are immutable
after import — once confirmed, the plan structure cannot be changed"*. That is no longer
true of the builder and the doc has been updated to match. What has **not** changed is
the execution layer: advance / skip / cancel / revert remain the mechanism for what
happens during a run. Editing a confirmed plan rewrites the plan; it does not rewrite
execution history.

`tests/js/plan-builder.test.js` still passes 10/10, including the two cases that assert a
reopened plan keeps its stored driver name across a save.

---

## 2026-08-04 — numpy's version pin removed

`requirements.txt` pinned an exact numpy version; it now reads a bare `numpy`. Render
resolves it against whatever Python it builds with, which is what the pin was fighting.
No code change and no behaviour change — numpy is a transitive convenience here, not
something the packing engine's arithmetic depends on.

---

## 2026-08-03 — A dispatcher can upload a batch of photos, not just one at a time

The proof-of-delivery control was a single `<input type="file" capture="environment">`.
`capture` is the right default on a phone — it opens the camera directly at the stop —
but a browser that honours it opens the camera for **one** shot and ignores `multiple`
entirely. A dispatcher working from a desktop, or from photos already shot into the
gallery, had to repeat the whole select-upload-wait cycle per photo.

### Added — two inputs, one handler

`capture` and `multiple` cannot be combined, so collapsing to one input would have meant
choosing which workflow to make worse. Both now exist in the stop row:

| Control | Input | Path |
|---|---|---|
| 📸 **Take photo** | `capture=environment`, single | The phone path, unchanged |
| 📁 **Add photos** | `multiple`, no capture | Gallery or desktop batch |

Neither costs the other a tap, which matters for something pressed at every stop of
every run.

### The batch decisions, and why

- **Sequential, not `Promise.all`.** Production is a single synchronous Gunicorn worker
  (see `render.yaml`), so firing ten uploads at once queues them anyway *and* starves
  every other dashboard request while they wait. Same reasoning as `delivery-export.js`.
- **One bad file does not abandon the batch.** Each upload is caught individually and
  collected into a `failures` list; the dispatcher gets `"3 saved, 1 failed"` rather
  than a partial upload with no way to tell which of ten photos landed.
- **The category is read once, up front.** The dropdown is live during the upload, and
  every file in one selection belongs to the category that was showing when it was
  picked.
- **Both inputs are disabled for the whole batch**, not just the one that fired — they
  share a status line, and a second batch started mid-flight would interleave its
  progress counts into it. CSS follows with `.timeline-upload-btn:has(input:disabled)`,
  because a disabled control silently swallows activation forwarded from its label: the
  untouched button would otherwise look available and do nothing.
- **The gallery refetches once per batch, not per file.** A ten-photo selection should
  not fire ten refetches of the panel directly below the button.

Covered by the dashboard jsdom suite, now 122 drives.

---

## 2026-08-03 — A truck TTAS says it has lost is now in the No GPS list

Operator report, following the speed fix below: a vehicle that had lost GPS
for nearly seven hours raised a "GPS stale 6h 48m" chip but did not appear
under the dashboard's **No GPS** filter — the one list a dispatcher opens to
find the trucks they cannot see.

### Fixed — the filter tested for a position, not for reachability

```js
if (f.quick === 'nogps' && a.gps && a.gps.last_update) return false;
```

That keeps only vehicles with **no position at all** — a plate TTAS returned
no row for, usually a mismatch in `vehicles` or a device missing from the
account. A vehicle TTAS reports as lost still carries the last fix taken
before the signal dropped, so it passed the "has a position" test and fell
straight through.

### Added — `MTH` is read as a state, not left as "unknown"

TTAS writes `MTH:6h48'` — *mất tín hiệu*, and how long for. `is_lost_signal()`
in `ttas_client` recognises it (plus the unabbreviated form and the spacing
and case variants — this string is scraped, not contracted), giving a fourth
`vehicle_status`, **`lost_signal`**, alongside running / stopped / unknown.
`tracking_service` surfaces it as `signal_lost`, and the filter keys off that.

**Declaration, not inference — chosen over widening the filter to a staleness
threshold.** Both were on the table. TTAS stating the device is unreachable is
a stronger fact than an old timestamp, and the two genuinely disagree: a
tracker reporting late is not a tracker that is gone. Reusing the 15-minute
stale threshold would have swept up every truck between reports.

Deliberately unchanged as a result:

- **The `gps_stale` chip still fires, with its computed duration.** It is
  derived from `last_update_iso` and never reads the phrase, which is why it
  independently agreed at 6h48 — the corroboration that identified this. Two
  independent paths to the same number are worth keeping.
- **The marker stays on the map.** Where a truck was last seen is the most
  useful thing left about it. Only the filter treats it as unseen.
- **The chip keeps the label "No GPS"** (operator's call) — dispatchers know
  where it is and what they use it for.

Note `MTH:6h48'` would have reported **6 km/h** under the pre-today speed
parse: the same first-number-wins bug as the entry below, third variant.
Already fixed there, and now pinned by a test naming this phrase.

### Verification

`pytest tests/` **491** (474 before). jsdom **112/112** (108 before).

Mutation-checked both halves: restoring the old filter condition fails the
two new jsdom cases, and the parked-duration mutation still fails 8 Python
cases.

## 2026-08-03 — A parked truck's speed was its parking time

Operator report: a vehicle standing still on TTAS was showing a non-zero
speed on the dispatch dashboard.

### Fixed — the number came out of the wrong part of the phrase

TTAS's DevList carries **no numeric speed field**. It sends a Vietnamese
status phrase, and every km/h figure the dashboard has ever shown is an
extraction from that prose. `normalize_vehicle` only inspects whether the
phrase *starts with* `Chạy` or `Dừng`; `_parse_speed_kmh` then took the first
number anywhere in the string.

For a moving vehicle that number is the speed — `"Chạy 42km/h"` → 42. For a
parked one the phrase counts **how long it has been parked**:

| TTAS phrase | Meaning | Dashboard showed |
|---|---|---|
| `Dừng 3h30'` | stopped 3 h 30 min | 3 km/h |
| `Dừng 6h4'` | stopped 6 h 4 min | 6 km/h |
| `Dừng 7h44'` | stopped 7 h 44 min | 7 km/h |

So the reported speed climbed the longer the truck sat still, and the same
payload simultaneously reported `vehicle_status: stopped_engine_off` — the
internal contradiction that identified it.

The number is now taken only when it **carries the km/h unit**. A `Dừng`
phrase reads as a genuine `0.0`, and durations are stripped before the
unitless fallback so a time can never be picked up as a speed.

**`None` still means "no reading", but `Dừng` is no longer one of them.** TTAS
saying the vehicle is stopped is knowledge, not the absence of it, and the
dashboard renders `None` as a blank rather than as a speed. The None-vs-0
distinction the module was built around is intact — it now separates *stopped*
from *uninterpretable* (`"Mất tín hiệu"`, `"---"`) instead of separating
`Chạy 0km/h` from everything else.

### Changed — the `reported_stopped` chip now fires when it should

`vehicle-list.js` flags a vehicle reporting ≤2 km/h while not parked at a
stop. Against the old parse this was effectively random: it fired for a truck
stopped `1h30'` (→ 1 km/h) and stayed silent for one stopped `3h30'` (→ 3
km/h). It now fires for genuinely stopped vehicles, so **expect more of these
chips than before** — that is the proxy finally working, not a new fault. The
`MAX_ATTENTION_CHIPS` overflow already handles a fleet parked overnight.

### Not fixed — the same bug survives in `app/routes/trips.py`

`trips.py:401-408` runs the identical first-number-wins regex into
`current_speed`, and `_parse_speed_kmh`'s docstring used to point at it as the
pattern to mirror. Left alone deliberately (scope), and recorded here so the
next person finds it: it feeds the fleet map rather than dispatch, and its two
trip pages were deleted 2026-07-31, so who still consumes it wants checking
before it is touched.

### Verification

`pytest tests/` **474** (460 before). The speed cases also moved out of
`TestTtasTimestampParsing` — which is about day-first dates — into
`TestSpeedPhraseParsing`, where a reader looking for this bug would go.

Mutation-checked: restoring first-number-wins fails 8 of the 18, including
every one of the operator's real phrases.

## 2026-08-02 — The driver named in a plan is the driver dispatch shows

Operator report: the plan builder prefills a driver when you pick a vehicle,
you can type over it, and the dispatch page then ignores what you typed and
shows the vehicle's usual driver anyway. Drivers swap trucks, so the page was
naming the wrong man.

### Fixed — the typed name never left the browser

Three things had to line up, and none of them did:

- `vehicle_assignments` could only store a **`driver_id`** into `drivers`.
- Almost nobody has a `drivers` row. `plan_service.list_drivers` synthesises
  the rest from `DISTINCT vehicles.current_driver` with **`id: None`**, so the
  autocomplete happily offers names that cannot be stored as an id — and the
  prefill path takes exactly those. `driver_id` was therefore usually NULL.
- `delivery-plan-builder.js` captured the name in `_driverName`, rendered it,
  and then omitted it from the `POST /api/assignments` body 600 lines later.

So the name was correct on screen at every step and simply never persisted.
Every reader then fell through to `v.current_driver`.

`vehicle_assignments.driver_name_override` (free text) now holds it, and the
builder sends it. Precedence everywhere the plan is read is
**typed name → linked `drivers` row → vehicle default**, expressed once as
`plan_service.DRIVER_NAME_SQL` for the plan-facing queries and inline in
`execution_service.get_dashboard_data` and `export_service.day_summary`, whose
fallback chains differ. The typed name outranks a linked record deliberately:
both being set means the dispatcher edited a prefilled value, and the edit is
the newer intent.

**A typed name does not create a `drivers` row** — explicitly asked for, and
tested. These are stand-ins for one day; promoting them would grow a roster
nobody maintains, out of what is really a note about that day's work. The
flip side is that the plan keeps a snapshot: reassigning a truck next week
does not rewrite who drove it today, which is the property the look-back case
needs.

The export folder names (`HuynhQuocTrong_79791`) follow the same precedence.
They had to — a handover folder disagreeing with the dashboard about who drove
is worse than either answer alone.

### Note — a new column needs the ALTER, not just the schema

`CREATE TABLE IF NOT EXISTS` is a no-op against an existing database, so
adding a column to `SCHEMA_SQL` alone reaches new databases only and fails at
query time on the deployed one. `database.py` grew `_ADDED_COLUMNS` and an
idempotent `_add_missing_columns()`, run from `init_delivery_tables`. Both
delivery test suites build their schema through that function, so the
migration is exercised on every run rather than only in production.

### Verification

`pytest tests/` **460** (442 before): `test_delivery.py` +13,
`test_delivery_routes.py` +5. The route-layer five are not redundant — the
field was being dropped in the request handler, which the service suite is
structurally blind to.

New **`tests/js/plan-builder.test.js`**, 10 cases, jsdom, the builder's first
frontend coverage. It boots the real IIFE over the real template and drives
the modal through the DOM, because the bug was invisible in any single
function: capture, render and save were each correct in isolation. Mutation
check — removing the one added line from the POST body fails 7 of the 10.

`tests/js/dashboard.test.js` is unchanged at 108, but note that one of its ETA
cases is **time-of-day dependent**. Pre-existing, unrelated to this change, and
worth fixing with an injected clock rather than by rerunning in the morning.

> **Corrected 2026-08-06.** This paragraph originally read *"two of its ETA cases
> ... run after ~23:13 local, a 47-minute ETA crosses midnight"*. Both details were
> wrong, and the diagnosis was written from reading rather than from running. It is
> **one** case — `a route running past midnight is marked, not shown as already
> late` — and it feeds `UI.etaClock()` a **36-hour** ETA, not 47 minutes. `etaClock`
> counts *calendar days crossed*, so from **12:00 local onwards** 36 hours lands two
> dates away and it renders `+2d` where the assertion expects `+1d`. The failure
> window is half the day, not the last 47 minutes of it. Verified by running the
> suite across shifted `TZ` values. The suggested fix — an injectable clock — still
> stands.

## 2026-08-02 — End-of-day export, and a persistent disk

Phase 2 of the proof-of-delivery work, plus the storage fix it depends on.

### Fixed — runtime data was on ephemeral storage

`render.yaml` had no `disk:` block, so everything written at runtime lived on
the container filesystem and was destroyed on every deploy and restart. Two
casualties:

- **`routing_system.db`.** `*.db` is gitignored, so it was never shipped in
  the repo either — `init_db()` simply recreated it empty on each boot.
- **`DeliveryPlans/`**, the proof photos. A rule that completing a stop needs
  a photo is worse than useless if the photo is gone next deploy: it looks
  like it is protecting you.

A 20 GB disk now mounts at `/var/data`, with `DB_PATH` and a new `DATA_DIR`
pointing at it. `DB_PATH` needed no code change — `config.py` joins it onto
`BASE_DIR`, and pathlib makes an absolute value replace the base rather than
append to it.

`image_service.BASE_DIR` became **`DATA_ROOT`**, read from `DATA_DIR` and
defaulting to the repo for local dev. It is deliberately the *parent* of
`DeliveryPlans/`, so `relative_path` values already stored
("DeliveryPlans/2026/…") resolve unchanged. The old name meant "repo root"
everywhere else in the codebase and "root that uploads hang off" here, which
was going to mislead someone.

Sizing is deliberate but not permanent: two photos per stop at 2-4 MB puts a
40-vehicle day near 0.5-1 GB. That is weeks, not years — the export is how
photos are meant to leave, and exported days should be pruned. Also note a
service with a disk cannot run more than one instance and loses zero-downtime
deploys; neither costs anything here, since production is already a single
synchronous worker.

### Added — `delivery_day_images` for photos that belong to a day

The loading shots (taken the evening before) and each driver's
empty-container shot never pass through a stop, so they have no `stop_id` to
hang off. They are handed over during the export itself and live in their own
table.

Uploads are **one file per request**. `MAX_CONTENT_LENGTH` is 25 MB for a
whole request, so a day's loading photos could never have been sent as one
multipart POST — and per-file uploads also mean a failed ZIP download does not
discard everything just handed over.

### Added — `export_service`, rebuilding the operator's folder shape

Files stay where they are written. The ZIP is assembled into the shape that
has always been built by hand:

```
2_8_BacLieuGiaRai_CanThoOMon/
  HinhThungTrong/                empty containers, driver name in the filename
  HinhNhanHang_01_08/            loading photos, flat and unsorted
  HuynhQuocTrong_79791/
    HinhGiaoHang_02_08/
      CTOM19/                    unload + door photos
  manifest.csv
```

Points worth recording:

- **`strip_accents()` maps `đ`/`Đ` by hand.** Every other Vietnamese
  diacritic decomposes under NFD and can be dropped, but `đ` is a distinct
  letter, not d-plus-mark. Missing it is the classic way this produces
  `NguynVn`. Mutation-checked.
- The 5-digit plate serial comes from `normalize_plate`, the same reduction
  the GPS plate matching uses (audit C-03), so the number in the folder is
  the one the rest of the system agrees on.
- The top-level folder name is **typed by the operator** — it carries route
  names that exist nowhere in the data — and is sanitized through the same
  `_safe_path_segment` as every other user-supplied path component. A test
  drives `../../etc` through it.
- Only `unload` and `door` are exported. An `extra` or mistyped category is
  left out rather than silently filed as proof of something.
- `HinhNhanHang` sits at the top level, flat. The operator's original tree
  nested it per driver and per station; sorting at handover was not worth the
  taps, so this follows the instruction rather than the sample.
- A missing file on disk is skipped with a warning instead of aborting. A ZIP
  of everything that survived is more use at 6pm than an error, and the
  manifest still records what was expected.

The manifest lists every stop, its photo counts, what is missing, and any
override reason — the only place a waived completion is recorded.

### Added — the End of Day page

`/delivery/export`: pick the date, review which stops are short of proof
(asked *before* the download, while drivers are still reachable), hand over
the loading and empty-container photos, name the folder, download. A preview
of the resulting tree is rendered as the name is typed.

Uploads run sequentially rather than in parallel: production is a single
synchronous worker, so twenty concurrent uploads would queue anyway while
starving every other request. The download says it is working, because
building the ZIP blocks that worker.

**It does not use `ApiClient`.** That helper prefixes `/api` itself and treats
any response without `success: true` as an error — an envelope the delivery
API has never used. `static/js/dashboard/api.js` already keeps its own
wrapper for this reason; this follows the module's real pattern rather than
bending either contract. Worth knowing before someone "fixes" it.

### Verification

`pytest tests/` **442** (417 before). jsdom **108/108**, unchanged — this
phase adds a page the dashboard suite does not cover.

Mutation-checked, all three caught: dropping the `đ` special case, trusting
the typed folder name instead of sanitizing it, and exporting every photo
category rather than just the two that are proof.

## 2026-08-02 — Completing a stop requires photographic proof

Operator request, phase 1 of two. The end-of-day export is phase 2.

### Added — a stop cannot be completed without proof

`advance_stop()` refuses `arrived → completed` unless the stop carries a
photo in **both** `PROOF_CATEGORIES` — `unload` (goods off the truck) and
`door` (the truck shut afterwards). That pair is what a dispute actually
turns on; either alone leaves half the question open.

Only the final step is gated. Arriving somewhere is not yet a claim about
what happened there, so there is nothing to prove.

Skip and cancel are **not** gated: they already carry a typed reason, and
photographing a delivery that never happened is usually impossible.

**Categories are not whitelisted on upload, deliberately.** The route
sanitizes any category into a safe path segment (audit S-04), and
`test_traversal_in_category_cannot_escape` depends on an unknown category
still being *accepted*. Tightening that would trade a tested security
property for a validation nicety. The consequence falls the safe way: a
mistyped category can never satisfy the gate.

### Added — an override, because a hard block strands drivers

`override_reason` completes a stop without photos, and the reason is written
into the phase history added yesterday. A driver with a dead phone must not
be stuck at a customer's gate, and the realistic alternative to an override
is somebody photographing their own boot to get on with the day.

A blank or whitespace-only reason is not an override. It would record that
proof was waived while saying nothing about why — the one thing that makes
the exception defensible a week later. The event log is the only place this
lives; nothing on `stop_executions` says "completed without proof", and
adding a column for it would duplicate the log.

### Added — the upload control that did not exist

`POST /api/stops/<id>/images` has existed and been tested since the module
was written, but **nothing in the app ever called it** — the dashboard
gallery is read-only. Each stop now has a category selector and an
`accept="image/*" capture="environment"` button, which opens the camera
directly on a phone and degrades to a file picker on a desktop.

It sits in the stop row, not the pinned current-stop card: that card is
re-rendered by replacing its `innerHTML` whenever its content changes, so a
poll landing mid-selection would discard the file input and whatever the
dispatcher had chosen. The row's nodes are stable across polls.

Two details that are invisible until they bite:

- the file input's value is cleared after every attempt, because selecting
  an identical file twice fires no `change` event — a retry after a failure
  would otherwise appear to do nothing;
- uploading invalidates the photo gallery's cache, or the photo just taken
  would be missing from the panel directly below the button that took it.

### Changed — 422, not 400, for a blocked completion

The request was well formed and the stop was exactly where the client
thought; it simply is not allowed yet. The response carries
`proof_required: true` and the list of missing categories, so the dashboard
recognises the case structurally rather than by matching English — and the
blocked Advance opens the reason row inline instead of firing a toast the
dispatcher can only read and dismiss.

`fetchJSON` now attaches `status` and `body` to the Error it throws. Additive:
every existing `catch (err) { err.message }` is untouched.

### Verification

`pytest tests/` **417** (399 before) — `test_delivery.py` 164,
`test_delivery_routes.py` 120. jsdom **108/108**.

Sixteen existing tests advanced a stop to completed and now had to supply
proof. They get a `_give_proof()` helper that inserts image rows directly:
the gate reads `delivery_stop_images`, not the filesystem, and a test that
had to write real .jpg files just to reach 'completed' would be re-testing
the upload path and leaving litter behind. One route test does go through
the real upload endpoint end to end.

Mutation-checked: accepting a whitespace override, and requiring only one of
the two categories, each fail their own tests and nothing else.

## 2026-08-01 — Stop phases are recorded, and corrections last the day

Operator request: phases should be stored and reviewable, not merely
correctable for a moment.

### Added — `stop_status_events`, one row per phase change

`stop_id`, `from_status`, `to_status`, `action` (advance / revert / skip /
cancel), `reason`, `occurred_at`. It lives in `SCHEMA_SQL`, which runs
`CREATE TABLE IF NOT EXISTS` on every boot, so no migration script was
needed.

There is deliberately **no `changed_by`**. The module has no authentication
(see the 2026-07-31 entry), so that column could only ever be blank, and a
blank accountability column implies a guarantee this system cannot make.
Related and worth stating plainly: this is an operational log, not a
tamper-proof audit trail — anyone with database access can edit both a
status and its history.

Every write goes through `_record_status_event()` on the **same connection**
as the UPDATE it describes, and only after that UPDATE reported a rowcount.
A refused or lost transition therefore leaves no event claiming it happened;
there is a test asserting exactly that for a rejected stale advance.

`_update_execution()` gained `_event_action`/`_event_reason` and reads the
prior status on that same connection immediately before the UPDATE, so the
recorded `from_status` is the one actually replaced rather than whatever the
caller believed it to be.

**Nothing was backfilled**, per the operator's call. Stops last touched
before today show an empty log, which is honest; seeding invented history is
the exact failure a history is meant to prevent.

### Changed — revert returns to the *recorded* phase

`_revert_target()` now prefers the logged `from_status` over the static
reverse map. The map is kept as a fallback for stops with no history, where
`skipped`/`cancelled` are still *inferred* from the presence of an
`actual_arrival_at` — not wrong, just unverifiable, which is why the log
exists.

**The subtle part is that reverts are excluded from that lookup.** After
planned → arrived → completed → revert, the newest event landing on
`arrived` is the revert itself, whose `from_status` is `completed`. Reading
it would send the next revert *forward*, turning a second undo into a redo.
`_last_forward_event()` asks "how did this stop legitimately get here", and
an undo is not how. Mutation-checked: dropping the `action != 'revert'`
filter fails only that test.

### Changed — the 15-minute window is now the plan's day

A correction is bookkeeping, and bookkeeping is finished at the end of a
shift, not within a quarter of an hour of the mistake. `can_revert()` now
takes `plan_date` instead of timestamps: a plan dated today or later is live
work and stays correctable; once its date has passed the record is closed.
`REVERT_WINDOW_MINUTES` is gone, and `list_stops` carries `plan_date` so the
answer stays computable from one row.

Two consequences stated in the docstring and worth repeating:

- `today` comes from the **server** clock, almost certainly UTC, while
  `plan_date` is a business date typed on Vietnam time (+7). Corrections
  therefore stay open roughly seven hours into the next local day. That is
  the lenient direction — a night shift can finish its paperwork — and never
  the direction that freezes work still in progress. Setting
  `TZ=Asia/Ho_Chi_Minh` would tighten it, but shifts every *new* timestamp
  seven hours against those already stored, so it belongs in its own change.
- A plan with no readable date is **not** correctable. Unknown reads as
  closed, matching the conservative choice made everywhere else here.

### Added — `GET /api/stops/<id>/history` and an in-stop panel

A **History** toggle on each stop, mirroring the Photos gallery's lazy
pattern and living outside the diffed content so it survives every poll:

```
09:14  planned → arrived
09:31  arrived → completed
09:32  completed → arrived  (reverted)
```

One deliberate difference from Photos, which caches forever: this log
changes every time a button on the stop is pressed, so `handleStopAction()`
refreshes it while open. A history panel omitting the change you just made
is worse than no panel. An empty log says so explicitly rather than
rendering blank, and a failed fetch says *that* — the two must not look
alike when someone is hunting a missing record.

Note the reason for a skip or cancel now outlives the revert that cleared
it: the execution row's `cancel_reason` is emptied, but the event keeps it.

### Verification

`pytest tests/` **399** (382 before) — `test_delivery.py` 151,
`test_delivery_routes.py` 111. jsdom **96/96**.

Both suites' plan fixtures now date plans to *today*. They were hard-coded to
past dates, which was harmless while nothing depended on the date and would
silently have put every revert test on the refusal path.

Mutation-checked: making `can_revert()` return True unconditionally fails 4
tests across both layers; removing the revert filter from the history lookup
fails the redo test alone.

The pre-existing afternoon-only ETA test noted in the previous entry still
fails after 12:00 local and passes before it (96/96 under a morning
timezone). Untouched — still outside scope.

## 2026-08-01 — GPS timestamps are parsed server-side; "GPS stale 4920h"

Reported by the operator: every vehicle on the dashboard warning "GPS stale
4920h".

### Fixed — TTAS dates were being read month-first in the browser

4920 hours is 205 days, which is exactly 8 January → 1 August. TTAS writes
`trktime` day-first (`01/08/2026` is 1 August, the Vietnamese convention the
report scraper in the same file already parses with `%d/%m/%Y`). That string
was passed to the browser as raw text and handed to `new Date()`, whose
fallback for non-ISO input is **month-first** — so `01/08` read as 8 January.
The clock time parsed correctly; only the date flipped, which is why the age
came out as a round hour count.

The severity depends on the day of the month, and the noisy case was the
least of it:

| Day | `new Date()` reads | Effect |
|---|---|---|
| 1st–11th | wrong date in the past | phantom staleness — the 4920h reported |
| 12th | 8 December, a *future* date | negative age, so **no flag at all** |
| 13th–31st | Invalid Date | `isNaN` guard skipped the check — **silence** |

So for roughly two thirds of every month the GPS staleness flag was not
merely wrong, it was **switched off** — a tracker that genuinely stopped
reporting raised nothing. The false alarms were visible; that was not.

`ttas_client.parse_ttas_timestamp()` now parses at the boundary and returns
ISO 8601, or `None` when the value is in no recognised format. One
implementation, one calendar convention, and a log line naming any shape it
does not recognise — throttled to one line per distinct value, since 40
vehicles on a 12-second poll would otherwise write ~200 lines a minute and
bury it.

`normalize_vehicle()` gains **`last_update_iso`** and leaves `last_update`
exactly as TTAS wrote it: `static/js/map.js` prints that field verbatim in
the fleet map popup, and replacing the operator's familiar format with ISO on
an unrelated page is not this fix's business. Anything computing an *age*
reads the ISO twin; anything *displaying* the value keeps the raw text.

### Added — "GPS age unknown", a third state

`computeAttention()` previously had two states, and folded "cannot tell" into
"fine". It now distinguishes:

- position + readable time → fresh, or `gps_stale` as before
- position + unreadable time → **`gps_time_unknown`**, "GPS age unknown"
- no position at all → `no_gps`, unchanged

`gps_time_unknown` is capped at WARN and never graded: an unknown age is not
evidence of a long one, and inferring CRITICAL from ignorance is how an alert
display loses its credibility. It also suppresses `reported_stopped` for that
vehicle — that flag asserts "moving at ~0 *right now*", and without a
trustworthy timestamp there is no "right now" to assert. Like `no_gps`, it is
silenced during a fleet-wide GPS outage.

The vehicle card shows TTAS's own text when the parse failed, rather than a
relative time it cannot justify. `_formatTime()` takes `(isoStr, rawStr)` and
deliberately never falls back to `new Date(rawStr)` — that fallback is the
bug itself, and there is a test that fails if it is reintroduced.

### The test fixtures were the reason this survived

`TTAS_PAYLOAD` used ISO dates, a format production may never send. Both the
service and route suites asserted a contract that did not exist — the same
failure mode as audit T-01/T-02, in the same module. The fixture is now
day-first, and `makeGps()` in the jsdom suite always emits both fields in the
shapes the server really produces.

### Verification

`pytest tests/` **382** (363 before). jsdom **89/89** (88 before).

Mutation-checked in both directions: flipping `_TTAS_TIME_FORMATS` to
month-first fails 6 parser tests; making `computeAttention()` fall back to
the raw text when the parse is null fails the test written specifically for
it. That second mutation initially passed, which exposed a real gap — the
existing cases used values (`13/08/2026`, `sometime`) that are unreadable to
*both* parsers. The added case uses `01/08/2026`, which the browser will
happily misread, and is the only one that pins the behaviour down.

### Unrelated pre-existing failure noticed

`tests/js/dashboard.test.js`'s "a route running past midnight" asserts
`etaClock(36h)` ends in `+1d`. 36 hours from any time at or after 12:00 local
lands two calendar days out, so the correct answer is `+2d` and the test
fails every afternoon. Confirmed by running the suite under `TZ=UTC` (05:19,
88/88) and local `+07` (12:19, 87/88). The code is right, the fixture's 36h
is not. Left alone — outside this change's scope.

## 2026-08-01 — Advance, Skip and Cancel can be undone

Operator request: dispatchers were mis-tapping Advance on the dashboard.

### Added — a bounded, one-step revert

Advance is a single unconfirmed tap sitting beside Skip and Cancel, on a panel
used on a phone in a moving vehicle. The double-tap guard added on 2026-07-31
(audit C-07) stops a mis-tap landing *twice*, but nothing walked back the one
that did land — the only remedy was editing `stop_executions` by hand.

`execution_service.revert_stop()` steps a stop back one position:

| from | to | cleared |
|---|---|---|
| `arrived` | `planned` | `actual_arrival_at` |
| `completed` | `arrived` | `actual_departure_at`, `completed_at` |
| `skipped` / `cancelled` | `arrived` if an arrival was recorded, else `planned` | the reason, `completed_at` |

Each transition clears exactly what its forward step wrote, so a reverted stop
is indistinguishable from one that was never actioned. Leaving a timestamp
behind would corrupt dwell time the same way C-07 did.

`skipped`/`cancelled` are the interesting pair: nothing records what the stop
was before it was skipped, but an `actual_arrival_at` can only have been
written by an advance — so a stop skipped after the driver had already arrived
returns to `arrived`. Sending it to `planned` would either strand a real
arrival time on a stop the dashboard calls unvisited, or destroy it.

Guards mirror `advance_stop()` exactly: the optional `expected_status` token
refuses a revert aimed at a status the stop has since left (409), and
`AND status = ?` on the UPDATE means two racing requests cannot step back
twice. Leaving a terminal status calls the new `_reopen_plan()`, the mirror of
`_maybe_complete_plan()` — without it a corrected plan stays `completed` and
drops out of the dashboard's active view, hiding the vehicle just fixed.

**The window is 15 minutes, measured from the timestamp of the action being
undone** — `completed_at`, or `actual_arrival_at` for an arrived stop — and
deliberately *not* from `updated_at`. A reorder rewrites `updated_at` on every
stop it renumbers, which would silently re-open the undo on a stop finished
hours earlier. There is a test for exactly that.

A stop whose reference timestamp is missing is treated as too old rather than
too fresh. That state can't be produced by `advance_stop()`; unknown age just
reads conservatively.

### Added — `POST /api/execution/revert`, and `can_revert` on `GET /api/stops`

Same request/response shape as `/execution/advance`, including `conflict: true`
with 409. Still open, like every other endpoint (see the 2026-07-31 entry).

`GET /api/stops` now stamps a `can_revert` boolean on each stop via
`execution_service.annotate_revertible()`. The dashboard draws its button from
that flag rather than recomputing the window in the browser, so the button and
the endpoint that honours it read one clock; a browser several minutes off
would otherwise show a button the API refuses. The endpoint re-checks on the
way in regardless — a stale page can still post.

### Added — Revert button and an Undo toast

`buildActionsHtml()` now takes the stop object rather than `(id, status)` and
emits a Revert button whenever `can_revert` is set, **including on terminal
stops**, where it previously returned nothing at all — a stop mis-advanced to
`completed` is precisely the one that needs it. It routes through the existing
`handleStopAction()`, inheriting the in-flight guard and the staleness token,
and is styled as a correction (muted, dashed, pushed right) rather than a
fourth way forward.

A successful Advance/Skip/Cancel also raises a toast carrying an Undo action
for 9 seconds, since the mis-tap is usually noticed a beat later, once the
panel repaints and shows the wrong stop. The undo has to name the status the
action produced before any refresh could tell it, so that walk is reproduced
client-side from the status the button was rendered with; when it can't be
determined the undo goes without a token and the server still refuses anything
illegal.

`UI.toast()` gained an optional fourth argument (`{actionLabel, onAction}`)
rendering one inline button. Purely additive — every existing three-argument
call is untouched. Dismissal now also sets `pointer-events: none`, because the
node lingers ~350ms for its fade and an invisible-but-clickable Undo was a
second request at a stop that had already moved.

No keyboard shortcut for undo: `a` (advance) is adjacent, and that adjacency is
how mis-taps happen in the first place.

### Not done

Reverts are not recorded anywhere — there is no auth (2026-07-31), so an audit
row could say what changed but never who. Flagged for the operator rather than
half-built.

### Verification

`pytest tests/` **363** (320 before): `tests/test_delivery.py` 128 (+29),
`tests/test_delivery_routes.py` 102 (+14). jsdom **77/77** (58 before).

Mutation-checked: dropping `actual_arrival_at = NULL` from the arrived→planned
UPDATE fails only the timestamp test; making `annotate_revertible()` read
`status` instead of the `execution_status` alias `list_stops` returns fails
only the alias test and the route's `can_revert` assertions.

## 2026-07-31 — Ages refresh on a 15s clock; ETA no longer drifts on repaint

Operator request. Frontend only.

### Fixed — displayed ages were only as fresh as the last successful poll

"GPS stale 23m" is computed as `Date.now() - gps.last_update` inside
`computeAttention()`, which only runs during a render — and renders only happen
when the 12-second poll returns. A slow or failing poll therefore froze the
number on screen while the real age kept climbing. The age shown was the age as
of the last successful network round trip, not now.

A 15-second ticker in `main.js` now calls `DASH.vehicleList.refreshAges()`,
which repaints only what is derived from the clock: GPS ages, attention
durations, and the severity tier when a flag crosses a threshold.

**It is not a poll, and it deliberately cannot move the view.** No network, and
no call into `DASH.map` at all — the surest way to honour "the map view moves
only in response to a click" (CLAUDE.md, dashboard map conventions) is for this
path never to reach the map module. There is a test asserting exactly that, and
mutation-checking confirms it fails if `refreshAges()` is made to touch the map.

It also does not reorder the list. A card moving out from under the pointer
mid-click is its own kind of snap, so sorting stays on the real poll — at most
12 seconds away, and a tier change is visible immediately regardless. Card nodes
are reused, never rebuilt, so hover and scroll survive.

The ticker skips while the tab is hidden, and its body is wrapped so a failure
there can never take the dashboard down — it is cosmetic.

### Fixed — arrival times crept later on every repaint

Introduced with the clock-time ETA earlier today. `eta_seconds` is measured from
the moment the server answered, but `UI.etaClock()` was adding it to
`Date.now()` at render time — so each repaint pushed the arrival further into the
future. Bounded by the poll interval before, but the 15-second ticker would have
made it visible: four small forward jumps a minute on a number that should not
move at all.

`UI.etaClock(seconds, fromMs)` now takes the instant the ETA landed.
`main.js` stamps `_receivedAt` on the payload as it arrives; `timeline.js` holds
it at module scope for the current render rather than threading a parameter
through four functions that do nothing else with it. A missing or malformed
baseline falls back to `Date.now()` — right on first paint, drifting after, which
is the old behaviour and never worse than it.

### Verification

jsdom **58/58** (49 before). `pytest tests/` unchanged at 331 — no Python
touched.

Mutation-checked: making `refreshAges()` call into `DASH.map` fails only the
map-safety test; ignoring the ETA baseline fails only the drift test.

**One test was deleted rather than kept.** An assertion that the attention strip
keeps its horizontal scroll position across a tick passed with the preserving
code removed — jsdom has no layout engine, so `scrollLeft` never resets on an
`innerHTML` swap. A test that cannot fail is worse than no test; the code stays,
with a comment recording that confirming it needs a real browser.

## 2026-07-31 — ETA shows time of arrival instead of a countdown

Operator request. Frontend only.

Every ETA on the dispatch dashboard now reads as a clock time — `ETA 14:35`
rather than `ETA 47 min`. Dispatchers work against the clock: an arrival time is
directly comparable to a delivery window, a site's closing time or a driver's
shift end, where a countdown has to be added to the current time first and is
wrong again by the time you look back at it.

`UI.etaClock()` and `UI.etaRelative()` in `static/js/utils.js`, applied at all
three render sites — the per-stop timeline detail, the pinned current-stop card,
and the map info bar. The remaining duration is kept on hover, since "how long
from now" is still the faster read when the question is whether a driver can fit
one more drop.

Details worth stating:

- **24-hour format**, explicitly. `14:35` misread as `02:35` is a four-hour
  dispatch error, and the locale default would have decided this.
- **A route crossing midnight is marked `+1d`.** Without it, an arrival after
  midnight renders as a time earlier than now, which reads as "already late"
  rather than "tomorrow".
- **A null ETA returns null, not a time.** This is audit L-10's shape: `null / 60`
  rounded to a confident `0 min` — "arriving now" — for a stop with no
  coordinates. In clock form the same bug would produce a plausible-looking
  `14:02`, which is worse, because nothing about it looks wrong. Guarded and
  mutation-tested: removing the guard fails exactly that test.

jsdom suite **49/49** (42 before). `pytest tests/` unchanged at 331 — no Python
touched.

## 2026-07-31 — Gross vehicle weights loaded from the fleet spreadsheet (data, not code)

`routing_system.db` updated in place, with permission. Envelope migration
committed and `gross_weight_kg` populated for 32 of 36 vehicles from
`DS XE VA TAI XE.xlsx`. No application code changed.

### What the source file actually contained

Two of its columns look like the vehicle envelope and are not, so this was
checked before anything was written:

- **`KÍCH THƯỚC`** matches `container_configs` exactly for all 32 rows — it is
  the **cargo box**, already in the database, and unusable for routing.
- **`THỰC TẾ ĐO` / `Cửa phụ`** are the rear and side door openings, also already
  stored as `container_features`.
- **`TT THỰC`** matches `payload_kg` 32/32.
- **`KLTB`** (khối lượng toàn bộ) exceeds payload on every row by 1.94–7.78 t of
  kerb weight — which is what makes it gross rather than payload or kerb. This is
  the only column that was usable, and it is the one that was missing.

Overall length, width, height and axle load are **not in the file** for any
vehicle. Those still come from type estimates, so `envelope_source` is now
`"mixed"` for all 32 box trucks and the dashboard banner still reports estimated
dimensions — correctly, since weight is now real and the three dimensions are not.

### Three vehicles were being routed under the wrong profile

All in the 1.5 t class, where the type estimate (3490 kg) sat just under the
3500 kg `goods`/`hgv` line and the real weights sit just over it:

| Plate | Estimated | Actual | Was | Now |
|---|---|---|---|---|
| 50H-93997 | 3490 kg | 3605 kg | `goods` | `hgv` |
| 50E-18820 | 3490 kg | 3605 kg | `goods` | `hgv` |
| 50H-94382 | 3490 kg | 4045 kg | `goods` | `hgv` |

They were being routed as light commercial vehicles and would have been sent past
`hgv=no` restrictions. Only 50H-93571 (2820 kg) is genuinely `goods`; the whole
rest of the fleet is `hgv`.

Two label/reality mismatches worth an operator's eye, left as they are because
the numbers are what routing uses: **50E-19424** is filed "5 Tons" but weighs
4995 kg gross — lighter than most of the 2.5 t class. **50H-80292** is filed
"2.5 Tons" at 5675 kg, the heaviest in its class.

### The 4 container tractors were not touched

50H-06136, 51D-48353, 51C-92980 and 51C-72095 carry no dimensions or weights in
the spreadsheet at all. They remain on `Container` type defaults
(`envelope_source: "type_default"`).

### How it was applied

- `routing_system.db-journal`, the hot journal left by the earlier aborted write,
  was removed first. `PRAGMA integrity_check` returned `ok` both before and after.
- Backup taken before writing.
- Every value was run through `validate_envelope()` — the same validator the
  Add/Edit Vehicle form uses — against the cargo figures already in the database,
  with the script set to refuse a partial write if any row failed. 32 validated,
  0 refused, no warnings.
- Each `UPDATE` asserted `rowcount == 1`, so a plate that failed to match would
  have aborted the transaction rather than silently doing nothing.

After: 32 rows with GVW, 4 without, integrity `ok`, all other table counts
unchanged (35 container configs, 40 features, 1 plan, 5 assignments, 20 stops,
20 executions, 323 fuel rows, 13 TLP packages). `pytest tests/` still 331.

`scripts/fill_vehicle_gvw_2026-07-31.sql` holds the equivalent statements for
reference and for replaying against another environment.

## 2026-07-31 — Vehicle-constrained routing, phase C: restrictions applied, degraded-route path

Dispatch ETAs now route against each vehicle's physical limits. Shipping on
`type_default` estimates by operator decision — the 36 registration certificates
are not available, and the release was not held for them. Every route computed
from an estimate says so on screen.

### Added — restrictions on every delivery routing request

`build_ors_options()` turns a vehicle row into an ORS options dict; `/api/eta`
resolves it per assignment and threads it through `calculate_etas_for_stops()`.
`plan_service.get_assignment()` was widened to carry the envelope columns.

**`options.vehicle_type` is decided by gross weight, never by the type label.**
The labels are payload classes used to categorise the fleet and the real gross
weights are nothing like them — a "2.5 Tons" truck is about 4990 kg laden. GVW
≤ 3500 kg → `goods`, above → `hgv`. This was raised because the original mapping
("1.5–2.5 t → goods, because goods means LCVs under 3.5 tonnes") contained a
contradiction — the 2.5 t class is over that line — and left "5 Tons" uncovered
by either rule. Deriving from the number resolves both and self-corrects when
real certificate data lands.

Unknown gross weight resolves to `hgv`. Wrong towards `goods` puts a truck down a
road tagged `hgv=no`; wrong towards `hgv` costs a detour. Only one of those is
recoverable.

Where the seven fleet types currently land, all on estimates:

| Type | GVW estimate | ORS type | Restrictions sent |
|---|---|---|---|
| 1.5 Tons | 3490 kg | `goods` | 2.65 m × 1.9 m × 5.3 m, 3.49 t |
| 2.5 Tons | 4990 kg | `hgv` | 2.9 × 2.0 × 6.2, 4.99 t |
| 5 Tons | 8500 kg | `hgv` | 3.2 × 2.2 × 7.5, 8.5 t |
| 8 Tons | 15000 kg | `hgv` | 3.5 × 2.35 × 9.0, 15 t |
| 9 Tons | 16000 kg | `hgv` | 3.5 × 2.35 × 9.5, 16 t |
| 10 Tons | 17500 kg | `hgv` | 3.6 × 2.4 × 10.0, 17.5 t |
| Container | 24000 kg | `hgv` | 3.8 × 2.45 × 11.5, 24 t |

### Added — the degraded-route ladder

Per leg: request with the vehicle's restrictions; on ORS **2009** only, retry
once with the dimensions dropped; if that also fails, report no route.

- **`avoid_borders` survives both attempts.** `routing.py` reapplies it after
  every caller, so the border rule is structurally outside what degrades. Asserted
  on both requests in the test.
- **`vehicle_type` survives the relaxation too.** Legal access bans are not
  dimensions — a truck barred by `hgv=no` is still barred when its height is the
  problem elsewhere. Only the physical limits are relaxed.
- **A transport failure is never retried as a restriction problem.**
  `OrsUnavailableError` returns immediately; only `OrsNoRouteError` climbs the
  ladder. An unrestricted leg does not retry at all — there is nothing to relax
  and the second call would be wasted against a rate limit `/api/eta` is already
  close to.

Legs carry `restriction_status`: `compliant`, `violated`, `unrestricted`,
`unknown`. `unrestricted` and `violated` are kept apart deliberately — "we did not
check" and "we checked and it failed" are different claims.

### Fixed — the ETA cache would have served routes under superseded specs

`_stops_cache_key()` now includes a stable hash of the active options. An
assignment's vehicle is fixed, so without it, editing a truck's dimensions would
keep serving routes computed under the old ones until the process restarted. The
hash uses sorted keys, so it depends on the values rather than on dict ordering.

### Added — the route says when it cannot be trusted

- **Violated legs render red on the map**, with a white casing beneath so they
  stay legible on both the satellite and near-white street basemaps — the same
  two-tone rule the vehicle markers follow. This required splitting the route
  from one joined polyline into one per leg; `lastRouteKey` now includes the
  status string, since identical geometry can flip between compliant and violated
  when a vehicle's specs are edited.
- **A banner above the timeline** states which of three things is true: legs were
  routed in violation (red), the route was computed from type estimates rather
  than the certificate (amber), or nothing was checked at all (grey). It names the
  vehicle's actual limits.
- **It does not claim which limit failed.** ORS reports only that no route was
  found; identifying the culprit means one extra request per restriction per leg.
  The warning names the limits and says a route respecting them could not be
  found.

One warning for the whole route, not one per stop: the dispatcher's question is
"is this route safe for this truck", answered once — the map already shows which
legs. It also keeps new state out of `_patchStop`'s diffing renderer.

**Not built: a fleet-wide restriction signal in the vehicle list.**
`/api/execution/dashboard` does no routing, so flagging violations across all 40
trucks would mean an ORS call per truck per 12-second poll. Restrictions are
visible for the selected vehicle only.

### Verification

`pytest tests/` — **331 passed** (309 before). Frontend: `node --check` clean,
jsdom suite **42/42** (34 before).

Mutation-checked:

- `GOODS_GVW_LIMIT_KG = 99999` (everything becomes `goods`) → fails exactly the
  three vehicle-type tests.
- `restrictions_fingerprint()` returning a constant → fails exactly the hash test
  and the cache-invalidation test.

A fixture problem surfaced and was fixed properly: `tests/test_delivery.py` and
`tests/test_delivery_routes.py` each hand-write a `vehicles` table, and both
missed the phase B columns, so the widened `get_assignment()` query failed in
suites unrelated to this change. Both now call `add_vehicle_envelope_columns()`
rather than restating the column list — a duplicated list drifts silently.

**Still not verified against the live ORS API.** No request has been made from
here; shapes come from the v9.7.1 spec. First deploy should confirm a known-good
route still returns a route, and that a restricted request is accepted.

## 2026-07-31 — Vehicle-constrained routing, phase B: envelope schema, form, validation, type fallbacks

Builds the place to put the vehicle data phase C needs. Phase C stays blocked
until the 36 registration certificates are transcribed — this is the plumbing
for that, plus a way to see how much of it is still missing.

### Fixed — `pytest tests/` was running migrations against the production database

Found while adding this phase's migration, and much the more serious finding.

`app/config.py` reads `DB_PATH` at **import time**, and `create_app()` then runs
`init_db()` — schema creation plus every migration in `run_all()` — against
whatever it resolved. So the first test module to import anything under `app/`
decided which database the entire session wrote to, and with `DB_PATH` unset,
`config.py` falls back to `BASE_DIR / "routing_system.db"`: the real database, in
the repository.

Modules guarding this in their own headers is not enough — it only protects a run
in which that module is imported first. `tests/test_routing.py`, added in phase A,
imported `app.services.routing` with no such guard, which was enough for
`pytest tests/` to point `init_db()` at the live file.

It had been silent because every migration in `run_all()` was a no-op against an
already-migrated database. Adding one that actually writes to `vehicles` turned it
into 88 `disk I/O error` failures in `test_delivery_routes.py` — a suite that has
nothing to do with either change.

`tests/conftest.py` now points `DB_PATH` at a throwaway file before any test
module is imported. A conftest is imported ahead of the modules beside it, so it
is the only place the guarantee can be made once, for every test file present and
future. Unconditional rather than `setdefault`, because an inherited `DB_PATH`
from a developer's shell is precisely the case being guarded against.

**Data was not lost.** `PRAGMA integrity_check` returns `ok` and every table
matches its pre-run count (36 vehicles, 35 container configs, 40 features, 1 plan,
5 assignments, 20 stops, 20 executions, 2 drivers, 323 fuel rows, 13 TLP
packages). The `ALTER TABLE` never committed — `vehicles` still has its original
seven columns. A stale `routing_system.db-journal` was left behind; see the note
at the end.

### Added — vehicle envelope columns

Five nullable columns on `vehicles` via `add_vehicle_envelope_columns()`
(`app/database/migrations.py`, additive and idempotent, matching the existing
`PRAGMA table_info` + `ALTER` style):

```
gross_weight_kg  overall_height_mm  overall_width_mm  overall_length_mm  axle_load_kg
```

**NULL is a meaningful state and must survive end to end.** It means "unknown",
which falls back to a type estimate; a `0` would be sent to ORS as a genuine
restriction and match no road at all. So the form posts `null` rather than `0`
for a blank field, `coerce_envelope_value()` maps blank/0/negative/garbage to
`None`, and `to_ors_restrictions()` omits unknown fields from the request instead
of defaulting them. Tested at each of the three layers, including that clearing a
previously-set field writes NULL rather than leaving the old value in place.

### Added — validation that catches the mistake this feature exists to prevent

Positive-numeric bounds would not have caught anything that matters. Cargo-box
figures pasted into envelope fields are all valid positive integers — `1810` is a
perfectly good height, it is just the wrong 1810 — and they understate the vehicle
in the direction that routes it under a bridge it hits.

So the blocking rule is **cross-field consistency** against the cargo compartment
the same form already collects: overall height and length must strictly exceed
their cargo counterparts, gross weight must exceed payload, overall width must be
at least cargo width. Entering 50H-36908's cargo numbers as its envelope trips
three of the four at once.

Width is non-strict by design: a body exactly as wide as its cargo is physically
possible, so an equal value cannot be called an error. Three flags on one save is
an unmissable signal regardless. (The route-layer test asserts exactly three, and
says why — a test written expecting four was wrong, not the validator.)

**Plausibility ranges warn rather than block**, anchored on QCVN 09:2024/BGTVT
(trucks ≤ 4.0 m tall, ≤ 2.5 m wide, ≤ 12.2 m long). Deliberately not fatal: a hard
rejection on a legitimate outlier gets the field left empty, and empty falls back
to a silent estimate. A flagged odd number beats an unflagged guess. The bounds
are fleet-wide rather than per-type, so a 39 t "2.5 Tons" truck passes — tightening
that means per-type ranges, which is more machinery than the check is worth.

### Added — per-type fallbacks, and provenance that travels with them

`TYPE_DEFAULTS` in `app/services/vehicle_specs.py` covers all seven types in use
(1.5/2.5/5/8/9/10 Tons, Container), applied **only** where a vehicle's own column
is NULL. `resolve_envelope()` returns the envelope and a source:
`"vehicle"` | `"mixed"` | `"type_default"` | `"none"`.

Every default is asserted to sit inside its own plausible range — a value that
would warn if typed by hand has no business being the silent fallback — and every
type in the database is asserted to have one, since a missing type resolves to
`"none"` and sends no restrictions at all.

### Added — form and table

The Add/Edit Vehicle modal gains a **Vehicle Envelope** group, above and visibly
separate from **Container Dimensions**, each labelled with what it is ("the whole
truck" / "the cargo box only") and the envelope group naming the registration
certificate as its source. Units are mm and kg throughout, matching the existing
cargo fields; conversion to the metres and tonnes ORS wants happens once, in
`to_ors_restrictions()`, rather than scattered where a 1000× slip would hide.

The vehicles table gains an **Envelope** column reading the measured dimensions,
or `Partly estimated` / `Estimated` / `Missing`. Phase B's real cost is
transcribing 36 certificates, and a gap nobody can see is a gap nobody closes.

Warnings are surfaced as toasts after the success toast, on a longer timeout,
since the point is a second look rather than a blocked save.

### Verification

`pytest tests/` — **309 passed** (273 before; +25 `tests/test_vehicle_specs.py`,
+11 `tests/test_fleet_routes.py`). Frontend `node --check` clean and the dashboard
jsdom suite still 34/34.

`test_fleet_routes.py` drives real HTTP because the service suite is structurally
blind to a validator that is never called or a column that is never written —
which is where a "validated" form that silently drops its values would live.

The migration was also run twice against a copy of the real database to confirm
idempotency and that existing rows get NULL rather than 0.

**Left for you: `routing_system.db-journal`.** The aborted write left a hot
journal beside the database; the sandbox has no permission to delete it, so reads
from here now fail. On Windows, SQLite should roll it back and remove it
automatically on the next open — start the app and it will most likely resolve
itself. If it does not, deleting `routing_system.db-journal` by hand is safe: the
main file passes `integrity_check` standalone and holds every row.

## 2026-07-31 — Vehicle-constrained routing, phase A: POST migration, border avoidance, failure-mode split

Backend only. Planned in `docs/VEHICLE_ROUTING_PLAN.md`, which records the phases
deliberately not done here and the one thing blocking them. Phase A needs no
vehicle data at all, which is why it went first.

### Fixed — advanced routing options were structurally unreachable

Both ORS call sites used the **GET** directions endpoint:

- `app/services/routing.py` — `f"{ORS_BASE_URL}/{profile}"` with
  `params={"api_key", "start", "end"}`
- `services/delivery/eta_service.py` — the same shape

`options` is a request **body** parameter, and the ORS docs state plainly that
the GET form *"does not allow advanced request options"*. So border avoidance and
the per-vehicle dimension restrictions were not misconfigured — they were
unreachable over the transport in use. Both now `POST {base}/{profile}/geojson`
with a JSON body and the key in an `Authorization` header.

The `/geojson` result type returns a FeatureCollection whose feature `properties`
carry the same `segments` the GET form did, so both parsers read the shape they
always read. That was verified against the ORS specification before either parser
was touched, since everything else in this phase sits on top of it.

### Added — `avoid_borders: "all"` on every routing request

This fleet does not leave Vietnam, and a route crossing into Cambodia or Laos is
wrong however much shorter it is. Applied at **both** call sites (the fleet map
and dispatch ETAs) — it needs no vehicle data, so there was no reason to phase it.

Unlike the dimension restrictions planned on top of it, this is a graph-level
constraint in ORS and does not depend on how well roads happen to be tagged in
OSM.

**The border rule is not droppable by a caller.** In `request_directions()`,
caller options are merged *first* and `BASE_OPTIONS` applied *last*. Phase C's
degraded-route retry relaxes the dimension restrictions when no compliant route
exists; it must not relax this one along with them, and enforcing that in the
merge order is better than trusting every future call site to remember it.

### Fixed — "no route exists" was indistinguishable from "ORS is broken"

`calculate_eta()` caught every exception into a haversine straight line tagged
`haversine_fallback`. Once restrictions are on, ORS error **2009** ("route could
not be found between locations") stops meaning *ORS had a problem* and starts
meaning *no legal route exists for this vehicle* — the finding the whole feature
exists to produce. The old code would have buried it as a network hiccup.

It is already reachable today: with `avoid_borders` in force, a destination
only approachable by leaving the country now answers with 2009.

- ORS reports this as **HTTP 404 with 2009 in the body**, so the response body is
  parsed *before* the status is judged. `raise_for_status()` first would flatten
  the finding into an indistinguishable HTTP error.
- Two exception types: `OrsNoRouteError` (with the ORS code attached) and
  `OrsUnavailableError`. 2009 and 2010 ("point was not found") raise the first;
  everything else — transport failure, 5xx, unparseable body — raises the second.
- `request_directions()` never substitutes a fallback of its own. What to show
  when there is no route belongs to the caller.
- ETA legs gained `route_status`: `"ok"` | `"no_route"` | `"unavailable"` |
  `"not_configured"` | `"no_coordinates"`, carried through `/api/eta`. `source`
  keeps its existing values, so nothing downstream had to change. **Nothing
  renders `route_status` yet** — that is phase C4, and it is exposed now so the
  UI work has something to read.
- `get_route_coords()` gained a matching `"status"`. Its three original keys are
  untouched: `app/routes/trips.py` indexes them directly from a background
  thread with no guard.

### Changed — one ORS transport instead of two

`request_directions()` lives in `app/services/routing.py` and is imported by
`services/delivery/eta_service.py`. The request shape, the always-on options and
the error classification now exist once. The import direction follows precedent —
`execution_service` already imports `app.db`, `tracking_service` already imports
`app.services.ttas_client`.

`get_routing_profile()` is left as-is despite all three branches returning
`driving-hgv`: it is the seam where the `vehicle_type` → ORS
`options.vehicle_type` mapping goes in phase C, and restrictions do nothing at
all unless that field is set. Commented to say so rather than deleted.

`print()` in the routing error paths became `logger.warning()`, matching
`eta_service` — these paths now carry information worth having in the Render logs
rather than only on stdout.

### Not done

Dimension restrictions (height/width/length/weight/axleload). **The data does not
exist.** All 23 tables were scanned for dimension-like columns; the only matches
are `container_configs` (the cargo compartment, for the bin-packing planner) and
`tlp_packages` (the parcels). There is no gross vehicle weight, overall height,
width, length or axle load anywhere in the schema, and no spreadsheet in the repo
holding them.

Cargo-box numbers are not substitutes and fail in the dangerous direction — a
2.35 m cargo box sits on a truck well over 3 m tall, and `payload_kg` excludes
the whole kerb weight. Feeding them to ORS would produce routes that look
height-checked and are not. See `docs/VEHICLE_ROUTING_PLAN.md` §3.

### Verification

`pytest tests/` — **273 passed** (254 before; +15 in the new `tests/test_routing.py`,
+4 in `tests/test_delivery.py`).

`tests/test_routing.py` covers the transport directly: the POST target and
headers, `avoid_borders` present on every request, a caller being unable to drop
it, the 2009/2010 → no-route split, 5xx and transport failures → unavailable, a
200 with no features, an unparseable body, and `get_route_coords` still returning
the three keys `trips.py` indexes on every failure path.

The two `eta_service` tests that patched `requests.get` now patch
`app.services.routing.requests.post`, and four were added for the new statuses.

Mutation-checked, both ways:

- `BASE_OPTIONS = {}` → fails exactly the three `avoid_borders` tests.
- `NO_ROUTE_CODES = ()` → fails exactly the five no-route tests.

Nothing else moves in either case, so these tests measure what they claim to.

**Not verified against the live ORS API.** No request was made — the API key is
in `.env`, which is not read. The request and response shapes come from the ORS
v9.7.1 specification. First real deployment should confirm a known-good route
still returns a route.

## 2026-07-31 — Dispatch board UX, phase 0: GPS trust, graded severity, density, quick filters, keyboard

Frontend-only. No schema change, no API change, no Python touched. Planned in
`docs/DISPATCH_UX_PLAN.md`, which also records the phases deliberately *not* done
here and why. Reference practice was taken from emergency dispatch (CAD),
electronic flight strips in air traffic control, and Endsley's situation-awareness
model; the recurring lesson from all three is that severity has to be perceivable
without being read, and that alerts which cannot be ranked stop being useful.

### Fixed — the "Live" pill made a claim it had not checked

`/api/execution/dashboard` has always returned `gps_source`, `gps_error`,
`gps_matched` and `gps_available`. The comment beside them in
`services/delivery/routes.py` says exactly why: *"so the dashboard can show a
degraded-GPS badge instead of a green Live pill over an empty map, which is what
let C-01 go unnoticed for the module's entire life."* Nothing in `static/` read
any of the four — `main.js` took `data.assignments` and dropped the rest. The
backend half of that fix shipped; the frontend half never did, so the header went
on reporting "Live" whenever the *request* succeeded, regardless of whether a
single position had matched a plate.

"The request succeeded" and "the map is live" are separate claims. `polling.js`
now resolves the second through an optional `okStatusProvider` hook, which
`main.js` registers before the first tick. Precedence, worst first:

| Condition | Pill | Class |
|---|---|---|
| `gps_error` set | `GPS down` + the message on hover | `poll-gpsdown` |
| no assignments carry a plate | `Live` | `poll-ok` |
| `gps_available === 0` | `No GPS` | `poll-gpsdown` |
| `gps_matched === 0`, positions present | `GPS 0/N` + "check plate formats" | `poll-gpsdown` |
| `gps_matched <` plates on the board | `GPS n/N` | `poll-degraded` |
| otherwise | `Live` | `poll-ok` |

The zero-matched case is styled as loudly as an outright request failure on
purpose: a map covered in positions that belong to nobody is worse than an empty
one, because it looks correct. An empty board is explicitly *not* a fault — the
denominator is assignments carrying a plate, not the assignment count, so a
dashboard with nothing on it still reads Live.

Per-vehicle, a card with no position at all rendered an empty GPS line,
indistinguishable from a fresh fix. It now reads `No GPS` in amber, and raises a
`no_gps` attention flag — suppressed when the outage is fleet-wide, since forty
identical chips is not triage and the header already tells that story once.

### Fixed — "Attention first" sorted by the wrong key

`vehicle-list.js` sorted on `attention[].length`: the *count* of flags. A vehicle
with three fresh mild flags therefore outranked one that had been stuck for three
hours — the sort inverted precisely in the case it exists for. It now orders by
worst severity, then by how long the worst flag has been standing, then by count.

### Changed — attention severity is graded, not binary

The three proxies (stuck at a stop, stale GPS, reporting ~0 km/h while not at a
stop) all latched on at their threshold and rendered as the same dot for ever
after. `computeAttention()` now returns `{reason, ageMs, severity}` with severity
derived from `ageMs / threshold`: WARN at 1×, CRITICAL at 2×. Thresholds are
unchanged (20 min stuck, 15 min GPS).

- `reported_stopped` is capped at WARN and never graded. The existing comment is
  right that one reading can be a red light, so it must not reach CRITICAL alone.
- Tiers carry hue *and* weight *and* size (critical dots are larger, critical
  plates underlined). Hue alone would be invisible to a red-weak dispatcher, and
  this panel is read at a glance for a full shift.
- Cards take a coloured left border rather than a background tint — background
  already carries hover and selection, and a third meaning on it made a selected
  card with a problem unreadable.
- The strip caps at 8 chips with a `+N more` chip that switches on Attention-first
  rather than growing without limit. It is sorted worst-first independently of the
  list, since it is the triage surface even when the list below it is not.

Still true, and still the ceiling on all of this: **no stop carries a planned
time**, so none of these proxies can detect a truck that is simply behind while
driving normally. They all detect symptoms of having stopped. That is phase 1.

### Added — compact density for the vehicle list

36 box trucks plus 4 containers, in a 280px column, at five lines per card: about
eight visible at once, which defeats the point of a fleet board. A `compact`
toggle in the left panel header collapses each card to a single row (~20+
visible), persisted to `localStorage` alongside the basemap choice.

Implemented as a stylesheet change and nothing else — `display: contents` on the
two wrapper divs promotes their children into the card's own flex row, so the card
markup and the diffing patch in `_patchCard` are untouched. That diffing render is
load-bearing for scroll and hover preservation and had no business being near a
density change. On phones the binding constraint is tap-target size rather than
row count, so compact is explicitly a no-op below 768px.

### Changed — quick filters in front, field filters behind a disclosure

The header carried branding, seven nav items, five filter controls, poll status,
three buttons and two dropdowns, wrapping at narrower widths. None of the five
filters expressed a dispatcher intent.

A chip row — All / Needs attention / Executing / No GPS — now sits where the
fields were; clicking the active chip clears it, so the row is its own off switch.
The five fields moved into a disclosure behind a **Filters** button, keeping their
ids, values and event bindings unchanged. The button carries a count badge, so a
filter left set inside a closed panel cannot quietly explain away an empty list.
The panel is fixed-width with wrapping fields rather than one long row, so its
footprint is predictable at any header width; it flips to right-anchored below
768px for the same reason the Plans panel clamps.

### Added — keyboard navigation

A shift is eight hours of this board and every interaction was a mouse click.

| Key | Action |
|---|---|
| `j` / `k` | move the focus ring down / up the filtered list |
| `Enter` | open the focused vehicle |
| `Esc` | close the disclosure, or clear the selection |
| `/` | open Filters and focus the plate field |
| `a` | advance the current stop |
| `f` | toggle Follow |
| `r` | refresh now |

- **`j`/`k` move a focus ring only; they do not select.** Selection fires three
  requests and a map zoom, so holding `j` down a 40-vehicle list would issue one
  set per vehicle. `Enter` commits. The ring is an outline where selection is a
  filled accent, so a card can legibly be both.
- Shortcuts are suppressed while focus is in an input, select, textarea or
  contenteditable, and while a skip/cancel reason row is open — `timeline.js`
  exposes `hasOpenReasonRow()` over the set that already suppresses background
  patching for those rows, rather than tracking open state twice. Without the
  first guard, typing a plate containing `a` or `f` would advance a stop and
  toggle Follow mid-search.
- `Esc` is the one key that works *from* a field, since escaping a filter box is
  the point of pressing it.
- `a` synthesises a click on the real Advance button rather than calling the API,
  so the in-flight guard, the `expected_status` staleness check and the disabled
  state all apply unchanged and cannot drift from the button's behaviour.
- Modifier combinations are left to the browser.
- Escape's deselect needed a `deselectAssignment()`; it is not expressible as
  `selectAssignment(null)`, which would unconditionally fire the three detail
  requests and a map zoom for a null id.

### Verification

`tests/js/dashboard.test.js` — 34 jsdom drives of the real modules against the
real template (loaded from disk with its `<script>` tags stripped, so an id
renamed in the HTML but not the JS fails the suite). Covers the GPS badge
precedence table, severity grading and the sort inversion, the quick filters, the
keyboard guards, and regression guards on card-node reuse and compact mode not
touching card markup.

Mutation-checked: restoring the old count-based sort fails
*"Attention-first puts a 3h stuck above three fresh mild flags"* and nothing else,
so that test measures what it claims to.

The drive also caught an unguarded `card.scrollIntoView()` in the focus-ring
code — now behind a `typeof` check, since scrolling is a nicety and moving the
ring is not.

`node --check` clean on all six dashboard modules. `pytest tests/` — 254 passed,
unchanged, as expected for a change that touches no Python.

jsdom is a dev-only dependency and is deliberately not vendored; the header of the
test file documents how to run it.

## 2026-07-31 — Removed dispatcher authentication; stop reordering on the dashboard; Plans panel positioning

Three operator-requested changes to the delivery/dispatch module.

### Removed — the dispatcher password (reverses audit C-04)

The shared-password gate added earlier the same day was removed at the operator's request: anyone who can reach the app can now change a plan. This is a deliberate reversal of a security fix, recorded plainly rather than buried — the trade accepted is that `POST /api/plans/clear`, which cascade-deletes every plan, assignment, stop, execution record and image row, is again reachable by anyone who can resolve the host. The app binds `0.0.0.0`. **If this is ever exposed beyond the internal network, this decision needs revisiting.**

- Deleted `app/auth.py` and `templates/login.html`. `/login`, `/logout` and `/api/auth/status` no longer exist.
- Dropped all 22 `@login_required` decorators from `services/delivery/routes.py` and the import behind them.
- `app/config.py`: `DISPATCH_PASSWORD` and `SESSION_LIFETIME` removed (with the now-unused `timedelta` import). `SECRET_KEY` and the `SESSION_COOKIE_*` hardening stay — they are app-wide defaults, and no route reads the session today.
- Frontend: `handleAuthFailure()` gone from `static/js/utils.js`, and the 401-redirect / 503-message branches gone from `static/js/dashboard/api.js` and `static/js/delivery-plan-builder.js`. Non-OK responses fall through to the same error path they always did — verified `ApiClient.fetch`'s behaviour for a non-OK, non-auth response is byte-for-byte what it was.
- `.env` still carries a `DISPATCH_PASSWORD` line. It is gitignored and now unread; harmless, but worth deleting by hand.
- `docs/DELIVERY_AUDIT_2026-07-31.md` was left as written. It is a record of what the audit found, not a statement of current configuration.

### Added — reorder stops from the dashboard

`POST /api/stops/reorder` has existed since the delivery module was built and **no UI had ever called it** — resequencing a live route meant editing the plan in the builder. The timeline panel now has up/down controls on each stop.

- Up/down buttons rather than drag-and-drop: the plan builder's Step 3 already has HTML5 drag, but those events don't fire on touch, and this panel is used on a phone in the cab.
- **Terminal stops are immovable, and nothing moves across one.** A completed / skipped / cancelled stop's position is a record of what happened; renumbering around it would rewrite history. A direction is disabled when the neighbour in that direction is terminal.
- **Optimistic.** The new order paints before the request goes out — a dispatcher resequencing a route does several stops at a time and a round trip plus an ETA recompute per click is unusable. Moves are POSTed strictly in click order through a promise chain (`state.reorderStops` in `dashboard/main.js`), because the server rewrites every `execution_sequence` on each call and two racing requests would settle on whichever finished last, not on what was clicked last. Exactly one refresh runs when a burst settles.
- A poll landing mid-reorder is suppressed (`pendingReorders` guard in `loadAssignmentDetail`), and `detailGeneration` is bumped on each move so a load already in flight is dropped. Without both, a background poll a second later visibly snaps the list back to the old order.
- **`timeline.js`'s rebuild key is now order-independent** (sorted stop ids). It was `list.map(s => s.id).join(',')`, so a reorder counted as a new set and wiped the container — collapsing every stop and closing any open photo gallery, which is precisely the state a dispatcher is mid-way through using when they resequence. Nodes are now moved with `insertBefore` instead.
- **Sequence badges now show `execution_sequence`, falling back to `planned_sequence`.** The whole dashboard *orders* by `execution_sequence`; `planned_sequence` is fixed at plan-build time. Showing the latter meant a reordered route rendered as 1, 3, 2 — the list order was right and the numbers on it disagreed. Fixed in the timeline badge, the pinned current-stop card, and the map's stop popup.

### Fixed — the Plans (⚙) panel opened off-screen

`.manage-plans-dropdown` was `position: absolute; right: 0` against `.manage-plans-wrap`, pinning the panel's *right* edge to the button's right edge. `.dashboard-header` is `flex-wrap: wrap`, so at narrower widths the button moves; once it sits near the left of a wrapped row, a 320px panel extends past the left edge of the viewport and only part of it is visible. `.dashboard-shell`'s `overflow: hidden` separately clipped the bottom.

Now `position: fixed`, placed by `positionManagePlans()` from the button's `getBoundingClientRect()`: right-aligned to the button where there is room, then clamped to the viewport on every side, with `max-height` set to the space actually remaining below the button so the Delete/Clear row stays reachable. Repositions on `resize`; Escape closes it. `.manage-plans-list` lost its fixed `max-height: 280px` in favour of `flex: 1; min-height: 0` so the panel height governs.

### Fixed — vehicle plate numbers rendered as bare white text on the map

Reported as "the plate number is white and the map is almost white". It was not a colour choice — the dark chip behind the plate was not being drawn behind the plate.

`L.divIcon` is built with `iconSize: [0, 0]`, so the hosting `.leaflet-marker-icon` really is 0×0. `.vehicle-marker-label` is a block-level child, so its used width resolved to `0`; the painted background box was just the 12px of horizontal padding, while `white-space: nowrap` pushed the plate text outside the box entirely. The result was near-white `--text-primary` type sitting directly on near-white OSM tiles, with a small dark sliver to its left. Fixed with `width: max-content`, which sizes the box to the plate. Shadow deepened slightly for a light basemap.

### Fixed — clicking a vehicle took ~15 seconds to update the right panel

Two independent causes, both in `loadAssignmentDetail`/`selectAssignment`. The click was already firing its requests immediately — the delay was in what was done with them.

**1. `Promise.all` gated the whole panel on the slowest request.** The three detail calls went out together and *nothing* painted until all three resolved. `/api/stops` and `/api/execution/progress` read local SQLite and answer in milliseconds; `/api/eta` issues one OpenRouteService call per remaining stop, serially, each with a 30-second server-side timeout. So the stop list — the thing the dispatcher actually clicked for — waited on routing. They are now awaited separately and each paints on arrival: stops first, then progress, then ETAs filling in behind. An ETA failure no longer counts as a detail-load failure; the timeline, stops and route stay on screen.

**2. The previous vehicle's data stayed on screen throughout.** `selectAssignment` emptied `state.selectedStops` and called `renderAll()`, whose right-panel branch is `if (state.selectedStops.length > 0)` — false, so it did nothing, and the timeline, map stops, route line and info bar all kept showing the *previously* selected truck. For those seconds the dispatcher was looking at another vehicle's stops with no indication anything was loading. `selectAssignment` now clears all four immediately and the timeline shows "Loading stops…", so "nothing selected" and "selected, waiting on the server" are visibly different states.

The three call sites that painted the right panel from state were collapsed into one `paintAssignmentDetail()`, since it now runs repeatedly with partial state and all of them have to agree.

Verified under jsdom driving the real modules against a stubbed API with controllable timing: all three requests fire on click, stale rows clear instantly, the stop list paints while the ETA is still hanging, progress and ETA each patch in on arrival, a superseded click is dropped rather than painted, and a rejected ETA leaves the stops intact.

**Not fixed — the server serialises these requests.** `render.yaml` runs `gunicorn wsgi:app` with no `--workers`/`--threads`, which is one synchronous worker, and `/api/execution/dashboard` performs a blocking TTAS HTTP fetch inside the request. A click landing mid-poll therefore still queues behind that fetch no matter what the frontend does. The fix is a `startCommand` change, but adding concurrency to a SQLite database with no `PRAGMA journal_mode=WAL` (see CLAUDE.md) trades this delay for "database is locked" errors, so it is not a drive-by — flagged for a deliberate decision.

### Added — click the satellite map for the imagery capture date

Clicking the map while the Satellite basemap is active queries Esri's World_Imagery `identify` endpoint and shows, in a popup at that point, when the imagery under it was actually taken, plus source, sensor, resolution and positional accuracy. It matters operationally: a yard photographed in 2016 may not be the yard the driver is looking at, and nothing else on the dashboard hints at how old the picture is.

Bound only while Satellite is selected — on the street layers there is no imagery to date. Marker clicks don't reach the map in Leaflet, so clicking a vehicle or a stop can't trigger it.

Four things about this API were established by querying it, not assumed, and each would have produced a wrong or broken feature:

- **`returnGeometry=false` is mandatory, not cosmetic.** Every result carries a detailed footprint polygon; with geometry left on, a *single-result* response measured ~75 KB.
- **`layers=all` is unusable here.** One click returned 100 records with `exceededTransferLimit: true`. `layers=visible` makes the service scale-filter to the layers actually drawn at the current zoom.
- **Two attribute schemas come back in the same response.** The footprint layers (0-4) use `DATE (YYYYMMDD)` / `RESOLUTION (M)` / `ACCURACY (M)` / `SOURCE_INFO`; the per-zoom metadata layers (5-18) use `SRC_DATE` / `SRC_RES` / `SRC_ACC` / `NICE_NAME`. Reading only one set silently yields a blank popup on half the layers.
- **Every value is a string, and a missing value is the literal `"Null"`** — not JSON `null`, not `""`. An unguarded read renders "Captured: Null".

Dates are normalised to ISO `yyyy-mm-dd`. The compact `20241229` form is preferred because it is unambiguous; `SRC_DATE2` arrives as US `12/29/2024` and is parsed by hand, since `new Date()` on that string is locale-dependent and would land on a different day — or an invalid date — in a d/m/y locale.

A point is covered by several overlapping footprints, so the popup picks the one whose cache-level range covers the zoom being viewed, then the sharpest, then the newest. ArcGIS reports its own failures with HTTP 200 and an `error` object, so `resp.ok` alone is not enough; there is also a 10-second abort.

Verified under jsdom against the exact payload Esri returned for Ho Chi Minh City, plus synthetic cases: request parameters and `lng,lat` ordering, the real payload rendering `2024-12-29 / Vivid Advanced · Vantor / WV02 / 0.5 m/pixel / ± 8.47 m`, an all-`"Null"` response failing honestly instead of inventing a date, HTTP-200-with-error, HTTP 503, the `SRC_*` schema with a US-format date, zoom-range preference beating a newer-but-wrong-tier record, and no request at all being issued on the Streets basemap.

### Added — clicking a stop locates it on the map

The timeline said *which* stop; the map said *where*. Connecting the two took a manual pan. Clicking a timeline row — or the pinned current-stop card — now centres the map on that stop and opens its popup, via a new `DASH.map.focusStop()`.

- **Zoom is raised to 15 only if the view is further out than that.** A dispatcher already at street level keeps their level; one looking at the whole city gets pulled close enough for the stop to mean anything.
- **Follow mode switches off.** It re-centres on the vehicle every poll, so leaving it on would drag the view off the stop within 12 seconds — the same class of complaint as the autopan bug above. `state.setFollowMode()` was extracted so the timeline can do this and keep the button label in sync.
- **A stop with no coordinates has no marker**, so `focusStop()` returns false and the caller toasts rather than leaving a click that silently did nothing.
- The reorder buttons already `stopPropagation()`, so moving a stop doesn't also fly the map to it. On the current-stop card, clicks on a `button`, `a` or `input` are ignored — Advance/Skip/Cancel, the `tel:` link and the reason input all live in there.

Verified under jsdom with real Leaflet: centre and zoom after a row click, zoom preserved when already at 17, follow flipped off, the no-coordinates toast with the map staying put, the reorder button firing a reorder without moving the map, the card locating on a background click, and the `tel:` link ignored.

**Known rough edge:** at ≤768px the timeline is a slide-over that covers the map, so on a phone the pan happens underneath a panel you then have to close. Locating and expanding share one click, and making that click also dismiss the panel would fire on every collapse too — left as-is rather than guessed at.

### Added — switchable basemap, satellite by default

A single basemap was tried first (CARTO Positron, on the reasoning that a desaturated base leaves the vehicle chip / current stop / route line as the only saturated colour) and the operator found it bland. Which basemap reads best is a matter of taste and lighting, not something one default gets right for everyone, so it became the dispatcher's choice instead of another guess:

- **Satellite** (default) — Esri World Imagery, paired with CARTO's transparent `dark_only_labels` tiles. The overlay is not optional: imagery carries no street names, so without it you can see the depot roof but not which road it is on.
- **Streets** — CARTO Voyager. Proper colour, calmer than raw OSM.
- **Muted** — CARTO Positron.

Leaflet's `L.control.layers` at `topleft`, stacking under the zoom buttons — `.map-controls` owns the top right and the vehicle info bar owns the bottom. The selection persists in `localStorage` under `dashboard_basemap`, wrapped in try/catch on both read and write since private-browsing mode throws on access, not only on write. The control is restyled to the dashboard's dark palette rather than sitting on the map as Leaflet's default white rectangle.

**Marker contrast had to become basemap-independent.** With the base switchable, a marker now has to survive both a near-white street map and dark satellite imagery. The vehicle chip and the stop dots each carry a dark fill/ring *and* a 1px light outer ring via `box-shadow` — the dark part defines them on light tiles, the light part on imagery. The stop dots' original plain white border did neither: it vanished on light tiles and took the pale grey `planned` state with it.

Verified under jsdom with real Leaflet: satellite plus its label overlay load by default, the control offers all three, switching swaps the tile layer and writes to storage, a fresh load restores the saved choice, and the autopan suppression from the previous fix still holds afterwards.

### Fixed — the map snapped back to the selected vehicle on every poll

Panning away to look at a street was impossible: within ~12 seconds the map dragged itself back onto the vehicle. Nothing in this codebase was calling `setView`/`panTo` on a poll — it was Leaflet's `Popup._adjustPan()`, which pans the map to keep an open popup in view and is on by default. `zoomToVehicle()` opens the selected vehicle's popup, and for a moving truck **two** separate paths reached `_adjustPan()` on every single poll:

1. `popup.setContent()` → `DivOverlay.update()` → `_adjustPan()` — the popup text carries GPS coordinates and speed, so it differs every poll.
2. `marker.setLatLng()` → fires `move` → `Layer._movePopup()` → `popup.setLatLng()` → `_adjustPan()`.

`updateVehicles`/`updateStops` now run both through a `withoutAutoPan()` helper that flips `popup.options.autoPan` off for the duration and restores it. Suppressed for background updates only — opening a popup still auto-pans (`Popup.onAdd` → `update` → `_adjustPan`), which is what keeps a popup readable when its marker sits near the edge of the map.

Automatic view changes are now limited to Follow mode (`panTo`, explicitly opted into). Zoom-on-select is unchanged: it fires from `selectAssignment()`, which is a direct response to a click and already returns early if the assignment is already selected.

Verified against real Leaflet 1.9.4 under jsdom rather than by inspection: two simulated polls produce four `_adjustPan()` calls (two per poll — confirming both paths were live), all with `autoPan` false, and the map centre after panning away is bit-identical before and after. The same harness with the helper neutered reproduces the bug — centre moves from 10.95/106.90 to 10.874/106.675, i.e. back onto the truck.

### Fixed — map control buttons became unreadable on hover

`.map-control-btn:hover` was `background: rgba(255,255,255,0.12)`. The base state is opaque `--surface-2`, so hovering *replaced* it with 12% white — effectively transparent, letting the OSM tiles through under near-white `--text-primary` text. Zoom Vehicle / Follow / Google Maps / GPS were least readable exactly when pointed at. Hover is now opaque `--surface-3` with an accent border, and `.active:hover` (Follow when engaged) darkens to `--accent-hover` instead of dropping to the neutral hover, which read as "turning off".

### Fixed — the timeline panel would not scroll

Expanding a few stops pushed the rest out of sight with no scrollbar. `.timeline` is a flex column with `overflow-y: auto`, but `.timeline-item` never set `flex-shrink`, so it defaulted to `1`: once the items were collectively taller than the panel the browser squashed them to fit rather than overflowing, and `overflow-y: auto` had nothing to scroll. Each item also carries `overflow: hidden`, so the squashed bodies were clipped rather than merely cramped — which is why the content looked like it had vanished instead of looking compressed. `.timeline-item` is now `flex-shrink: 0`.

**The same defect exists in `.vehicle-list` / `.vehicle-card` in the left panel** (same flex-column-plus-`overflow-y:auto` shape, no `flex-shrink` on the card). It is more visible there because there is no `overflow: hidden` on the card, so text spills between cards instead of being clipped. Left alone per scope control — noted here for whoever picks it up.

### Testing
- `pytest tests/` — **254 passed, 0 failed.** (258 before: the 8 removed authentication tests were replaced by 4 open-access ones.)
- `tests/test_delivery_routes.py`: the `auth_client` fixture is gone, all 82 uses now take the plain `client`. `TestAuthentication` became `TestOpenAccess` — the inverse regression guard, failing if any of the 22 mutating endpoints ever returns 401/403/503 again, plus an assertion that `/login` 404s. The existing reorder-validation tests were already route-level and needed no change.
- All modified JavaScript checked with `node --check`.
- `create_app()` verified to build and register 107 routes with no `/login` among them.

### Not done
- No confirmation step was added in front of the now-ungated destructive endpoints beyond the `confirm()` dialogs already in the UI.
- The plan builder's Step 3 reordering was left alone — the operator confirmed it is already workable.

## 2026-07-31 — Removed the Trip Management / Trip History pages (superseded by Dispatch)

Both pages were the original dispatch UI. The delivery dashboard was later built as a separate implementation rather than reusing them, leaving two pages doing the same job. Dispatch is the one that matches current requirements, so the older pair is gone.

### Removed
- `templates/manage-trips.html`, `templates/trip-history.html`
- `static/js/manage-trips.js`, `static/js/trip-history.js`
- Page routes `/manage-trips` and `/trip-history`
- The "Trips ▾" nav dropdown from all 7 remaining templates (removed whole, not just its two links — otherwise an empty dropdown button would be left behind)
- Eight endpoints whose only callers were those two pages, verified by scanning every surviving `static/js/**` and `templates/*.html` file rather than by assumption: `/api/set-destination`, `/api/trips/history`, `/api/trip-history`, `/api/clear-trip`, `/api/update-trip`, `/api/clear-all-trips`, `/api/geofence-events`. `app/routes/trips.py` drops from 782 to ~500 lines.
  - This also closes the duplicate-endpoint item at `docs/CODEBASE_ANALYSIS_REPORT.md:183` — `/api/trips/history` and `/api/trip-history` both routed to the same function; both are now gone.

### Kept, deliberately
- **`/api/route-data`, `/api/advance-trip`, `/api/cancel-trip`** — these are *not* trip-page endpoints. `static/js/map.js` on the main fleet map calls all three, so removing `app/routes/trips.py` wholesale would have broken the landing page. This was the main risk in the request and the reason the module was narrowed rather than deleted.
- **`/api/refresh-routes` and the background route-refresh thread** — left untouched pending a decision (see below). `/api/refresh-routes` now has no in-app caller, but `app.py` documents it as the external-scheduler entry point for production, which is exactly the mechanism a fix would use.

### Consequence worth knowing
`/api/set-destination` was the **only** way to create a `vehicle_trips` row, and it lived on the Trip Management page. Nothing can create a trip any more, so the main map's surviving route-line / advance / cancel code operates on a table that is empty and can no longer be populated through the UI. Those code paths are effectively vestigial. `map.js` was left alone — it is the landing page and its cleanup was not part of this request. Recorded here rather than actioned silently.

### Not touched
- `vehicle_trips` and `geofence_events` tables — both are empty (0 rows), harmless, and `scripts/migrate_to_delivery.py` still reads `vehicle_trips`. Dropping them is a separate decision.
- The Vietnamese internship report at repo root still documents the removed pages; it is explicitly out of scope per `CLAUDE.md`.
- `graphify-out/` still lists the deleted files — regenerate with `graphify update .`.

### Documentation
- `CLAUDE.md`: the "3 pages still use the legacy global `showToast()`" note is now 1 page (`locations.js`) — the other two were the deleted files.
- `README.md`: `trips.py`'s description narrowed to what it actually does now.

### Testing
- `pytest` — **258 passed, 0 failed**, unchanged. No test referenced the removed pages or endpoints, which is itself a data point: the route-layer suite added in Phase 5 covers delivery, not trips.
- Verified `create_app()` still builds and registers 110 routes, that none of the removed paths resolve, and that the four intended survivors do.

## 2026-07-31 — Delivery Module Phases 4 & 5: Frontend Hardening + Route-Layer Test Suite

Final remediation phases against `docs/DELIVERY_AUDIT_2026-07-31.md`. Each Phase 4 finding was re-verified by execution before implementation, following the C-06 retraction in Phase 3. All three held.

### Fixed — frontend
- **Stale responses could overwrite the current selection (F-05)** — `loadAssignmentDetail()` wrote `state.selectedStops` / `selectedEta` unconditionally once its three requests resolved. The 12-second poll calls it too, so a click landing mid-poll was the common case: the previously-selected vehicle's detail could resolve *after* the newly-clicked one and overwrite it, leaving the vehicle list highlighting one truck while the timeline, map stops and info bar showed another. Added a monotonic generation token — a load writes only if it is still the newest and the assignment is still selected.
- **Unknown ETAs displayed as "ETA: 0 min" (L-10)** — `Math.round(null / 60)` is `0` in JavaScript, and `eta_service` sets `eta_seconds: None` for any stop without coordinates. The info bar therefore told a dispatcher the truck was arriving *now* when the truth was "unknown". `timeline.js` already guarded this with a `typeof` check; `main.js` did not. Verified in Node before fixing.
- **A throwing error-handler could kill polling permanently (F-06)** — `isPolling = false` sat after the try/catch rather than in a `finally`, so anything thrown from the catch block latched the flag and disabled both the 12-second poll and manual refresh for the rest of the session, with the status pill frozen on its last value. Now in `finally`; verified by driving a tick whose error handler itself throws and confirming subsequent ticks still run.
- **Refreshes after an action were silently dropped (F-04)** — `refreshNow()` returned immediately if a poll was in flight, so the refresh chained onto a successful Advance/Skip/Cancel was thrown away and the dispatcher saw no change for up to 12 seconds *on an action they had just taken*. This directly undermined the Phase 3 double-tap fix: the first tap succeeded, nothing visibly happened, and a second tap was the natural response. Requests are now coalesced — a refresh arriving mid-poll runs when the in-flight tick finishes. Verified: three refreshes fired during one slow tick produce exactly one catch-up run, with no overlap.
- **Background tabs polled forever (P-08)** — added `visibilitychange` handling; the interval is cleared while the tab is hidden and resumes with an immediate catch-up tick. Dispatchers leave this page open all day.
- **No client-side request timeout (P-08)** — `/api/eta` issues one ORS call per remaining stop, serially, each with a 30-second server timeout, so a slow route could hang well past the poll interval and freeze the dashboard behind a green "Live" pill. `api.js` now aborts at 20 seconds with a clear message.

### Added — route-layer test suite (T-01)
**`tests/test_delivery_routes.py`, 92 tests.** The audit's most consequential structural finding was that all 49 existing tests imported service modules directly and **nothing exercised the route layer** — which is exactly where every Critical bug lived. C-01 was one line inside a request handler; C-02/C-03 were only observable in an assembled response; C-04 is a property of routes; C-05's duplicate write sat behind an endpoint. A service-level suite is structurally incapable of catching any of them.

Coverage, driving real HTTP through `app.test_client()` with TTAS mocked:
- **GPS pipeline** — GPS reaching the dashboard, telemetry parsed from raw TTAS keys, all five plate formats matching one vehicle, unknown plates not matching, 0,0 reported as no-fix, malformed coordinates not 500-ing, failures surfaced rather than hidden, and ETA not double-normalized.
- **Authentication** — all 22 mutating endpoints parametrized and asserted to reject anonymous callers; read endpoints asserted to stay open; wrong password, logout, and the fail-closed 503 when `DISPATCH_PASSWORD` is unset.
- **Execution lifecycle** — full progression, the double-tap 409 leaving `actual_departure_at` unset, skip/cancel with reasons, current-stop advancement, plan auto-completion, temp-stop insertion reopening a completed plan, and empty-assignment progress.
- **Reorder validation** — full, partial and foreign-id cases, including an assertion that no duplicate `execution_sequence` values are left behind.
- **Excel import** — plate variants collapsing to one assignment with no new vehicles, unknown plates rejected with nothing written, and that no request flag can turn the import into a vehicle-creation path.
- **Uploads** — accepted image types, rejected `.html`/`.svg`/`.php`/`.txt`/extensionless, oversized and empty rejection, traversal in `category` confined to the upload root, two same-second uploads both surviving, and round-tripping an uploaded file back through `send_file`.

### Fixed — test isolation
**The image tests were writing into the repository.** `image_service` derives `UPLOAD_ROOT` from its own file location, so every run left real `.jpg` files in `DeliveryPlans/`; dozens had accumulated. It also made `test_delete_image_removes_file` depend on the checkout being writable — which is why that test failed on every run throughout this work. An autouse fixture in both delivery test files now redirects `BASE_DIR`/`UPLOAD_ROOT` to a per-test temp directory.

**The suite is fully green for the first time: 258 passed, 0 failed.** The single failure reported in the Phase 1-3 entries above was this, not a code defect.

### Testing
- `pytest tests/` (excluding the non-pytest helper scripts) — **258 passed, 0 failed**, up from a 48-passed baseline before this work.
- Polling behaviour verified by executing the module under a browser-like shim rather than by inspection: refresh coalescing, no overlapping ticks, and survival of a throwing error handler.
- All modified JavaScript checked with `node --check`.

### Still open (not in scope for these phases)
- **P-01 / P-02 remain the biggest risk.** Fixing C-01 restored the synchronous TTAS fetch and serial ORS calls into the request path. With 36 vehicles the dashboard will be slower than the broken version was. The audit's Phase 3 proposal — a GPS adapter with a background refresher and parallel/batched ORS — is unimplemented.
- `_route_cache` in `eta_service` is still unbounded (T-10); `get_plan` still N+1 (P-03); missing indexes D-03/D-04 and the duplicate index D-02 are untouched.
- Vehicle identity is centralized for delivery and fuel only; `oil.py` and `fleet.py` keep their own inline plate handling.
- **Verify the Render persistent disk (D-10).** Still the cheapest high-value check available, and everything above is moot without it.

## 2026-07-31 — Delivery Module Phase 3: Execution Correctness (and one retracted audit finding)

Third remediation phase against `docs/DELIVERY_AUDIT_2026-07-31.md`. Before implementing, each Phase 3 finding was re-verified by running it. Two held, one did not.

### Retracted — audit findings C-06 and F-01 were wrong

The audit claimed the dashboard's rebuild cache key `list.map(s => s.id).join(',')` "encodes set membership, not order", so reordering stops produced an identical key and the UI never re-rendered. Rated High / Confirmed.

`Array.prototype.join` preserves order. `[10,11,12].join(',')` is `"10,11,12"`; `[11,10,12].join(',')` is `"11,10,12"`. The key is order-sensitive, a reorder changes it, and both `timeline.js` and `map.js` do rebuild. Verified in Node against the exact expression, and end-to-end: `list_stops()` returns `[3,2,1]` after reordering `[1,2,3]`.

Compounding it, **no frontend code calls `POST /api/stops/reorder` at all** — the only "reorder" match in `static/js/` is a drag handle in the plan *builder*, which reorders locally before save. The dashboard has no reorder UI, so the scenario could not arise either way.

Root cause of the mistake: the "set key" phrasing in the surrounding source comments was taken at face value rather than checked against what `join` does, and the finding was rated Confirmed without executing anything. Both entries are struck through in place in the audit with the disproving evidence, and the document now carries a warning that any remaining "Confirmed" label is provisional until re-verified by execution.

### Fixed
- **A double-tap on Advance marked a stop delivered with no arrival record (C-07)** — confirmed by execution: two calls took a stop `planned` → `arrived` → `completed`, stamping `actual_arrival_at` and `actual_departure_at` **in the same second** and destroying dwell time. If it was the last stop, `_maybe_complete_plan` fired and the plan left the dashboard's active view entirely. On a mobile dispatch UI an impatient second tap is routine, not an edge case.
  - `advance_stop()` now takes an optional `expected_status` — the status the dispatcher's screen was actually showing. When it no longer matches, the move is refused with a message telling them to refresh.
  - The UPDATE additionally carries `AND status = ?`, so if two requests do arrive together only one can affect a row; the loser sees `rowcount == 0` and reports the conflict instead of double-stepping. This closes the genuine race, not just the double-click.
  - `POST /api/execution/advance` returns **409** with `conflict: true` for a stale advance, so the client can distinguish "you're out of date, refresh" from "malformed request".
  - `timeline.js` renders the button with `data-expected-status`, disables it for the duration of the request, and holds an in-flight token per stop+action so a second tap is dropped client-side before it ever becomes a request.
  - `expected_status` is optional throughout — callers that omit it keep the previous behaviour.
- **Assignments with no stops reported "1 remaining" (C-09)** — `total = sum(counts.values()) or 1` put a division guard on the total rather than the division, so an empty assignment showed `total: 1, remaining: 1` on its vehicle card and info bar, and a dispatcher went looking for a stop that did not exist. Only the division needed guarding.
  - The seven-line progress computation existed **twice, verbatim including the bug**, in `get_assignment_progress` and `get_dashboard_data`. Extracted to `_progress_from_counts()` — one home, one fix (audit duplicate-logic cluster 5).
- **`reorder_stops` validated nothing (recorded as C-06b)** — the real bug in the function C-06 wrongly accused. It accepted any list and applied it stop-by-stop:
  - a **partial** list renumbered only the stops it named, producing `execution_sequence` values of `[1, 1, 2]`. Nothing enforces uniqueness on that column, so `ORDER BY execution_sequence LIMIT 1` in `get_current_stop` became non-deterministic — **the dashboard could show the wrong next stop**;
  - ids from a **different** assignment matched no row yet the function returned `True`, so the caller got a silent no-op.

  It now requires the list to name every stop of the assignment exactly once, returns `(ok, message)` matching `advance_stop`'s convention, and names precisely what's wrong (`missing stop(s) [...]` / `stop(s) [...] not in this assignment`). The route surfaces that message instead of a generic "Reorder failed".

### Already done
Phase 3 item 4 (L-06, the plan-status UPDATE inside the per-vehicle loop) was completed in Phase 2 — restructuring that loop made leaving the bug in place indefensible.

### Testing
- `pytest tests/test_delivery.py` — **98 passed, 1 failed**, up from 86. The failure remains the sandbox `unlink` permission artifact documented in the Phase 1 entry.
- 12 new tests across `TestAdvanceAtomicity`, `TestReorderValidation` and `TestProgressWithoutStops`, including assertions that the deliberate two-step progression still works and that a failed double-tap leaves `actual_departure_at` unset.
- 12 end-to-end checks through `app.test_client()`: the double-tap returning 409 with the stop still `arrived`, the genuine second step still succeeding, partial and full reorders, and an empty assignment reporting zero through the dashboard endpoint.
- **`test_progress_empty` was rewritten.** It asserted `total == 1` with the comment *"fallback to avoid div-by-zero"* — it encoded C-09 as intended behaviour, the same category of problem as the GPS contract tests corrected in Phase 1. Two of the three tests changed in these phases were wrong rather than merely outdated.

## 2026-07-31 — Core Fleet Data Is Now Read-Only to Background Processes

Follow-on to Phase 2, at the user's direction and widened beyond the delivery module. The rule: **`vehicles` is the source of truth, and only a human editing Vehicle Management may change it.** New data flowing into the system may read and link to a vehicle, never create one, and never silently alter core fields — plate number, vehicle type, dimensions, or driver name.

Phase 2 stopped the delivery import from creating vehicles. This entry removes every remaining path.

### Fixed
- **Logging fuel created vehicles and overwrote the driver name (`app/routes/fuel.py`)** — the worst of the remaining offenders, and live on every fuel entry. `INSERT INTO vehicles ... ON CONFLICT(plate_number) DO UPDATE SET current_driver = ...` meant:
  - a plate not stored byte-identically created a new vehicle, so logging fuel for `50E18463` while the fleet held `50E-18463` produced a duplicate truck — the same root cause as C-05, still shipping;
  - whatever name was typed on the fuel form silently became the vehicle's official `current_driver`. A relief driver covering one shift would permanently overwrite the assigned driver, with nothing shown to anyone.

  Both removed. The plate is now resolved through `services.vehicle_identity` (exact → canonical → 5-digit serial) and the fuel row is stored under the fleet's canonical plate. The same check was added to the edit path, so an edit can't introduce an unknown plate either.
- **The boot migration re-ran that upsert across all fuel history on every startup (`app/database/migrations.py`)** — `backfill_vehicles_from_fuel_log` is now **link-only**: it resolves unlinked `fuel_log` rows onto existing vehicles and normalises their plate, and never inserts or edits a vehicle. Plates matching nothing are left alone and named in a warning log rather than conjured into existence.
- **`scripts/migrate_to_delivery.py` created a vehicle for any key it couldn't find** — now resolves everything up front and aborts with the full list of unregistered plates, refusing to run rather than inventing rows.

### Changed — unknown vehicle now prompts instead of failing
Rejecting an entry outright would block someone standing at a petrol station. Instead, an unrecognised plate returns **409** with a structured body, and the UI offers to go register it:
- `services/vehicle_identity.unknown_vehicle_response()` returns `error_code`, a plain-language `message`, a `redirect_to` URL, and an `unknown_vehicle` block carrying what's already known.
- `suggest_plate_format()` turns `51D99999` into `51D-99999` (two province digits, one-or-two series letters, 4-5 digit serial) so the form arrives with a well-formed plate. It is a *suggestion in an editable field* — it never rewrites stored data, and returns the input unchanged when the shape isn't recognised.
- `static/js/fuel-efficiency.js` catches the rejection, confirms with the user, and redirects. `static/js/vehicle-management.js` reads `?new=1&plate=…&driver=…`, opens the Add Vehicle dialog pre-filled, focuses the type field, and clears the query string so a refresh doesn't reopen it. If the vehicle turns out to already exist it opens it for editing instead of offering a duplicate.
- **Dimensions are deliberately not pre-filled.** Nothing upstream knows them, and guessing core specs is the behaviour being removed.
- `ApiClient.fetch` (`static/js/utils.js`) now attaches the response body and status to the thrown `Error` (`err.data`, `err.status`). Callers reading only `err.message` are unaffected.

Because matching is loose, this prompt fires only for a truck genuinely not in the fleet — not for a formatting difference. `50E-18463`, `50E18463`, `50E 18463`, `50e-18463`, `18463` and a padded ` 18463 ` all resolve to the same vehicle, verified by test.

### Reviewed and left alone
- **`app/routes/fleet.py`** — Vehicle Management. The legitimate owner; creating and editing a vehicle is the explicit point of the request.
- **`services/google_sheet_service.py`** — already correct. It resolves on the 5-digit serial and skips unknown plates with a warning; its docstring already said *"the system never creates new vehicles from sync data."*
- **`truck_load_planner/routes.py`** — writes `container_configs`, which is user-driven container spec management, not automatic.
- **The one-time `tlp_trucks` → `container_configs` migration** (`migrations.py`) is the single remaining place outside Vehicle Management that writes a core field (`container_config_id`, i.e. dimensions). Kept: it does not act on new data, it relocates dimensions the user already entered from a retired table, and it is double-guarded to run once per database lifetime. It now **logs a warning naming what it changed** — the objection was to silent alteration, not to migration.

### Added
- **`tests/test_vehicle_core_data.py`** — 36 tests asserting the invariant directly, so it can't quietly regress:
  - the boot migration links fuel history without modifying `vehicles`, and does not overwrite `current_driver` from a fuel form;
  - a static scan of ten modules for `INSERT INTO vehicles` and for `UPDATE vehicles SET` touching `plate_number` / `vehicle_type` / `current_driver`;
  - an assertion that `container_config_id` is written in exactly one file;
  - `vehicle_identity` exposes no write helper of any kind;
  - the loose-match sweep, so the "new vehicle" prompt can't start false-firing on a format variant.

### Testing
- `pytest tests/test_delivery.py tests/test_vehicle_core_data.py tests/test_scorer.py` — **148 passed, 1 failed**. The single failure is the sandbox `unlink` permission artifact documented in the Phase 1 entry, unrelated and expected to pass on Windows.
- 15 end-to-end checks through `app.test_client()` confirming the vehicles table is byte-identical before and after fuel logs submitted under a *different* driver name — the exact scenario that previously rewrote `current_driver`.
- Two bugs were caught by the new tests rather than by review: the dimension-writing migration above, and (during Phase 2) a mis-grouped bare serial.

### Note
While editing `app/routes/fuel.py` I initially split its `from app import config, state` import and briefly broke the module; caught by a syntax/import check before any test run. Flagging it because the file is large and worth a skim on your side.

## 2026-07-31 — Delivery Module Phase 2: Vehicle Identity Service

Second remediation phase against `docs/DELIVERY_AUDIT_2026-07-31.md`. Closes C-05 (Excel import silently creating duplicate vehicle rows), L-03 (one truck split across two assignments), T-12 (the duplicate-merge script gone stale), and — unavoidably, see below — L-06.

The audit found seven plate-identity implementations with five incompatible semantics, and a canonical normalizer (`services/plate_utils.py`) that the delivery module had never imported. Phase 1 pointed delivery's GPS matching at it; this phase gives the whole concern a home.

### Added
- **`services/vehicle_identity.py`** — resolution only. **The module has no write path at all**: there is no `create_vehicle()`, no insert, no upsert. `resolve()` returns a `VehicleRef` or `None`, and adding a truck to the fleet is a Vehicle Management action (`app/routes/fleet.py`), never a side effect of importing a spreadsheet. A test asserts the module never grows a write helper.
  - Match precedence, strictest first: exact `plate_number` → canonical (case/separator-insensitive, matching what `ttas_client.py` already does for TTAS report dropdowns) → 5-digit serial via `normalize_plate`. `matched_by` on the result records which strategy won, so a dispatcher can be told *why* a plate matched. Confirmed against real fleet data: `50E-18463`, `50E18463`, `50E 18463`, `50e-18463`, `18463` and even an en-dash `50E–18463` all resolve to the same vehicle row.
  - **Ambiguity is refused, not guessed.** Two genuinely different full plates sharing a serial (`50H-18463` / `51C-18463`) disable serial matching for that serial and log a warning, rather than attaching stops to whichever truck happened to be indexed first.
  - **Bare-serial duplicate rows lose to full plates**, including on exact match. A row whose `plate_number` is just `09473` is a known artifact of the old Google Sheet sync that `tests/merge_duplicate_vehicles.py` exists to delete; new assignments must not attach to a row a future merge will remove. This surfaced as a genuine test failure during the phase and the resolver was corrected, not the test.
  - `VehicleIndex` is built once per operation rather than per lookup — `app/routes/fuel.py` currently re-scans the whole `vehicles` table on every insert (audit P-06) and this is the seam to fix that behind later.
  - **Deliberately not built: a `vehicle_aliases` table.** `normalize_plate` already collapses every variant present in this fleet's data, so an alias registry would be an empty table solving a problem that does not exist yet. `resolve()` is the seam if genuinely arbitrary aliases ever appear.

### Fixed
- **Excel import created duplicate vehicles on any plate-format variance (C-05)** — `confirm_import` built `{plate_number: id}` and did exact-string lookup; a miss ran `INSERT INTO vehicles`. A spreadsheet saying `50E18463` against a stored `50E-18463` produced a 37th vehicle with no type, no driver and no GPS association, polluting `/api/fleet/vehicles`, the TLP picker and fuel/oil reporting — and the delivery assignment attached to the phantom, so it could never match GPS even after Phase 1. Import now resolves through `vehicle_identity`; an unrecognised plate raises `UnknownVehicles` and the whole import rolls back with nothing written.
  - **Imports never create vehicles, under any circumstance.** There is no override flag. An unknown plate in a plan is a typo or an unregistered truck — not a format this resolver can't handle, since it already matches on the 5-digit serial regardless of how the sheet spelled it. `confirm_import`'s signature is asserted in tests to have no creation escape hatch.
  - `POST /api/plans/import/save` returns **409** (not 400 — the request is well-formed, it conflicts with fleet state) carrying `unknown_vehicles`, naming exactly which plates to check.
- **One truck imported as two assignments (L-03)** — grouping keyed on the raw spreadsheet string, so a file mixing `50E-18463` and `50E18463` split one driver's stops across two dashboard rows. Rows now group by *resolved vehicle id*. **Unresolved identifiers group by their 5-digit serial**, since that is what distinguishes a vehicle in this fleet — so `51D-77777`, `51D77777` and a bare `77777` are reported as one problem to fix rather than three. (Caught by a test written for this phase: canonical-form grouping collapsed the first two but not the bare serial.)
- **`preview_import` now reports resolution** when given a `db_path` — each assignment carries `resolved`, `resolved_plate`, `matched_by`, and the response carries `unknown_vehicles`. Unknown plates surface at preview time rather than as a failure at save time. The parameter is optional and the old behaviour is preserved without it.
- **`tests/merge_duplicate_vehicles.py` was stale (T-12)** — `INTEGER_FK_TABLES` listed only `fuel_log` and `tlp_load_plans`. The delivery module shipped after that script was written, so merging a duplicate would either abort on the `vehicles` DELETE (`vehicle_assignments.vehicle_id` has no `ON DELETE` action, and `DatabaseManager` enables FK enforcement) or, with FKs off, leave every assignment pointing at a deleted vehicle. Added `("vehicle_assignments", "vehicle_id")`.
- **Plan status UPDATE ran inside the per-vehicle loop (L-06)** — scheduled for Phase 3, but this phase restructured that exact loop and leaving a known bug in freshly-written code was indefensible. It now runs once after the loop, and only when at least one assignment was created: an empty import used to return success while the plan silently stayed `draft` and never reached the dashboard. **Phase 3 item 4 is therefore already complete.**

### Changed
- `confirm_import` returns a summary dict (`assignments_created`, `stops_created`, `plan_confirmed`) instead of a bare `True`, and the route passes it through. `plan_confirmed: false` is how an empty import now reports itself honestly.

### Still open: other paths that auto-create vehicles
Delivery no longer writes to `vehicles`. Three other places still do, and two of them can create the same duplicates C-05 created. Documented, not changed — they are outside this phase's scope and touch live fuel/oil data.
- **`app/routes/fuel.py:437`** — logging fuel upserts the vehicle by exact `plate_number`. `ON CONFLICT(plate_number)` only matches a byte-identical string, so recording fuel against `50E18463` while the fleet holds `50E-18463` **creates a duplicate row today**. Same root cause as C-05, still live, and the highest-value next target for `vehicle_identity`.
- **`app/database/migrations.py:179`** — `backfill_vehicles_from_fuel_log` upserts vehicles from `fuel_log` on every boot, with its own inline copy of the last-5-digit logic.
- **`scripts/migrate_to_delivery.py:84`** — one-off migration script, same exact-match-then-insert pattern.
- `app/routes/fleet.py:65` is the legitimate one: Vehicle Management, where adding a truck is the explicit point of the request.

### Testing
- `pytest tests/test_delivery.py` — **86 passed, 1 failed**, up from 59 after Phase 1. The single failure is the same analysis-sandbox `unlink` permission artifact documented in the Phase 1 entry; unchanged by this phase and expected to pass on Windows.
- 27 new tests across `TestVehicleIdentity`, `TestImportVehicleResolution` and `TestPreviewImportResolution`, including a parametrized sweep of all seven stored/lookup format combinations, the ambiguous-serial refusal, the bare-serial-duplicate preference, an assertion that a rejected import writes **nothing** (vehicle count unchanged, plan still `draft`), and a signature assertion that `confirm_import` cannot be talked into creating a vehicle.
- 12 end-to-end checks through `app.test_client()` covering the strict-import behaviour, plus the earlier full merge-script scenario: a delivery assignment pointing at a duplicate `09473` row is correctly repointed to `50H-09473` and the duplicate deleted — the exact operation that would have silently orphaned data before the FK-list fix.

### Notes
- **The Excel import pipeline has no frontend consumer.** `delivery-plan-builder.js` builds plans manually through the already-correct `vehicle_id` path and never calls `/api/plans/import/*`. The 409 change therefore has no UI blast radius.
- `merge_duplicate_vehicles.py` still has no guard for missing tables (it would already fail this way on `tlp_load_plans`). Any database the app has booted against will have `vehicle_assignments`, since `create_app()` calls `init_delivery_tables()` unconditionally, so the added entry does not create a new realistic failure path. Left as-is rather than widen this phase's footprint.
- Vehicle identity is now centralized *for the delivery module only*. `fleet.py`, `fuel.py`, `oil.py` and `migrations.py` still carry their own inline variants (audit duplicate-logic cluster 1). Migrating them is deliberately deferred — delivery had zero production rows and was a zero-risk proving ground; fuel and oil have live data and working reports.

## 2026-07-31 — Delivery Module Phase 1: GPS Pipeline Repair + Security Hardening

First remediation phase against `docs/DELIVERY_AUDIT_2026-07-31.md` (68 findings). Closes the five Critical items and the two highest-severity security findings. The audit's central conclusion drove the ordering: the dashboard's GPS was not "unreliable", it was **dead**, and had been since the module was written — four defects stacked on top of each other, only the last of which was the plate-format mismatch the team had identified.

### Fixed

- **GPS pipeline was entirely non-functional (C-01)** — `services/delivery/routes.py` did `from app import fetch_vehicle_data` inside a bare `except Exception`. That name resolves to the `app` **package**, which has never exported it (it lives in `app/services/ttas_client.py`; `app.py` and `app/routes/trips.py` both import it correctly). Every call raised `ImportError`, was swallowed, and returned `([], "error", ...)` — so `/api/execution/dashboard` never attached a `gps` key to any assignment, `/api/eta` always returned "Vehicle GPS not available", no map marker was ever created, and Zoom/Follow/Open-in-Google-Maps were permanent no-ops. Now imported at module scope from `app.services.ttas_client`, so a regression of this kind aborts `create_app()` instead of silently degrading one request at a time. `_ttas_vehicles()` keeps a narrow `except` but logs a traceback rather than flattening it into an empty list.
- **GPS normalization read the wrong dict schema (C-02)** — `tracking_service.normalize_gps_position()` read `speed_status` / `vehicle_status` / `engine_status` / `last_update` / `driver_name`, which are the *output* key names of `normalize_vehicle()`, from *raw* TTAS DevList items whose keys are `speed` / `ad3` / `trktime` / `driver` / `biensoxe`. Every one of those resolved to its default, and no `device_name` was emitted at all — so even with C-01 fixed there was nothing to match a position to a vehicle on. Rewritten to delegate raw-key parsing to `normalize_vehicle()` rather than reimplement it: that function already owns the six-key plate fallback chain, the Vietnamese speed-phrase → status derivation, and `safe_float`/`clean_text` coercion, and duplicating it would create a second source of truth for TTAS's field names. Also emits `plate_key` (the normalized 5-digit serial) so callers never have to re-derive it.
  - Related, same root cause: `routes.py`'s ETA handler called `normalize_gps_position()` a **second** time on an already-normalized dict, whose keys are `lat`/`lng` rather than `latitude`/`longitude` — coercing both to `0.0` and placing the vehicle at 0°N 0°E. Removed.
  - `safe_float()` returns `0.0` (not `None`) for missing coordinates, so an exact 0,0 reading is now reported as `lat: None, lng: None` — "no fix" rather than a position in the Gulf of Guinea. The frontend's existing `if (!gps || gps.lat == null)` guard already handles it.
- **Plate matching (C-03)** — `.strip().lower()` on both sides matched only byte-identical strings, and was also inconsistent with the rest of the codebase (`fleet.py`/`fuel.py`/`oil.py` all use `.upper()`). Both sides now go through `services.plate_utils.normalize_plate` — the canonical, already-documented normalizer that `google_sheet_service.py` and `merge_duplicate_vehicles.py` use but which the delivery module had never imported. `50E-18463`, `50E18463`, `50E 18463`, `50e-18463` and `18463` now all resolve to the same vehicle. New `_gps_by_plate_key()` helper indexes positions once per request and warns on serial collisions instead of silently keeping an arbitrary one.
- **No authentication on any endpoint (C-04)** — including `POST /api/plans/clear`, which cascade-deletes every plan, assignment, stop, execution record and image row, and was reachable unauthenticated on a publicly-deployed host. New `app/auth.py`: session-based login against a shared `DISPATCH_PASSWORD`, `hmac.compare_digest` comparison, `@login_required` applied to all **22** mutating endpoints. GET endpoints deliberately left open so the 12-second dashboard poll keeps working — locking reads risked taking dispatch dark for less exposure removed than it sounds (stop addresses and manager phone numbers remain readable without auth; tracked as follow-up, not fixed here).
  - **Fails closed**: with `DISPATCH_PASSWORD` unset, mutating endpoints return 503 rather than allowing access. An unset secret must not silently reopen the hole. **This means the variable has to be set before deploying** — see Deployment note below.
  - Session cookies hardened in `create_app()`: `HttpOnly`, `SameSite=Lax` (which also blocks the cross-site POSTs that would be the CSRF vector against the newly-protected endpoints — a mitigation, not a substitute for CSRF tokens), `Secure` outside debug, 14-day lifetime.
- **Stored XSS in the dispatcher dashboard (S-02)** — `map.js`, `timeline.js` and `main.js` each carried a private `escapeHtml` that built a text node and read back `.innerHTML`. Per the HTML fragment-serialization algorithm that escapes only `&`, `<`, `>` and NBSP — **not quotes** — while the canonical `UI.escapeHtml` in `utils.js` (already loaded by the same page, already used correctly by `vehicle-list.js`) does escape both quote characters. All three sinks were attribute-context: `map.js` `title="${escapeHtml(s.station_name)}"` and `timeline.js` `title=`/`alt="${escapeHtml(img.category)}"`, where `station_name` comes from Excel import or `POST /api/stops` and `category` comes straight from an unvalidated form field. All three private copies replaced with `UI.escapeHtml`. This is the same class of bug the 2026-07-29 refactor fixed elsewhere — these three files were missed then.
- **Stored XSS via plan status (S-03)** — `main.js`'s manage-plans list interpolated raw `p.status` into both a `class` attribute and a text node with no escaping, and `PUT /api/plans/<id>` accepts arbitrary strings for it (no `CHECK` constraint on the column). The class now maps onto a known-status allowlist and the display value is escaped. The server-side status enum remains open — deferred to Phase 4 where it belongs with the other schema constraints.
- **Path traversal to arbitrary in-repo file write (S-04)** — `image_service.ensure_folder()` interpolated `station_code` and `category` straight into the upload path, both attacker-controlled, so `../../../static/js` let `mkdir(parents=True)` + `save()` write into served static directories. New `_safe_path_segment()` strips separators and traversal sequences, falls back to a constant when a value reduces to nothing, and caps length; `ensure_folder()` additionally re-checks containment under `UPLOAD_ROOT` after resolution. `serve_image` re-checks containment too, since rows written before this fix could still point outside.
- **Unrestricted upload type and size (S-05)** — no extension allowlist, no size cap, no MIME check, and `serve_image` hands the stored path to `send_file()`, which infers `Content-Type` from the extension — so an uploaded `.html` or `.svg` was served as `text/html`/`image/svg+xml` from the application's own origin. Added `ALLOWED_EXTENSIONS` (SVG excluded deliberately: it is an image format that can execute script), a 10 MB per-file limit sized without buffering the payload, and a 25 MB `MAX_CONTENT_LENGTH` ceiling on all request bodies. Rejections surface as 400 with a readable message via the new `UploadRejected` exception.
- **Image filename collisions destroyed evidence (C-08)** — not in the Phase 1 brief, but fixed here because it is a two-line change inside the exact function being hardened for S-05. Filenames were `{unix_seconds}{ext}`, so two photos of the same stop and category in the same second silently overwrote each other, leaving two DB rows pointing at one file. Now suffixed with 8 hex chars of a UUID, keeping the sortable timestamp prefix.

### Added
- `app/auth.py`, `templates/login.html` (styled from the existing `style.css` variables), `GET /api/auth/status` so the frontend can show a login/logout control without probing a mutating endpoint.
- `app/config.py`: `DISPATCH_PASSWORD`, `SESSION_LIFETIME`, `MAX_UPLOAD_MB`. Deliberately **not** added to `required_env_vars` — that would make the app refuse to boot for every existing deployment; `app/auth.py` fails closed per-request instead, so the failure is visible and scoped rather than silent or total.
- `api.js` now redirects to `/login` on a 401 (preserving the return path) and surfaces the 503 "auth not configured" message verbatim rather than as a bare `HTTP 503`.
- `/api/execution/dashboard` returns `gps_matched` and `gps_available`. The dashboard already received `gps_source`/`gps_error` and displayed neither — had the status pill shown "GPS: error" instead of a green "Live" over an empty map, C-01 would have been caught on day one. Wiring these into the UI is Phase 4.

### Testing
- `pytest tests/test_delivery.py` — **59 passed, 1 failed**, up from a 48-passed baseline. The single failure (`test_delete_image_removes_file`) is an analysis-sandbox artifact: the mounted filesystem returns `Operation not permitted` on `unlink`. Verified as environmental by re-running the identical delete flow with `UPLOAD_ROOT` pointed at a writable temp dir — passes there. **Expected to pass on Windows.**
- 22 end-to-end checks driven through a real `app.test_client()` with a mocked TTAS payload: GPS reaching the dashboard, a `50E18463`-vs-`50E-18463` mismatch resolving, telemetry parsed from raw keys, coordinates not 0,0, every auth boundary (open GET, blocked POST/PUT/DELETE, wrong password, correct password, unconfigured 503), path-traversal neutralisation, and the upload allowlist and size cap. 22/22.
- The three `TestTrackingService` GPS tests that the audit flagged as encoding the *wrong* contract (T-02) were rewritten rather than patched — they fed `speed_status`-keyed dicts and so passed against a function that could never work in production. Now built on a raw-TTAS fixture and expanded from 5 tests to 13, including a parametrized sweep of the five plate formats.
- `FakeFileStorage` in the test suite gained a `.stream`, which a real Werkzeug `FileStorage` always has. Its absence had let the fake pass tests a real upload could not.

### Deployment note
**`DISPATCH_PASSWORD` must be set before the next deploy** or every mutating delivery endpoint will return 503 (reads and the rest of the app are unaffected). Not added to `render.yaml` — it is a secret and should be set in the Render dashboard, not committed.

### Known limitations / deliberately not fixed here
- Fixing C-01 restores the synchronous TTAS fetch and serial ORS calls into the request path — audit P-01/P-02. Phase 1 makes GPS *correct*, not *fast*; under 36 vehicles this will be slower than the broken version was. Ship to staging first; Phase 3 addresses it.
- `tests/test_delivery.py`'s image tests write into the real `DeliveryPlans/` upload root rather than a temp dir, and have left ~30 stray `.jpg` files there across previous runs. Test-infrastructure fix, deferred.
- `services/delivery/tracking_service.py` now transitively imports `app.config` (via `ttas_client`), which raises when `.env` is absent. Kept out of module scope via a deferred import so the pure-function tests still work without a configured environment, but the coupling is new.
- Route-layer tests exist only as the ad-hoc verification script above; the permanent suite is Phase 5.

## 2026-07-30 — Documentation Reorganization: Consolidated into docs/

Prompted directly by the redundancy this session's TLP work kept running into: the algorithm was documented three times (`SORTING_STRATEGY.md`, `SYSTEM.md`'s "Sorting Algorithm" section, `README.md`'s "Algorithm Reference" section) and had drifted — only `SORTING_STRATEGY.md` was kept current through Phases 1-6 above, so the other two were actively wrong (still describing the pre-Phase-1 4-term scorer, `LargestFirstStrategy`-only single-vehicle default, and pure `LargestVehicleFirstStrategy` multi-vehicle distribution). The delivery module was documented twice (`DELIVERY_MODULE.md`, and a smaller duplicate inside `SYSTEM.md`). User asked for all docs reorganized into a `docs/` folder with redundant/repetitive content removed, keeping documentation minimal.

### Changed
- **New canonical TLP doc**: `docs/TRUCK_LOAD_PLANNER.md` — merges the (kept-current) `SORTING_STRATEGY.md` with `SYSTEM.md`'s non-duplicated TLP content (3D step-animation controls, 2D canvas coordinate mapping, TLP database schema, auto-arrange API request/response shape, frontend validation-panel behavior). Root `SORTING_STRATEGY.md` and `SYSTEM.md` deleted — their content isn't lost, it's here, once, current.
- **Moved into `docs/`, unchanged content**: `CHANGELOG.md` (this file), `CODEBASE_ANALYSIS_REPORT.md`, `DELIVERY_MODULE.md` (already the more complete of the two delivery docs — `SYSTEM.md`'s duplicate section was simply dropped, not merged, since it had nothing `DELIVERY_MODULE.md` lacked).
- **`README.md`** (stays at repo root — universal convention): removed its stale "Algorithm Reference" and "Engine Architecture" sections (now pointers to `docs/TRUCK_LOAD_PLANNER.md`), updated the TLP test-count/command reference for `tests/test_auto_arrange_e2e.py` (added this session, Phase 5).
- **`CLAUDE.md`**: Reference Documents section updated to the new `docs/` paths; removed the `INSTRUCTIONS.md` entry (file doesn't exist — a stale reference to an already-retired original delivery-module spec, confirmed no-longer-needed).
- Fixed path references in code comments that pointed at the old root locations: `truck_load_planner/engine/support.py`, `app.py`.

### Removed
- `docs/MASTER_PLAN.md` + `docs/PHASE_1_Live_Updates.md` through `PHASE_5_Real_Time.md` — the original pre-build planning specs for the Dispatch module, which per this file's own history is already built and shipped (Phases 1-3 QA'd, see the dated entries below). Same category as the retired `INSTRUCTIONS.md`: a historical spec superseded by what's actually in the code and in this changelog, not living reference documentation.

### Not touched (explicitly out of scope)
- The two Vietnamese internship-report files at repo root — personal academic documents unrelated to the app, already flagged as out-of-scope in `CLAUDE.md`.
- `CLAUDE.md`/`AGENTS.md` themselves — agent-instruction/config files auto-loaded by tooling, not documentation-about-the-codebase; moving them would break the mechanism that reads them.

## 2026-07-30 — Truck Load Planner Phase 6: Frontend Fidelity Fixes

Final phase of the 6-phase truck-load-planner improvement plan (Phases 1-5 above). Closes the "is it the algorithm or the UI" question the investigation opened with: the frontend independently recomputed some metrics, misrendered rotated packages in 3D, and let manual edits bypass backend validation entirely — meaning some of what looked like "the algorithm produced instability" was actually the UI, not the backend. `static/js/truck-load-planner.js` only.

### Fixed
- **Floor-utilization stat counted every placement, including stacked ones** (`updateStatus()`) — a package stacked on top of another doesn't occupy new floor space, but the client-side calculation summed every placement's footprint regardless of `z`, inflating the floor % once anything was stacked. Volume and weight stats were checked too and are mathematically identical to the backend's `volume_used_pct`/weight sum already (same simple formula, no real divergence) — left as-is rather than force a backend round-trip for numbers that were already correct. Fixed to only count `z === 0` placements, matching `engine/statistics.py::compute_statistics`'s `floor_used_pct` exactly.
- **3D view ignored package rotation** (`update3DScene()`) — the package mesh loop always built box geometry from raw length/width regardless of `rotation`, while the 2D top/side/back views already correctly swap them for 90°/270° (`_drawPackages()`). A validly-placed rotated package rendered with the wrong box extents in 3D only, making a correct backend placement look wrong. Fixed to swap length/width for 90°/270°, matching `_drawPackages()`. Verified in-browser: forced a placement to `rotation: 90` and confirmed via the actual THREE.js mesh geometry that its box dimensions swapped (`1200×1000` vs. an unrotated same-type package's `1000×1200`) and repositioned correctly.
- **Manual drag/rotate edits were never re-validated against the backend** (`_validateAllPlacements()`) — the method was a literal stub (comment: "For comprehensive validation, we'd call the batch endpoint / For now, just update the UI based on status calculation") that only re-ran the client-only checklist, which has no support/stacking check at all. A dispatcher could drag a package into an unsupported or otherwise backend-invalid position and the UI would still show "All checks passed." No new backend endpoint was needed — wired to the existing single-placement `/api/tlp/session/validate` route (already used for new-package-from-palette drops), called with the moved placement's new position against the rest of the plan. `updateValidationUI(result)`'s `result` parameter existed but was dead code (never passed by any caller) — now actually used: when the backend rejects a placement, the status bar shows its real reason instead of just "Issues detected".
  - Ordering fix found during this same change: `updateStatus()` calls its own no-arg `updateValidationUI()` internally, so the backend-informed call had to run *after* it in the `dragend` handler, or it would be immediately overwritten by the client-only recompute.

### Testing
- Started the dev server (`python app.py`) and drove the actual Truck Load Planner page in-browser against a real fleet vehicle (50E-18463, 13 real packages) rather than a synthetic fixture.
- Auto Arrange: 13/13 placed, all 5 client-side checks passed, no console errors.
- Forced a rotation via the console and confirmed the 3D mesh geometry swap directly (not just visually) — see above.
- Dragged a package into a real collision with a neighbor: validation panel flagged "No collision" ✗ and the status bar showed the actual backend reason ("Collision with nearby package") pulled through `updateValidationUI(result)` — confirms the stub replacement works end-to-end, not just in isolation. Undid the drag; re-confirmed "All checks passed" and zero console errors throughout.
- One pre-existing console exception (`filterPackages`, `this.placements is not iterable`, fires during `init()` before a vehicle is selected) was observed but not touched — present before this phase's changes and outside its scope.
- Backend suite unaffected by this phase (no Python changes): `pytest tests/test_scorer.py tests/test_auto_arrange_e2e.py -v` — 31/31 passing.

## 2026-07-30 — Truck Load Planner Phase 5: Regression Test Coverage (+ 2 stacking bugs it caught)

Phase 5 of the 6-phase truck-load-planner improvement plan (Phases 1-4 above). `tests/test_scorer.py`'s 26 tests are real but narrow (0-2 packages, unit-level); `tests/test_all.py` matches pytest's `test_*.py` discovery but contains zero `test_*` functions, so it silently contributes nothing despite having real end-to-end logic. Neither covered utilization, stacking correctness, or multi-vehicle truck-count behavior at realistic scale — exactly the properties Phases 1-4 changed. New file: `tests/test_auto_arrange_e2e.py`, 5 tests, deterministic (fixed dimensions, no randomness), ~3.4s total.

### Fixed (found while writing these tests, not part of the original plan)
Writing a real end-to-end stacking test — with no explicit `max_stack_layers` set on any package, the common case — finally exercised the Phase 1 hard-cap path under realistic conditions and surfaced two bugs in it:
- **The Phase 1 hard cap didn't actually limit tower height.** `max_stack_layers`/`_count_above` enforces *breadth* (how many separate packages can share one base's top surface), not *depth* — a linear single-file column never has more than one package directly on any given package, so the breadth check can never block it from growing. A tall single-column test towered until it hit the container's physical height boundary, not the intended cap (16 packages stacked in a 5000mm-tall container before this fix). Added `_tower_depth()` and a real column-depth check in `check_support` — an actual hard constraint on how many packages deep a single-file stack can go, independent of the breadth check.
- **`_count_above` wasn't scoped to XY overlap with the specific base package** — it counted *any* placement in the entire plan sharing the same Z-height, not ones actually stacked on that base. A 2000-candidate check found this was mostly dormant before Phase 1 (only triggered for packages with an explicit non-zero `max_stack_layers`, which is rare), but Phase 1's fallback made it load-bearing for the ~100% of packages that don't set one — meaning it could reject a valid stack because an unrelated package happened to share its height elsewhere in the container. Fixed to require actual XY overlap with the base, matching its docstring's original intent. (A related bug in `check_support`'s "packages directly below" collection has the same root cause but was deliberately left alone during Phase 3 — see that phase's entry — since it wasn't something this session's changes newly activated.)

### Added
- `test_single_vehicle_realistic_shipment_all_placed_with_reasonable_utilization` — 20-package fixed shipment, asserts full placement and a utilization floor (catches a catastrophic regression, not tuned to an exact number).
- `test_stacking_used_when_floor_alone_is_insufficient` — a scenario sized so floor space alone can't fit everything; asserts stacking is actually used.
- `test_stack_depth_hard_cap_is_enforced` — the tall single-column scenario above; asserts no column exceeds `_SYSTEM_MAX_STACK_LAYERS`. Would have caught the depth-cap bug fixed above.
- `test_distribute_across_vehicles_prefers_single_smallest_fitting_truck` — small shipment, asserts only the smallest van gets used (Phase 4's single-truck preference).
- `test_distribute_across_vehicles_minimizes_truck_count_for_multi_truck_shipment` — a shipment sized to genuinely need multiple vehicles; asserts the two smallest vans are never touched. Would have caught a regression back to Phase 4's fixed smallest-first fallback.

### Testing
- `pytest tests/test_scorer.py tests/test_auto_arrange_e2e.py -v` — 31/31 passing, 3.66s total.
- Test parameters (package/container dimensions, counts) were empirically calibrated against the real algorithm rather than computed from theoretical volume — real packing efficiency for large-relative-to-container boxes came in well under naive volume-ratio estimates during calibration, which is itself a useful data point for anyone tuning `usable_space`/candidate generation further.

## 2026-07-30 — Truck Load Planner Phase 4: Vehicle Candidate Selection to Minimize Truck Count

Phase 4 of the 6-phase truck-load-planner improvement plan (Phases 1-3 above). Prompted by a scope addition: fixing per-truck packing quality doesn't help if the system picks more/larger trucks than necessary for a shipment — more trucks means higher operating cost. While investigating, found uncommitted, untracked WIP already sitting in the working tree (`engine/vehicle_selection.py`, wired live as the default via `distribution.py`) attempting exactly this, with two real defects fixed here rather than reverted (per direction, treated as scratch — structure kept, logic redesigned).

### Fixed
- **Multi-truck fallback filled small vehicles before large ones** (`engine/vehicle_selection.py::SmallestVehicleThatFitsStrategy`) — when no single vehicle could hold an entire shipment, the fallback reused ascending (smallest-first) order for the incremental multi-vehicle loop, which tends to *increase* the number of trucks needed compared to largest-first. Now falls back to descending (largest-first) order; the placement loop's existing `if not remaining_pkgs: break` naturally stops recruiting more vehicles once everything is placed, so this is enough to minimize truck count without needing a separate capacity-estimation step.
- **Single-vehicle-fits-all probe ran the full 15-pass `optimized` strategy per candidate vehicle** before any real placement decision — now probes with a single fast pass (`largest_first`) instead, only spending the expensive `optimized` pass once, on the vehicle that already proved feasible, to refine the final layout.
- **Added a cheap feasibility prefilter** (`_cheap_could_fit_all`) — total package volume/weight vs. vehicle capacity, and each package's footprint (with rotation) vs. cargo cross-section — to skip an arrangement attempt against a vehicle that obviously can't work, before spending any real placement cost on it.
- **Consolidated the duplicated per-vehicle placement loop** (`engine/distribution.py::distribute_across_vehicles`) — it previously maintained a second, independently-written copy of the single-vehicle path's placement loop (`find_best_for_pkg` + inline `place_package` calls). Now delegates to the same `auto_arrange.py::_run_ordered_pass` pipeline the single-vehicle strategies use, so scoring/stacking fixes (Phases 1-2) and performance fixes (Phase 3) apply identically to both paths instead of needing to be ported twice. `find_best_for_pkg` itself is left in place (unused internally now, but still part of the module's public surface — imported by `routes.py`).

### Fixed during verification (not part of the original plan, found while testing)
- **Duplicate placement bug**: the refinement re-run (`largest_first` probe succeeds → re-run `optimized` for a better layout) initially called `auto_arrange` a second time on the *already-populated* planner without resetting it first. `OptimizedStrategy` captures "already placed" as its baseline and adds new placements on top of it — so the second call placed every package a second time at new positions instead of refining the first placement (an 8-package test shipment came back with `placed=16`). Fixed by resetting the planner to its true empty baseline (`planner.import_plan(initial_states[...])`) before the refinement call. Caught by a small functional verification script, not the unit test suite — none of the 26 existing tests exercise this multi-call path.

### Testing
- `pytest tests/test_scorer.py -v` — 26/26 passing.
- Small functional scripts (not the full multi-seed sweep, per direction to avoid slow verification loops going forward): an 8-package shipment sized to fit one small van correctly used only that van (1 truck, not falling back to a larger default); a 60-package shipment across a 6-vehicle mixed fleet (2 vans, 2 mid trucks, 2 large containers) correctly used only the 2 large containers rather than spreading across smaller trucks, all 60 placed, no failures. Both confirmed against the duplicate-placement bug fix above.
- Not yet cross-checked against a full statistical sweep (Phase 3's lesson: this kind of change benefits from one, but those are slow — deferred to Phase 5's regression suite rather than run ad hoc again this pass).

## 2026-07-30 — Truck Load Planner Phase 3: Performance (reduced scope)

Phase 3 of the 6-phase truck-load-planner improvement plan (Phases 1-2 above). Originally scoped to 3 items; 2 were found unsafe/out-of-reach for a performance-only pass during implementation and deferred rather than shipped half-verified.

### Fixed
- **`OptimizedStrategy` discarded the caller's `candidate_limit` on every trial** (`truck_load_planner/engine/auto_arrange.py`) — removed the unconditional `planner._candidate_limit = None` before each of the 15 trials. In practice this only affects requests that explicitly pass `profile=fast` together with `strategy=optimized`, since the default `balanced` profile never sets a limit in the first place (`routes.py`'s `if profile.candidate_limit and ...` guard) — but in that combination, the "fast" profile's speed/quality tradeoff was being silently ignored.

### Attempted and reverted (documented, not shipped)
- **Spatial-index-narrowed `check_support`** — tried routing the "packages directly below" scan through the existing `UniformGrid` spatial index (already used for collision checks) to cut its O(n) scan. A 2000-candidate randomized equivalence check against the un-narrowed version found 167 mismatches: the *original* algorithm matches "below" packages by Z-height alone across the **entire** plan, not scoped to XY proximity — a same-height package anywhere in the container gets checked against stacking-mode/weight/footprint rules before the XY-overlap coverage/centroid check runs later. Narrowing by XY first (the natural way to use the spatial index) silently changed real accept/reject outcomes. This may itself be a latent bug (a valid stack position could be rejected due to a rule conflict with an unrelated package that merely shares its height, not one actually underneath it) worth investigating separately, but fixing it wasn't this pass's goal, and a safety-critical validation path isn't the place for an unplanned behavior change. Reverted; the reasoning is now recorded directly in `engine/support.py::check_support`'s docstring so it isn't re-attempted blind.
- **Spatial-index for `scorer._build_others_with_layers`** — assessed but not attempted. Unlike collision/support, this needs full-plan layer info for every candidate (contact-area scoring checks all 6 faces against every neighbor, not just "nearby" ones), so a grid query alone doesn't reduce it the same way; a real fix would mean maintaining layer info incrementally as packages are placed (similar to how `PlanningState` already maintains extreme points incrementally) rather than recomputing from scratch per candidate — a bigger change than this pass's scope. Deferred.
- **Early-exit tuning for the 15-trial `OptimizedStrategy` sweep** — deferred. Phase 2's verification already showed this specific 15-trial ensemble is sensitive enough to weight/scoring changes that an untested tuning change regressed aggregate placement rate before being caught; without Phase 5's regression suite in place yet, a similar change to trial/exit logic couldn't be verified with confidence in the time available.

### Testing
- `pytest tests/test_scorer.py -v` — 26/26 passing.
- 2000-candidate randomized equivalence check (see above) — used to catch the `check_support` regression before it shipped, not to validate a change that was kept.

## 2026-07-30 — Truck Load Planner Phase 2: Fixed Empty-Space/Utilization Scoring

Phase 2 of the 6-phase truck-load-planner improvement plan (Phase 1: stacking, above). Targets "leaves too much empty space" — `x_position` never actually measured row/slice completion despite being described that way, and `usable_space` (the only real gap-awareness term) could be outweighed by `contact_area` alone.

### Fixed
- **`x_position` was a flat "prefer small X" bias, not a slice-completion signal** (`truck_load_planner/engine/scorer.py`) — replaced with `_score_x_position()`, which rewards a candidate that closes out the container width at the deepest X reached so far (within its own height band, so a stack elsewhere at a different height doesn't count against a floor candidate's row). Weight sign flipped from `-200` to `+200` to match the new higher-is-better raw value; `OptimizedStrategy`'s `dense`/`stack_friendly` profile overrides updated the same way (`-350`/`-300` → `350`/`300`).
- **`usable_space`'s dead-strip penalty could be outweighed by `contact_area` alone** — boosted its base weight from `1` to `3` so a placement that leaves an unusable gap for remaining packages can no longer be rescued by a merely-good contact score.

### Fixed during verification (not part of the original plan, found while testing)
- **Over-eager fix**: initially scaled the `dense`/`stack_friendly` weight-profile `usable_space` overrides proportionally with the base change (`2.0`/`2.5` → `6.0`/`7.5`), reasoning they were multipliers relative to base. A 36-scenario random sweep (mixed container sizes, 25-45 packages each) showed this measurably regressed `OptimizedStrategy`'s aggregate placement rate (966/1293 baseline → 910/1293), even though the standalone `LargestFirstStrategy` improved (586/1293 → 709/1293) as intended. Root cause: those overrides are independently pre-tuned absolute values, not ratios — scaling them re-applied the same fix twice and overweighted `usable_space` within those two profiles. Reverted to the original absolute values (`2.0`/`2.5`); see `SORTING_STRATEGY.md` Section 4 for the note against repeating this mistake.

### Testing
- `pytest tests/test_scorer.py -v` — 26/26 passing throughout.
- Full before/after sweep (3 containers × 12 seeds × 25-45 packages, `largest_first` + `optimized`) comparing pre-Phase-1 baseline against the corrected Phase 1+2 code was run to validate the fix above; a follow-up full-scale re-run to confirm the final numbers after the profile-override correction was interrupted partway (slow — itself evidence for the Phase 3 performance fix) and not completed. A smaller 8-scenario version of the same sweep post-fix showed `optimized` placing 77.9% with the corrected profiles (vs. 70.4% with the over-tuned version), consistent with the fix working, but this wasn't cross-checked against baseline at the same small scale. Flagged for confirmation once Phase 5's regression suite exists; user has opted to verify manually in the meantime rather than block further phases on more sweep runs.

## 2026-07-30 — Truck Load Planner Phase 1: Fixed Stacking Scoring Bias + Hard Height Cap

Root-cause investigation into "auto-arrange is slow, leaves empty space, doesn't stack when it should, and sometimes stacks too high" found `SORTING_STRATEGY.md` was stale (doesn't match `engine/scorer.py`'s actual weights) and that the scoring algorithm itself had two real defects driving the stacking complaints specifically. This is Phase 1 of a 6-phase plan (see `SORTING_STRATEGY.md` for current-state doc, updated in this pass); performance, empty-space, multi-vehicle/fleet-size, regression-test, and frontend-fidelity fixes are tracked as later phases.

### Fixed
- **Scoring categorically favored an empty floor tile over stacking, regardless of context** (`truck_load_planner/engine/scorer.py::_score_stack_and_tower`) — a fresh floor spot scored `stack_level:1000 + tower_height:500 = 1500` raw combined vs. `300 + 300 = 600` for stacking one layer up, a ~900-point gap under the base scoring weights (both terms carry weight `1`). This meant the algorithm would pick available floor space over a stacking position essentially unconditionally, even when stacking was clearly the more space-efficient choice. Rebalanced to `200/100` (floor) vs. `150/60` (layer 1) — floor is still the default tiebreak, but the gap is now small enough that `contact_area`/`usable_space` can tip a genuinely-better stack position into winning. Confirmed on a realistic 20-package/box-truck scenario: stacked-package count went from 2/20 to 5/20 with identical total-placed and utilization (i.e. more stacking, not fewer packages placed).
- **`max_stack_layers=0` was treated as literally unlimited** (`truck_load_planner/engine/support.py::_check_stacking_rules`) — this is documented (README.md, SORTING_STRATEGY.md, DB default) as "no explicit per-package override," not "physically unlimited," but the code had no fallback, so most packages (which don't set an explicit override) had no stack-height ceiling at all beyond the soft `tower_height` scoring penalty. Added `_SYSTEM_MAX_STACK_LAYERS = 3` as a hard cap applied when a package's own `max_stack_layers` is 0; an explicit tighter per-package value still takes precedence.

### Changed
- `SORTING_STRATEGY.md` rewritten to match verified, actual behavior: real `SCORING_WEIGHTS` (6 terms, not the doc's old fabricated 4-term/10000-weight scheme), the real default strategy (`OptimizedStrategy`, not `LargestFirstStrategy`), the real (and currently in-flux) multi-vehicle selection behavior, and corrected the `candidate_limit`/`tighten_step_mm` config-points table (the latter is dead config — `tighten_position()` hardcodes its own step and never reads it).

### Testing
- `pytest tests/test_scorer.py -v` — 26/26 passing (3 tests asserting exact `stack_level`/`tower_height` raw values updated to match the new calibration; no other test changes needed).
- Manual: realistic 20-package/box-truck scenario (before/after comparison via `Planner.auto_arrange`, both `largest_first` and `optimized` strategies) — confirmed increased stacking with no placement-count or utilization regression.
- Noted for Phase 5 (regression test coverage): an artificial exact-fit edge case (container dimensions sized to a knife-edge multiple of package dimensions) showed one fewer package placed under `OptimizedStrategy` post-fix (7/8 vs. 8/8) — traced to tie-breaking sensitivity between the base scoring weights and `OptimizedStrategy`'s pre-existing `dense`/`stack_friendly` weight-profile trials (`auto_arrange.py::_weight_profiles`), not reproduced in the realistic scenario above. Flagged as a case worth covering explicitly once Phase 5's regression suite exists, rather than chased further on a hand-built degenerate scenario now.

## 2026-07-30 — Site-Wide Navigation: Fixed Dispatch Dropdown Bug + Reorganized Structure

Two related complaints: the Dispatch page's nav dropdowns were visually broken, and the overall nav "doesn't follow any rules or best practice." No shared nav template exists anywhere in this app — all ~9 pages fully copy-paste the identical `<nav>` block — so both were investigated and fixed per-file rather than via a new shared-template refactor (explicitly deferred, see below).

### Fixed
- **Dispatch page's nav dropdowns were invisible and unclickable** (`static/css/delivery-dashboard.css`) — `.dashboard-header .header-nav` had an *unguarded* `overflow-x: auto`, while every other page correctly wraps the identical rule in `@media (max-width: 768px)`. Setting `overflow-x` forces the browser to also compute `overflow-y: auto` (CSS spec behavior), so the dropdown menus — `position:absolute`, opening below the nav's ~34px height — were being clipped to zero visible height at *every* screen width, with no scrollbar cue since `scrollbar-width: none` hides it. The click handler fired correctly the whole time; the menu just never rendered. Moved the rule into the existing mobile-only media query, matching every other page.
- **Dispatch was also missing the click-outside-to-close script** (`templates/delivery-dashboard.html`) present on every other page (`document.addEventListener('click', ...)` closing any open `.fleet-dropdown`). Added it.
- Verified live in-browser: dropdown now has real height, is clickable, and closes on an outside click; zero console errors.

### Changed — nav reorganization (applied identically across 9 templates: `index.html`, `delivery-dashboard.html`, `delivery-plan-builder.html`, `manage-trips.html`, `trip-history.html`, `locations.html`, `oil-change.html`, `vehicle-management.html`, `fuel-efficiency.html`)
- **New top-level order**: `Map | Dispatch | Plan Builder | Trips ▾ | Locations | Load Planner | Fleet ▾` (previously `Map | Trips ▾ | Delivery ▾ | Locations | Load Planner | Fleet ▾`).
- **Dispatch promoted to a top-level link** — previously two clicks deep (`Delivery ▾ → Dispatch`) despite being the most-used page.
- **"Delivery ▾" removed** — once Dispatch moved out, it only had one item left (Plan Builder); a one-item dropdown added a click for no reason, so Plan Builder became a bare top-level link instead.
- **"Trips ▾" and "Fleet ▾" kept as dropdowns** — both still group 2-4 genuinely related destinations.
- **Active-page highlighting added** — each page hardcodes `active` (the pre-existing `.btn-nav.active` style, previously unused in this header) on its own corresponding link/button, since there's no shared template to compute this dynamically. For pages under a dropdown (Trip Management/History → Trips ▾; Oil Change/Vehicles/Fuel/Container → Fleet ▾), the dropdown's own button gets the active state. This required removing the inline `background:none;border:none;color:#c9d1d9;` from those specific buttons, since inline styles otherwise override the `.active` class's background.

### Considered and explicitly not done
- **Consolidating the 9 copy-pasted nav blocks into one shared Jinja include/macro** — this is *why* Dispatch could drift and break without affecting any other page in the first place, but the user asked to reorganize the existing per-page pattern first, not take on a template refactor in the same pass.
- **Adding a full nav to `truck-load-planner.html`** — initially assessed as a navigation dead-end, but on inspection it already has a `← Dashboard` back-link (`templates/truck-load-planner.html:1052`); left as-is rather than forcing the full multi-item nav onto a deliberately minimal, focused full-screen tool.

### Testing
- `pytest tests/test_delivery.py` — 49/49 passing (no backend touched).
- Manual: dev server + browser — verified the Dispatch dropdown renders/clicks/closes correctly, verified active-state highlighting on Dispatch (dispatch page), Trips ▾ (manage-trips page), and Fleet ▾ (oil-change page), zero console errors on each.

### Remaining Technical Debt
- The no-shared-template problem itself remains — any future nav change still means editing 9 files by hand. Flagged as a candidate for a later pass if this drift recurs.

## 2026-07-30 — Dispatch Module Post-Phase-3: Plan Auto-Completion + Live Speed Signal

Two of three items from a production-usage planning review (real dispatcher feedback after tagging `dispatch-phase-3`): the dashboard never removed old/test plans because nothing ever transitioned a plan out of `confirmed`/`executing`, and TTAS's live speed telemetry (crawled from the tracking site) was being discarded entirely. A third item (manual "Archive Plan" action) was explicitly deferred pending observation of production usage after auto-completion ships. No schema change, additive only, backward compatible.

### Added
- **Plan auto-completion** (`services/delivery/execution_service.py`) — a plan's `status` now automatically transitions to `completed` once every stop across *every* vehicle assignment under it has reached a terminal state (`completed`/`skipped`/`cancelled`). Wired into the three call sites that produce a terminal stop status: `advance_stop()`'s `arrived→completed` branch, and `_update_execution()` (used by both `skip_stop()`/`cancel_stop()`) — the latter only runs the (more expensive) full-plan check when the status being written is itself terminal. Uses the `completed` value the schema already documents for `delivery_plans.status`; no migration needed.
  - **Safeguard**: `insert_temp_stop()` now reverts a plan from `completed` back to `executing` if a new pending stop is added to it — otherwise a dispatcher inserting a stop into an already-auto-completed plan would silently hide that pending work from the dashboard, which would be a worse bug than the one being fixed.
- **Live speed as a supplementary signal only** (`services/delivery/tracking_service.py::normalize_gps_position()`) — TTAS's raw `speed_status` is Vietnamese status text (e.g. "Chạy 42km/h"), not a clean number, exactly as flagged before implementation. Added `_parse_speed_kmh()`, a defensive regex extraction (mirroring the one already proven in `app/routes/trips.py`, not duplicating its exact behavior — this one returns `None` rather than defaulting to `0` when nothing numeric is found, since "unknown" and "confirmed stopped" are different facts). The new `speed_kmh` field is additive on the existing flat GPS dict — by design, this flat/`.get()`-based shape already accommodates future telemetry (e.g. `heading`) without another contract change, so no restructuring was needed to satisfy that ask.
  - **Explicitly not used for ETA or routing** — the existing ORS route-based ETA (Phase 2) remains the sole ETA authority. Instantaneous `distance ÷ speed` is a known bad pattern (a vehicle stopped at a red light would read speed=0 → ETA→∞).
  - Surfaced in the vehicle info bar (`#vibarSpeed`) and map marker popup as read-only context.
  - Feeds a new, third attention proxy in `vehicle-list.js::computeAttention()`: `reported_stopped` — live speed ≤2 km/h while GPS is fresh (not stale) and the vehicle isn't already parked at a stop. Purely corroborating/informational, same as the existing `stuck`/`gps_stale` proxies from Phase 3.

### Deferred (explicit decision, not forgotten)
- Manual "Archive Plan" action — holding off to observe whether auto-completion alone resolves the dashboard-clutter complaint in real usage before adding a manual escape hatch.
- A default rolling date-window filter was considered and rejected during planning: a plan can legitimately span into the next day, and filtering by `plan_date === today` risked hiding real, still-active work.

### Testing
- 9 new tests: `TestPlanAutoCompletion` (4 — single-assignment completion, partial-completion no-op, multi-assignment requirement, revert-on-insert-into-completed-plan) and `TestTrackingService` (5 — embedded-speed parsing, unparseable→`None`, missing-field→`None`, decimal speed, and explicitly distinguishing a genuine `0` reading from "unknown"). Full suite: 49/49 passing.
- Manual: dev server + browser (console-mocked `DASH.api.*`, same technique as the Phase 3 QA pass) — confirmed the info bar and map popup render the parsed speed, the `reported_stopped` attention chip/dot fire at low speed and clear at normal speed, no console errors. Auto-completion itself was verified via the isolated pytest suite rather than against the real `routing_system.db`'s existing plans, to avoid irreversibly mutating that data during a manual check.

## 2026-07-30 — Dispatch Module Phase 3 QA Pass: Two Bugs Fixed

Final QA pass on Phase 3 before tagging, covering: Follow mode over an extended session, attention chips crossing real thresholds, photo gallery under multiple-images/missing/slow-network conditions, inline-reason-edit durability under polling and rapid interaction, listener/memory growth, and browser performance over a simulated 30-minute session. Verified via a console-level mock harness driving `DASH.api.*` with realistic synthetic data (moving GPS, threshold-crossing timestamps, multi-image responses, artificial network delay) since this sandbox has no live TTAS/ORS credentials. Two real bugs found and fixed in `static/js/dashboard/timeline.js`; everything else confirmed correct.

### Fixed
- **Duplicate photo-gallery fetches under slow network** (`timeline.js::bindPhotosToggle`) — rapid toggle clicks while a fetch was in flight (`loaded` was still `false`) triggered a second concurrent request to `/api/stops/<id>/images`. Reproduced with 4 rapid clicks during a 3s artificial delay → confirmed 2 fetch calls. Added a `loading` guard alongside the existing `loaded` one; re-tested identically → confirmed 1 call.
- **Abandoned reason edit permanently blanked a stop's content** (`timeline.js::render`) — the `openReasonStopIds` guard added to protect an in-progress skip/cancel edit from being wiped by a background poll was never cleared. If a dispatcher opened Skip/Cancel on a stop and navigated away (selected a different vehicle, or deselected) without confirming or cancelling, that stop's `.timeline-detail-wrap` — including its Advance/Skip/Cancel buttons — stayed permanently empty on every future render for the rest of the session, even after a full rebuild created a brand-new DOM node for it (reproduced and confirmed: `detailWrapInnerHtmlLength: 0` after abandon-and-return). Fixed by clearing `openReasonStopIds` at the two points where stale reason-row state can no longer correspond to real DOM: the empty-list branch and the full-rebuild branch of `render()`. Re-verified the original in-progress-edit-survives-polling behavior still holds (30 consecutive same-assignment polls) after this change.

### Verified, no changes needed
- **Follow mode**: `panTo`-based re-centering tracked 20 simulated GPS-movement cycles smoothly with zero jitter, and correctly preserved a dispatcher's manually-set zoom level (tested at zoom 10, forced there by the user, vs. the manual "Zoom to Vehicle" button's zoom-14) throughout — confirming it never fights a manual pan/zoom.
- **Attention chips**: fired and cleared correctly against realistic threshold-crossing data for both proxies independently (stuck-at-stop crossing 20min, GPS-stale crossing 15min) and returned to hidden when both dropped back under threshold.
- **Photo gallery**: multiple images, zero images, and slow-network (3s artificial delay) scenarios all rendered the correct state once the duplicate-fetch fix above was applied.
- **Listener/memory growth over ~150 simulated poll cycles** (≈30min at the real 12s interval) mixed with UI interactions: DOM node count grew by only 3 (not scaling with cycle count), heap usage was flat (0MB measured growth via `performance.memory`), and an instrumented `addEventListener` audit found every element outside the attention strip bound its listener exactly once — no rebinding anywhere. The attention strip's repeated rebind count is many distinct short-lived chip elements (each bound once, each discarded together with its listener on the next full-innerHTML rebuild) rather than the same node being bound repeatedly — already a documented, deliberate Phase 3 simplification given the strip's small size, and confirmed non-leaking by the flat DOM/heap metrics, so left unchanged per "fix only issues found."
- `pytest tests/test_delivery.py` — 40/40 passing throughout (no backend touched by either fix).

### Remaining Known Limitations (unchanged from Phase 3)
- Attention thresholds (20min stuck, 15min GPS-stale) remain untuned against real fleet data.
- True SLA-based delay still requires a schema column, out of scope per the earlier decision.
- Could not test Follow mode / attention chips / photo gallery against real TTAS GPS or real uploaded images in this sandbox — verified via realistic synthetic data instead.

## 2026-07-30 — Dispatch Module Phase 3: Operational Workspace

Frontend-only workflow improvements to the Dispatch dashboard, based on a workflow analysis grounded in the actual code (not `docs/PHASE_3_Dispatcher_Workspace.md`'s aspirational layout). No grid/layout redesign, no new backend logic beyond the pre-existing image API, no schema change. All changes additive to `static/js/dashboard/{vehicle-list,timeline,map,main}.js`, `templates/delivery-dashboard.html`, `static/css/delivery-dashboard.css`, plus one method added to `api.js`.

### Added
- **Attention proxies** (`vehicle-list.js`) — since no scheduled/promised time exists anywhere in the schema, "delay" is approximated from data already available every poll: a vehicle `arrived` at a stop for more than 20 minutes without advancing ("stuck"), or a vehicle whose GPS hasn't updated in 15+ minutes ("GPS stale"). Surfaced as a small dot on the vehicle card, a dismissed-when-empty attention strip at the top of the vehicle list, and an "Attention first" sort toggle — all pure client-side derivation, no schema change.
- **Pinned current-stop card** (`timeline.js`, new `#currentStopCard` element) — the selected vehicle's current stop (contact name, address, phone, ETA) is now always visible at the top of the Timeline panel regardless of scroll position, with mirrored Advance/Skip/Cancel actions so the single most common action never requires scrolling.
- **Click-to-call** — `manager_phone` is now a `tel:` link in both the pinned card and each per-stop detail body (previously plain text).
- **Read-only photo gallery** (`timeline.js` + `api.js::stopImages()`) — a "📷 Photos" toggle per stop lazily fetches `/api/stops/<id>/images` (backend untouched, this endpoint already existed with zero consumers anywhere in the app before this) and shows a thumbnail strip; clicking a thumbnail opens the original in a new tab. Lives in its own DOM node outside the diffed detail content so its open/loaded state survives every poll.
- **Follow-vehicle map mode** (`map.js::followVehicle()`, new `#followVehicleBtn`) — `panTo` (no forced zoom, no popup) re-centers on the selected vehicle every poll while active; resets automatically on deselection or switching to a different vehicle.

### Changed
- **Skip/Cancel no longer use `prompt()`/`alert()`** (`timeline.js`) — clicking either swaps the action buttons for an inline reason input (Confirm/Enter to submit, × to abort), with `UI.toast()` reporting errors and enforcing "cancel requires a non-empty reason" (previously a silent `if (!reason) return`). Shared between the per-stop body and the pinned card via one `bindActionDelegation()`/`handleStopAction()` implementation, avoiding duplicate logic.
- Added `<script src="/static/js/utils.js">` to `delivery-dashboard.html` — first use of `UI.toast()`/`UI.escapeHtml()` on this page, per `CLAUDE.md`'s convention for new fetch/toast/escape code. The page's own `DASH.api` fetch wrapper (a different response contract than `ApiClient`) was kept as-is, matching the module it was already established in.

### Fixed (self-consistency issue caught during implementation)
- Because the new reason row is non-blocking (unlike the old native `prompt()`, which paused all JS until dismissed), a background poll can now legitimately fire while a dispatcher is mid-typing a skip/cancel reason. Content diffing for a stop with an open reason row is suppressed (`openReasonStopIds` set) until it closes, so an in-progress edit is never silently wiped — the exact kind of state-loss bug this dashboard's Phase 1 work was about eliminating.

### Testing
- `pytest tests/test_delivery.py -v` — 40/40 passing, unaffected (no backend logic changed).
- Manual: dev server + browser — verified the pinned card renders with a working `tel:` href, the inline reason row appears/confirms/cancels with zero native dialogs, the required-reason toast fires correctly, the photo gallery lazy-fetches and shows the correct empty state, and the Follow toggle switches to its active visual state. Could not visually trigger an actual attention chip/dot, since no vehicle in this sandbox's data currently has live GPS or a long-arrived stop meeting either threshold — the toggle and empty-strip behavior were confirmed, the firing condition itself was not.

### Remaining Technical Debt / Deferred
- Attention thresholds (20 min stuck, 15 min GPS-stale) are reasonable defaults, not tuned against real fleet data — may need adjustment once used in production.
- True SLA-based delay (vs. a promised/scheduled time) remains unavailable — would need a schema column, explicitly deferred per this phase's scope decision.

### Out of Scope
- A few other pre-existing dead-for-the-same-reason status-map entries in `vehicle-list.js`/CSS (noted in the Phase 0 entry) remain untouched.
- Alerts, WebSockets, routing/backend redesign — reserved for later phases per `docs/MASTER_PLAN.md`.

## 2026-07-30 — Dispatch Module Phase 2: Route Intelligence

Extends the existing ORS integration (`services/delivery/eta_service.py`, `services/delivery/routes.py`) to surface road geometry, remaining/travelled distance, and avoid redundant ETA recalculation; updates the map's route rendering (`static/js/dashboard/map.js`, `main.js`) to draw it. No new endpoints, no schema change, no new routing provider, polling interval unchanged.

### Added
- **Road-following route geometry** — `eta_service.calculate_eta()` now parses the `geometry.coordinates` ORS was already returning (previously discarded) and converts GeoJSON `[lng, lat]` to Leaflet's `[lat, lng]`. Each leg in `calculate_etas_for_stops()`'s output now carries this as `"geometry"` (`None` for haversine/fallback legs, where no real road path exists).
- **In-memory route cache** (`eta_service.py`, module-level `_route_cache` + `threading.Lock`) — `calculate_etas_for_stops(..., assignment_id=...)` reuses the previous result when the remaining stop set/order/coordinates are unchanged AND the vehicle has moved less than `ROUTE_CACHE_GPS_THRESHOLD_M` (50m, filters GPS jitter without masking real movement). Invalidates on assignment change (different cache key), stop order/destination change (stop-id+lat+lng tuple differs), stop completion/skip (changes which stops are "remaining"), and significant GPS movement. Kept local to `eta_service.py` rather than `app/state.py` — that module's docstring scopes it to the fleet/fuel/oil/trips blueprints + TTAS session, a different package/concern than `services/delivery`. `assignment_id` defaults to `None`, which bypasses the cache entirely (existing callers/tests unaffected).
- **Remaining/travelled/total distance** — `/api/eta` now also returns `remaining_distance_km` (from the last remaining leg's new `cumulative_km`), `travelled_distance_km` (new `calculate_travelled_distance_km()` — a straight-line, best-effort sum across already-passed stops, intentionally not ORS-routed to avoid extra API calls for a secondary figure), and `total_distance_km`. Surfaced in the dashboard's vehicle info bar via a new `#vibarDistance` span.

### Changed
- `map.js::updateRoute(eta, stops)` (signature changed, both call sites in `main.js` updated) — now builds the polyline by concatenating each remaining leg's road geometry in order; falls back to a straight segment only for the specific leg(s) missing geometry, and to the old straight-line-through-all-stops behavior only when there's no live ETA at all (GPS offline) — never blanks the route. Solid line when real road geometry was used, dashed when it's a straight-line fallback, so dispatchers can tell the difference at a glance. The existing "skip redraw if the path is unchanged" check (from Phase 1) is unchanged, now comparing the richer coordinate list.
- Vehicle info bar's "ETA:" label is unchanged (still time-to-next-stop, from `etas[0].eta_seconds`, per Phase 0's established contract) — the new distance figures are additive, not a replacement, to avoid an unrequested semantic change.

### Testing
- 9 new tests in `tests/test_delivery.py::TestEtaService`: geometry coordinate-order conversion, `geometry: None` on non-ORS legs, `cumulative_km` tracking, cache hit (ORS mock called once across two identical calls), cache invalidation by GPS move / stop-set change, cache tolerating sub-threshold GPS jitter, cache bypass when `assignment_id` is omitted, and `calculate_travelled_distance_km` (zero when nothing passed, positive sum otherwise). Full suite: 40/40 passing.
- Manual: dev server + browser — confirmed no console errors and correct graceful fallback (old straight-line-through-stops behavior, unchanged) in this sandbox, which has no TTAS/ORS credentials configured so `/api/eta` returns `{"error": "Vehicle GPS not available", "etas": []}` for every vehicle. The road-geometry/caching logic itself could only be exercised through the mocked unit tests in this environment.

### Remaining Technical Debt / Deferred
- `travelled_distance_km` is straight-line (haversine), not road-following — an intentional trade-off to avoid extra ORS calls for a secondary metric; flagged in case a later phase wants it more precise.
- Route cache has no eviction/TTL — acceptable at this fleet's scale (40 vehicles' worth of tiny cache entries), not worth the complexity here.

### Out of Scope
- Alerts, WebSockets, new routing providers, backend/database redesign — reserved for later phases per `docs/MASTER_PLAN.md`.
- Could not visually confirm real road polylines rendering in this sandbox (no ORS/TTAS credentials available) — recommend a manual check against the live Render deployment or a local `.env` with real credentials before considering this phase fully verified end-to-end.

## 2026-07-30 — Dispatch Module Phase 1: Incremental Live Updates

Rendering-only pass on the Dispatch dashboard's poll-driven refresh (`static/js/dashboard/{vehicle-list,map,timeline}.js`, small `main.js` call-site changes). No new endpoints, no schema change, no WebSockets, polling interval (12s) unchanged. Verified against the live code, not `SYSTEM.md`/`DELIVERY_MODULE.md`.

### Fixed
- **Vehicle list rebuilt from scratch every 12s poll** (`vehicle-list.js`) — `container.innerHTML = html` destroyed and recreated every card (and rebound every click listener) regardless of whether anything changed, resetting scroll position and hover/focus state. Now keeps a `Map<assignment_id, cardElement>`: creates only new cards, patches text/class/width on existing ones by comparing old vs. new values, removes cards for ids no longer present, and reorders via targeted `insertBefore` only when order actually changed. Click listeners are bound once per card at creation.
- **Vehicle markers cleared and recreated every poll** (`map.js`) — `vehicleMarkerLayer.clearLayers()` + full rebuild destroyed marker identity (and any open popup) every 12s. Now diffs by assignment id: moves existing markers via `setLatLng`, patches the label/border color by writing directly to the existing icon's DOM node (no `setIcon`), and updates popup content via `popup.setContent()` — which Leaflet applies live even while the popup is open, instead of closing it. Same approach for the selected assignment's stop markers (full rebuild only when the stop-id set changes, i.e. on selection switch); the route polyline is skipped entirely when its coordinates haven't changed.
- **Found and fixed while implementing the above**: `map.js::updateVehicles` read `gps.latitude`/`gps.longitude`, but `tracking_service.normalize_gps_position()` (`services/delivery/tracking_service.py`) has always output `lat`/`lng` — so vehicle markers were never actually placed on the map, independent of any rendering-strategy concern. Corrected to `gps.lat`/`gps.lng`.
- **Timeline rebuilt from scratch on every poll while a vehicle was selected** (`timeline.js`) — same `innerHTML` replacement pattern, plus a real state-loss bug: `collapsed = isCompleted ? '' : 'open'` was recomputed from status on every render, so a dispatcher's manual expand/collapse of a stop was silently reverted on the next poll (≤12s later). Now keeps a `Map<stop_id, element>` scoped to the selected assignment: full rebuild only when the stop-id set changes (selection switch, or a stop inserted); otherwise patches the header (seq/name/status badge) directly and swaps only the detail/action-button body content when its generated HTML actually differs. The collapse/expand toggle and Advance/Skip/Cancel actions are bound once per stop via delegated listeners on creation, so they never need rebinding and are unaffected by later body-content patches — this is what fixes the collapse-state loss.
- `main.js`'s `renderAll()` "no selection" branch bypassed the timeline module by setting `#timeline`'s `innerHTML` directly, which would have left `timeline.js`'s new node cache pointing at detached DOM. Added `DASH.timeline.clear()` (an alias for `render([], null, null)`) and routed that branch through it.

### Remaining Technical Debt / Deferred
- Timeline/vehicle-list reordering only handles add/remove/patch; if the *same* set of ids arrives in a different order on a same-key poll (structurally shouldn't happen — backend order is a stable `ORDER BY`, and stop order only changes via explicit reorder/insert actions that go through `refreshNow()`), the timeline won't reorder. Vehicle list already handles this case via `insertBefore` reconciliation; timeline was left simpler since its stop order is more stable. Flagged for Phase 3 if it ever surfaces.
- `map.js::currentZoomAssignment` remains an unused variable (pre-existing, out of scope).

### Out of Scope
- Alerts, routing changes, WebSockets, polling-interval changes — reserved for Phases 2/4/5 per `docs/MASTER_PLAN.md`.
- No new automated frontend tests were added (no JS test harness exists in this repo); verified manually via a running dev server + browser (see below) plus the existing `pytest tests/test_delivery.py` (unaffected, backend untouched except the one-line GPS field fix, which is frontend-only).

## 2026-07-30 — Dispatch Module Phase 0: Bug Fixes

Bug-fix-only stabilization pass on the Dispatch/delivery-dashboard module (`templates/delivery-dashboard.html`, `static/js/dashboard/*.js`, `services/delivery/*.py`), verified against actual code rather than the (partly stale) `SYSTEM.md`/`DELIVERY_MODULE.md` docs. No UI redesign, no schema change, no new features.

### Fixed
- **ETA contract mismatch** (`services/delivery/eta_service.py::calculate_etas_for_stops`) — backend never returned the `stop_id`/`eta_seconds` fields the dashboard frontend (`main.js`, `timeline.js`) reads, so stop ETAs never rendered and the summary bar showed `NaN`. Added both fields (mirroring existing `id`/`cumulative_sec`) without removing the originals.
- **Dead header refresh button** — `#refreshNowBtn` in `delivery-dashboard.html` had no event listener. Bound it to the existing `DASH.state.refreshNow()` (same mechanism `#refreshGPSBtn` already used).
- **Status/Plan filters could never return results** — `get_dashboard_data()` (`execution_service.py`) never selected a `plan_status` field at all (every card silently defaulted to "confirmed"), and separately its `WHERE dp.status IN ('confirmed','executing')` scope (intentional — an active-ops board) meant "Draft/Completed/Cancelled" could never match. Added `dp.status AS plan_status` to the query, removed the three unreachable options from `#filterStatus`, and filtered the Plan dropdown (`main.js::populateFilterPlans`) to only list confirmed/executing plans.
- **Driver source duplication** — the dashboard showed only `vehicles.current_driver` (a generic default edited in Vehicle Management), ignoring the dispatcher-assigned, per-delivery `vehicle_assignments.driver_id → drivers.name` that Plan Builder already treats as authoritative and override-capable. `get_dashboard_data()` now `LEFT JOIN`s `drivers` and returns `COALESCE(NULLIF(d.name,''), v.current_driver)` under the same `current_driver` field name (no frontend change needed).
- **Dead `enroute` UI handling** — `execution_service.advance_stop()` only ever implements `planned → arrived → completed`; nothing sets `status = 'enroute'`, confirmed by the existing passing test `test_advance_planned_to_completed` and by `CHANGELOG.md`'s own prior description of `advance_stop`. Removed the unreachable `enroute` branches from `vehicle-list.js`, `timeline.js`, `map.js` status maps and their corresponding `delivery-dashboard.css` classes. Backend `IN ('planned', 'enroute', 'arrived')` clauses left untouched (harmless, matches the schema's documented status domain).

### Known Issues / Out of Scope
- `SYSTEM.md`/`DELIVERY_MODULE.md` still document a 4-state `planned → enroute → arrived → completed` lifecycle that doesn't match the shipped 2-step `advance_stop`; docs were not updated as part of this bug-fix-only pass.
- `docs/dispatch/PHASE_0_BUG_FIXES.md` / `DISPATCH_ARCHITECTURE.md` referenced by the originating ticket don't exist in this repo — only `docs/MASTER_PLAN.md` + `docs/PHASE_1..5_*.md` (phases 1–5, no Phase 0 doc).
- `vehicle-list.js::statusClass()` and `delivery-dashboard.css` still contain a few other status-map entries (`arrived`, `skipped`, `planned` on `plan_status`-scoped elements) that are dead for the same reason `enroute` was — out of scope since only `enroute` was flagged.

## 2026-07-29 — Architecture Refactor: Frontend Namespace, DatabaseManager, AABB Unification, `app/` Package Extraction

Implements Phase 1 items 1–6, Phase 2 items 7–8, Phase 3 items 13–15, and Phase 4 items 17–20 of `CODEBASE_ANALYSIS_REPORT.md`'s Priority Action Items (see that file's updated status column for the full picture, including what's still pending).

### Added

#### `CLAUDE.md` (project root)
- Lean AI-context file per report §10.1 — project structure, key architectural facts, how to run, common-task pointers. Superseded almost immediately by the `app/` extraction below; kept up to date across this session.

#### Frontend: `ApiClient` + `UI` namespace (`static/js/utils.js`)
- `ApiClient.fetch/get/post/put/del` — centralized `fetch()` wrapper with a single `API_BASE` constant (`/api`), replacing 3 duplicated `apiFetch()` copies (`fuel-efficiency.js`, `oil-change.js`, `vehicle-management.js`)
- `UI.toast()` — replaces 6 divergent `showToast`/`toast` implementations across `map.js`, `fuel-efficiency.js`, `fuel-sync.js`, `vehicle-management.js`, `oil-change.js`, `truck-load-planner.js`; standardizes on `(message, type, duration)` argument order
- `UI.escapeHtml()` — replaces 4 `escapeHtml`/`escHtml` copies, **fixing an XSS gap**: the `fuel-efficiency.js` and `vehicle-management.js` copies didn't escape single quotes
- Deduplicated `todayISO`, `formatDate`, `fmtNum` (from `fuel-efficiency.js` + `oil-change.js`) and `normalizeText`, `getDistanceMeters`, `isPointInPolygon` (shadowed in `map.js`) into `utils.js`
- Backward-compatible global `showToast()` alias kept in `utils.js` — `locations.js`, `trip-history.js`, and `manage-trips.js` (out of this refactor's scope) still call the bare global function
- Added `<script src="/static/js/utils.js">` to 5 templates that never loaded it before (`fuel-efficiency.html`, `oil-change.html`, `vehicle-management.html`, `truck-load-planner.html`, `delivery-plan-builder.html`) — required for `ApiClient`/`UI` to exist on those pages at all

#### `EnginePackage.from_legacy()` (`truck_load_planner/engine/package.py`)
- Single classmethod factory handling both legacy-object (`models.Package`, attribute access) and legacy-dict (plain or underscore-prefixed keys) shapes, replacing 4 inline `EnginePackage(...)` construction sites across `session.py` and `routes.py`

#### `app/db.py` — `DatabaseManager`
- Context-manager connection wrapper: `PRAGMA foreign_keys = ON` by default (fixes a silent data-integrity gap — `services/delivery/image_service.py`'s old `get_conn()` never enabled it), auto-commit on success, auto-rollback + close on exception
- Replaces the 4 duplicated `get_conn()`/`_get_db()` copies in `services/delivery/plan_service.py`, `execution_service.py`, `image_service.py`, and `truck_load_planner/routes.py`
- `truck_load_planner/routes.py` connections use `enable_fk=False` deliberately — that schema has no `ON DELETE CASCADE`, and 3 of its routes (`delete_package`, `delete_shipment_item`, `delete_shipment`) delete a parent row without cleaning up all referencing children; turning FK enforcement on there would newly raise `IntegrityError` on those routes. Flagged as a follow-up, not fixed here.

#### `truck_load_planner/geometry/aabb.py` — unified `AABB`
- Merged the two previously-diverged `AABB` classes (`geometry/aabb.py` basic version, `engine/geometry.py` clearance-aware superset) into one canonical class
- `engine/geometry.py` is now a 15-line re-export (`AABB` + the 4 transform helpers, which were already duplicated verbatim in `geometry/transform.py`) — no import-site changes needed anywhere

#### `truck_load_planner/logistics/adapters.py`
- `check_boundary`, `calculate_total_weight`, `check_weight` now delegate to their `engine/` equivalents instead of duplicating logic; `boundary.py`/`weight.py` re-export from here, public signatures unchanged
- `volume.py`, `constraints.py::get_door_status`, and `placement.py::try_place` were **not** adapted — no engine equivalent exists for the exact same behavior (volume math, live door-status reporting, and `try_place` is confirmed dead code with zero callers), and inventing one was out of scope

#### `app/` package — extracted from the `app.py` monolith
`app.py` shrank from **3,625 lines to 225 lines**. New structure:

| Module | Contents |
|---|---|
| `app/config.py` | Env vars, constants (`DB_PATH`, `ORS_*`, `TTAS_*`, `FLASK_*`) |
| `app/state.py` | Shared mutable runtime state (route cache, locks, `known_locations`, TTAS session) — not in the original report plan, added because the blueprints below can't share plain module globals across files the way one big file could |
| `app/database/schema.py` + `migrations.py` | `init_db()` split into table creation vs. column migrations/backfill |
| `app/utils/geo.py`, `export.py` | Geo math helpers; a genuinely new shared CSV-response helper (oil and fuel exports each had their own copy before) |
| `app/services/ttas_client.py`, `routing.py`, `locations.py` | TTAS session/scraping, ORS routing, manual-location file I/O (the last one also not in the original plan — needed so `create_app()` can populate `state.known_locations` at startup without a circular import against `app.py`) |
| `app/routes/fleet.py`, `fuel.py`, `oil.py`, `trips.py` | The 4 domain Blueprints named in the report, covering all 65+ routes |
| `app/__init__.py` | `create_app()` factory — config, `init_db()`, blueprint registration |

#### `wsgi.py`
- Dedicated Gunicorn entry point. **Required**, not optional: `app.py` (file) and `app/` (package) share the name `app`, and `import app` always resolves to the package. `render.yaml`'s existing `startCommand: gunicorn app:app` would have broken on the next deploy since `app/__init__.py` only exposes `create_app()`, not a module-level Flask instance. `render.yaml` updated to `gunicorn wsgi:app`.

### Fixed
- N+1 query in `execution_service.get_dashboard_data()`: was 1 + 2×N queries (101 for 50 assignments), now a flat 3 queries regardless of N (window-function query for each assignment's current stop, one `GROUP BY` for status counts)
- XSS gap in `UI.escapeHtml()` vs. the two `escapeHtml`/`escHtml` copies that didn't escape `'`
- `image_service.py` connections now enforce `PRAGMA foreign_keys = ON` (previously the only one of the 4 `get_conn()` copies that didn't)
- A bug in this session's own first draft of `UI.toast()`: unconditionally adding a `.toast-container` CSS class to the page's toast container broke positioning on the 3 pages (`oil-change`, `vehicle-management`, `truck-load-planner`) that already had their own `#toast-container` CSS rule — fixed by only adding the shared class when the element isn't already `position: fixed`

### Changed
- `truck_load_planner/session.py` — `_to_engine_pkg()` and `_from_legacy_dict()` now delegate to `EnginePackage.from_legacy()`
- `truck_load_planner/routes.py` — `_get_packages_from_request()` delegates to `EnginePackage.from_legacy()`; all 30 `_get_db()` call sites migrated to `DatabaseManager`
- `services/delivery/plan_service.py`, `execution_service.py`, `image_service.py` — all functions migrated from manual `get_conn()`/`try`/`finally` to `with DatabaseManager(db_path).connect() as conn:`
- `tests/test_delivery.py` — one test called the now-removed `plan_service.get_conn()` directly; updated to use `DatabaseManager` (still tests the same rollback-on-FK-violation behavior)

### Removed
- `services/delivery/tracking_service.py` — 4 dead functions (`get_ttas_vehicles`, `update_ttas_cache`, `find_vehicle_by_plate`, `find_vehicle_by_id`) and their backing module globals (`_ttas_vehicles_cache`, `_cache_timestamp`); `normalize_gps_position()` (the one live function) kept
- Duplicated `mm_to_px`/`px_to_mm`/`compute_scale`/`rotate_dimensions` definitions in `engine/geometry.py` (now re-exported from `geometry/transform.py` instead)

### Verification
Every change above that touched behavior (not just file location) was checked with a recovered-vs-new equivalence test comparing outputs on real data before/after: `init_db()` against a fresh DB and a copy of the production DB (17 and 23 tables, byte-identical schema + row counts), `get_dashboard_data()` (13→3 queries, identical JSON), `EnginePackage.from_legacy()` (10 scenarios incl. zero-weight and empty-input edge cases), the `logistics/adapters.py` delegates, and `csv_response()`. The full test suite (57 tests) and a live server + browser pass (every route, a real write, the background route-refresh thread, and the map/dashboard/TLP pages) were run after each major step, not just at the end.

---

## 2026-07-26 — Phase 1: Delivery Plan Management Rewrite

### Added

#### New Database Schema (6 tables, coexists with legacy `vehicle_trips`)
- `drivers` — driver registry with name, phone, license
- `delivery_plans` — daily delivery plan header (status: draft/confirmed/executing/completed/cancelled)
- `vehicle_assignments` — vehicle-to-plan mapping (FK → plans, vehicles, drivers)
- `delivery_plan_stops` — immutable stop definitions (planned_sequence, station, coords, manager, product, notes)
- `stop_executions` — mutable runtime state (execution_sequence, status: planned/enroute/arrived/completed/skipped/cancelled, timestamps)
- `delivery_stop_images` — per-stop image metadata with categories (loading/delivery/extra), GPS coords, timestamps

All tables use `CREATE TABLE IF NOT EXISTS` with foreign keys (`ON DELETE CASCADE`) and covering indexes. Unique index enforces 1:1 stop→execution.

#### Service Layer (`services/delivery/`)
- **`plan_service.py`** (531 lines) — full CRUD for plans, assignments, stops, drivers; Excel import pipeline (parser → validator → preview → confirm)
- **`execution_service.py`** (235 lines) — current stop derivation (first planned/enroute by execution_sequence), advance (planned→arrived→completed), skip, cancel, reorder, insert temp stop, progress statistics
- **`tracking_service.py`** (49 lines) — TTAS GPS wrapper, vehicle plate lookup, position normalization
- **`eta_service.py`** (102 lines) — ORS-based ETA with Haversine fallback, single-leg and multi-stop cumulative calculations
- **`image_service.py`** (124 lines) — upload with auto folder creation (DeliveryPlans/YYYY/MM/DD/Plate/Station/Category/), list, serve, delete with file cleanup

#### REST API (24 endpoints under `/api`, Flask Blueprint)
- `/drivers` — list, create
- `/plans` — CRUD, confirm, import parse, import save
- `/assignments` — CRUD
- `/stops` — CRUD, skip, cancel, reorder, insert
- `/execution` — current, advance, dashboard, progress
- `/eta` — ETA for remaining stops
- `/stops/<id>/images` — list, upload
- `/images/<id>` — serve file, delete

#### Migration Script (`scripts/migrate_to_delivery.py`)
- One-way, idempotent export from legacy `vehicle_trips` into the new delivery schema
- Handles pickup/waypoints/destination → stops, status mapping, vehicle/driver creation
- Safe to re-run (checks for existing migration plans, `--force` to override)

#### Unit Tests (`tests/test_delivery.py` — 31 tests)
| Area | Tests |
|------|-------|
| ETA calculation | 7 (Haversine, ORS success/failure, multi-stop, empty) |
| Stop progression | 7 (advance lifecycle, skip, cancel, auto-advance on complete) |
| Reordering | 6 (reorder, insert temp, execution sequence updates) |
| Image management | 5 (upload, categories, delete removes file, empty, nonexistent) |
| Progress/dashboard | 5 (all planned, partial, skip counts, empty, dashboard) |
| Transactions | 2 (FK rollback, cascade delete) |

### Fixed
- `image_service.py` relative_path now derived from actual file path instead of `datetime.now()` (folder used `plan_date`, path used `now` — mismatch fixed)
- `image_service.py` orphan files cleaned up if DB insert fails after file save
- `execution_service.get_dashboard_data()` reduced from N+1 connections to single connection (inlined current_stop + progress queries)
- Migration script `import json` moved from loop to top-level
- Migration script now sets `PRAGMA foreign_keys = ON`

### Changed
- `app.py` (+9 lines) — registers delivery blueprint, sets `DB_PATH` in app config, calls `init_delivery_tables()`
- No existing routes, functions, or tables modified — legacy system completely undisturbed

### Changed

#### Simplified Scoring (`engine/scorer.py`)
- Reduced from 14 scoring categories to 4: `package_contact` (1000), `x_preference` (200), `floor_contact` (100), `y_balance` (50)
- Removed: wall_contact, face_contact, compactness, stack_quality, vertical_stability, z_preference, rear_proximity, cluster_cohesion, dead_space_quality, load_profile_stability

#### Simplified Candidate Generation (`engine/candidate_points.py`)
- Removed: `settle_package()`, `generate_slide_candidates()`, `generate_floor_anchors()`
- Candidates now come only from origin + right/front/top faces of placed boxes
- `tighten_position()` simplified — no longer needed as a separate pass

#### Simplified Placement Pipeline (`engine/auto_arrange.py`)
- Removed `ColumnStrategy` (only `LargestFirstStrategy` remains)
- Removed: frontier gap penalty, stack ceiling penalty, Y-slide fallback, gap-filling pass, post-placement compaction pipeline, debug instrumentation

#### Simplified Distribution (`engine/distribution.py`)
- Removed: `compact_placements()`, `compact_stacks()`, `fill_frontier_gaps()`, `fill_interior_gaps()`, `_try_local_rearrangement()`, `balance_fleet_profiles()`
- Only `distribute_across_vehicles()` and `reassign_load_sequences()` remain

#### Simplified Profiles (`engine/profile.py`)
- Removed repair/compaction-related fields; only name, candidate_limit, tighten_step_mm remain

#### Simplified Routes (`routes.py`)
- Default strategy changed from `"column"` to `"largest_first"`
- Removed all repair, consolidation, balance, compaction pipeline calls and imports

#### Simplified Internal Engine (`engines/internal/engine.py`)
- Removed `optimize_layout()`, `consolidate_fleet()` calls
- Only `distribute_across_vehicles()` remains

#### Package Sort Order
- Changed from `volume DESC, weight DESC, footprint DESC` to `(non-stackable first), volume DESC, weight DESC, footprint DESC`
- Non-stackable packages now always sort before stackable ones

### Removed
- `engine/repair.py` (386 lines) — destroy-and-repair optimizer
- `engine/consolidation.py` (197 lines) — near-empty vehicle elimination
- `engine/dead_space.py` (319 lines) — future-packability estimation
- `engine/frontier.py` (106 lines) — 1D Y-strip frontier tracker
- Total: 1,008 lines removed from engine; engine package reduced 51% (5,958 → 2,922 lines)

### Consolidated Test Files
- **Unified 19 script files** into `tests/test_all.py` with 5 subcommands and 16 modes:
  - `benchmark`: distribution, floor_contact, real_data
  - `diagnose`: general, kbf_lc900, candidates, stacking
  - `debug`: py3dbp, stats, validation, vehicles
  - `query`: vehicles, tables, db, shipments
  - `instrument`: trace, bug-trace
- Deleted 17 files from `scripts/`; moved `debug_arrange.py` and `merge_duplicate_vehicles.py` to `tests/`
- All output now saves to `reports/{cmd}_{mode}_{timestamp}.txt`

### Removed Modules (Deleted)
- `engine/repair.py` — destroy-and-repair LNS optimizer
- `engine/consolidation.py` — near-empty vehicle elimination
- `engine/dead_space.py` — future-packability estimation
- `engine/frontier.py` — 1D Y-strip frontier tracker
- `scripts/` directory (17 files unified into `tests/test_all.py`)

## 2026-07-22 — Frontier-Based Gap Prevention, Gap-Filling Pass, Debug Instrumentation

### Added

#### FrontierTracker (`engine/frontier.py`)
- New module implementing a 1D Y-strip frontier for gap-aware placement:
  - `get_frontier_at(y)` — returns the maximum X (depth) of the packed front at a given Y, within a Y-strip of configurable `strip_width_mm` (default 200–250 mm)
  - `gap_distance(x, y, z, w)` — measures how far a candidate is from the frontier at its Y-strip; positive = ahead of frontier, negative = behind (in a gap)
  - `gap_ratio(x, y, z, w)` — gap_distance normalized by `container.length`
  - `update()` / `update_from_placement()` / `reset()` — frontier state management
- Integrated into `LargestFirstStrategy.arrange()` and `ColumnStrategy.arrange()`:
  - Gap penalty during candidate scoring: `-min(gap_distance × (0.5 + gap_ratio × 0.5), 500)`
  - Y-slide fallback after frontier check

#### Frontier Gap-Filling Pass (`fill_frontier_gaps` in `engine/distribution.py`)
- Post-placement pass that detects frontier gaps (packages with xmin > frontier at their Y-strip)
- For each gapped package: tries `settle_package()` first (analytical O(K)), falls back to `tighten_position()` only when settle gives no improvement
- Guard: only re-places when `tx >= pl.x - 1.0` (meaningful forward improvement ≥ 1 mm)
- Replaces `fill_interior_gaps` calls in compaction pipelines
- Immediately updates frontier after each re-placement

#### Detailed Debug Instrumentation (`engine/auto_arrange.py`)
- `all_candidate_details` per debug entry captures every candidate evaluated:
  - Input position, tightened position, validity, raw score, gap penalty, stack ceiling penalty, full breakdown, adjusted score
- `slide_details` per debug entry tracks Y-slide fallback candidates

#### `scripts/debug_arrange.py`
- New comprehensive debugger that logs every step/decision for every package:
  - Sorting order, per-package all-candidate decision log, frontier state, gap check (adjacent with Y-overlap), per-package frontier gap analysis, settle/tighten test, compaction steps, position changes, validation
  - Saves to `reports/debug_<scenario>_<timestamp>.txt`
- Scenarios: `kbf_lc900`, `mixed`, `column-test`, `real` (full 46-package real shipment)
- `--full` flag for per-strip breakdown
- `real` scenario: 46 packages placed, score 100.0, valid, ~10 000-line report

### Fixed

#### Duplicate-Name Bug in Gap-Filling Pass
- `engine/auto_arrange.py`: `list.remove(x)` crashes when `x` appears multiple times in `unplaced_packages`
- Fixed: replaced with `Counter` from `collections` for count-based tracking

### Removed
- `tests/test_auto_arrange.py` — deleted (63 test cases, called "useless")

---

## 2026-07-21 — Load Profile Stability Metric Fix, Floor Anchors, Local Rearrangement, Benchmark Correction

### Changed

#### Load Profile Stability Metric
- **`engine/scorer.py::_score_load_profile_stability()`** — metric fixed from `sum(adjacent_diffs) / ((n-1) × H)` to `max_step / container.height`. Old metric had ~0.1 weighted-point range (negligible) and ranked concentrated towers better than gradual staircases. New metric creates a 4.15 point gap (59× improvement), correctly penalising tall isolated stacks.

#### Floor Anchor Candidates
- **`engine/candidate_points.py::generate_floor_anchors()`** — new function that finds the largest empty floor rectangles via Y-boundary sweep (O(N²) with N ≤ floor packages), generating front/center/rear positions for the top 2 regions. Augments (not replaces) extreme-point candidates to help fill empty floor regions.

#### Tighten Position
- **`engine/candidate_points.py::tighten_position()`** — new function that snaps a candidate back to its nearest extreme point after rotation, fixing candidate drift from floor anchor and right-wall candidates.

#### Top-K Tighten Architecture
- **`engine/distribution.py::find_best_for_pkg()`** — scores all candidates, tightens the top 5, then re-scores before picking the best. Replaces "tighten everything" approach that caused 20–50× runtime blowup. ~1.5–2× overhead vs original.
- **`engine/auto_arrange.py::LargestFirstStrategy.arrange()`** — same top-K tighten applied to both main and gap-filling passes.

#### Local Rearrangement
- **`engine/distribution.py::_try_local_rearrangement()`** — when the only feasible candidate is a stack, identifies which floor packages geometrically block the floor candidate (clearance-aware AABB overlap), removes ≤3, places the current package, re-places blockers, and only accepts if floor score > stack score. Uses full snapshot/restore via `import_placements` for safe rollback. Recursion depth = max 1.
- **Floor-count guard** — rearrangement only fires when `n_floor ≤ 10` to avoid O(N²) overhead on densely-packed large containers (prevented 3× distribution blowup from 17.8s→54.7s).
- `_snapshot_placements()` / `_restore_placements()` — helpers for clean rollback.
- `_find_blocking_floor_packages()` — calculates which floor packages block a candidate position.
- `_best_floor_candidate()` — picks the best floor-level position for a given package.

#### Repair Optimizer
- **`engine/repair.py::_is_better()`** priority 3 flipped from `n_floor > o_floor` to `n_floor < o_floor` (prefer smaller empty floor regions). No impact on current dataset (always returns `Improved: False`).

#### Benchmark Correction
- **Old benchmark was wrong**: loaded 31 DB rows with no quantity expansion (vs web UI 46 instances from PACKAGES with qty). Also omitted `cargo_length_mm`/`cargo_width_mm`/`cargo_height_mm`/`payload_kg` from vinfo dict, so `_vehicle_capacity()` returned 0 for all and vehicles sorted in plate-number order (smallest first) instead of largest-first by capacity.
- **Corrected benchmark**: 46 packages, 32 vehicles sorted by `volume × max(payload, 1)` descending. Largest = V38/V39 (9700×2370×2300mm, 52.9m³). Results: 2 vehicles (was 5), 12 stacks baseline → 9 with rearrangement. Repair remains a no-op (Improved: False).

### Added
- `_count_stacks()` and `_per_vehicle_empty_floor()` helpers in `engine/repair.py` (diagnostic utilities).
- `scripts/benchmark_final.py` — corrected 46-package 3-config benchmark (Run A: baseline, Run B: rearrangement, Run C: rearrangement+repair).

---

## 2026-07-20 — Largest-Vehicle-First Fleet Distribution, Strict Unstackable Enforcement, Door-Aware Animation

### Changed

#### Fleet Distribution: Best-Fit Decreasing → Largest-Vehicle-First
- **`engine/distribution.py:176`** — rewritten `distribute_across_vehicles()`:
  - Sorts vehicles by combined capacity (volume_mm³ × payload_kg) descending
  - For each vehicle (biggest → smallest), tries to place all remaining packages
  - Leftovers roll over to the next (smaller) vehicle
  - Removed waste estimation (`estimate_remaining_after` no longer called)
  - Removed Phase 3 rear-door redirect (no longer needed)
  - Removed per-package BFD cross-vehicle comparison

#### Package Sort: Priority-Grouped → Strict Volume Descending
- **`engine/distribution.py:192-194`**: removed `_pkg_priority()` grouping; sort is now purely `-volume`
- **`engine/auto_arrange.py:48-51`**: same change — no more non-stackable-before-stackable grouping
- Placement sequence within each vehicle is now strictly biggest-first, eliminating `big → small → big → small` patterns

#### Strict Unstackable Enforcement
- **`engine/support.py:60-63`**: added top-package check in `_check_stacking_rules()` — an unstackable package (`stacking_mode=NONE`) cannot be placed on top of another package
- **`engine/package.py:33-35`**: added `__post_init__` to `Package` dataclass — auto-derives `stacking_mode` from `stackable`:
  ```python
  if not self.stackable and self.stacking_mode == StackingMode.NORMAL:
      self.stacking_mode = StackingMode.NONE
  ```
  Previously only `Package.from_dict()` derived `stacking_mode` correctly; all direct `Package(...)` construction sites left it at the default `NORMAL`, so `stackable=False` had no effect on stacking validation.

#### Door-Used Propagation (Animation)
- **`engine/placement.py:14`**: added `door_used: str = "rear"` to `Placement` dataclass
- **`engine/validation.py:27`**: added `door_used: str = "rear"` to `ValidationResult`
- **`engine/validation.py:153`**: captures `door_used` from `check_door_sweep()` result
- **`engine/planner.py:60`**: passes `result.door_used` to `append_placement()`
- **`engine/state.py:63`**: stores `door_used` on the `Placement`
- **`routes.py:718`**: includes `door_used` in the frontend placement dict
- **`static/js/truck-load-planner.js:3126`**: reads `placement.door_used` and selects entry point:
  - `"rear"` → `(d.len + pl, y, z)`
  - `"side_right"` → `(x, y, d.wid + pw)`
  - `"side_left"` → `(x, y, -pw)`

### Removed
- `estimate_remaining_after()` is no longer called by `distribute_across_vehicles` (kept for backward compat)
- BFD waste estimation logic
- Phase 3 rear-door redirect logic

---

## 2026-07-19 — Dead Space Quality (Future-Packability Estimation)

### Added

#### Dead Space Quality Scoring
- **`engine/dead_space.py`** — new module implementing future-packability estimation:
  - `compute_dead_space_quality()` — estimates how usable the remaining free space will be after placing a package
  - **Gap-ray heuristic**: for each of 6 faces, measures distance to nearest obstacle (package or wall) in the outward direction — O(faces × nearby_packages)
  - **Flush-face exclusion**: faces with gap ≤ 10mm are skipped (cannot create dead space)
  - **Difficulty-weighted reference set**: selects the 3 hardest remaining packages (by volume × aspect ratio); harder packages dominate the per-face score
  - **Continuous scoring**: product of clamped sorted-dimension ratios — smooth 0–1, no binary fit/no-fit
  - **Area-weighted**: larger faces contribute more to the final quality score
  - **Spatial index support**: uses `query_aabb_fn` when available for O(nearby) instead of O(all_placements)
- **`dead_space_quality: 10`** added to `SCORING_WEIGHTS` in `engine/scorer.py` (total now 130, clamped to 100)
- `remaining_packages` parameter threaded through `Planner.score_placement()` → `Planner.evaluate_position()` → `scorer.score_placement()`
- `LargestFirstStrategy.arrange()` in `auto_arrange.py` now passes `sorted_packages[i+1:]` as remaining packages at both main-candidate and Y-slide evaluation sites
- `_find_best_for_pkg()` in `routes.py` now accepts and forwards `remaining_pkgs` for all 3 phases

### Changed
- `SCORING_WEIGHTS` total increased from 120 to 130 to accommodate `dead_space_quality: 10`
- `score_placement()` and `Planner.score_placement()` accept optional `remaining_packages` parameter (defaults to None → no dead-space penalty)
- `test_weights_are_configurable` updated for new weight key and sum (120→130)
- `test_score_placement_returns_placementscore` updated to assert `dead_space_quality` in breakdown

---

## 2026-07-19 — Y-Balance, X-Preference, Rear-Proximity Scoring; Combined-Support Stacking; Rear-Door Routing; Y-Slide Fallback

### Added

#### Weight-Balance Scoring (Y-Balance)
- **`_score_y_balance()`** in `engine/scorer.py` — computes Y-centre-of-gravity of all packages (existing + candidate) using actual `weight_kg` values; rewards positions that bring the COG closer to `container.width / 2`
- Weight `y_balance: 15` — new scoring factor for even left-right weight distribution
- Reduced `wall_contact` 15→10 and `z_preference` 20→10 to accommodate

#### X-Preference & Rear-Proximity Scoring
- **`_score_x_preference()`** — rewards low x values (deep placement near front wall); weight 5
- **`_score_rear_proximity()`** — penalizes packages whose rear edge is within 8% (min 300mm) of the rear door; weight 10
- Together these create a strong gradient pushing packages toward the front wall while avoiding the rear door
- Reduced `package_contact` 20→15 and `compactness` 10→5 to accommodate

#### Combined-Support Stacking Model
- **`engine/support.py`** — replaced the per-package footprint area check with a combined-support model:
  - Grid-samples candidate XY footprint (20×20); counts samples inside **any** below package's AABB (union of overlap regions)
  - Requires coverage ≥ 90% of candidate footprint (configurable via `support_threshold` parameter)
  - **Centre-of-mass guard**: candidate's XY footprint centre must lie within at least one below package's XY extent — prevents unstable bridging/overhang
  - Allows realistic stacking across multiple adjacent packages (e.g., wide box on two narrower boxes side-by-side)

#### Right-Wall Candidate
- Added `(0, container.width - pkg.width - clearance, 0)` as a base candidate in both `auto_arrange.py` `arrange()` and `routes.py` `_find_best_for_pkg()`
- Gives the scorer a balanced starting point instead of always biasing to `y=0`

#### Y-Slide Fallback
- **`generate_slide_candidates()`** in `engine/candidate_points.py` — when a package fails all extreme-point candidates, slides each base candidate left/right in Y by steps of 100mm (up to 3 steps each direction)
- Integrated into both `LargestFirstStrategy.arrange()` and `_find_best_for_pkg()` in `routes.py`

#### Phase 3 — Rear-Door Redirect (Vehicle Distribution)
- **`_distribute_across_vehicles()`** now includes Phase 3: if the best position touches the rear wall (`xmax ≥ container.length`), redirect the package to the last vehicle unconditionally (if it can accommodate)
- Fills the last vehicle's unused space with packages that would be unloaded first

#### Clearance Margin
- `clearance_mm: float = 10.0` field added to `Package` dataclass (`engine/package.py`)
- `AABB.from_dimensions()` accepts optionally inflated AABBs via `clearance` parameter (`engine/geometry.py`)
- Spatial AABBs in `state.py` store inflated AABBs; extreme points offset by `+2*clearance`
- Boundary check uses actual AABB; collision uses inflated AABB; support uses actual AABB

### Changed

#### Candidate Priority — Removed Y Bias
- Factor 5 in `_candidate_priority()` changed from origin-proximity (biased to `y=0`) to front-center proximity (no Y bias): `dist = sqrt(x² + (y − width/2)² + z²)`
- Packages are no longer pulled toward the left wall; scorer's `y_balance` handles left-right distribution

#### Scoring Weights Rebalanced
| Category | Old | New |
|----------|-----|-----|
| floor_contact | 25 | 25 |
| wall_contact | 15 | 10 |
| package_contact | 20 | 15 |
| face_contact | 10 | 10 |
| compactness | 10 | 5 |
| stack_quality | 5 | 5 |
| vertical_stability | 10 | 10 |
| z_preference | 20 | 10 |
| x_preference | — | 5 |
| rear_proximity | — | 10 |
| y_balance | — | 15 |
| **Total** | **115** | **120** |

### Fixed
- `_find_best_for_pkg()` now converts `candidates` to a mutable list before inserting the right-wall candidate
- `test_score_placement_corner_best` updated — y_balance makes centre positions competitive with corners
- `test_weights_are_configurable` updated for new weight keys and sum

---

## 2026-07-19 — Best-Fit Decreasing, Candidate Priority, Stacking Defaults, 3D Fullscreen & Labels

### Added

#### Best-Fit Decreasing (Vehicle Selection)
- **`_distribute_across_vehicles()`** in `routes.py` changed from First-Fit Decreasing to **Best-Fit Decreasing (BFD)**:
  - New `_estimate_remaining_after()` helper computes vehicle fullness after placement as three ratios (volume%, floor%, payload%)
  - Primary comparator: sum of three remaining ratios (lower = tighter fit → better)
  - Secondary comparator (tiebreaker): placement score
  - Previously used a blended weighted score; now uses clean two-tier comparison
  - BFD picks the vehicle that will be fullest after accepting the package, rather than the first that fits

#### Candidate Priority (Pre-Validation Ranking)
- **`_candidate_priority()`** in `routes.py` — module-level function that ranks extreme-point candidate positions BEFORE expensive validation:
  - Five factors scored independently (total 0–100):
    - **Touching surfaces** (0–60): counts how many container walls (rear, left, right, floor) the candidate touches; more touching = higher score
    - **Z-height** (0–15): inverse of z-start; lower positions score higher
    - **Wall-contact area** (0–15): package footprint edge length touching container walls, normalised to max possible; rewards wall-hugging
    - **Back-to-front loading** (0–20): prefers low X (rear wall); score drops linearly as X increases; naturally enforces rear-first placement without hard constraints
    - **Origin proximity** (0–10): distance from (0,0,0); closer is better (avoids floating islands)
  - `_find_best_for_pkg()` expands candidates with both rotations, then sorts them by priority descending
  - Validation loop can early-exit as soon as a high-score candidate is validated (since highest-priority + best-scoring so far are checked first)
  - Over 2× reduction in validation calls vs brute-force order

#### Back-to-Front Loading
- Back-to-front priority factor integrated into `_candidate_priority()` (score 0–20)
- No explicit ordering constraint — packages naturally load toward the front (high X) as the rear fills, guided by the priority rank
- Replaces need for a separate `load_sequence` sort on the frontend

#### 3D View Toolbar & Fullscreen
- **`#tlp-3d-toolbar`** with step animation controls (prev/next/play/end/counter) inside the 3D container; visibility toggled by `_sync3DToolbar()`
- **Fullscreen toggle** via `#tlp-3d-btn-fullscreen`: adds `.fullscreen` CSS class (fixed viewport cover, z-index 9999, no-resize) — uses CSS positioning, not the native Fullscreen API
- **Toolbar opacity**: `0` in normal state, `1` on hover or when `.fullscreen`
- **Package labels**: `_makeTextSprite()` creates a THREE.Sprite with the package name rendered on a canvas; displayed 30px above each package in `update3DScene()` and `_stepShowPermanent()`
- **Keyboard shortcuts**: `F` toggles fullscreen; `Escape` exits fullscreen (along with existing deselect)

### Changed

#### Stacking Defaults (`stackable`)
- **`routes.py:830`**: inline-packages branch of `_get_packages_from_request` hardcoded `stackable=True`; now reads dict key
- **`session.py:49`**: `_from_legacy_dict` default changed from `1` (True) → `0` (False)
- **`engine/planner.py:359,372`**: `load_legacy_placements` default changed from `1` (True) → `0` (False)
- **`routes.py:772`**: `_build_placement_dict` now exports both `"stackable"` and `"allow_stacking"` keys for frontend compatibility

#### Candidate Point Rotation
- **`engine/candidate_points.py:28–34`**: standalone `generate_candidate_points` now swaps length/width for rotation 90/270 (was using raw `length_mm`/`width_mm` unchanged)

#### Door Sweep Always Enabled
- **`engine/validation.py:87–98`**: when no door features configured, defaults to `{"rear_door": {"width_mm": container.width, "height_mm": container.height}}` so the sweep check always runs

#### Step Animation Buttons Persist
- `_stepEndMode()` accepts optional `resetStep` param (default `true`); completion paths (`stepEnd`, auto-play finish) pass `false` so toolbar buttons remain visible after animation ends

### Fixed

- **Fullscreen toolbar sync**: `toggle3DFullscreen()` now calls `_sync3DToolbar()` so step buttons appear on entering fullscreen
- **`update3DScene()` step-mode guard**: calls `_stepEndMode(false)` instead of `_stepEndMode()` to prevent hiding buttons on scene refresh
- **Back view left/right inversion**: the 2D back view now correctly renders the container from the rear perspective looking forward — the left wall (Y=0) appears on the right side of the canvas, matching real-world orientation. Updated `_drawPackages`, `_focusOnPackage`, drag-and-drop, `_showPreview`, `_throttledValidate`, `_onDrop`, and `_quickValidate` to consistently flip the X axis for the back view.

---

## 2026-07-18 — Multi-Vehicle Distribution, Door Access Validation, Step Animation

### Added

#### Multi-Vehicle Distribution (First-Fit Decreasing)
- **`_distribute_across_vehicles()`** in `routes.py` rewritten to use **First-Fit Decreasing** bin packing:
  - Maintains `active_indices` — vehicles that already hold packages
  - **Phase 1**: tries active vehicles first (fills them to capacity)
  - **Phase 2**: only opens a new vehicle when no active one can accommodate
  - Result: minimises total vehicle count naturally
- Shared candidate evaluation extracted into `_find_best_for_pkg()` helper
- `new_active` variable prevents premature marking during Phase 2 iteration

#### Door Access Validation (`engine/access.py` — new module)
- **`check_rear_door()`**: validates package cross-section fits through rear door opening AND sweep volume from rear wall to position is clear of placed packages
- **`check_side_door()`**: validates cross-section fits side door, package X-range overlaps door position, sweep from side wall is clear (both left and right walls)
- **`check_door_access()`**: orchestrator — tries rear door → side_right → side_left, returns `door_used` or failure reason
- Integrated into `validate_placement()` — every candidate position in auto-arrange is validated against door access

#### Weight Constraint in Stacking (`engine/support.py`)
- **Rule 5**: top package must be lighter than every package directly below it
- `check_support()` now accepts `package` parameter for weight comparison
- Updated `validation.py` and `planner.py` to pass package to support check

#### Step Animation (Frontend)
- **Fly-in animation**: each package starts outside the rear door (`x = container.length + pl`) and slides into its final position over 500ms with cubic ease-out
- Driven by `requestAnimationFrame` inside `_animate3D()` — mesh position is interpolated via `lerpVectors`
- Step state tracked separately (`_stepPermanentPkgs[]`, `_stepAnimState`) to avoid conflicts with `update3DScene()`
- Auto-cleanup: step mode ends and scene rebuilds when complete or on normal `update3DScene()` call

#### Step UI Controls
- **◀ Prev**: go back one step, re-show all previous packages
- **0/15** counter: current step / total
- **▶ Next**: advance one step (animate next package flying in)
- **▶▶ Play**: auto-play all steps sequentially (700ms per package)
- **⏭ End**: show all packages immediately, exit step mode

#### Arrange Results Panel
- New **Arrange Results** section in left sidebar after auto-arrange
- Lists every vehicle that received packages with its count
- Click any vehicle to switch the viewer to its placements and start step animation
- Auto-enables 3D view if not already on

### Changed
- **Auto-arrange always uses multi-vehicle distribution** — removed `vehicle_id` from payload; the backend distributes across all vehicles with container configs
- **`update3DScene()`**: accepts optional `skipPackages` boolean for step animation mode
- **`_getContainerDims()` fallback**: now handles `currentContainer` being null by reading from `currentVehicle` directly

### Fixed
- **Mesh leak in step animation end**: `stepEnd()` now calls `_stepClearPermanent()` before exiting to properly dispose Three.js meshes
- **Null scene guard in `_stepClearPermanent()`**: checks `this._threeScene` before attempting `scene.remove()`
- **Animation deadlock**: `_stepNext()` fallback path handles case where `_stepCreateAnimMesh()` returns null (shows package immediately instead of hanging)

---

## 2026-07-18 — Phase 4: Auto Arrange Engine (v1)

### Added
- `engine/auto_arrange.py` — Strategy-based automatic package placement
- `LargestFirstStrategy`: non-stackable first, volume/footprint/weight desc, 0/90° rotations, early-exit at 99.99+
- `Planner.auto_arrange()`, `Planner.validate_position()`
- `POST /api/tlp/auto-arrange` endpoint
- UI toolbar button with `app.autoArrange()`
- Multi-vehicle mode when `vehicle_id` is omitted (greedy per-package best-fit)

### Fixed
- Package list not appearing on first load (tab default was "Placed")
- Auto Arrange required a selected vehicle (now supports multi-vehicle)
- `savePackage()` ignored HTTP errors

---

## 2026-07-18 — Phase 3: Placement Evaluation Engine

- `PlacementScore` dataclass with `total`, `breakdown`, `warnings`, `metadata`
- `SCORING_WEIGHTS` (totals 100): floor_contact 25, wall_contact 15, package_contact 20, face_contact 10, compactness 10, stack_quality 5, vertical_stability 10, z_preference 20
- 7 isolated scoring functions + `z_preference` (added in later revision)
- `planner.evaluate_position()`, `evaluate_candidates()`, `evaluate_plan()`

---

## 2026-07-18 — Door Rendering Fixes

- Vehicle management rear door scaling fix (geometry_json/geometry fallback)
- TLP 3D rear door width was hardcoded to 50mm; now uses feature geometry
- Added interior floor plane to vehicle management 3D view

---

## 2026-07-18 — Gravity, Stacking & Engine Refinement

- Gravity simulation in side/back views (snap Z to floor or stackable top)
- `engine/support.py` — area-based stacking validation
- `engine/candidate_points.py` — candidate position generator
- `engine/planner.py` — orchestrator with evaluate APIs
- Package create/edit: Allow Stacking checkbox, Quantity input
- Various coordinate/boundary/drag bug fixes

---

## 2026-07-18 — Inline Package Editor & Canvas UX

- Create/edit packages directly in sidebar
- Weight enforcement on drag-and-drop
- Canvas pan, rotation buttons, undo/redo
- Package centering on palette drag, grab offset preservation

---

## 2026-07-13 — Container Fuel, Anomaly Detection, Vehicle Management

- Fuel Efficiency Dashboard (KPIs, chart, refuel log, anomaly highlighting)
- Container Fuel page with partial-tank support
- Anomaly Detection (moving-average baseline + adjustable multiplier)
- Vehicle Management CRUD with vehicle type presets
- Per-vehicle baseline profiles (normal L/100km)
- Refuel log CRUD with modal and CSV export

---

## 2026-07-11 — Refinements

- All efficiency units consistently L/100km
- Day selector for per-day filtering
- Total Spend KPI card
- No-KM row highlighting with ⚠ badge
- Dynamic month population from actual data
