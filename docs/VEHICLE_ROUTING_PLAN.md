# Vehicle-Constrained Routing — Plan

Status: **Phases A, B and C shipped 2026-07-31** (see `docs/CHANGELOG.md`).

**Envelope data, re-verified 2026-08-15** against `routing_system.db` — unchanged since
the 2026-08-06 check below:

| Column | Populated | Note |
|---|---|---|
| `gross_weight_kg` | **32 of 36 vehicles** | Backfilled 2026-07-31 from the fleet spreadsheet (`scripts/fill_vehicle_gvw_2026-07-31.sql`). The 4 gaps are exactly the 4 Container vehicles |
| `overall_height_mm` | 0 of 36 | |
| `overall_width_mm` | 0 of 36 | |
| `overall_length_mm` | 0 of 36 | |
| `axle_load_kg` | 0 of 36 | |

So the original "running entirely on `type_default` estimates" is no longer quite
right: **weight** is real data for every non-container vehicle, which is the input
`ors_vehicle_type()` uses to choose `goods` vs `hgv`. **Dimensions and axle load are
still entirely `type_default`**, and every route computed from an estimate is labelled
as one on screen.

The registration-certificate data in §3.1 is still missing for the four dimension
columns and was not treated as a release blocker. Swapping estimates for measured
values remains a data task with no code attached: fill the columns and the routing
follows. Re-derive the table above with:

```sql
SELECT COUNT(*), COUNT(gross_weight_kg), COUNT(overall_height_mm),
       COUNT(overall_width_mm), COUNT(overall_length_mm), COUNT(axle_load_kg)
FROM vehicles;
```

One decision changed during implementation: `options.vehicle_type` is derived
from **actual gross weight**, not the vehicle_type label. See the phase C
changelog entry.

Goal: routes that respect each vehicle's physical limits (weight, height, width,
length) and never cross a national border, even if the legal route is longer.

### Decisions taken (2026-07-31)

- **Scope.** `avoid_borders: "all"` applies at **both** ORS call sites
  (`app/services/routing.py` for the fleet map, `services/delivery/eta_service.py`
  for dispatch ETAs). Dimension restrictions go into **delivery only** for now.
- **No compliant route.** Do not fail closed and do not hide it. Fall back to a
  less-restricted route, **draw it in red**, and warn the dispatcher explicitly.
  Design in §5.
- **Envelope data source.** Understood to be existing fleet master data. It is
  not — see §3.1. Unresolved.

---

## 1. What ORS supports

Verified against the [ORS routing-options reference](https://giscience.github.io/openrouteservice/api-reference/endpoints/directions/routing-options)
(v9.7.1), not from memory.

For `profile=driving-hgv`, inside the request body's `options` object:

```json
{
  "avoid_borders": "all",
  "vehicle_type": "delivery",
  "profile_params": {
    "restrictions": {
      "length": 6.2,
      "width": 2.1,
      "height": 3.2,
      "weight": 4.99,
      "axleload": 3.4,
      "hazmat": false
    }
  }
}
```

Units: **metres** for length/width/height, **tonnes** for weight/axleload.

Three things the docs are explicit about, each of which changes the design:

1. **There are no defaults.** A restriction that isn't sent isn't applied. Sending
   four of five limits silently leaves the fifth unchecked.
2. **`options.vehicle_type` is mandatory for restrictions to work at all.** It
   selects which OSM access tags are honoured (`hgv=no` vs `goods=no` vs
   `delivery=no` and so on). Omit it and the restrictions object is inert.
   Allowed: `hgv`, `bus`, `agricultural`, `delivery`, `forestry`, `goods`.
3. **`avoid_borders: "all"` is a `driving-*` option** and is independent of
   everything above — it needs no vehicle data and can ship on its own.

---

## 2. Three blockers in the current code

### B1 — Both ORS calls use GET, which cannot carry `options`

`options` is a **request-body** parameter. Both call sites use the GET form:

- `app/services/routing.py:31` — `f"{ORS_BASE_URL}/{profile}"` with
  `params={"api_key", "start", "end"}`
- `services/delivery/eta_service.py:44` — identical shape

There is no query-string equivalent. Every restriction below requires moving to
`POST {ORS_BASE_URL}/{profile}/geojson` with a JSON body and the key in an
`Authorization` header. The GeoJSON response shape appears to match what both
parsers already expect (`features[0].properties.segments[0]`,
`geometry.coordinates`), so downstream code should be unaffected — but that is an
assumption and step A0 below is to prove it against the real endpoint before
anything is built on it.

### B2 — `get_routing_profile()` is dead branching

```python
if "dau" in vehicle_type or "heavy" in ...:  return "driving-hgv"
if "tai" in vehicle_type or "van" in ...:    return "driving-hgv"
return "driving-hgv"
```

All three branches return the same value. This is, however, exactly the right
place for the `vehicle_type` → ORS `options.vehicle_type` mapping that B1 needs,
so it gets a purpose rather than a deletion.

### B3 — A failed restricted route currently degrades into a straight line

`calculate_eta()` catches everything and falls back to a haversine straight line
with `source: "haversine_fallback"`. Once restrictions are on, ORS error 2009
("route could not be found") stops meaning "ORS had a problem" and starts meaning
**"no legal route exists for this vehicle to this stop"** — which is precisely the
information this feature exists to surface. Papering over it with a straight-line
estimate would hide the one answer the dispatcher needs.

"ORS unreachable" and "no route satisfies this vehicle" must become
distinguishable in the response, and the second must be visible on the dashboard.

---

## 3. The data gap — this is the real work

### 3.1 The fleet master data does not contain vehicle dimensions

Checked exhaustively, not assumed. Every one of the 23 tables in
`routing_system.db` was scanned for any column matching
`weight|height|width|length|gvw|axle|tare|kerb|gross|dimen|spec`. Two tables
matched:

- `container_configs` → `cargo_length_mm`, `cargo_width_mm`, `cargo_height_mm`
  (plus `payload_kg`) — the **cargo compartment**, for the bin-packing planner.
- `tlp_packages` → `length`, `width`, `height`, `weight_kg` — the **packages**
  being loaded.

Nothing else. No gross vehicle weight, no overall height, width or length, no
axle load, no tare weight, anywhere in the schema. There is also no spreadsheet
or CSV in the repository holding them (`data/` is empty; no `.xlsx`/`.csv` exists
outside the virtualenvs).

`container_configs` is the natural thing to mistake for fleet master data — it is
per-vehicle, it is dimensional, and it is the only such table. It cannot serve
this purpose, for the reasons in the table below.

**This is the blocker.** Phases A (border avoidance) and B (schema + form) can
proceed regardless. Phase C cannot produce a correct route until real numbers
exist.

### 3.2 Why the cargo numbers cannot stand in

`container_configs` is linked from `vehicles.container_config_id` (32 of 36
vehicles). `vehicles` itself holds only `plate_number`, `vehicle_type`,
`current_driver`, `container_config_id`. The Add/Edit Vehicle form in
`vehicle-management.html` collects plate, type, driver, the four cargo numbers and
door geometry — nothing about the vehicle envelope.

Cargo-box numbers are **not** substitutes, and the substitution fails in the
dangerous direction:

| ORS needs | Meaning | Nearest stored value | Why it must not be used |
|---|---|---|---|
| `height` | ground → highest point | `cargo_height_mm` (1.58–2.35 m) | Excludes chassis, floor and roof. A truck with a 2.35 m box stands well over 3 m. Declaring 2.35 m routes it under bridges it will hit. |
| `width` | widest point | `cargo_width_mm` (1.55–2.40 m) | Excludes mirrors and body overhang. |
| `length` | bumper → bumper | `cargo_length_mm` (3.02–9.70 m) | Excludes the cab entirely — off by 2 m or more. |
| `weight` | **gross** vehicle weight, laden | `payload_kg` (880–8 900 kg) | Payload excludes kerb weight. A "2.5 t" truck carrying 1 600 kg has a GVW near 5 t. Understated by the whole tare weight. |
| `axleload` | per-axle load | *nothing* | Not stored anywhere. |

Mapping cargo dimensions onto ORS restrictions would produce routes that look
constrained and are not. That is worse than today's unconstrained routing, because
today nobody believes the route is height-checked.

So: **new vehicle-envelope fields are a prerequisite, not an optional extra.**

### Proposed shape

Additive nullable columns on `vehicles` (no new table — one row per vehicle
already exists and this is per-vehicle data):

```
gross_weight_kg     INTEGER   -- GVW from the registration certificate
overall_height_mm   INTEGER
overall_width_mm    INTEGER
overall_length_mm   INTEGER
axle_load_kg        INTEGER   -- nullable; omitted from the request when unset
```

With a per-`vehicle_type` fallback table (7 types exist: 1.5/2.5/5/8/9/10 Tons,
Container) in one module, used **only** when a vehicle's own column is null.

And a hard rule: the API response carries `restrictions_source` —
`"vehicle"` | `"type_default"` | `"none"` — so the dashboard can show that a route
was computed from an estimate rather than from the truck's actual papers. Silent
fallback to a default is how a wrong number becomes trusted.

---

## 4. Phasing

### Phase A — border avoidance + POST migration  ✅ shipped

Independent of all vehicle data; deliverable on its own.

One deviation from the plan as written: A0 was satisfied against the ORS v9.7.1
specification rather than a live call, because the API key lives in `.env` and is
not read. The first deployment should confirm a known-good route still returns a
route.

- **A0.** Prove the POST `/geojson` response shape against the real endpoint
  before touching either parser. Everything else depends on this.
- **A1.** `app/services/routing.py` and `services/delivery/eta_service.py` move
  from GET to POST with a body. Behaviour otherwise identical.
- **A2.** Send `{"avoid_borders": "all"}` on every request. This is the piece
  that needs no new data and satisfies "avoid crossing border no matter longer
  route" on its own.
- **A3.** Split ORS failure modes so 2009 is not reported as a network problem
  (B3). Straight-line fallback stays for genuine unavailability only.

Acceptance: identical routes to today for a domestic trip, plus a route that
previously crossed into Cambodia now detours or reports no route.

Both call sites get `avoid_borders` — that is the agreed scope, and it costs
nothing since it needs no vehicle data. `app/routes/trips.py` runs the background
refresh thread, so A1's POST migration there is the riskier half of this phase and
should land separately from the delivery side.

### Phase B — vehicle envelope data  ✅ shipped (B1–B3; B4 is yours)

- **B1.** Migration adding the five nullable columns (`app/database/migrations.py`,
  additive, matching the existing `ALTER`/backfill style).
- **B2.** `app/routes/fleet.py` create/update carry the new fields; the Add/Edit
  Vehicle form in `vehicle-management.html` gains a "Vehicle envelope" group,
  visibly separate from the existing "Cargo compartment" group so the two are
  never confused again.
- **B3.** A per-type fallback map, and `restrictions_source` on the response.
- **B4.** Someone fills in 36 rows. **This is a data-entry task, not a code task,
  and it is the critical path** — Phase C is inert until it is done. The vehicles
  table should show which trucks still lack envelope data so the gap is visible
  and shrinking rather than invisible.

### Phase C — apply the restrictions  ✅ shipped

Delivery only, per the agreed scope — `services/delivery/eta_service.py`. The
fleet map keeps unrestricted routing (with borders avoided) until this has proved
itself in dispatch.

- **C1.** One builder, `app/services/vehicle_routing.py`, turning a vehicle row
  into an ORS `options` dict. Placed in `app/services/` rather than inside the
  delivery package because the fleet map is the obvious second consumer once this
  settles, and the delivery package already imports `app.db` and
  `app.services.ttas_client`, so the direction is established.
- **C2.** `get_routing_profile()` becomes the `vehicle_type` → ORS `vehicle_type`
  mapping (B2 above): the 1.5–2.5 t box trucks are `delivery` or `goods`; the
  8–10 t and Container vehicles are `hgv`. This choice changes which OSM access
  tags apply and should be made deliberately, not defaulted.
- **C3.** **The ETA cache key must include a fingerprint of the restriction set**
  (`services/delivery/eta_service.py:_stops_cache_key`). It is currently
  `(stop_id, lat, lng)` per stop plus GPS. An assignment's vehicle is fixed, so
  the exposure is narrow — but editing a truck's specs would keep serving routes
  computed under the old ones until the process restarts.
- **C4.** The degraded-route path, below.

---

## 5. When no compliant route exists

Decided: draw it anyway, in red, with an explicit warning. The dispatcher keeps a
usable ETA and owns the decision; nothing is silently hidden and nothing silently
blocks.

### Retry ladder

Per failing leg:

1. Request with the vehicle's full restriction set.
2. On ORS error **2009** (route not found) — and only 2009 — retry **once** with
   the dimension restrictions dropped. `avoid_borders: "all"` is **kept on both
   attempts**: the border rule is absolute and is not part of the degradation.
3. If attempt 2 succeeds, return it tagged `restriction_status: "violated"`.
4. If attempt 2 also fails, that is a genuine no-route (or ORS trouble) and takes
   the existing failure path.

Each leg carries `restriction_status`: `"compliant"` | `"violated"` |
`"unrestricted"` (no envelope data for this vehicle) | `"unknown"` (ORS
unavailable, haversine estimate). Four states, because collapsing them is how a
guess gets read as a fact.

### Why we cannot say *which* limit was breached — cheaply

ORS reports only that no route was found; it does not name the blocking
restriction. Identifying the culprit means re-requesting with one restriction
dropped at a time — up to five extra calls **per failing leg**, against a 40
requests/minute budget that `/api/eta` is already close to.

So: the default warning names the vehicle's limits and says the route could not
respect them, without claiming which one. If per-restriction attribution turns out
to matter operationally, it belongs behind an explicit "why?" action on that
stop — one dispatcher-initiated diagnosis, not five calls on every poll.

### Presentation

- The leg's polyline renders red on the map, distinct from the normal route
  colour, and must stay legible on both the satellite and near-white basemaps —
  the same two-tone rule the vehicle markers follow.
- The stop's timeline row carries a warning with the vehicle's declared limits.
- The vehicle raises an attention flag reusing the Phase 0 severity tiers, so this
  arrives through the channel dispatchers already scan rather than a new one.
- `restriction_status: "unrestricted"` gets its own, quieter treatment. "We did not
  check" and "we checked and it failed" are different claims and must not share a
  colour.

---

## 6. What this will and will not prevent

Stating this plainly matters more than the feature does. A restriction system
that is trusted beyond its evidence is more dangerous than none.

**Will help:** ORS honours OSM's `maxheight`, `maxweight`, `maxwidth`,
`maxlength` and the `hgv`/`goods`/`delivery` access tags where they are present,
and `avoid_borders: "all"` is a hard graph-level constraint that does not depend
on tagging at all.

**Will not help:**

- **OSM restriction tagging in Vietnam is sparse** compared to Western Europe,
  where these ORS features were built and tuned. An untagged low bridge is
  invisible to the router. This lowers risk; it does not remove it, and drivers
  must not be told the route is guaranteed.
- **HCMC truck curfews (giờ cấm tải)** — time-windowed bans on trucks in the
  inner city — have no representation in ORS at all. For a fleet on 50/51-series
  plates this is plausibly a larger day-to-day exposure than bridge heights.
  Out of scope here; naming it so it is not assumed to be covered.
- **Axle-load limits** cannot be sent until someone sources the numbers; the
  parameter is omitted rather than guessed.

**Rate limits.** The public ORS free tier is documented at 40 directions requests
per minute and roughly 2 000–2 500 per day (worth confirming against the account
in use). `/api/eta` already issues one call per remaining stop, serially — 40
vehicles × 10 stops is 400 calls for one full refresh, before the `trips.py`
background thread. Restrictions do not increase the call count, but this feature
lands on a budget that is already tight, and the existing route cache is what is
holding it together.

---

## 7. Open questions

1. **Where do the envelope numbers come from?** The one blocker. They are not in
   the database (§3.1), so they have to be transcribed from somewhere:
   registration certificates (`giấy đăng kiểm`, which carry GVW and overall
   dimensions), manufacturer specs by model, or physical measurement — the last
   giving dimensions but no GVW. Until this is answered, Phase C has nothing to
   compute from.
2. **`options.vehicle_type` per fleet segment.** The 1.5–2.5 t box trucks are
   plausibly `delivery` or `goods`; the 8–10 t and Container vehicles `hgv`. This
   selects which OSM access tags are honoured, so it is an operational decision
   rather than a default to be picked in code.
3. **`hazmat`** — does anything in this fleet carry hazardous goods? Assumed
   false.
4. **ORS plan in use.** Whether `ORS_BASE_URL` points at the public API or a
   self-hosted instance changes the rate-limit picture in §6 entirely. Not read
   from `.env` here by policy.

---

## References

- [ORS Routing Options (v9.7.1)](https://giscience.github.io/openrouteservice/api-reference/endpoints/directions/routing-options)
- [ORS tag filtering — driving-hgv](https://giscience.github.io/openrouteservice/technical-details/tag-filtering)
- [ORS API restrictions and rate limits](https://openrouteservice.org/restrictions/)
- [ORS country list (for `avoid_countries`)](https://giscience.github.io/openrouteservice/technical-details/country-list)
