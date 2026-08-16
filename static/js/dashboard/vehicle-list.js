// ================================================================
// Dispatch Dashboard — Vehicle List (Left Panel)
// ================================================================
window.DASH = window.DASH || {};

(function () {
  'use strict';

  // Attention proxies — no scheduled/promised time exists in the schema, so
  // "delay" is approximated from data already available every poll: a
  // vehicle arrived at a stop far longer than a normal stop takes, or a
  // vehicle whose GPS has gone quiet. Both are purely derived, no backend
  // change needed.
  //
  // Worth being honest about the limit (docs/DISPATCH_UX_PLAN.md G1): every
  // proxy here detects a *symptom of having stopped*. A truck that is ninety
  // minutes behind while driving perfectly trips none of them. Only a planned
  // arrival time per stop can catch that, and no column holds one yet.
  const STUCK_THRESHOLD_MS = 20 * 60 * 1000;
  const GPS_STALE_THRESHOLD_MS = 15 * 60 * 1000;
  // Corroborating signal only (never a hard alert): live TTAS speed reads
  // ~0 while the vehicle isn't parked at a stop. A single reading can just
  // be a red light, so this stays informational, same as the other proxies.
  const REPORTED_STOPPED_SPEED_KMH = 2;

  // Severity grows with how far past its threshold a flag has run, instead of
  // latching on at the threshold and looking identical forever after — a
  // 21-minute stuck and a 3-hour stuck used to render as the same dot. Both
  // CAD and ATC displays grade continuously for exactly this reason.
  const SEV = { NONE: 0, WARN: 1, CRITICAL: 2 };
  const SEV_CLASS = { 1: 'sev-warn', 2: 'sev-critical' };

  // Above this many chips the strip stops being triage and starts being a
  // wall — the ATC strip-bay literature's warning about alerts becoming a
  // hindrance. The overflow chip switches on Attention-first instead.
  const MAX_ATTENTION_CHIPS = 8;

  // Set from main.js on every poll. When TTAS matched *no* plates at all, the
  // per-vehicle "no GPS" flag is suppressed: forty identical chips is not
  // triage, and the header badge tells that story once, correctly.
  let gpsFleetOutage = false;

  function gradeByAge(ageMs, thresholdMs) {
    const ratio = ageMs / thresholdMs;
    if (ratio >= 2) return SEV.CRITICAL;
    if (ratio >= 1) return SEV.WARN;
    return SEV.NONE;
  }

  function formatDuration(ms) {
    const mins = Math.floor(ms / 60000);
    if (mins < 60) return mins + 'm';
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    return h + 'h' + (m > 0 ? ' ' + m + 'm' : '');
  }

  function statusClass(status) {
    const map = {
      draft: 'status-draft',
      confirmed: 'status-confirmed',
      executing: 'status-executing',
      arrived: 'status-arrived',
      completed: 'status-completed',
      skipped: 'status-skipped',
      cancelled: 'status-cancelled',
      planned: 'status-planned',
    };
    return map[status] || 'status-draft';
  }

  function statusLabel(status) {
    return (status || 'unknown').replace('_', ' ');
  }

  function setText(el, text) {
    if (el && el.textContent !== text) el.textContent = text;
  }

  // Returns [{ reason, ageMs, severity }], worst first. Empty means healthy.
  function computeAttention(a) {
    const flags = [];
    const now = Date.now();
    const cs = a.current_stop;

    if (cs && cs.execution_status === 'arrived' && cs.actual_arrival_at) {
      const arrivedAt = new Date(cs.actual_arrival_at).getTime();
      if (!isNaN(arrivedAt)) {
        const ageMs = now - arrivedAt;
        const severity = gradeByAge(ageMs, STUCK_THRESHOLD_MS);
        if (severity > SEV.NONE) flags.push({ reason: 'stuck', ageMs, severity });
      }
    }

    // Three distinct states, not two. `last_update_iso` is the server's
    // parse of TTAS's `trktime` (ttas_client.parse_ttas_timestamp) and is
    // null when that value was in no format we recognise.
    //
    // The age is NOT computed from `gps.last_update` any more. That field is
    // TTAS's raw day-first text, and `new Date()` reads non-ISO strings
    // month-first: "01/08/2026" became 8 January, so on 1 August every
    // vehicle reported GPS ~205 days stale. Worse, from the 13th of any
    // month the string parsed as Invalid Date and the isNaN guard here
    // skipped the check entirely — silence, on the flag whose whole job is
    // to notice a tracker that stopped reporting.
    const gps = a.gps;
    let gpsIsFresh = false;
    if (!gps || !gps.last_update) {
      // No position at all for this plate — a distinct condition from a stale
      // one, and previously rendered as an empty GPS line, which reads exactly
      // like a fresh one.
      if (!gpsFleetOutage) {
        flags.push({ reason: 'no_gps', ageMs: 0, severity: SEV.WARN });
      }
    } else {
      const lastUpdate = new Date(gps.last_update_iso || NaN).getTime();
      if (isNaN(lastUpdate)) {
        // There is a position on the map, but nothing can be said about how
        // old it is. Never graded past WARN: an unknown age is not evidence
        // of a long one, and claiming CRITICAL from ignorance is how an
        // alert display loses its credibility.
        if (!gpsFleetOutage) {
          flags.push({ reason: 'gps_time_unknown', ageMs: 0, severity: SEV.WARN });
        }
      } else {
        const ageMs = now - lastUpdate;
        gpsIsFresh = ageMs <= GPS_STALE_THRESHOLD_MS;
        const severity = gradeByAge(ageMs, GPS_STALE_THRESHOLD_MS);
        if (severity > SEV.NONE) flags.push({ reason: 'gps_stale', ageMs, severity });
      }
    }

    if (gpsIsFresh && gps.speed_kmh != null && gps.speed_kmh <= REPORTED_STOPPED_SPEED_KMH
        && (!cs || cs.execution_status !== 'arrived')) {
      // Deliberately capped at WARN and never graded: one reading can be a
      // red light, so this must never be able to reach CRITICAL on its own.
      flags.push({ reason: 'reported_stopped', ageMs: 0, severity: SEV.WARN });
    }

    flags.sort((x, y) => (y.severity - x.severity) || (y.ageMs - x.ageMs));
    return flags;
  }

  function maxSeverity(flags) {
    return flags.reduce((m, f) => Math.max(m, f.severity), SEV.NONE);
  }

  function maxAge(flags) {
    return flags.reduce((m, f) => Math.max(m, f.ageMs), 0);
  }

  function attentionReasonText(flag, a) {
    if (flag.reason === 'stuck') return `Stuck ${formatDuration(flag.ageMs)} at stop`;
    if (flag.reason === 'gps_stale') return `GPS stale ${formatDuration(flag.ageMs)}`;
    if (flag.reason === 'no_gps') return 'No GPS position';
    // Says what is actually wrong — the position is on the map, its age is
    // not knowable — rather than inventing a duration or staying quiet.
    if (flag.reason === 'gps_time_unknown') return 'GPS age unknown';
    if (flag.reason === 'reported_stopped') {
      return `Reporting ${Math.round(a.gps.speed_kmh)} km/h, not at a stop`;
    }
    return flag.reason;
  }

  function attentionLabel(flags, a) {
    return flags.map((f) => attentionReasonText(f, a)).join(' · ');
  }

  function createCard(assignmentId) {
    const card = document.createElement('div');
    card.className = 'vehicle-card';
    card.dataset.assignmentId = assignmentId;
    card.innerHTML = `
      <div class="vc-header">
        <div>
          <div class="vc-vehicle-row">
            <span class="vc-attention-dot" style="display:none;"></span>
            <span class="vc-vehicle"></span>
          </div>
          <div class="vc-driver"></div>
        </div>
        <span class="status-badge"></span>
      </div>
      <div class="vc-body">
        <div class="vc-current-stop"></div>
        <div class="vc-progress">
          <div class="vc-progress-bar">
            <div class="vc-progress-fill"></div>
          </div>
          <span class="vc-progress-text"></span>
        </div>
        <div class="vc-meta">
          <span class="vc-plan-name"></span>
          <span class="vc-gps-time"></span>
        </div>
      </div>`;
    card.addEventListener('click', () => {
      const id = parseInt(card.dataset.assignmentId, 10);
      DASH.state.selectAssignment(id);
    });
    return card;
  }

  DASH.vehicleList = {
    _cardNodes: new Map(), // assignment_id → card element
    _lastAssignments: [],
    _lastSelectedId: null,
    _toggleBound: false,
    _compactBound: false,

    // Exposed so the quick-filter chips in main.js and the jsdom drives don't
    // each reimplement the thresholds.
    computeAttention,
    maxSeverity,
    SEV,

    // Called by main.js before render() each poll. A fleet-wide GPS outage is
    // the header's story to tell, not forty cards'.
    setGpsFleetOutage(isOutage) {
      gpsFleetOutage = !!isOutage;
    },

    // Diffs against previously-rendered cards instead of rebuilding
    // innerHTML every poll — preserves scroll position, hover state, and
    // avoids rebinding a click listener per card every 12s.
    render(assignments, selectedId) {
      this._lastAssignments = assignments || [];
      this._lastSelectedId = selectedId;
      this._bindAttentionToggle();
      this._bindCompactToggle();

      const container = document.getElementById('vehicleList');
      const countEl = document.getElementById('vehicleCount');
      let list = this._lastAssignments;

      if (list.length === 0) {
        container.innerHTML = '<div class="empty-state">No vehicles found</div>';
        if (countEl) countEl.textContent = '';
        this._cardNodes.clear();
        this._renderAttentionStrip([], new Map());
        return;
      }

      if (countEl) countEl.textContent = list.length;

      const attentionByAssignment = new Map();
      list.forEach((a) => attentionByAssignment.set(a.assignment_id, computeAttention(a)));

      const toggle = document.getElementById('attentionFirstToggle');
      if (toggle && toggle.checked) {
        list = list.slice().sort((a, b) => {
          const fa = attentionByAssignment.get(a.assignment_id);
          const fb = attentionByAssignment.get(b.assignment_id);
          // Worst severity, then how long it has been that way, then flag
          // count as a last resort. Sorting by count alone — which is what
          // this did — ranked three fresh mild flags above a vehicle that had
          // been stuck for three hours, inverting the sort precisely when it
          // mattered most.
          return (maxSeverity(fb) - maxSeverity(fa))
              || (maxAge(fb) - maxAge(fa))
              || (fb.length - fa.length);
        });
      }

      this._renderAttentionStrip(
        list.filter((a) => attentionByAssignment.get(a.assignment_id).length > 0),
        attentionByAssignment
      );

      if (this._cardNodes.size === 0 && container.querySelector('.empty-state')) {
        container.innerHTML = '';
      }

      const seen = new Set();
      const orderedNodes = [];

      list.forEach((a) => {
        seen.add(a.assignment_id);
        let card = this._cardNodes.get(a.assignment_id);
        if (!card) {
          card = createCard(a.assignment_id);
          this._cardNodes.set(a.assignment_id, card);
        }
        this._patchCard(card, a, a.assignment_id === selectedId, attentionByAssignment.get(a.assignment_id));
        orderedNodes.push(card);
      });

      this._cardNodes.forEach((card, id) => {
        if (!seen.has(id)) {
          card.remove();
          this._cardNodes.delete(id);
        }
      });

      let ref = container.firstChild;
      orderedNodes.forEach((card) => {
        if (card !== ref) {
          container.insertBefore(card, ref);
        } else {
          ref = ref.nextSibling;
        }
      });
    },

    // Repaint only what is derived from the clock — GPS ages, attention
    // durations, severity tiers as a flag crosses a threshold. Driven by a
    // timer rather than by the poll, because otherwise an age is only as fresh
    // as the last successful network round trip: a stalled or failing poll
    // leaves "GPS stale 15m" on screen while the real age keeps climbing.
    //
    // Deliberately does NOT: create or remove cards, reorder the list, or call
    // into DASH.map. Reordering would move a card out from under the pointer
    // mid-click, and anything touching the map risks moving the view — which
    // must only ever happen in response to a click (see CLAUDE.md, dashboard
    // map conventions). Sorting is left to the next real poll, at most 12s
    // away; a tier that changes here is visible immediately even so.
    refreshAges() {
      const list = this._lastAssignments || [];
      if (list.length === 0 || this._cardNodes.size === 0) return;

      const attentionByAssignment = new Map();
      list.forEach((a) => attentionByAssignment.set(a.assignment_id, computeAttention(a)));

      list.forEach((a) => {
        const card = this._cardNodes.get(a.assignment_id);
        if (!card) return;
        this._patchCard(card, a, a.assignment_id === this._lastSelectedId,
                        attentionByAssignment.get(a.assignment_id));
      });

      this._renderAttentionStrip(
        list.filter((a) => attentionByAssignment.get(a.assignment_id).length > 0),
        attentionByAssignment
      );
    },

    _bindAttentionToggle() {
      if (this._toggleBound) return;
      const toggle = document.getElementById('attentionFirstToggle');
      if (!toggle) return;
      this._toggleBound = true;
      toggle.addEventListener('change', () => {
        this.render(this._lastAssignments, this._lastSelectedId);
      });
    },

    // Compact mode is a pure CSS class on the list container — the card markup
    // and the diffing patch above are deliberately untouched by it. 36 box
    // trucks plus 4 containers do not fit a 280px column at five lines each.
    _bindCompactToggle() {
      if (this._compactBound) return;
      const toggle = document.getElementById('compactModeToggle');
      const container = document.getElementById('vehicleList');
      if (!toggle || !container) return;
      this._compactBound = true;

      let saved = null;
      try { saved = localStorage.getItem('dashCompactList'); } catch (e) { /* private mode */ }
      toggle.checked = saved === '1';
      container.classList.toggle('compact', toggle.checked);

      toggle.addEventListener('change', () => {
        container.classList.toggle('compact', toggle.checked);
        try {
          localStorage.setItem('dashCompactList', toggle.checked ? '1' : '0');
        } catch (e) { /* private mode */ }
      });
    },

    _renderAttentionStrip(flagged, attentionByAssignment) {
      const strip = document.getElementById('attentionStrip');
      if (!strip) return;

      if (flagged.length === 0) {
        strip.style.display = 'none';
        strip.innerHTML = '';
        return;
      }

      // Sorted independently of the list — the strip is the triage surface, so
      // it is always worst-first even when the list below it is not.
      const ordered = flagged.slice().sort((a, b) => {
        const fa = attentionByAssignment.get(a.assignment_id);
        const fb = attentionByAssignment.get(b.assignment_id);
        return (maxSeverity(fb) - maxSeverity(fa)) || (maxAge(fb) - maxAge(fa));
      });

      const shown = ordered.slice(0, MAX_ATTENTION_CHIPS);
      const overflow = ordered.length - shown.length;

      // The strip scrolls horizontally and this rebuilds its innerHTML, which
      // resets scrollLeft to 0. Harmless every 12s; jarring when the 15s age
      // ticker does it too, mid-read.
      const scrollLeft = strip.scrollLeft;

      strip.style.display = '';
      let html = shown.map((a) => {
        const flags = attentionByAssignment.get(a.assignment_id);
        const label = attentionLabel(flags, a);
        const plate = UI.escapeHtml(a.plate_number || 'Vehicle #' + a.assignment_id);
        const sevClass = SEV_CLASS[maxSeverity(flags)] || '';
        return `<div class="attention-chip ${sevClass}" data-assignment-id="${a.assignment_id}" title="${UI.escapeHtml(label)}">
          <span class="attention-chip-plate">${plate}</span>
          <span class="attention-chip-reason">${UI.escapeHtml(label)}</span>
        </div>`;
      }).join('');

      if (overflow > 0) {
        html += `<div class="attention-chip attention-chip-more" data-attention-more="1" title="Sort the list so these come first">+${overflow} more</div>`;
      }
      strip.innerHTML = html;
      if (scrollLeft) strip.scrollLeft = scrollLeft;

      strip.querySelectorAll('.attention-chip[data-assignment-id]').forEach((chip) => {
        chip.addEventListener('click', () => {
          DASH.state.selectAssignment(parseInt(chip.dataset.assignmentId, 10));
        });
      });

      const more = strip.querySelector('[data-attention-more]');
      if (more) {
        more.addEventListener('click', () => {
          const toggle = document.getElementById('attentionFirstToggle');
          if (!toggle || toggle.checked) return;
          toggle.checked = true;
          toggle.dispatchEvent(new Event('change'));
        });
      }
    },

    _patchCard(card, a, isSelected, attentionFlags) {
      card.classList.toggle('selected', !!isSelected);

      const progress = a.progress || { completed: 0, total: 0, progress_pct: 0 };
      const status = a.plan_status || 'confirmed';
      const gps = a.gps || {};
      const stopName = a.current_stop ? a.current_stop.station_name || a.current_stop.station_code || 'Stop #' + a.current_stop.planned_sequence : 'No active stop';

      setText(card.querySelector('.vc-vehicle'), a.plate_number || 'Vehicle #' + a.assignment_id);
      setText(card.querySelector('.vc-driver'), a.current_driver || 'No driver');

      const flags = attentionFlags || [];
      const severity = maxSeverity(flags);
      card.classList.toggle('attention-warn', severity === SEV.WARN);
      card.classList.toggle('attention-critical', severity === SEV.CRITICAL);

      const dot = card.querySelector('.vc-attention-dot');
      dot.style.display = flags.length > 0 ? '' : 'none';
      if (flags.length > 0) {
        const dotClass = 'vc-attention-dot ' + (SEV_CLASS[severity] || '');
        if (dot.className !== dotClass) dot.className = dotClass;
        dot.title = attentionLabel(flags, a);
      }

      const badge = card.querySelector('.status-badge');
      const badgeClass = 'status-badge ' + statusClass(status);
      if (badge.className !== badgeClass) badge.className = badgeClass;
      setText(badge, statusLabel(status));

      const stopEl = card.querySelector('.vc-current-stop');
      setText(stopEl, stopName);
      if (stopEl.title !== stopName) stopEl.title = stopName;

      const fill = card.querySelector('.vc-progress-fill');
      const fillClass = 'vc-progress-fill ' + statusClass(status);
      if (fill.className !== fillClass) fill.className = fillClass;
      const width = (progress.progress_pct || 0) + '%';
      if (fill.style.width !== width) fill.style.width = width;

      setText(card.querySelector('.vc-progress-text'), `${progress.completed || 0}/${progress.total || 0}`);
      setText(card.querySelector('.vc-plan-name'), a.plan_name || '');

      // A vehicle with no position at all used to render an empty string here,
      // which is indistinguishable from a fresh fix. Say so explicitly.
      const gpsEl = card.querySelector('.vc-gps-time');
      const hasFix = !!gps.last_update;
      setText(gpsEl, hasFix ? 'GPS: ' + this._formatTime(gps.last_update_iso, gps.last_update) : 'No GPS');
      gpsEl.classList.toggle('vc-gps-missing', !hasFix);
    },

    // `isoStr` is the server's parse; `rawStr` is TTAS's own text, shown
    // as-is when the parse failed. Never falls back to `new Date(rawStr)` —
    // that is the month-first misread this whole change exists to remove,
    // and a wrong relative time ("2m ago" for a 3-hour-old fix) is worse
    // than the raw string the dispatcher can read for themselves.
    _formatTime(isoStr, rawStr) {
      if (!isoStr) return rawStr || '';
      try {
        const d = new Date(isoStr);
        if (isNaN(d.getTime())) return rawStr || isoStr;
        const now = new Date();
        const diff = Math.floor((now - d) / 1000);
        if (diff < 60) return 'now';
        if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
        if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
        return d.toLocaleDateString();
      } catch {
        return rawStr || isoStr;
      }
    },
  };
})();
