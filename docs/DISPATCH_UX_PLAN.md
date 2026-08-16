# Dispatch Dashboard — UX Improvement Plan

Status: **Phase 0 shipped 2026-07-31** (see `docs/CHANGELOG.md` for what landed and
why). Phases 1–2 remain proposed and unapproved as of **2026-08-15**; they are
sketched here to the level needed to judge whether Phase 0's choices boxed them in —
they did not.

**Verified still-unshipped (re-checked 2026-08-15):** `planned_arrival_at` and
`service_minutes` appear nowhere in `app/database/migrations.py`, `services/` or
`static/`, and the right panel's empty state is still `Select a vehicle to view stops`
(`timeline.js`). Phase 1's derived schedule and Phase 2's exception queue have not been
started.

**The dashboard did keep moving, outside this plan.** Since Phase 0 it has gained undo
(`/api/execution/revert`), per-stop phase history, photo-proof gating, batch photo
upload, `MTH` lost-signal detection in the No GPS filter, the end-of-day export page,
and a straight-line distance ruler (`dashboard/measure.js`, 2026-08-13). None of that is
Phase 1 or Phase 2 work — it came from operator reports and the delivery audit. Read
this document as the *time-dimension* roadmap specifically, not as a general record of
dashboard progress; `docs/CHANGELOG.md` is that record.

Scope: `templates/delivery-dashboard.html`, `static/js/dashboard/*.js`,
`static/css/delivery-dashboard.css`. Phase 1 additionally touches
`app/database/migrations.py` and `services/delivery/`.

Operating context confirmed with the operator (2026-07-31):

- Stops have **no customer-promised times**. Trucks leave in the morning and work
  the sequence. Any schedule must therefore be *derived*, not entered.
- Dispatchers run this board on a **desktop monitor, all day**. Density and
  keyboard access are first-class; mobile must keep working but is not the target.

---

## 1. Reference practice

Three domains solve a version of this problem and were reviewed for transferable
patterns.

**Emergency dispatch (CAD).** Time-in-status is the primary alarm channel: a unit's
row changes appearance continuously as it sits, so severity is perceived without
reading text. Priority is carried by colour, relative size and position — never by
a uniform badge. Design goal is stated as minimising clicks and rendering priority
intelligible at a glance.

**Air traffic control / electronic flight strips.** The *task* is the unit of work,
not the vehicle. A controller's picture is the whole strip bay; there is no
"select an aircraft to see what's pending" step. Each strip carries planned and
actual on the same line. The literature's repeated warning: badly-tuned alerts
become a hindrance, and a cumbersome UI increases head-down time.

**Situation-awareness theory (Endsley).** Three levels — perception (what is
there), comprehension (what it means), projection (what happens next). Useful as a
scoring rubric below.

**Trucking dispatch boards.** Consistent finding that dispatcher-language quick
filters ("needs attention", "my loads today") outperform generic field filters for
the common case, and that a single row should carry driver, status, current load
and vehicle together.

---

## 2. Current state

### What is already right

Worth stating explicitly, because several of these are load-bearing and must
survive every change below:

- `vehicle-list.js` diffs against previously-rendered cards rather than rebuilding
  `innerHTML`, preserving scroll position and hover, and avoiding a click-listener
  rebind every 12s.
- `polling.js` coalesces refreshes requested mid-flight, and stops polling on
  `visibilitychange`.
- `map.js` never moves the view except on direct click; `withoutAutoPan()` wraps
  background updates.
- The attention strip, per-card attention dot, and "Attention first" toggle are
  already exception-based thinking — this plan extends that instinct rather than
  introducing it.

### Gaps, ranked

**G1 — Nothing in the schema can make a stop late.**
`delivery_plan_stops` has `planned_sequence` but no planned time, no window, no
service duration. `stop_executions` records actuals only. `vehicle-list.js` says so
in its own comments and substitutes three proxies: stuck >20 min at a stop, GPS
stale >15 min, and reporting ~0 km/h while not at a stop. These detect *symptoms of
having stopped*. A truck can be 90 minutes behind while moving perfectly and the
board stays clean. This is the ceiling on everything else.

> **The third proxy did not work until 2026-08-03.** TTAS sends a status phrase rather
> than a number, and the parser took the first digits in it — so a truck stopped
> `1h30'` read as 1 km/h and tripped the ≤2 threshold, while one stopped `3h30'` read as
> 3 and did not. Fixed; expect more of these flags than the board previously showed.
> A caution for the rest of this plan: a proxy that is silent is indistinguishable from
> a proxy that is working, and this one was silent for a month.

**G2 — The "Live" pill can be wrong.**
`/api/execution/dashboard` deliberately returns `gps_source`, `gps_error`,
`gps_matched` and `gps_available`; the code comment states this was surfaced *"so
the dashboard can show a degraded-GPS badge instead of a green Live pill over an
empty map, which is what let C-01 go unnoticed for the module's entire life."*
`main.js:328` reads `data.assignments` and discards the other four.
`polling.setStatus()` knows only `ok` / `error` / `paused`. The backend half of that
fix shipped; the frontend half did not.

**G3 — Fleet triage requires drilling.**
The right panel reads "Select a vehicle to view stops" until a vehicle is clicked.
There is no view answering "what needs me right now" across the fleet. The
attention strip is close, but it is a chip row above the list, not a work queue.

**G4 — 36 vehicles, roughly 8 visible.**
32 box trucks plus 4 containers, per `routing_system.db` on 2026-08-06. (This gap
was written as "40 vehicles / 36 box trucks plus 4 containers" — the box-truck count
had been read as the fleet total. The argument is unaffected: 36 cards at ~5 lines
each in a 280px column still cannot be seen at once.) `.vehicle-card` is a ~5-line
block in that column. The dispatcher can never see the fleet at once, which is the
reason a dispatch board exists.

**G5 — Severity is binary, and the sort ranks the wrong thing.**
All three proxies render as the same dot. A 21-minute stuck and a 3-hour stuck are
visually identical. Worse, "Attention first" sorts by `attention[].length` — the
*count* of flags — so a vehicle with three mild flags outranks one that has been
stuck for two hours. Count is not severity.

**G6 — Header overload, filters the wrong shape.**
One header carries branding, 6 nav items + a Fleet dropdown, 5 filter controls, poll
status, refresh, timeline toggle, a Manage Plans dropdown and New Plan — with
`flex-wrap: wrap`, so it reflows at narrow widths. The five filters are generic
(plan / date / plate / driver / status); none expresses a dispatcher intent.

**G7 — No keyboard path.**
Every interaction is a mouse click, on a tool used for an entire shift.

### Endsley scoring

| Level | Current |
|---|---|
| L1 Perception — where is everything, what state | **Strong.** Map, statuses, progress, GPS age all present. |
| L2 Comprehension — is this normal or bad | **Weak.** Three binary proxies, ungraded, equally weighted. |
| L3 Projection — what happens next | **Absent.** ETA to next stop only; nothing about finishing the day. |

---

## 3. Phase 0 — frontend only, no schema change  ✅ shipped

Chosen to go first. No migration, no API change, no Python touched. Shipped
2026-07-31; the changelog entry is the record of what each item actually became.
Two deviations from the plan below, both noted in place: the attention strip
gained an 8-chip cap (not planned, but the fleet-wide GPS-outage case made it
necessary), and `deselectAssignment()` had to be written because Escape could not
reuse `selectAssignment(null)`.

### 0.1 GPS trust badge  *(correctness — do this first)*

**Files:** `main.js`, `polling.js`, `delivery-dashboard.css`

- `main.js:327` keeps the full dashboard payload, not just `.assignments`;
  `gps_source` / `gps_error` / `gps_matched` / `gps_available` go into `DASH.state`.
- `polling.setStatus()` gains a `degraded` state alongside `ok` / `error` / `paused`.
- Precedence, worst first:
  1. `gps_error` set → `GPS unavailable` (critical styling) with the error on hover.
  2. `gps_available > 0 && gps_matched === 0` → `GPS: 0/N matched` — this is the
     C-01 signature and must be visually loud; it means every position on the map
     is unmatched, usually a plate-format break.
  3. `gps_matched < assignments-with-plates` → `GPS n/N` (warning styling).
  4. otherwise → `Live` as today.
- Per-vehicle: a card whose assignment has no `gps` object at all currently renders
  an empty GPS line, which is indistinguishable from fresh. It gets an explicit
  `No GPS` marker.

**Acceptance:** with TTAS returning positions that match zero plates, the header
does not read `Live`. Verified by stubbing the dashboard response under jsdom.

### 0.2 Graded severity

**Files:** `vehicle-list.js`, `delivery-dashboard.css`

- `computeAttention()` returns `{reason, ageMs, severity}[]` instead of `string[]`.
- `severity` derives from `ageMs / threshold`: `<1` → none, `1–2` → warn,
  `>2` → critical. Thresholds stay where they are (20 min stuck, 15 min GPS).
  `reported_stopped` is capped at warn — the existing comment is right that a
  single reading can be a red light, and it should never be able to reach critical.
- Card carries a left border in the severity colour; the dot is tiered rather than
  binary. Attention chips sort by severity, then age.
- **"Attention first" sorts by max severity, then age, then flag count** — fixing
  G5's inversion.
- Colours must clear the same bar as the map markers: readable on the dark shell,
  and not relying on hue alone (a shape or weight difference carries the tier too).

**Acceptance:** jsdom test driving `vehicle-list.js` against a stub — a fixture with
one 3-hour stuck vehicle and one with three fresh mild flags sorts the stuck one
first. This is the case that currently sorts backwards.

### 0.3 Density mode

**Files:** `delivery-dashboard.css`, `delivery-dashboard.html`, `vehicle-list.js`

- A `compact` class on `.vehicle-list` collapses each card to a single ~28px row:
  plate · driver · status · progress · current stop · GPS age. Target ≥20 visible.
- **CSS-only where possible.** The existing card markup is reused so the diffing
  render in `_patchCard` is untouched — that logic is load-bearing and this change
  has no reason to go near it.
- Toggle sits in the left panel header next to "Attention first"; persisted to
  `localStorage`, same as the basemap choice in `map.js`.
- Compact mode is desktop-only; the mobile breakpoint keeps full cards, since tap
  targets there are the binding constraint.

### 0.4 Quick filters

**Files:** `delivery-dashboard.html`, `main.js`, `delivery-dashboard.css`

- A chip row replaces the five fields as the default header content:
  **All · Needs attention · Executing · No GPS**. (A **Behind** chip is added in
  Phase 1, when "behind" becomes computable.)
- Chips are a view over the existing `applyFilters()` predicate — no new filtering
  path, one more clause.
- The five existing controls move behind a **Filters** disclosure. They keep their
  current ids, values and behaviour; state survives open/close. Nothing existing is
  removed.
- This also relieves G6: the header's widest flexing element becomes a fixed-width
  chip row.

> **Shipped, with one correction (2026-08-03).** **No GPS** was implemented as
> `a.gps && a.gps.last_update` — vehicles with *no position at all*, i.e. a plate TTAS
> returned no row for. That missed the case the chip is most often opened for: a truck
> TTAS reports as `MTH:6h48'` (*mất tín hiệu*) still carries the last fix taken before
> the signal dropped, so it passed the "has a position" test. The clause now also
> accepts `gps.signal_lost`. The chip answers "which trucks can I not see?", not "which
> have no coordinates?" — worth remembering when the **Behind** chip is added, since it
> will face the same question about what the dispatcher is actually asking.

### 0.5 Keyboard

**Files:** `main.js` (new `keyboard.js` if it exceeds ~60 lines)

| Key | Action |
|---|---|
| `j` / `k` | next / previous vehicle in the current filtered order |
| `Enter` | select focused vehicle |
| `Esc` | deselect / close disclosure |
| `/` | focus plate search |
| `a` | advance the selected vehicle's current stop |
| `f` | toggle Follow |
| `r` | refresh now |

Guards, all mandatory:

- No handler fires while focus is in an `input`, `select`, or `textarea`.
- No handler fires while any reason row is open — `timeline.js` already tracks
  these in `openReasonStopIds`; reuse it rather than adding a second flag.
- `a` goes through the same `expected_status` path as the button, so the existing
  double-tap protection still applies.

### 0.6 Verification

Per CLAUDE.md, frontend changes get no pytest coverage, so this is the only real
check:

- `node --check` on every touched file.
- jsdom, driving the actual module against a stub, for: the severity ordering
  (0.2), the GPS badge precedence table (0.1), and the keyboard guards (0.5).
  Inspection is not sufficient — the 2026-07-31 dashboard work found several bugs
  this way that reading had missed.
- Manual pass: confirm scroll position, open Filters disclosure, and typed filter
  text all survive a poll cycle.
- `docs/CHANGELOG.md` entry in the existing dated style.

### Explicitly out of scope for Phase 0

Schema changes; the `/api/eta` serial-ORS problem; the exception queue; anything
in `map.js` beyond severity colours; the header nav structure; auth (deliberately
absent — see CLAUDE.md).

---

## 4. Phase 1 — the time dimension  *(sketch)*

The highest-ceiling change, and the one Phase 0 is deliberately shaped not to
block.

Because stops are route-order with no promised times, the schedule must be
**derived, once, and frozen**:

- Add `planned_arrival_at` and `service_minutes` to `delivery_plan_stops`
  (`app/database/migrations.py`, additive, nullable).
- Populate at plan-confirm from the ORS route legs already fetched, plus a shift
  start time and a default service duration. **No new dispatcher data entry.**
- Freezing at confirm matters: a baseline that recomputes as the truck moves can
  never show slip, because it always agrees with reality.

Unlocks: planned-vs-actual on each timeline row; cumulative slip (`+22 min`); slip
projected onto the remaining stops — the first L3 capability on the board; a real
**Behind** filter chip; and "will this truck finish the day" as an answerable
question.

Open question to resolve before starting: what is a realistic default
`service_minutes`, and does it differ between box trucks and containers?

## 5. Phase 2 — fleet exception queue  *(sketch)*

Replace the right panel's "Select a vehicle to view stops" empty state with a
ranked, fleet-wide queue of every active exception — the ATC strip-bay idea,
scoped to exceptions. Each row jumps to the vehicle in one click. Reads far better
once Phase 1 supplies schedule-based exceptions, but can ship on the Phase 0
graded proxies alone.

## 6. Dropped

**Appointment windows per stop.** Was drafted as a Phase 3. Dropped — the operator
confirmed stops are route-order with no customer-promised times, so per-stop
windows would be data entry with no consumer. Revisit only if the operation takes
on appointment-based customers.

---

## References

- [Designing for Situation Awareness (Endsley) — ACM](https://dl.acm.org/doi/10.5555/2208018)
- [FAA — Air Traffic Control Decision Support Tool Design](https://hf.tc.faa.gov/publications/2019-atc-decision-support-tool/full_text.pdf)
- [Situation Awareness in Air Traffic Control — US DOT](https://rosap.ntl.bts.gov/view/dot/16675/dot_16675_DS1.pdf)
- [Designing Electronic Flight Strips for Air Traffic Control (NTNU)](https://www.ntnu.no/documents/10401/1286462006/mats.ruste.holen.pdf/9cf03a4f-ec78-4f9d-9e8a-55ab980bce17)
- [Well-Designed 911 Dispatch Program — Core77](https://www.core77.com/posts/20497/well-designed-911-dispatch-program-by-electronic-ink-20497)
- [Creating an Emergency Dispatch Workstation UI Design — Rossul](https://www.rossul.com/portfolio/dispatch-console-controls/)
- [Computer-aided dispatch — Wikipedia](https://en.wikipedia.org/wiki/Computer-aided_dispatch)
- [UX strategies for logistics management software — Zigpoll](https://www.zigpoll.com/content/what-are-the-most-effective-ux-strategies-for-optimizing-user-interfaces-in-logistics-management-software-to-improve-driver-and-dispatch-communication)
- [Dispatch Software case study — Lindi Wheaton](https://www.lindiwheaton.com/dispatch-software/)
- [Trucking Dispatch Software Development — Cleveroad](https://www.cleveroad.com/blog/trucking-dispatch-software/)
