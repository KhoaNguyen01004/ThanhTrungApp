// ================================================================
// Dispatch Dashboard — Main Orchestrator
// ================================================================
window.DASH = window.DASH || {};

(function () {
  'use strict';

  // ── State ──────────────────────────────────────────────────
  const state = {
    plans: [],
    allAssignments: [],  // unfiltered from API
    filteredAssignments: [],
    selectedAssignmentId: null,
    // Keyboard focus ring. Deliberately separate from selection: j/k move this
    // without firing the three detail requests a selection costs.
    focusedAssignmentId: null,
    selectedStops: [],
    selectedAssignmentDetail: null,
    selectedEta: null,
    followMode: false,
    // Trust metadata from /api/execution/dashboard. The endpoint has always
    // returned these four; nothing read them, so the header said "Live" over a
    // map whose positions matched no plate at all — the exact scenario the
    // backend comment says they were surfaced to prevent.
    gpsStats: { source: '', error: null, matched: 0, available: 0 },
    filters: {
      plan: '',
      date: '',
      vehicle: '',
      driver: '',
      status: '',
      // Dispatcher-intent filter, distinct from the five field filters below
      // it: '' | 'attention' | 'executing' | 'nogps'.
      quick: '',
    },
  };

  DASH.state = state;

  // ── Filter logic ───────────────────────────────────────────
  function applyFilters() {
    const f = state.filters;
    state.filteredAssignments = state.allAssignments.filter((a) => {
      if (f.plan && a.plan_id !== parseInt(f.plan, 10) && a.plan_name !== f.plan) return false;
      if (f.date && a.plan_date !== f.date) return false;
      if (f.vehicle) {
        const q = f.vehicle.toLowerCase();
        const plate = (a.plate_number || '').toLowerCase();
        if (!plate.includes(q)) return false;
      }
      if (f.driver) {
        const q = f.driver.toLowerCase();
        const driver = (a.current_driver || '').toLowerCase();
        if (!driver.includes(q)) return false;
      }
      if (f.status && a.plan_status !== f.status) return false;
      if (f.quick === 'attention' && DASH.vehicleList.computeAttention(a).length === 0) return false;
      if (f.quick === 'executing' && a.plan_status !== 'executing') return false;
      // "Vehicles I cannot see", which is two conditions, not one. A plate
      // TTAS returned no row for has no position at all — usually a plate
      // mismatch in `vehicles` or a device missing from the account. A
      // vehicle TTAS reports as MTH (mất tín hiệu) still carries the last
      // fix before the signal dropped, so it passes a "has a position" test
      // while being exactly what this filter is asked to find.
      if (f.quick === 'nogps'
          && a.gps && a.gps.last_update && !a.gps.signal_lost) return false;
      return true;
    });

    // If selected assignment was filtered out, deselect
    if (state.selectedAssignmentId) {
      const stillExists = state.filteredAssignments.find(
        (a) => a.assignment_id === state.selectedAssignmentId
      );
      if (!stillExists) {
        state.selectedAssignmentId = null;
        state.selectedStops = [];
        state.selectedAssignmentDetail = null;
        state.selectedEta = null;
      }
    }
  }

  // ── Populate filters ───────────────────────────────────────
  function populateFilterPlans() {
    const sel = document.getElementById('filterPlan');
    const currentVal = sel.value;
    sel.innerHTML = '<option value="">All Plans</option>';
    const seen = new Set();
    state.plans.forEach((p) => {
      if (seen.has(p.id)) return;
      if (p.status !== 'confirmed' && p.status !== 'executing') return;
      seen.add(p.id);
      sel.innerHTML += `<option value="${p.id}">${escapeHtml(p.plan_name || 'Plan #' + p.id)}</option>`;
    });
    sel.value = currentVal;
  }

  // ── Bind filter events ─────────────────────────────────────
  function bindFilterEvents() {
    const filterIds = ['filterPlan', 'filterDate', 'filterVehicle', 'filterDriver', 'filterStatus'];
    filterIds.forEach((id) => {
      const el = document.getElementById(id);
      if (!el) return;
      el.addEventListener('input', () => {
        state.filters.plan = document.getElementById('filterPlan').value;
        state.filters.date = document.getElementById('filterDate').value;
        state.filters.vehicle = document.getElementById('filterVehicle').value.trim().toLowerCase();
        state.filters.driver = document.getElementById('filterDriver').value.trim().toLowerCase();
        state.filters.status = document.getElementById('filterStatus').value;
        updateFiltersBadge();
        applyFilters();
        renderAll();
      });
      el.addEventListener('change', () => {
        // Trigger same handler for select changes
        el.dispatchEvent(new Event('input'));
      });
    });
  }

  // ── Quick filters ──────────────────────────────────────────
  // Dispatcher intents rather than fields. The five field filters still exist
  // and still work; they just no longer have to be the first thing in reach
  // for the cases that come up every few minutes.
  function bindQuickFilters() {
    const row = document.getElementById('quickFilters');
    if (!row) return;
    row.addEventListener('click', (e) => {
      const chip = e.target.closest('.quick-chip');
      if (!chip) return;
      const value = chip.dataset.quick || '';
      // Clicking the active chip clears it, so the row is its own "off" switch
      // and nobody has to hunt for an All chip they can already see.
      state.filters.quick = state.filters.quick === value ? '' : value;
      syncQuickFilterChips();
      applyFilters();
      renderAll();
    });
    syncQuickFilterChips();
  }

  function syncQuickFilterChips() {
    document.querySelectorAll('#quickFilters .quick-chip').forEach((chip) => {
      const value = chip.dataset.quick || '';
      chip.classList.toggle('active', value === state.filters.quick
        || (value === '' && !state.filters.quick));
    });
  }

  // The five field filters collapse behind a disclosure. They keep their ids,
  // their values and their event bindings — this only hides the row, so a
  // filter left set stays set, and stays visible in the button's label.
  function bindFiltersDisclosure() {
    const btn = document.getElementById('filtersToggleBtn');
    const panel = document.getElementById('dashboardFilters');
    if (!btn || !panel) return;
    btn.addEventListener('click', () => {
      panel.classList.toggle('open');
      btn.classList.toggle('active', panel.classList.contains('open'));
    });
  }

  // Shown on the disclosure button so a filter that is hiding inside a closed
  // panel can't quietly explain away an empty vehicle list.
  function updateFiltersBadge() {
    const badge = document.getElementById('filtersActiveCount');
    if (!badge) return;
    const f = state.filters;
    const n = [f.plan, f.date, f.vehicle, f.driver, f.status].filter(Boolean).length;
    badge.textContent = n > 0 ? String(n) : '';
    badge.style.display = n > 0 ? '' : 'none';
  }

  // ── Select assignment ──────────────────────────────────────
  function selectAssignment(assignmentId) {
    if (state.selectedAssignmentId === assignmentId) return;

    // A measurement belongs to the vehicle it was taken for, and this call
    // zooms the map to a different truck — leaving pins behind would strand
    // them off-screen with a total that no longer describes anything on it.
    // Guarded by the early return above, so re-clicking the selected vehicle
    // (including its map marker, which stays clickable while measuring) leaves
    // the measurement alone.
    if (DASH.measure) DASH.measure.onVehicleChange();

    state.selectedAssignmentId = assignmentId;
    state.selectedStops = [];
    state.selectedAssignmentDetail = null;
    state.selectedEta = null;
    state.followMode = false;
    setFollowButtonState();

    // Clear the previous vehicle's detail *now*, before any request goes out.
    // renderAll() below repaints the right panel only when selectedStops is
    // non-empty, so without this the timeline, map stops, route line and info
    // bar all kept showing the *previously* selected truck until the new data
    // landed. The click looked like it had done nothing — or worse, like it had
    // selected a vehicle whose stops belonged to someone else.
    DASH.timeline.clear('Loading stops…');
    DASH.map.updateStops([], null);
    DASH.map.updateRoute(null, []);
    updateInfoBar(assignmentId, [], null, null);
    showVehicleMapControls();

    renderAll();

    // Load detailed data for selected assignment
    loadAssignmentDetail(assignmentId);

    // Zoom map
    DASH.map.zoomToVehicle(assignmentId);
  }

  // Escape's counterpart to selectAssignment(). Not expressible as
  // selectAssignment(null): that path unconditionally issues the three detail
  // requests and a map zoom for whatever id it was handed. renderAll() already
  // knows how to paint the no-selection state, so this only has to reach it.
  function deselectAssignment() {
    if (!state.selectedAssignmentId) return;
    detailGeneration++; // drop any detail load still in flight
    state.selectedAssignmentId = null;
    state.selectedStops = [];
    state.selectedAssignmentDetail = null;
    state.selectedEta = null;
    renderAll();
  }

  function showVehicleMapControls() {
    document.getElementById('zoomToVehicleBtn').style.display = '';
    document.getElementById('followVehicleBtn').style.display = '';
    document.getElementById('openGmapsBtn').style.display = '';
  }

  // The one place the right panel and the map's per-assignment layers are
  // painted from state. Called repeatedly as each of the three detail requests
  // lands, so it must be safe to run with a partial state — a null ETA renders
  // the timeline without ETAs and the route as straight lines, which is what
  // the dispatcher sees for the moment before /api/eta answers.
  function paintAssignmentDetail(assignmentId) {
    const currentStopId = getCurrentStopId(state.selectedStops);
    DASH.timeline.render(state.selectedStops, currentStopId, state.selectedEta);
    DASH.map.updateStops(state.selectedStops, currentStopId);
    DASH.map.updateRoute(state.selectedEta, state.selectedStops);
    updateInfoBar(assignmentId, state.selectedStops, state.selectedAssignmentDetail, state.selectedEta);
  }

  // Monotonic token for assignment-detail loads. Every call takes the next
  // value; when its three requests resolve, it writes to state only if it is
  // still the newest.
  //
  // Without it, a detail load for the previously-selected vehicle could
  // resolve *after* the one the dispatcher just clicked and overwrite it —
  // leaving the vehicle list highlighting one truck while the timeline, map
  // stops and info bar showed another (audit F-05). The 12-second poll calls
  // this too, so a click landing mid-poll is the common case, not a rare one.
  let detailGeneration = 0;

  // Number of stop reorders painted locally but not yet acknowledged. Declared
  // here rather than beside state.reorderStops below because loadAssignmentDetail
  // reads it.
  let pendingReorders = 0;

  async function loadAssignmentDetail(assignmentId) {
    const generation = ++detailGeneration;

    // Superseded while a request was in flight — drop the result rather than
    // paint stale data over the current selection. Also skips writing over a
    // reorder the dispatcher just made locally that the server hasn't
    // acknowledged yet: that response was built from the old order.
    const isStale = () =>
      generation !== detailGeneration ||
      state.selectedAssignmentId !== assignmentId ||
      pendingReorders > 0;

    // All three go out together, but they are NO LONGER awaited together.
    // /api/stops and /api/execution/progress read local SQLite and answer in
    // milliseconds; /api/eta issues one OpenRouteService call per remaining
    // stop, serially, each with a 30-second server-side timeout. Promise.all
    // held the whole right panel hostage to the slowest of the three, so
    // clicking a vehicle showed nothing for as long as the ETA took — the
    // "it takes 15 seconds to react" report. Each response now paints on
    // arrival, so the stop list appears essentially immediately and ETAs fill
    // in behind it.
    const stopsRequest = DASH.api.stops(assignmentId);
    const progressRequest = DASH.api.progress(assignmentId);
    const etaRequest = DASH.api.eta(assignmentId);

    // Each is awaited below, but an early `return` on a stale generation can
    // leave one un-awaited. Park a handler on each now so a rejection can't
    // surface as an unhandled promise rejection.
    [stopsRequest, progressRequest, etaRequest].forEach((p) => p.catch(() => {}));

    try {
      const stops = await stopsRequest;
      if (isStale()) return;
      state.selectedStops = stops || [];
      paintAssignmentDetail(assignmentId);
      showVehicleMapControls();
      if (state.followMode) DASH.map.followVehicle(assignmentId);
    } catch (e) {
      if (!isStale()) console.error('Failed to load stops:', e);
      return; // Without stops there is nothing for the other two to annotate.
    }

    try {
      const progress = await progressRequest;
      if (isStale()) return;
      state.selectedAssignmentDetail = progress || null;
      paintAssignmentDetail(assignmentId);
    } catch (e) {
      if (!isStale()) console.error('Failed to load progress:', e);
    }

    try {
      const eta = await etaRequest;
      if (isStale()) return;
      // Stamped on arrival: eta_seconds is measured from when the server
      // answered, so every later repaint needs that instant as its baseline
      // rather than its own Date.now(). Without it the arrival time creeps
      // forward on each render.
      if (eta) eta._receivedAt = Date.now();
      state.selectedEta = eta || null;
      paintAssignmentDetail(assignmentId);
    } catch (e) {
      // An ETA failure is not a detail-load failure. The timeline, stops and
      // route are already on screen and stay there.
      if (!isStale()) console.error('Failed to load ETA:', e);
    }
  }

  // ── Follow-vehicle toggle ───────────────────────────────────
  function setFollowButtonState() {
    const btn = document.getElementById('followVehicleBtn');
    if (!btn) return;
    btn.classList.toggle('active', state.followMode);
    btn.textContent = state.followMode ? '◉ Following' : '◎ Follow';
  }

  // Follow is a competing intent with looking at anything else on the map, so
  // anything that deliberately moves the view somewhere other than the vehicle
  // switches it off. Otherwise the next poll pans straight back and undoes it.
  state.setFollowMode = function (on) {
    if (state.followMode === on) return;
    state.followMode = on;
    setFollowButtonState();
  };

  function getCurrentStopId(stops) {
    if (!stops) return null;
    const activeStatuses = ['planned', 'arrived'];
    for (const s of stops) {
      if (activeStatuses.includes(s.execution_status)) {
        return s.id;
      }
    }
    return null;
  }

  // ── Update info bar ────────────────────────────────────────
  function updateInfoBar(assignmentId, stops, progress, eta) {
    const bar = document.getElementById('vehicleInfoBar');
    const a = state.allAssignments.find((x) => x.assignment_id === assignmentId);
    if (!a) { bar.style.display = 'none'; return; }

    bar.style.display = '';
    document.getElementById('vibarVehicle').textContent = a.plate_number || 'Vehicle';
    document.getElementById('vibarDriver').textContent = a.current_driver || 'No driver';
    const statusEl = document.getElementById('vibarStatus');
    statusEl.textContent = a.plan_status || 'unknown';
    statusEl.className = 'status-badge status-' + (a.plan_status || 'draft');

    const p = progress || { completed: 0, total: 0, progress_pct: 0 };
    document.getElementById('vibarProgress').textContent = `Progress: ${p.completed}/${p.total} (${p.progress_pct}%)`;

    // eta_seconds is null for a stop with no coordinates, and Math.round(null/60)
    // is 0 — so an unknown ETA rendered as a confident "ETA: 0 min", telling a
    // dispatcher the truck is arriving now (audit L-10). timeline.js already
    // guarded this with a typeof check; the info bar did not.
    const firstEta = eta && eta.etas && eta.etas.length > 0 ? eta.etas[0].eta_seconds : null;
    const etaEl = document.getElementById('vibarEta');
    const etaClock = UI.etaClock(firstEta, eta && eta._receivedAt);
    etaEl.textContent = etaClock ? `ETA: ${etaClock}` : 'ETA: --';
    etaEl.title = etaClock ? `in ${UI.etaRelative(firstEta)}` : '';

    const distanceEl = document.getElementById('vibarDistance');
    if (eta && (eta.remaining_distance_km || eta.travelled_distance_km)) {
      distanceEl.textContent = `${eta.travelled_distance_km || 0} km done • ${eta.remaining_distance_km || 0} km left`;
    } else {
      distanceEl.textContent = '';
    }

    const gps = a.gps;

    // Supplementary operational context only — never used for ETA/routing.
    const speedEl = document.getElementById('vibarSpeed');
    speedEl.textContent = gps && gps.speed_kmh != null ? `${Math.round(gps.speed_kmh)} km/h` : '';

    // Reads the server's parse, not TTAS's raw text: new Date() takes a
    // non-ISO string month-first, which turned a day-first "01/08/2026" into
    // 8 January. When the parse failed, show TTAS's own text rather than a
    // confidently wrong clock time.
    let gpsTime = '';
    if (gps && gps.last_update_iso) {
      const d = new Date(gps.last_update_iso);
      gpsTime = isNaN(d.getTime()) ? (gps.last_update || '') : d.toLocaleTimeString();
    } else if (gps && gps.last_update) {
      gpsTime = gps.last_update;
    }
    document.getElementById('vibarGpsTime').textContent = gpsTime ? 'GPS: ' + gpsTime : '';
  }

  // ── Render all panels ──────────────────────────────────────
  function renderAll() {
    DASH.vehicleList.render(state.filteredAssignments, state.selectedAssignmentId);
    DASH.map.updateVehicles(state.filteredAssignments);
    // Re-applied after every render: vehicleList reorders and recycles card
    // nodes, so the ring has to be re-attached rather than assumed to persist.
    applyFocusRing();

    if (state.selectedAssignmentId) {
      // Only once stops have arrived — otherwise this would paint over the
      // "Loading stops…" placeholder that selectAssignment just put up.
      if (state.selectedStops.length > 0) {
        paintAssignmentDetail(state.selectedAssignmentId);
      }
    } else {
      DASH.timeline.clear();
      document.getElementById('vehicleInfoBar').style.display = 'none';
      document.getElementById('zoomToVehicleBtn').style.display = 'none';
      document.getElementById('followVehicleBtn').style.display = 'none';
      document.getElementById('openGmapsBtn').style.display = 'none';
      state.followMode = false;
      setFollowButtonState();
      // Clear map extras
      DASH.map.updateStops([], null);
      DASH.map.updateRoute(null, []);
    }
  }

  // ── GPS trust ──────────────────────────────────────────────
  // "The request succeeded" and "the map is live" are separate claims, and the
  // poll pill used to make the second on the strength of the first. These
  // resolve the second one from the four fields /api/execution/dashboard has
  // always returned and nothing ever read.

  // Only assignments carrying a plate can be matched against a GPS position at
  // all, so they are the denominator — not the whole assignment list.
  function assignmentsExpectingGps() {
    return state.allAssignments.filter((a) => a.plate_number).length;
  }

  function isFleetGpsOutage() {
    const g = state.gpsStats;
    if (g.error) return true;
    if (assignmentsExpectingGps() === 0) return false;
    if (g.available === 0) return true;
    return g.matched === 0;
  }

  // Returned to polling.js, which owns the pill. Worst case first.
  function gpsPollStatus() {
    const g = state.gpsStats;
    const expecting = assignmentsExpectingGps();
    const src = g.source || 'unknown';

    if (g.error) {
      return { status: 'gpsdown', label: 'GPS down', title: `GPS source (${src}) failed: ${g.error}` };
    }

    // Nothing on the board is expecting a position, so there is nothing to be
    // wrong about. An empty board must not read as a fault.
    if (expecting === 0) return { status: 'ok' };

    if (g.available === 0) {
      return { status: 'gpsdown', label: 'No GPS', title: `GPS source (${src}) returned no positions.` };
    }

    // Positions arrived and not one matched a plate. This is audit C-01's
    // exact signature — almost always a plate-format break — and it is the
    // case that most needs to be loud, because every marker on the map is
    // then a position nobody asked for.
    if (g.matched === 0) {
      return {
        status: 'gpsdown',
        label: `GPS 0/${g.available}`,
        title: `${g.available} position(s) from ${src} matched none of the ${expecting} plate(s) on the board. Check plate formats.`,
      };
    }

    if (g.matched < expecting) {
      return {
        status: 'degraded',
        label: `GPS ${g.matched}/${expecting}`,
        title: `${expecting - g.matched} vehicle(s) on the board have no live position.`,
      };
    }

    return { status: 'ok' };
  }

  // ── Main tick (called by polling) ──────────────────────────
  async function onPollTick() {
    const data = await DASH.api.dashboard();
    const raw = data.assignments || [];

    state.gpsStats = {
      source: data.gps_source || '',
      error: data.gps_error || null,
      matched: data.gps_matched || 0,
      available: data.gps_available || 0,
    };

    // Set before isFleetGpsOutage() runs — it counts the assignments that are
    // expecting a position, so it has to see this poll's list, not the last.
    state.allAssignments = raw;

    // A fleet-wide GPS failure is one fact, not forty. Told once by the header
    // badge; the per-vehicle "no GPS" flag stands down so the attention strip
    // isn't buried under identical chips.
    DASH.vehicleList.setGpsFleetOutage(isFleetGpsOutage());

    applyFilters();
    renderAll();

    // If a plan filter doesn't exist yet and we have data, refresh plan list periodically
    if (state.plans.length === 0 && raw.length > 0) {
      loadPlans();
    }

    // Reload selected assignment detail
    if (state.selectedAssignmentId) {
      const stillExists = state.allAssignments.find(
        (a) => a.assignment_id === state.selectedAssignmentId
      );
      if (stillExists) {
        await loadAssignmentDetail(state.selectedAssignmentId);
      }
    }
  }

  // ── Keyboard ───────────────────────────────────────────────
  // A shift is eight hours of this board. j/k move a focus ring only — they
  // do not select — because selecting fires three requests and a map zoom, and
  // holding j down the list would issue one set per vehicle. Enter commits.

  function focusableAssignments() {
    return state.filteredAssignments;
  }

  function applyFocusRing() {
    const cards = document.querySelectorAll('#vehicleList .vehicle-card');
    cards.forEach((card) => {
      const id = parseInt(card.dataset.assignmentId, 10);
      const on = id === state.focusedAssignmentId;
      card.classList.toggle('focused', on);
      // 'nearest' so a focus move never scrolls a card that is already fully
      // visible — the list must not jump under a dispatcher who is reading it.
      // Guarded because scrolling is a nicety and the focus ring is not: if
      // scrollIntoView is missing or throws, the ring must still move.
      if (on && typeof card.scrollIntoView === 'function') {
        card.scrollIntoView({ block: 'nearest' });
      }
    });
  }

  function moveFocus(delta) {
    const list = focusableAssignments();
    if (list.length === 0) return;
    let idx = list.findIndex((a) => a.assignment_id === state.focusedAssignmentId);
    // Nothing focused yet: j starts at the top, k at the bottom.
    if (idx === -1) idx = delta > 0 ? -1 : 0;
    const next = Math.min(list.length - 1, Math.max(0, idx + delta));
    state.focusedAssignmentId = list[next].assignment_id;
    applyFocusRing();
  }

  // Typing must always win. Without this, searching for a plate containing
  // 'a' or 'f' would advance a stop and toggle Follow while the dispatcher
  // typed. The reason-row check is the same one that suppresses background
  // patching for a row being edited.
  function keyboardIsSuppressed(e) {
    if (e.ctrlKey || e.metaKey || e.altKey) return true;
    const el = document.activeElement;
    if (el) {
      const tag = (el.tagName || '').toLowerCase();
      if (tag === 'input' || tag === 'select' || tag === 'textarea' || el.isContentEditable) return true;
    }
    if (DASH.timeline && typeof DASH.timeline.hasOpenReasonRow === 'function'
        && DASH.timeline.hasOpenReasonRow()) return true;
    return false;
  }

  function bindKeyboard() {
    document.addEventListener('keydown', (e) => {
      // Escape is the one key that must work *from* a field, since getting out
      // of a filter box is the whole point of pressing it.
      if (e.key === 'Escape') {
        const panel = document.getElementById('dashboardFilters');
        if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
        // Ahead of the filter panel and the selection, and ordered explicitly
        // here rather than left to listener registration order in measure.js:
        // Escape while measuring must finish the measurement, not deselect the
        // vehicle underneath it.
        if (DASH.measure && DASH.measure.isActive()) {
          DASH.measure.clear();
          return;
        }
        if (panel && panel.classList.contains('open')) {
          panel.classList.remove('open');
          document.getElementById('filtersToggleBtn').classList.remove('active');
          return;
        }
        if (state.selectedAssignmentId) {
          // Keep the ring where the selection was, so Escape then Enter is a
          // round trip rather than losing the dispatcher's place in the list.
          state.focusedAssignmentId = state.selectedAssignmentId;
          deselectAssignment();
        }
        return;
      }

      if (keyboardIsSuppressed(e)) return;

      switch (e.key) {
        case 'j':
          e.preventDefault();
          moveFocus(1);
          break;
        case 'k':
          e.preventDefault();
          moveFocus(-1);
          break;
        case 'Enter':
          if (state.focusedAssignmentId) {
            e.preventDefault();
            selectAssignment(state.focusedAssignmentId);
          }
          break;
        case '/': {
          e.preventDefault();
          // The field lives inside the disclosure now, so open it first —
          // focusing a hidden input silently does nothing.
          const panel = document.getElementById('dashboardFilters');
          const btn = document.getElementById('filtersToggleBtn');
          if (panel && !panel.classList.contains('open')) {
            panel.classList.add('open');
            if (btn) btn.classList.add('active');
          }
          const field = document.getElementById('filterVehicle');
          if (field) { field.focus(); field.select(); }
          break;
        }
        case 'a': {
          // Synthesises a click on the real Advance button rather than calling
          // the API directly, so the in-flight guard, the expected_status
          // staleness check and the disabled state all apply unchanged.
          const btn = document.querySelector('#currentStopCard [data-action="advance"]')
                   || document.querySelector('#timeline [data-action="advance"]');
          if (btn && !btn.disabled) {
            e.preventDefault();
            btn.click();
          }
          break;
        }
        case 'f':
          if (state.selectedAssignmentId) {
            e.preventDefault();
            document.getElementById('followVehicleBtn').click();
          }
          break;
        case 'r':
          e.preventDefault();
          state.refreshNow().catch((err) => console.error('Refresh error:', err));
          break;
        default:
          break;
      }
    });
  }

  // ── Age ticker ─────────────────────────────────────────────
  // Ages ("GPS stale 23m") were only recomputed when a poll returned, so a
  // slow or failing poll froze them while the real age kept climbing — the
  // number on screen was the age as of the last successful round trip, not
  // now. This repaints them on a clock instead.
  //
  // It is not a poll: no network, no map calls, no reordering. The map view
  // must only move in response to a click, and the surest way to honour that
  // is for this path never to reach DASH.map at all.
  const AGE_REFRESH_MS = 15000;
  let ageTimer = null;

  function startAgeTicker() {
    if (ageTimer) return;
    ageTimer = setInterval(() => {
      // A background tab does not need repainting, and polling.js already
      // stops its own timer on hidden. Checked per tick rather than by
      // binding visibilitychange, so there is one less listener to leak.
      if (document.hidden) return;
      try {
        DASH.vehicleList.refreshAges();
      } catch (e) {
        // Must never take the dashboard down with it: this is cosmetic.
        console.error('Age refresh failed:', e);
      }
    }, AGE_REFRESH_MS);
  }

  // ── Load plans for filter ──────────────────────────────────
  async function loadPlans() {
    try {
      state.plans = await DASH.api.plans();
      populateFilterPlans();
    } catch (e) {
      console.error('Failed to load plans:', e);
    }
  }

  // ── Bind map control buttons ───────────────────────────────
  function bindMapControls() {
    document.getElementById('refreshNowBtn').addEventListener('click', async () => {
      try {
        await DASH.state.refreshNow();
      } catch (e) {
        console.error('Refresh error:', e);
      }
    });

    document.getElementById('zoomToVehicleBtn').addEventListener('click', () => {
      if (state.selectedAssignmentId) {
        DASH.map.zoomToVehicle(state.selectedAssignmentId);
      }
    });

    document.getElementById('followVehicleBtn').addEventListener('click', () => {
      if (!state.selectedAssignmentId) return;
      state.followMode = !state.followMode;
      setFollowButtonState();
      if (state.followMode) {
        DASH.map.followVehicle(state.selectedAssignmentId);
      }
    });

    document.getElementById('openGmapsBtn').addEventListener('click', () => {
      if (state.selectedAssignmentId) {
        DASH.map.openGoogleMaps(state.selectedAssignmentId, state.selectedStops);
      }
    });

    document.getElementById('refreshGPSBtn').addEventListener('click', async () => {
      try {
        await DASH.state.refreshNow();
      } catch (e) {
        console.error('GPS refresh error:', e);
      }
    });
  }

  // ── Expose refresh for external use (timeline actions) ─────
  state.selectAssignment = selectAssignment;

  state.refreshNow = async function () {
    await DASH.polling.refreshNow(onPollTick);
  };

  // ── Stop reordering ────────────────────────────────────────
  // Optimistic: the new order is painted before the request goes out, because
  // a dispatcher resequencing a live route does it several stops at a time and
  // waiting for a round trip (plus an ETA recompute) per click is unusable.
  //
  // Moves are POSTed strictly in click order through a promise chain — the
  // server rewrites every execution_sequence on each call, so two requests
  // racing would settle on whichever finished last, not on what was clicked
  // last. Only the final move of a burst triggers a refresh.
  let reorderChain = Promise.resolve();

  state.reorderStops = function (assignmentId, orderedStops) {
    // Drop any assignment-detail load already in flight; it was built from
    // the previous order and would overwrite what was just painted.
    detailGeneration++;

    state.selectedStops = orderedStops;
    paintAssignmentDetail(assignmentId);

    const stopIds = orderedStops.map((s) => s.id);
    pendingReorders++;
    reorderChain = reorderChain
      .then(() => DASH.api.reorderStops(assignmentId, stopIds))
      .catch((err) => UI.toast(`Reorder failed: ${err.message}`, 'error', 6000))
      .finally(() => {
        pendingReorders--;
        // Resync against the server once the burst settles — this is also what
        // recomputes ETAs for the new sequence.
        if (pendingReorders === 0) state.refreshNow();
      });
    return reorderChain;
  };

  // ── Init ──────────────────────────────────────────────────
  function init() {
    DASH.map.init();
    // After map.init() — it reads the Leaflet instance out of DASH.map.
    if (DASH.measure) DASH.measure.init();
    // Binds its own DOM only, so order against measure doesn't matter — but it
    // must still run after map.init(), because map.js's shift+right-click
    // handler calls into it.
    if (DASH.streetview) DASH.streetview.init();
    bindFilterEvents();
    bindQuickFilters();
    bindFiltersDisclosure();
    bindMapControls();
    bindManagePlansEvents();
    bindKeyboard();
    setFollowButtonState();
    updateFiltersBadge();

    // Load initial data
    Promise.all([loadPlans()]).catch(() => {});

    // Registered before start() so the very first tick's pill is already
    // GPS-aware rather than an unconditional "Live".
    DASH.polling.okStatusProvider = gpsPollStatus;

    // Start polling
    DASH.polling.start(onPollTick);
    startAgeTicker();

    // Invalidate map size after layout settles
    setTimeout(() => DASH.map.invalidateSize(), 500);

    // Timeline toggle (mobile)
    const toggleBtn = document.getElementById('timelineToggleBtn');
    const closeBtn = document.getElementById('timelineCloseBtn');
    const rightPanel = document.getElementById('rightPanel');
    if (toggleBtn && rightPanel) {
      toggleBtn.addEventListener('click', function () {
        rightPanel.classList.toggle('open');
      });
      if (closeBtn) {
        closeBtn.addEventListener('click', function () {
          rightPanel.classList.remove('open');
        });
      }
      // Close timeline when clicking on map
      document.getElementById('centerPanel').addEventListener('click', function () {
        if (rightPanel.classList.contains('open')) {
          rightPanel.classList.remove('open');
        }
      });
    }
  }

  // ── Plan Management (delete/clear) ──────────────────────────
  const managePlansState = {
    selectedIds: new Set(),
  };

  // The panel is position:fixed, so it has to be placed against the button's
  // viewport rect. Right-aligned to the button where there is room, then
  // clamped to the viewport on every side — the header wraps at narrow widths
  // and the button can end up anywhere along it, including close enough to the
  // left edge that a right-aligned 320px panel would hang off-screen.
  const MANAGE_PLANS_MARGIN = 8;

  function positionManagePlans() {
    const dd = document.getElementById('managePlansDropdown');
    const btn = document.getElementById('managePlansBtn');
    if (!dd || !btn || !dd.classList.contains('open')) return;

    const rect = btn.getBoundingClientRect();
    const m = MANAGE_PLANS_MARGIN;
    const width = Math.min(320, window.innerWidth - m * 2);

    let left = rect.right - width;
    left = Math.min(left, window.innerWidth - width - m);
    left = Math.max(m, left);

    const top = rect.bottom + 4;

    dd.style.width = `${width}px`;
    dd.style.left = `${left}px`;
    dd.style.top = `${top}px`;
    // Never taller than the space left below the button, so the action row
    // stays reachable instead of falling past the bottom of the window.
    dd.style.maxHeight = `${Math.max(160, window.innerHeight - top - m)}px`;
  }

  function toggleManagePlans(show) {
    const dd = document.getElementById('managePlansDropdown');
    if (!dd) return;
    dd.classList.toggle('open', show !== undefined ? show : !dd.classList.contains('open'));
    if (dd.classList.contains('open')) {
      populateManagePlansList();
      positionManagePlans();
    }
  }

  function populateManagePlansList() {
    const list = document.getElementById('managePlansList');
    if (!list) return;
    const plans = state.plans.length > 0 ? state.plans : [];
    if (plans.length === 0) {
      list.innerHTML = '<div class="manage-plans-empty">No plans found</div>';
      document.getElementById('deleteSelectedPlansBtn').disabled = true;
      return;
    }
    // Plan status is stored without a CHECK constraint and PUT /api/plans/<id>
    // accepted arbitrary strings, so p.status was an injection vector into
    // both a class attribute and a text node (audit S-03). Map it onto a
    // known set for the class, and escape it for display.
    const KNOWN_STATUSES = ['draft', 'confirmed', 'executing', 'completed', 'cancelled'];
    let html = '';
    plans.forEach((p) => {
      const checked = managePlansState.selectedIds.has(p.id) ? 'checked' : '';
      const rawStatus = p.status || 'draft';
      const statusClass = KNOWN_STATUSES.includes(rawStatus) ? rawStatus : 'draft';
      html += `
        <label class="manage-plans-item">
          <input type="checkbox" value="${p.id}" ${checked}>
          <a class="plan-item-name" href="/delivery/edit/${p.id}" title="Edit plan">${escapeHtml(p.plan_name || 'Plan #' + p.id)}</a>
          <span class="plan-item-date">${escapeHtml(p.plan_date || '')}</span>
          <span class="plan-item-status ${statusClass}">${escapeHtml(rawStatus)}</span>
        </label>
      `;
    });
    list.innerHTML = html;

    // Bind checkbox changes
    list.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
      cb.addEventListener('change', () => {
        const id = parseInt(cb.value, 10);
        if (cb.checked) {
          managePlansState.selectedIds.add(id);
        } else {
          managePlansState.selectedIds.delete(id);
        }
        const btn = document.getElementById('deleteSelectedPlansBtn');
        if (btn) btn.disabled = managePlansState.selectedIds.size === 0;
      });
    });
  }

  async function deleteSelectedPlans() {
    const ids = Array.from(managePlansState.selectedIds);
    if (ids.length === 0) return;
    if (!confirm(`Are you sure you want to delete ${ids.length} selected plan(s)? This cannot be undone.`)) return;
    try {
      await DASH.api.deletePlans(ids);
      UI.toast(`Deleted ${ids.length} plan(s)`, 'success');
      managePlansState.selectedIds = new Set();
      toggleManagePlans(false);
      // Reload plans and data
      await loadPlans();
      await DASH.state.refreshNow();
    } catch (e) {
      UI.toast(`Delete failed: ${e.message}`, 'error');
    }
  }

  async function clearAllPlans() {
    if (!confirm('Are you sure you want to delete ALL plans? This cannot be undone.')) return;
    try {
      await DASH.api.clearPlans();
      UI.toast('All plans cleared', 'success');
      managePlansState.selectedIds = new Set();
      toggleManagePlans(false);
      // Reload plans and data
      await loadPlans();
      await DASH.state.refreshNow();
    } catch (e) {
      UI.toast(`Clear failed: ${e.message}`, 'error');
    }
  }

  function bindManagePlansEvents() {
    const btn = document.getElementById('managePlansBtn');
    const close = document.getElementById('managePlansClose');
    const deleteBtn = document.getElementById('deleteSelectedPlansBtn');
    const clearBtn = document.getElementById('clearAllPlansBtn');

    if (btn) btn.addEventListener('click', (e) => { e.stopPropagation(); toggleManagePlans(); });
    if (close) close.addEventListener('click', () => toggleManagePlans(false));
    if (deleteBtn) deleteBtn.addEventListener('click', deleteSelectedPlans);
    if (clearBtn) clearBtn.addEventListener('click', clearAllPlans);

    // Close on outside click. The panel is still a DOM child of .manage-plans-wrap
    // despite being position:fixed, so contains() covers clicks inside it.
    document.addEventListener('click', (e) => {
      const wrap = document.querySelector('.manage-plans-wrap');
      if (wrap && !wrap.contains(e.target)) {
        toggleManagePlans(false);
      }
    });

    // A resize (or an orientation change, or the header re-wrapping) moves the
    // button out from under an open panel.
    window.addEventListener('resize', positionManagePlans);

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') toggleManagePlans(false);
    });
  }

  // ── Utility ────────────────────────────────────────────────
  // Canonical escaper from utils.js (loaded before this file); the private
  // copy this replaces did not escape quotes (audit S-02).
  const escapeHtml = UI.escapeHtml;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
