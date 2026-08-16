/* ================================================================
 * Dispatch Dashboard — jsdom drives
 * ================================================================
 * Frontend changes get no pytest coverage at all (CLAUDE.md, Definition of
 * Done), so this is the only real verification the dashboard modules get.
 * These drive the *actual* modules against the *actual* template markup —
 * the template is loaded from disk and its <script> tags stripped, so an id
 * renamed in the HTML but not the JS fails here rather than in production.
 *
 * Run:
 *     npm install jsdom          # once, anywhere on NODE_PATH
 *     node tests/js/dashboard.test.js
 *
 * jsdom is a dev-only dependency and is deliberately not vendored into the
 * repo; if it is installed elsewhere, point NODE_PATH at it:
 *     NODE_PATH=/tmp/node_modules node tests/js/dashboard.test.js
 */
'use strict';

const fs = require('fs');
const path = require('path');
const assert = require('assert');
const { JSDOM } = require('jsdom');

const ROOT = path.resolve(__dirname, '..', '..');
const JS = (f) => fs.readFileSync(path.join(ROOT, 'static', 'js', f), 'utf8');

// ── Tiny runner ────────────────────────────────────────────────
const results = [];
function test(name, fn) {
  try {
    fn();
    results.push([true, name]);
  } catch (e) {
    results.push([false, name, e]);
  }
}

const MIN = 60 * 1000;

// ── Harness ────────────────────────────────────────────────────
// Builds a live dashboard: real utils.js, polling.js, vehicle-list.js,
// timeline.js and main.js over the real template. api/map are stubbed because
// they are the only two that reach outside the page.
function boot({ assignments = [], gps = {} } = {}) {
  let html = fs.readFileSync(path.join(ROOT, 'templates', 'delivery-dashboard.html'), 'utf8');
  html = html.replace(/<script[\s\S]*?<\/script>/g, '');

  // runScripts:'outside-only' gives the window its own JS realm, so window.eval
  // runs the modules with `window` as their global object. Without it the
  // scripts execute in Node's realm and every bare `DASH` reference — which is
  // how these modules address each other in a browser — fails to resolve.
  const dom = new JSDOM(html, {
    url: 'http://localhost/delivery/dashboard',
    pretendToBeVisual: true,
    runScripts: 'outside-only',
  });
  const { window } = dom;
  global.window = window;
  global.document = window.document;
  global.localStorage = window.localStorage;

  const dashboardPayload = {
    assignments,
    gps_source: gps.source !== undefined ? gps.source : 'ttas',
    gps_error: gps.error !== undefined ? gps.error : null,
    gps_matched: gps.matched !== undefined ? gps.matched : assignments.length,
    gps_available: gps.available !== undefined ? gps.available : assignments.length,
  };

  const calls = { mapVehicles: 0 };

  // utils.js declares `const UI`/`const ApiClient` at top level. Separate
  // <script> tags in a browser share one global lexical environment, but each
  // window.eval() call gets its own and discards it — so the bindings are
  // promoted onto window here to reproduce the browser's visibility rules.
  window.eval(JS('utils.js') + '\n;window.UI = UI; window.ApiClient = ApiClient;');

  // Stubs must exist before main.js's init() runs.
  window.DASH = window.DASH || {};
  window.DASH.api = {
    dashboard: async () => dashboardPayload,
    plans: async () => [],
    stops: async () => [],
    progress: async () => ({ completed: 0, total: 0, progress_pct: 0 }),
    eta: async () => null,
    advance: async () => ({}),
  };
  window.DASH.map = {
    init() {}, invalidateSize() {}, updateVehicles() { calls.mapVehicles++; },
    updateStops() {}, updateRoute() {}, zoomToVehicle() {}, followVehicle() {},
    openGoogleMaps() {}, focusStop: () => true,
  };

  window.eval(JS('dashboard/polling.js'));
  window.eval(JS('dashboard/vehicle-list.js'));
  window.eval(JS('dashboard/timeline.js'));
  window.eval(JS('dashboard/main.js'));

  return { dom, window, DASH: window.DASH, payload: dashboardPayload, calls };
}

// Drives one poll cycle by hand, so the tests never wait on the 12s timer.
async function tick(h) {
  await h.DASH.state.refreshNow();
}

function cardOrder(window) {
  return Array.from(window.document.querySelectorAll('#vehicleList .vehicle-card'))
    .map((c) => c.dataset.assignmentId);
}

// A GPS block as the server actually assembles it: `last_update` is TTAS's
// own day-first text for display, `last_update_iso` is the server-side parse
// and the only field any age is computed from. Fixtures carrying just one of
// the two are how the month-first misread went unnoticed for the module's
// whole life — so this helper always emits both.
function makeGps(ageMs = 0, over = {}) {
  const at = new Date(Date.now() - ageMs);
  const pad = (n) => String(n).padStart(2, '0');
  return Object.assign({
    // dd/MM/yyyy HH:mm:ss — the format that made `new Date()` return
    // 8 January for 1 August, and Invalid Date from the 13th onward.
    last_update: `${pad(at.getDate())}/${pad(at.getMonth() + 1)}/${at.getFullYear()} `
               + `${pad(at.getHours())}:${pad(at.getMinutes())}:${pad(at.getSeconds())}`,
    last_update_iso: at.toISOString(),
    speed_kmh: 40,
  }, over);
}

function makeAssignment(id, over = {}) {
  return {
    assignment_id: id,
    plate_number: over.plate || ('51C-' + id),
    current_driver: 'Driver ' + id,
    plan_id: 1,
    plan_name: 'Plan A',
    plan_date: '2026-07-31',
    plan_status: over.plan_status || 'executing',
    progress: { completed: 1, total: 5, progress_pct: 20 },
    current_stop: over.current_stop !== undefined ? over.current_stop : null,
    gps: over.gps !== undefined ? over.gps : makeGps(),
  };
}

function stuckFor(ms) {
  return { execution_status: 'arrived', actual_arrival_at: new Date(Date.now() - ms).toISOString(), station_name: 'Depot' };
}

// ================================================================
(async function run() {

  // ── 0.2 Severity grading ─────────────────────────────────────
  {
    const h = boot();
    const { computeAttention, SEV } = h.DASH.vehicleList;

    test('stuck just past the 20m threshold grades WARN, not CRITICAL', () => {
      const flags = computeAttention(makeAssignment(1, { current_stop: stuckFor(21 * MIN) }));
      const stuck = flags.find((f) => f.reason === 'stuck');
      assert.ok(stuck, 'expected a stuck flag');
      assert.strictEqual(stuck.severity, SEV.WARN);
    });

    test('stuck past 2x the threshold grades CRITICAL', () => {
      const flags = computeAttention(makeAssignment(1, { current_stop: stuckFor(45 * MIN) }));
      assert.strictEqual(flags.find((f) => f.reason === 'stuck').severity, SEV.CRITICAL);
    });

    test('a stop arrived 5m ago raises no flag at all', () => {
      const flags = computeAttention(makeAssignment(1, { current_stop: stuckFor(5 * MIN) }));
      assert.strictEqual(flags.filter((f) => f.reason === 'stuck').length, 0);
    });

    test('reported_stopped is capped at WARN and can never reach CRITICAL', () => {
      const flags = computeAttention(makeAssignment(1, {
        gps: makeGps(0, { speed_kmh: 0 }),
      }));
      const rs = flags.find((f) => f.reason === 'reported_stopped');
      assert.ok(rs, 'expected a reported_stopped flag');
      assert.strictEqual(rs.severity, SEV.WARN);
    });

    test('a missing GPS object flags no_gps, distinct from a stale fix', () => {
      const flags = computeAttention(makeAssignment(1, { gps: null }));
      assert.ok(flags.some((f) => f.reason === 'no_gps'));
      assert.ok(!flags.some((f) => f.reason === 'gps_stale'));
    });

    test('no_gps is suppressed while the whole fleet is dark', () => {
      h.DASH.vehicleList.setGpsFleetOutage(true);
      const flags = computeAttention(makeAssignment(1, { gps: null }));
      assert.strictEqual(flags.length, 0, 'fleet-wide outage is the header’s story, not 40 chips');
      h.DASH.vehicleList.setGpsFleetOutage(false);
    });

    // ── GPS age: three states, and the month-first misread ──────
    // TTAS writes `trktime` day-first. It used to reach the browser as raw
    // text and be read by `new Date()`, which takes non-ISO strings
    // month-first. The age is now computed only from the server's parse.
    {
      // The exact reported symptom: on 1 August every vehicle claimed its
      // GPS was 4920h (205 days) stale, because "01/08/2026" read as 8 Jan.
      const dayFirstToday = makeGps(2 * MIN);

      test('a fresh day-first fix is not read as months stale', () => {
        const flags = computeAttention(makeAssignment(1, { gps: dayFirstToday }));
        const stale = flags.find((f) => f.reason === 'gps_stale');
        assert.ok(!stale, stale && `expected no stale flag, got one aged ${Math.round(stale.ageMs / 3600000)}h`);
      });

      test('a genuinely old fix still raises the stale flag', () => {
        const flags = computeAttention(makeAssignment(1, { gps: makeGps(40 * MIN) }));
        const stale = flags.find((f) => f.reason === 'gps_stale');
        assert.ok(stale, 'a 40-minute-old fix must still be flagged');
        assert.strictEqual(stale.severity, SEV.CRITICAL);
      });

      test('the raw day-first text is ignored even when it would parse', () => {
        // 03/08/2026 is 3 August; read month-first it is 8 March — five
        // months of phantom staleness. Only last_update_iso may be believed.
        const flags = computeAttention(makeAssignment(1, {
          gps: { last_update: '03/08/2026 09:00:00', last_update_iso: new Date().toISOString(), speed_kmh: 40 },
        }));
        assert.ok(!flags.some((f) => f.reason === 'gps_stale'));
      });

      test('a null parse is never rescued by re-reading the raw text', () => {
        // The sharp case: "01/08/2026" is unreadable to the server only if
        // TTAS changed format, but `new Date()` will happily read it
        // month-first as 8 January and produce the original 4920h phantom.
        // A fallback to the raw string here would reintroduce the whole bug,
        // so the age must stay unknown.
        const flags = computeAttention(makeAssignment(1, {
          gps: { last_update: '01/08/2026 09:00:00', last_update_iso: null, speed_kmh: 40 },
        }));
        assert.ok(flags.some((f) => f.reason === 'gps_time_unknown'));
        const stale = flags.find((f) => f.reason === 'gps_stale');
        assert.ok(!stale, stale && `invented an age of ${Math.round(stale.ageMs / 3600000)}h from raw text`);
      });

      test('an unreadable timestamp warns instead of going silent', () => {
        // From the 13th of any month the old code hit Invalid Date and its
        // isNaN guard skipped the check entirely — a dead tracker raised
        // nothing at all for two thirds of every month.
        const flags = computeAttention(makeAssignment(1, {
          gps: { last_update: '13/08/2026 09:00:00', last_update_iso: null, speed_kmh: 40 },
        }));
        const unknown = flags.find((f) => f.reason === 'gps_time_unknown');
        assert.ok(unknown, 'an unknown GPS age must say so');
        assert.strictEqual(unknown.severity, SEV.WARN);
      });

      test('unknown age is never graded critical from ignorance', () => {
        const flags = computeAttention(makeAssignment(1, {
          gps: { last_update: 'sometime', last_update_iso: null, speed_kmh: 40 },
        }));
        assert.ok(!flags.some((f) => f.severity === SEV.CRITICAL));
      });

      test('unknown age is distinct from having no position at all', () => {
        const unreadable = computeAttention(makeAssignment(1, {
          gps: { last_update: 'sometime', last_update_iso: null, speed_kmh: 40 },
        }));
        assert.ok(!unreadable.some((f) => f.reason === 'no_gps'),
          'the truck has a position — the map is drawing it');
        assert.ok(computeAttention(makeAssignment(1, { gps: null }))
          .some((f) => f.reason === 'no_gps'));
      });

      test('an unknown age never counts as fresh enough to judge speed', () => {
        // reported_stopped means "moving at ~0 right now". Without a
        // trustworthy timestamp there is no "right now" to assert.
        const flags = computeAttention(makeAssignment(1, {
          gps: { last_update: 'sometime', last_update_iso: null, speed_kmh: 0 },
        }));
        assert.ok(!flags.some((f) => f.reason === 'reported_stopped'));
      });

      test('unknown age is suppressed during a fleet-wide outage, like no_gps', () => {
        h.DASH.vehicleList.setGpsFleetOutage(true);
        const flags = computeAttention(makeAssignment(1, {
          gps: { last_update: 'sometime', last_update_iso: null, speed_kmh: 40 },
        }));
        assert.ok(!flags.some((f) => f.reason === 'gps_time_unknown'));
        h.DASH.vehicleList.setGpsFleetOutage(false);
      });
    }
  }

  // ── 0.2 The sort inversion this phase exists to fix ──────────
  {
    // #1 carries two mild flags (barely stuck, barely stale). #2 carries one,
    // but it has been stuck for three hours. The old sort ranked by flag
    // *count* and therefore put #1 first — this is that exact case.
    const mild = makeAssignment(1, {
      current_stop: stuckFor(21 * MIN),
      gps: makeGps(16 * MIN, { speed_kmh: 30 }),
    });
    const severe = makeAssignment(2, {
      current_stop: stuckFor(180 * MIN),
      gps: makeGps(),
    });

    const h = boot({ assignments: [mild, severe] });
    await tick(h);

    test('fixture is the real inversion case: more flags on the milder vehicle', () => {
      const a = h.DASH.vehicleList.computeAttention(mild);
      const b = h.DASH.vehicleList.computeAttention(severe);
      assert.ok(a.length > b.length, `expected mild to carry more flags (${a.length} vs ${b.length})`);
      assert.ok(h.DASH.vehicleList.maxSeverity(b) > h.DASH.vehicleList.maxSeverity(a));
    });

    test('Attention-first puts a 3h stuck above three fresh mild flags', () => {
      const toggle = h.window.document.getElementById('attentionFirstToggle');
      toggle.checked = true;
      toggle.dispatchEvent(new h.window.Event('change'));
      assert.deepStrictEqual(cardOrder(h.window), ['2', '1']);
    });

    test('the attention strip is worst-first regardless of the list sort', () => {
      const toggle = h.window.document.getElementById('attentionFirstToggle');
      toggle.checked = false;
      toggle.dispatchEvent(new h.window.Event('change'));
      const chips = Array.from(h.window.document.querySelectorAll('#attentionStrip .attention-chip[data-assignment-id]'));
      assert.strictEqual(chips[0].dataset.assignmentId, '2');
    });

    test('critical severity reaches the card as a class, not just a tooltip', () => {
      const card = h.window.document.querySelector('.vehicle-card[data-assignment-id="2"]');
      assert.ok(card.classList.contains('attention-critical'), card.className);
      assert.ok(card.querySelector('.vc-attention-dot').className.includes('sev-critical'));
    });

    h.DASH.polling.stop();
  }

  // ── 0.1 GPS trust badge precedence ───────────────────────────
  {
    const two = [makeAssignment(1), makeAssignment(2)];

    async function pill(gps) {
      const h = boot({ assignments: two, gps });
      await tick(h);
      const el = h.window.document.getElementById('pollStatus');
      const out = { text: el.textContent, cls: el.className, title: el.title };
      h.DASH.polling.stop();
      return out;
    }

    const full = await pill({ matched: 2, available: 2 });
    const partial = await pill({ matched: 1, available: 2 });
    const unmatched = await pill({ matched: 0, available: 7 });
    const none = await pill({ matched: 0, available: 0 });
    const errored = await pill({ matched: 0, available: 0, error: 'TTAS login failed' });

    test('all plates matched reads Live', () => {
      assert.strictEqual(full.text, 'Live');
      assert.ok(full.cls.includes('poll-ok'));
    });

    test('a partial match is degraded, and says how many', () => {
      assert.strictEqual(partial.text, 'GPS 1/2');
      assert.ok(partial.cls.includes('poll-degraded'), partial.cls);
    });

    test('positions that matched no plate never read Live (audit C-01)', () => {
      assert.notStrictEqual(unmatched.text, 'Live');
      assert.strictEqual(unmatched.text, 'GPS 0/7');
      assert.ok(unmatched.cls.includes('poll-gpsdown'), unmatched.cls);
      assert.match(unmatched.title, /plate formats/i);
    });

    test('no positions at all never reads Live', () => {
      assert.notStrictEqual(none.text, 'Live');
      assert.ok(none.cls.includes('poll-gpsdown'), none.cls);
    });

    test('a GPS source error is reported with its message', () => {
      assert.strictEqual(errored.text, 'GPS down');
      assert.match(errored.title, /TTAS login failed/);
    });

    test('an empty board is not a GPS fault', async () => {
      const h = boot({ assignments: [], gps: { matched: 0, available: 0 } });
      await tick(h);
      assert.strictEqual(h.window.document.getElementById('pollStatus').textContent, 'Live');
      h.DASH.polling.stop();
    });
  }

  // ── 0.4 Quick filters ────────────────────────────────────────
  {
    const h = boot({
      assignments: [
        makeAssignment(1),
        makeAssignment(2, { gps: null }),
        makeAssignment(3, { plan_status: 'confirmed' }),
      ],
      gps: { matched: 2, available: 2 },
    });
    await tick(h);

    function clickChip(value) {
      const chip = h.window.document.querySelector(`#quickFilters .quick-chip[data-quick="${value}"]`);
      assert.ok(chip, 'missing chip: ' + value);
      chip.dispatchEvent(new h.window.Event('click', { bubbles: true }));
    }

    test('the No GPS chip keeps only vehicles without a fix', () => {
      clickChip('nogps');
      assert.deepStrictEqual(cardOrder(h.window), ['2']);
    });

    test('clicking the active chip clears it', () => {
      clickChip('nogps');
      assert.strictEqual(cardOrder(h.window).length, 3);
    });

    test('the Executing chip excludes confirmed-but-not-started plans', () => {
      clickChip('executing');
      assert.deepStrictEqual(cardOrder(h.window).sort(), ['1', '2']);
      clickChip('executing');
    });

    // ── MTH: TTAS saying the tracker went quiet ──────────────────
    //
    // Operator-reported 2026-08-03. TTAS writes `MTH:6h48'` and the vehicle
    // keeps the last fix taken before the signal dropped, so it passes a
    // "has a position" test — and was therefore missing from the one list a
    // dispatcher opens to find the trucks they cannot see.
    {
      const lost = boot({
        assignments: [
          makeAssignment(1),
          makeAssignment(2, { gps: null }),
          makeAssignment(3, { gps: makeGps(0, { signal_lost: true }) }),
          makeAssignment(4, { gps: makeGps(45 * MIN) }),
        ],
        gps: { matched: 3, available: 3 },
      });
      await tick(lost);

      function clickLostChip(value) {
        const chip = lost.window.document
          .querySelector(`#quickFilters .quick-chip[data-quick="${value}"]`);
        chip.dispatchEvent(new lost.window.Event('click', { bubbles: true }));
      }

      test('the No GPS chip includes a vehicle TTAS reports as MTH', () => {
        clickLostChip('nogps');
        assert.ok(cardOrder(lost.window).includes('3'),
          'a lost-signal truck is invisible in the list meant to find it');
      });

      test('a vehicle with no fix at all is still included', () => {
        assert.ok(cardOrder(lost.window).includes('2'));
      });

      test('a merely stale fix is not treated as a lost signal', () => {
        // 45 minutes old raises a stale chip, but TTAS has not declared the
        // tracker unreachable — inference and declaration stay separate.
        assert.ok(!cardOrder(lost.window).includes('4'));
      });

      test('a tracked vehicle is still excluded', () => {
        assert.deepStrictEqual(cardOrder(lost.window).sort(), ['2', '3']);
        clickLostChip('nogps');
      });

      lost.DASH.polling.stop();
    }

    test('the field filters still work from inside the disclosure', () => {
      const field = h.window.document.getElementById('filterVehicle');
      field.value = '51C-3';
      field.dispatchEvent(new h.window.Event('input', { bubbles: true }));
      assert.deepStrictEqual(cardOrder(h.window), ['3']);
      assert.strictEqual(h.window.document.getElementById('filtersActiveCount').textContent, '1',
        'an active filter hiding in a closed panel must be counted on the button');
      field.value = '';
      field.dispatchEvent(new h.window.Event('input', { bubbles: true }));
    });

    h.DASH.polling.stop();
  }

  // ── 0.5 Keyboard ─────────────────────────────────────────────
  {
    const h = boot({ assignments: [makeAssignment(1), makeAssignment(2), makeAssignment(3)] });
    await tick(h);

    const key = (k, opts) => h.window.document.dispatchEvent(
      new h.window.KeyboardEvent('keydown', Object.assign({ key: k, bubbles: true, cancelable: true }, opts))
    );

    test('j moves the focus ring without selecting', () => {
      key('j');
      const focused = h.window.document.querySelectorAll('#vehicleList .vehicle-card.focused');
      assert.strictEqual(focused.length, 1);
      assert.strictEqual(focused[0].dataset.assignmentId, '1');
      assert.strictEqual(h.DASH.state.selectedAssignmentId, null, 'j must not fire a detail load');
    });

    test('k at the top of the list does not wrap around', () => {
      key('k');
      assert.strictEqual(h.DASH.state.focusedAssignmentId, 1);
    });

    test('j stops at the last vehicle', () => {
      key('j'); key('j'); key('j'); key('j');
      assert.strictEqual(h.DASH.state.focusedAssignmentId, 3);
    });

    test('Enter selects the focused vehicle', () => {
      key('Enter');
      assert.strictEqual(h.DASH.state.selectedAssignmentId, 3);
    });

    test('Escape clears the selection and leaves the ring behind', () => {
      key('Escape');
      assert.strictEqual(h.DASH.state.selectedAssignmentId, null);
      assert.strictEqual(h.DASH.state.focusedAssignmentId, 3);
    });

    test('/ opens the Filters disclosure and focuses the plate field', () => {
      key('/');
      assert.ok(h.window.document.getElementById('dashboardFilters').classList.contains('open'));
      assert.strictEqual(h.window.document.activeElement.id, 'filterVehicle');
    });

    test('typing in a filter field does not trigger shortcuts', () => {
      const before = h.DASH.state.focusedAssignmentId;
      h.window.document.getElementById('filterVehicle').focus();
      key('j'); key('k'); key('f'); key('a');
      assert.strictEqual(h.DASH.state.focusedAssignmentId, before,
        'a plate containing j/k must not move the focus ring while being typed');
    });

    test('Escape works from inside a field, and closes the disclosure', () => {
      key('Escape');
      assert.ok(!h.window.document.getElementById('dashboardFilters').classList.contains('open'));
    });

    test('an open skip/cancel reason row suppresses shortcuts', () => {
      assert.strictEqual(typeof h.DASH.timeline.hasOpenReasonRow, 'function');
      const real = h.DASH.timeline.hasOpenReasonRow;
      h.DASH.timeline.hasOpenReasonRow = () => true;
      const before = h.DASH.state.focusedAssignmentId;
      key('k');
      assert.strictEqual(h.DASH.state.focusedAssignmentId, before);
      h.DASH.timeline.hasOpenReasonRow = real;
    });

    test('modifier combinations are left to the browser', () => {
      const before = h.DASH.state.focusedAssignmentId;
      key('j', { ctrlKey: true });
      key('r', { metaKey: true });
      assert.strictEqual(h.DASH.state.focusedAssignmentId, before);
    });

    h.DASH.polling.stop();
  }

  // ── 0.3 Compact density ──────────────────────────────────────
  {
    const h = boot({ assignments: [makeAssignment(1)] });
    await tick(h);

    test('the compact toggle only ever touches a class on the container', () => {
      const toggle = h.window.document.getElementById('compactModeToggle');
      const list = h.window.document.getElementById('vehicleList');
      const before = h.window.document.querySelector('.vehicle-card').innerHTML;

      toggle.checked = true;
      toggle.dispatchEvent(new h.window.Event('change'));
      assert.ok(list.classList.contains('compact'));
      assert.strictEqual(h.window.document.querySelector('.vehicle-card').innerHTML, before,
        'compact must not alter card markup — the diffing render depends on it');
    });

    test('the compact choice survives a reload', () => {
      assert.strictEqual(h.window.localStorage.getItem('dashCompactList'), '1');
    });

    h.DASH.polling.stop();
  }

  // ── Regression guards on behaviour this phase must not break ──
  {
    const h = boot({ assignments: [makeAssignment(1), makeAssignment(2)] });
    await tick(h);

    test('card nodes are reused across polls, not rebuilt', async () => {
      const before = h.window.document.querySelector('.vehicle-card[data-assignment-id="1"]');
      await tick(h);
      const after = h.window.document.querySelector('.vehicle-card[data-assignment-id="1"]');
      assert.strictEqual(before, after, 'a rebuilt node loses scroll/hover state');
    });

    test('a vehicle with a fresh fix still shows its GPS age, not "No GPS"', () => {
      const el = h.window.document.querySelector('.vehicle-card[data-assignment-id="1"] .vc-gps-time');
      assert.match(el.textContent, /^GPS: /);
      assert.ok(!el.classList.contains('vc-gps-missing'));
    });

    h.DASH.polling.stop();
  }

  // ── Phase C: routing-restriction banner ──────────────────────
  {
    const h = boot({ assignments: [makeAssignment(1)] });
    await tick(h);
    const el = () => h.window.document.getElementById('restrictionBanner');

    const legs = (statuses) => statuses.map((s, i) => ({
      stop_id: i + 1, lat: 10.8, lng: 106.6, eta_seconds: 600,
      restriction_status: s,
    }));

    test('a fully compliant route on real vehicle data says nothing', () => {
      h.DASH.timeline._renderRestrictionBanner({
        etas: legs(['compliant', 'compliant']),
        restrictions: { height: 2.9, weight: 4.99 },
        restrictions_source: 'vehicle',
      });
      assert.strictEqual(el().style.display, 'none', 'silence is the correct output here');
    });

    test('a violated leg warns, counts the legs, and names the limits', () => {
      h.DASH.timeline._renderRestrictionBanner({
        etas: legs(['compliant', 'violated', 'violated']),
        restrictions: { height: 3.2, weight: 8.5 },
        restrictions_source: 'vehicle',
      });
      assert.ok(el().className.includes('violated'), el().className);
      assert.match(el().textContent, /2 legs/);
      assert.match(el().textContent, /3\.2 m tall/);
      assert.match(el().textContent, /8\.5 t/);
    });

    test('one violated leg is not pluralised', () => {
      h.DASH.timeline._renderRestrictionBanner({
        etas: legs(['violated']),
        restrictions: { height: 3.2 },
        restrictions_source: 'vehicle',
      });
      assert.match(el().textContent, /1 leg /);
    });

    test('a compliant route on type estimates is flagged, differently', () => {
      h.DASH.timeline._renderRestrictionBanner({
        etas: legs(['compliant']),
        restrictions: { height: 2.9 },
        restrictions_source: 'type_default',
      });
      // "Routed against a guess" must not look like "routed against the
      // registration certificate", nor like an outright violation.
      assert.ok(el().className.includes('estimated'), el().className);
      assert.ok(!el().className.includes('violated'));
      assert.match(el().textContent, /not its registration certificate/);
    });

    test('a vehicle with nothing recorded says the route was not checked', () => {
      h.DASH.timeline._renderRestrictionBanner({
        etas: legs(['unrestricted']),
        restrictions: {},
        restrictions_source: 'none',
      });
      assert.ok(el().className.includes('unchecked'), el().className);
      assert.match(el().textContent, /not checked/i);
    });

    test('a violation outranks an estimate when both apply', () => {
      h.DASH.timeline._renderRestrictionBanner({
        etas: legs(['violated']),
        restrictions: { height: 3.6 },
        restrictions_source: 'type_default',
      });
      assert.ok(el().className.includes('violated'), el().className);
    });

    test('the banner clears when a route with nothing to say arrives', () => {
      h.DASH.timeline._renderRestrictionBanner({
        etas: legs(['compliant']),
        restrictions: { height: 2.9 },
        restrictions_source: 'vehicle',
      });
      assert.strictEqual(el().style.display, 'none');
      assert.strictEqual(el().innerHTML, '');
    });

    test('no ETA data at all leaves the banner hidden', () => {
      h.DASH.timeline._renderRestrictionBanner(null);
      assert.strictEqual(el().style.display, 'none');
    });

    h.DASH.polling.stop();
  }

  // ── ETA as a clock time, not a countdown ─────────────────────
  {
    const h = boot({ assignments: [makeAssignment(1)] });
    await tick(h);
    const UI = h.window.UI;

    test('an ETA renders as time of day', () => {
      const now = new Date();
      const expected = new Date(now.getTime() + 47 * 60 * 1000);
      const pad = (n) => String(n).padStart(2, '0');
      assert.strictEqual(UI.etaClock(47 * 60),
        `${pad(expected.getHours())}:${pad(expected.getMinutes())}`);
    });

    test('arrival is 24h, so 14:35 is never mistaken for 02:35', () => {
      assert.ok(!/[ap]m/i.test(UI.etaClock(3600)));
    });

    test('a route running past midnight is marked, not shown as already late', () => {
      const clock = UI.etaClock(36 * 3600);
      // Without the day marker this reads as a time earlier than now.
      assert.match(clock, /\+1d$/);
    });

    test('a null ETA yields null, never a fabricated arrival time', () => {
      // This is audit L-10's shape: null/60 rounded to a confident "0 min",
      // i.e. "arriving now". It must not come back in clock form as "14:02".
      assert.strictEqual(UI.etaClock(null), null);
      assert.strictEqual(UI.etaClock(undefined), null);
      assert.strictEqual(UI.etaClock('600'), null);
      assert.strictEqual(UI.etaClock(NaN), null);
      assert.strictEqual(UI.etaClock(Infinity), null);
      assert.strictEqual(UI.etaClock(-60), null);
    });

    test('zero seconds is a real answer and renders a time', () => {
      assert.match(UI.etaClock(0), /^\d{2}:\d{2}$/);
    });

    test('the relative duration is kept for the tooltip', () => {
      assert.strictEqual(UI.etaRelative(47 * 60), '47 min');
      assert.strictEqual(UI.etaRelative(135 * 60), '2h 15m');
      assert.strictEqual(UI.etaRelative(120 * 60), '2h');
      assert.strictEqual(UI.etaRelative(null), null);
    });

    test('the info bar shows a clock time with the duration on hover', () => {
      const bar = h.window.document.getElementById('vibarEta');
      h.DASH.timeline.render([], null, null);
      // Drive the real painter through a selection with a known ETA.
      h.DASH.state.selectedEta = { etas: [{ stop_id: 1, eta_seconds: 47 * 60 }] };
      h.DASH.state.selectedStops = [{ id: 1, lat: 10.8, lng: 106.6, execution_status: 'planned' }];
      h.DASH.state.selectedAssignmentId = 1;
      h.DASH.state.refreshNow();
      // Painted synchronously by updateInfoBar via paintAssignmentDetail.
      return new Promise((resolve) => setTimeout(() => {
        assert.match(bar.textContent, /^ETA: (\d{2}:\d{2}|--)/);
        resolve();
      }, 10));
    });

    h.DASH.polling.stop();
  }

  // ── What a dispatcher actually sees for an unreadable timestamp ──
  {
    const h = boot({
      assignments: [makeAssignment(1, {
        gps: { last_update: '13/08/2026 09:00:00', last_update_iso: null, speed_kmh: 40 },
      })],
    });
    await tick(h);

    test('the card shows TTAS’s own text rather than a wrong relative time', () => {
      const cell = h.window.document
        .querySelector('.vehicle-card[data-assignment-id="1"] .vc-gps-time').textContent;
      // Not "2m ago", not "205 days" — the raw value, which the dispatcher
      // can read for themselves, and no invented age.
      assert.match(cell, /13\/08\/2026 09:00:00/);
      assert.ok(!/ago/.test(cell), cell);
    });

    test('the card is not marked as having no GPS at all', () => {
      const cell = h.window.document
        .querySelector('.vehicle-card[data-assignment-id="1"] .vc-gps-time');
      assert.ok(!cell.classList.contains('vc-gps-missing'));
    });

    test('the attention chip names the real problem', () => {
      const chip = h.window.document.querySelector('#attentionStrip .attention-chip');
      assert.ok(chip, 'expected an attention chip for an unknown GPS age');
      assert.match(chip.textContent, /GPS age unknown/);
    });

    h.DASH.polling.stop();
  }

  // ── Age ticker: refresh without moving anything ──────────────
  {
    const stale = (mins) => makeAssignment(1, {
      gps: makeGps(mins * MIN),
    });

    const h = boot({ assignments: [stale(16), makeAssignment(2)] });
    await tick(h);

    const gpsCell = (id) => h.window.document
      .querySelector(`.vehicle-card[data-assignment-id="${id}"] .vc-gps-time`).textContent;
    const chipText = () => (h.window.document.querySelector('#attentionStrip .attention-chip') || {}).textContent || '';

    test('ages advance without a poll', () => {
      const before = gpsCell(1);
      // Push the fixture's timestamp further into the past, exactly as real
      // time passing would, then tick without any network round trip.
      // The age is read from last_update_iso, so that is the field real time
      // passing would move — mutating last_update alone would prove nothing.
      Object.assign(h.DASH.vehicleList._lastAssignments[0].gps, makeGps(24 * MIN));
      h.DASH.vehicleList.refreshAges();
      assert.notStrictEqual(gpsCell(1), before);
      assert.match(gpsCell(1), /24m ago/);
    });

    test('an attention duration advances too', () => {
      assert.match(chipText(), /GPS stale 24m/);
    });

    test('a severity tier crossing a threshold is applied on a tick', () => {
      const card = h.window.document.querySelector('.vehicle-card[data-assignment-id="1"]');
      assert.ok(card.classList.contains('attention-warn'), card.className);
      // 15m threshold, so 2x is 30m — past that it must go critical without
      // waiting for a poll.
      Object.assign(h.DASH.vehicleList._lastAssignments[0].gps, makeGps(40 * MIN));
      h.DASH.vehicleList.refreshAges();
      assert.ok(card.classList.contains('attention-critical'), card.className);
      assert.ok(!card.classList.contains('attention-warn'));
    });

    test('the ticker never touches the map', () => {
      const before = h.calls.mapVehicles;
      h.DASH.vehicleList.refreshAges();
      // The one rule that must not bend: the view moves only on a click.
      // Not reaching DASH.map at all is how that is guaranteed here.
      assert.strictEqual(h.calls.mapVehicles, before);
    });

    test('the ticker never reorders the list', () => {
      const before = cardOrder(h.window);
      const toggle = h.window.document.getElementById('attentionFirstToggle');
      toggle.checked = true;   // sorting is on; #1 is critical, #2 is clean
      h.DASH.vehicleList.refreshAges();
      // A card moving out from under the pointer mid-click is its own kind of
      // snap. Sorting waits for the next real poll.
      assert.deepStrictEqual(cardOrder(h.window), before);
      toggle.checked = false;
    });

    test('the ticker reuses card nodes rather than rebuilding them', () => {
      const node = h.window.document.querySelector('.vehicle-card[data-assignment-id="1"]');
      h.DASH.vehicleList.refreshAges();
      assert.strictEqual(
        h.window.document.querySelector('.vehicle-card[data-assignment-id="1"]'), node);
    });

    // NOT tested here: that the attention strip keeps its horizontal scroll
    // position across a tick. jsdom has no layout engine, so scrollLeft never
    // resets on an innerHTML swap and the assertion passes whether the
    // preserving code is present or not — verified by mutation. The code is in
    // _renderAttentionStrip; confirming it needs a real browser.

    test('a tick before any render is a no-op, not a crash', () => {
      const fresh = boot({ assignments: [] });
      fresh.DASH.vehicleList.refreshAges();
      fresh.DASH.polling.stop();
    });

    h.DASH.polling.stop();
  }

  // ── ETA does not drift as it is repainted ────────────────────
  {
    const h = boot({ assignments: [makeAssignment(1)] });
    await tick(h);

    test('an arrival time is fixed to when the ETA arrived, not to now', () => {
      // Two repaints of the same payload, five minutes apart, must name the
      // same arrival time. Recomputing from Date.now() would push it later on
      // each one — four times a minute, once the age ticker is running.
      const landed = Date.now() - 5 * 60 * 1000;
      assert.strictEqual(
        h.window.UI.etaClock(1800, landed),
        h.window.UI.etaClock(1800, landed)
      );
      // And that baseline genuinely changes the answer, so the assertion above
      // is not passing for trivial reasons.
      assert.notStrictEqual(
        h.window.UI.etaClock(1800, landed),
        h.window.UI.etaClock(1800, Date.now())
      );
    });

    test('a bad baseline falls back to now rather than producing nonsense', () => {
      assert.match(h.window.UI.etaClock(600, NaN), /^\d{2}:\d{2}$/);
      assert.match(h.window.UI.etaClock(600, 'soon'), /^\d{2}:\d{2}$/);
    });

    h.DASH.polling.stop();
  }

  // ── Revert: undoing a mis-tapped Advance / Skip / Cancel ─────
  // Advance is one unconfirmed tap beside Skip and Cancel, pressed on a phone
  // in a moving vehicle. Two things here are easy to get wrong by inspection:
  // the button is drawn from a server flag through the same diffing renderer
  // that patches every poll, and the undo has to reconstruct the status the
  // action landed in before any refresh could tell it.
  {
    const revertStop = (over) => Object.assign({
      id: 1, station_name: 'Stop 1', execution_status: 'planned',
      planned_sequence: 1, execution_sequence: 1, can_revert: false,
    }, over);

    // Records what the timeline asked the API to do, and lets a call be made
    // to fail on demand.
    function withRecordedApi(h, { revertFails = false } = {}) {
      const calls = [];
      const record = (name, resp) => (...args) => {
        calls.push([name, ...args]);
        return Promise.resolve(resp);
      };
      h.DASH.api.advance = record('advance', { ok: true, status: 'advanced' });
      h.DASH.api.skip = record('skip', { ok: true });
      h.DASH.api.cancel = record('cancel', { ok: true });
      h.DASH.api.revert = revertFails
        ? (...args) => { calls.push(['revert', ...args]); return Promise.reject(new Error('stale')); }
        : record('revert', { ok: true, status: 'planned' });
      h.DASH.state.refreshNow = () => { calls.push(['refresh']); return Promise.resolve(); };
      return calls;
    }

    const actionsOf = (window, stopId) => Array.from(
      window.document.querySelectorAll(`#timeline [data-actions-for="${stopId}"] [data-action]`)
    ).map((b) => b.dataset.action);

    const settle = (window, ms = 0) => new Promise((r) => window.setTimeout(r, ms));
    const click = (window, selector) => window.document.querySelector(selector).click();
    const toastText = (window) => window.document.getElementById('toast-container').textContent;
    const undoBtn = (window) => window.document.querySelector('#toast-container .toast-action');

    // Which stops offer the button
    {
      const h = boot();
      h.DASH.timeline.render([
        revertStop({ id: 1, execution_status: 'planned', can_revert: false }),
        revertStop({ id: 2, execution_status: 'arrived', can_revert: true }),
        revertStop({ id: 3, execution_status: 'completed', can_revert: true }),
        revertStop({ id: 4, execution_status: 'completed', can_revert: false }),
      ], 2, null);

      test('a stop nobody has touched offers no undo', () => {
        assert.ok(!actionsOf(h.window, 1).includes('revert'));
      });

      test('an arrived stop keeps its forward actions and gains Revert', () => {
        assert.deepStrictEqual(actionsOf(h.window, 2), ['advance', 'skip', 'cancel', 'revert']);
      });

      test('a completed stop offers Revert alone — it has no other action', () => {
        assert.deepStrictEqual(actionsOf(h.window, 3), ['revert']);
      });

      test('a completed stop past the window offers nothing at all', () => {
        assert.deepStrictEqual(actionsOf(h.window, 4), []);
      });

      test('no skip/cancel reason row is emitted where only Revert shows', () => {
        assert.strictEqual(h.window.document.querySelector('[data-reason-for="3"]'), null);
      });

      h.DASH.polling.stop();
    }

    // The staleness token, and the in-flight guard
    {
      const h = boot();
      const calls = withRecordedApi(h);
      h.DASH.timeline.render([revertStop({ id: 7, execution_status: 'completed', can_revert: true })], null, null);
      const btn = h.window.document.querySelector('#timeline [data-action="revert"]');
      btn.click();
      btn.click();
      await settle(h.window);

      test('Revert posts the status its row was rendered with', () => {
        assert.deepStrictEqual(calls[0], ['revert', 7, 'completed']);
      });

      test('a double-tapped Revert is one request, not two', () => {
        assert.strictEqual(calls.filter((c) => c[0] === 'revert').length, 1);
      });

      test('a successful Revert refreshes the dashboard', () => {
        assert.ok(calls.some((c) => c[0] === 'refresh'));
      });

      test('undoing an undo is not offered — the way forward is Advance', () => {
        assert.strictEqual(undoBtn(h.window), null);
      });

      h.DASH.polling.stop();
    }

    // Advance offers an undo that knows where the stop landed
    {
      const h = boot();
      const calls = withRecordedApi(h);
      h.DASH.timeline.render([revertStop({ id: 9, execution_status: 'planned' })], null, null);
      click(h.window, '#timeline [data-action="advance"]');
      await settle(h.window);
      const undo = undoBtn(h.window);
      const text = toastText(h.window);
      if (undo) undo.click();
      await settle(h.window);

      test('an advance offers an Undo in its toast', () => {
        assert.ok(undo, 'no undo action was rendered');
        assert.match(text, /arrived/);
      });

      test('the undo targets the status advancing produced, not the one it left', () => {
        assert.deepStrictEqual(calls.find((c) => c[0] === 'revert'), ['revert', 9, 'arrived']);
      });

      test('the undone toast stops accepting clicks while it fades out', () => {
        // The node lingers ~350ms for the fade; still-clickable means a second
        // impatient tap fires a request at a stop that has already moved.
        assert.strictEqual(undo.closest('.toast').style.pointerEvents, 'none');
      });

      h.DASH.polling.stop();
    }

    // Advancing a stop that was already arrived undoes to completed
    {
      const h = boot();
      const calls = withRecordedApi(h);
      h.DASH.timeline.render([revertStop({ id: 10, execution_status: 'arrived' })], null, null);
      click(h.window, '#timeline [data-action="advance"]');
      await settle(h.window);
      undoBtn(h.window).click();
      await settle(h.window);

      test('undo of the second advance targets completed', () => {
        assert.deepStrictEqual(calls.find((c) => c[0] === 'revert'), ['revert', 10, 'completed']);
      });

      h.DASH.polling.stop();
    }

    // Skip and Cancel get the same treatment
    for (const [action, landed] of [['skip', 'skipped'], ['cancel', 'cancelled']]) {
      const h = boot();
      const calls = withRecordedApi(h);
      h.DASH.timeline.render([revertStop({ id: 11, execution_status: 'planned' })], null, null);
      click(h.window, `#timeline [data-action="${action}"]`);
      h.window.document.querySelector('#timeline [data-reason-input]').value = 'mis-tap';
      click(h.window, '#timeline [data-reason-confirm]');
      await settle(h.window);
      undoBtn(h.window).click();
      await settle(h.window);

      test(`an undone ${action} reverts from '${landed}'`, () => {
        assert.deepStrictEqual(calls.find((c) => c[0] === 'revert'), ['revert', 11, landed]);
      });

      h.DASH.polling.stop();
    }

    // Proof upload + the blocked-completion override
    {
      const h = boot();
      h.DASH.polling.stop();
      await settle(h.window, 5);
      const calls = withRecordedApi(h);

      const uploads = [];
      h.DASH.api.uploadStopImage = (stopId, file, category) => {
        uploads.push([stopId, file && file.name, category]);
        return Promise.resolve({ id: 1 });
      };
      let photoCalls = 0;
      h.DASH.api.stopImages = () => { photoCalls++; return Promise.resolve([]); };

      h.DASH.timeline.render([revertStop({ id: 30, execution_status: 'arrived' })], null, null);

      const input = h.window.document.querySelector('[data-upload-input="30"]');
      const videoInput = h.window.document.querySelector('[data-upload-video-input="30"]');
      const multiInput = h.window.document.querySelector('[data-upload-multi-input="30"]');
      const categoryEl = h.window.document.querySelector('[data-upload-category="30"]');

      test('every stop offers both proof categories, unload first', () => {
        assert.deepStrictEqual(
          Array.from(categoryEl.options).map((o) => o.value), ['unload', 'door']);
      });

      test('the camera input opens the camera on a phone', () => {
        assert.strictEqual(input.getAttribute('capture'), 'environment');
        assert.strictEqual(input.getAttribute('accept'), 'image/*');
      });

      test('the video input is separate and asks for video only', () => {
        // A combined accept="image/*,video/*" with capture makes the browser
        // choose, and it chooses stills — so folding this into the photo
        // button would produce a photo button wearing a video label.
        assert.ok(videoInput, 'no video capture input rendered');
        assert.strictEqual(videoInput.getAttribute('capture'), 'environment');
        assert.strictEqual(videoInput.getAttribute('accept'), 'video/*');
      });

      test('the batch input takes photos and video and does not force the camera', () => {
        // `capture` and `multiple` are mutually exclusive — a browser that
        // honours capture opens the camera for one shot and ignores
        // multiple. If capture ever reappears here, batch selection is dead
        // on exactly the devices this page is used on.
        assert.ok(multiInput, 'no multi-select input rendered');
        assert.ok(multiInput.hasAttribute('multiple'));
        assert.strictEqual(multiInput.hasAttribute('capture'), false);
        assert.strictEqual(multiInput.getAttribute('accept'), 'image/*,video/*');
      });

      // jsdom won't let a real FileList be assigned, so the property is
      // redefined. The handler reads the whole list, not just files[0].
      const setFiles = (el, names) =>
        Object.defineProperty(el, 'files', {
          value: names.map((name) => ({ name })), writable: true, configurable: true,
        });

      setFiles(input, ['door.jpg']);
      categoryEl.value = 'door';
      input.dispatchEvent(new h.window.Event('change'));
      await settle(h.window);

      test('the upload carries the chosen category', () => {
        assert.deepStrictEqual(uploads[0], [30, 'door.jpg', 'door']);
      });

      test('the status line confirms which photo was saved', () => {
        const status = h.window.document.querySelector('[data-upload-status="30"]').textContent;
        assert.match(status, /Locked door/);
      });

      test('the input is cleared so the same file can be retried', () => {
        // Selecting an identical file twice fires no change event otherwise,
        // so a retry after a failure would silently do nothing.
        assert.strictEqual(input.value, '');
      });

      // Open the gallery, then upload again: the panel must not keep showing
      // the set of photos it cached before the new one existed.
      click(h.window, '[data-photos-toggle="30"]');
      await settle(h.window);
      const afterOpen = photoCalls;
      input.dispatchEvent(new h.window.Event('change'));
      await settle(h.window);

      test('an upload refreshes the open photo gallery', () => {
        assert.ok(photoCalls > afterOpen, 'the gallery kept its stale cache');
      });

      // ── A batch of photos in one selection ───────────────────────
      uploads.length = 0;
      const beforeBatch = photoCalls;
      setFiles(multiInput, ['a.jpg', 'b.jpg', 'c.jpg']);
      categoryEl.value = 'unload';
      multiInput.dispatchEvent(new h.window.Event('change'));
      await settle(h.window, 10);

      test('every file in one selection is uploaded', () => {
        assert.deepStrictEqual(uploads, [
          [30, 'a.jpg', 'unload'],
          [30, 'b.jpg', 'unload'],
          [30, 'c.jpg', 'unload'],
        ]);
      });

      test('the batch reports how many landed', () => {
        const status = h.window.document.querySelector('[data-upload-status="30"]').textContent;
        assert.match(status, /3 Unloaded goods files saved/);
      });

      test('a batch refreshes the gallery once, not once per file', () => {
        // Ten photos must not mean ten refetches of the same gallery.
        assert.strictEqual(photoCalls - beforeBatch, 1);
      });

      test('the multi input is cleared after the batch', () => {
        assert.strictEqual(multiInput.value, '');
      });

      // Category is read once, at selection time. A dispatcher who changes
      // the dropdown while a batch is in flight must not split the batch
      // across two categories.
      uploads.length = 0;
      h.DASH.api.uploadStopImage = (stopId, file, category) => {
        uploads.push([stopId, file && file.name, category]);
        categoryEl.value = 'door'; // change it mid-flight
        return Promise.resolve({ id: 1 });
      };
      setFiles(multiInput, ['x.jpg', 'y.jpg']);
      categoryEl.value = 'unload';
      multiInput.dispatchEvent(new h.window.Event('change'));
      await settle(h.window, 10);

      test('a category change mid-batch does not split the batch', () => {
        assert.deepStrictEqual(uploads.map((u) => u[2]), ['unload', 'unload']);
      });

      // ── One bad file in the middle ───────────────────────────────
      uploads.length = 0;
      const toasts = [];
      h.window.UI.toast = (msg, kind) => { toasts.push([msg, kind]); };
      h.DASH.api.uploadStopImage = (stopId, file, category) => {
        uploads.push([stopId, file && file.name, category]);
        return file.name === 'bad.gif'
          ? Promise.reject(new Error("Unsupported file type '.gif'"))
          : Promise.resolve({ id: 1 });
      };
      setFiles(multiInput, ['ok1.jpg', 'bad.gif', 'ok2.jpg']);
      categoryEl.value = 'unload';
      multiInput.dispatchEvent(new h.window.Event('change'));
      await settle(h.window, 10);

      test('one rejected file does not abandon the rest of the batch', () => {
        // Otherwise a dispatcher has no way to tell which of ten photos
        // actually landed, and re-picking all ten duplicates the good ones.
        assert.deepStrictEqual(uploads.map((u) => u[1]), ['ok1.jpg', 'bad.gif', 'ok2.jpg']);
      });

      test('a partial batch says how many failed', () => {
        const status = h.window.document.querySelector('[data-upload-status="30"]').textContent;
        assert.match(status, /2 saved, 1 failed/);
      });

      test('a partial batch surfaces the failure as an error toast', () => {
        assert.ok(toasts.some(([msg, kind]) => kind === 'error' && /gif/.test(msg)),
          'the rejected file was never reported');
      });

      test('every input is re-enabled after a partial batch', () => {
        assert.strictEqual(input.disabled, false);
        assert.strictEqual(videoInput.disabled, false);
        assert.strictEqual(multiInput.disabled, false);
      });

      h.DASH.polling.stop();
    }

    // ── The evidence gallery: video playback and removing a mis-upload ──
    {
      const h = boot();
      h.DASH.polling.stop();
      await settle(h.window, 5);
      withRecordedApi(h);

      let gallery = [
        { id: 7, category: 'unload', media_kind: 'image' },
        { id: 8, category: 'door', media_kind: 'video' },
      ];
      h.DASH.api.stopImages = () => Promise.resolve(gallery.slice());
      const deleted = [];
      h.DASH.api.deleteStopImage = (id) => { deleted.push(id); return Promise.resolve({ ok: true }); };

      const toasts = [];
      h.window.UI.toast = (msg, kind) => { toasts.push([msg, kind]); };

      h.DASH.timeline.render([revertStop({ id: 40, execution_status: 'arrived' })], null, null);
      click(h.window, '[data-photos-toggle="40"]');
      await settle(h.window, 5);

      const photosEl = () => h.window.document.querySelector('[data-photos-for="40"]');

      test('a photo renders as an image', () => {
        assert.ok(photosEl().querySelector('img[src="/api/images/7/file"]'));
      });

      test('a video renders as a video element, not a broken image', () => {
        const video = photosEl().querySelector('video[src="/api/images/8/file"]');
        assert.ok(video, 'video evidence rendered through the image path');
        assert.strictEqual(photosEl().querySelector('img[src="/api/images/8/file"]'), null);
      });

      test('a video thumbnail only preloads metadata', () => {
        // Three 100 MB clips would otherwise be pulled in full the moment the
        // panel opens, over the mobile connection dispatch is on.
        assert.strictEqual(
          photosEl().querySelector('video').getAttribute('preload'), 'metadata');
      });

      test('a video is visibly marked as one', () => {
        // A metadata-preloaded video is a still frame, indistinguishable from
        // a photo without the badge.
        assert.ok(photosEl().querySelector('.timeline-photo-badge'));
      });

      // ── Removing evidence attached to the wrong stop ──────────────
      h.window.confirm = () => false;
      click(h.window, '[data-remove-image="7"]');
      await settle(h.window, 5);

      test('declining the confirmation deletes nothing', () => {
        // This unlinks the file immediately and there is no undo, so a stray
        // tap must not be able to destroy proof of delivery.
        assert.deepStrictEqual(deleted, []);
      });

      h.window.confirm = () => true;
      gallery = [{ id: 8, category: 'door', media_kind: 'video' }];
      click(h.window, '[data-remove-image="7"]');
      await settle(h.window, 5);

      test('confirming removes the mis-uploaded evidence', () => {
        assert.deepStrictEqual(deleted, ['7']);
      });

      test('the gallery repaints without waiting for a poll', () => {
        assert.strictEqual(photosEl().querySelector('[data-remove-image="7"]'), null);
        assert.ok(photosEl().querySelector('[data-remove-image="8"]'));
      });

      // ── A delete the server refuses ──────────────────────────────
      deleted.length = 0;
      toasts.length = 0;
      h.DASH.api.deleteStopImage = () => Promise.reject(new Error('Image not found'));
      click(h.window, '[data-remove-image="8"]');
      await settle(h.window, 5);

      test('a failed delete is reported and the control comes back', () => {
        assert.ok(toasts.some(([msg, kind]) => kind === 'error' && /Image not found/.test(msg)),
          'the failure was swallowed');
        const btn = photosEl().querySelector('[data-remove-image="8"]');
        assert.ok(btn && btn.disabled === false, 'the button stayed disabled after a failure');
      });

      h.DASH.polling.stop();
    }

    // A completion the server refuses for want of photos
    {
      const h = boot();
      h.DASH.polling.stop();
      await settle(h.window, 5);
      const calls = withRecordedApi(h);
      h.DASH.api.advance = (stopId, expectedStatus, overrideReason) => {
        calls.push(['advance', stopId, expectedStatus, overrideReason]);
        if (overrideReason) return Promise.resolve({ ok: true, status: 'completed' });
        const err = new Error('This stop needs a photo of the unloaded goods and the locked door before it can be completed.');
        err.status = 422;
        err.body = { proof_required: true, missing: ['unload', 'door'] };
        return Promise.reject(err);
      };

      h.DASH.timeline.render([revertStop({ id: 31, execution_status: 'arrived' })], null, null);
      click(h.window, '#timeline [data-action="advance"]');
      await settle(h.window, 5);

      const reasonRow = () => h.window.document.querySelector('#timeline [data-reason-for="31"]');

      test('a blocked completion asks for a reason rather than just complaining', () => {
        assert.notStrictEqual(reasonRow().style.display, 'none');
        assert.strictEqual(reasonRow().dataset.pendingAction, 'advance');
      });

      test('the prompt says what it wants', () => {
        assert.match(reasonRow().querySelector('[data-reason-input]').placeholder, /No photo/);
      });

      test('the server’s explanation is surfaced', () => {
        assert.match(toastText(h.window), /locked door/);
      });

      // Confirming with nothing typed must not waive the requirement.
      click(h.window, '#timeline [data-reason-confirm="31"]');
      await settle(h.window);

      test('an empty override is refused before it reaches the server', () => {
        assert.strictEqual(calls.filter((c) => c[0] === 'advance').length, 1);
        assert.match(toastText(h.window), /why there is no photo/);
      });

      reasonRow().querySelector('[data-reason-input]').value = 'phone battery died';
      click(h.window, '#timeline [data-reason-confirm="31"]');
      await settle(h.window);

      test('a typed override completes the stop', () => {
        assert.deepStrictEqual(
          calls.filter((c) => c[0] === 'advance').pop(),
          ['advance', 31, 'arrived', 'phone battery died']);
      });

      test('the override keeps the expected-status guard', () => {
        // Losing the token here would let a stale panel complete a stop that
        // had already moved on.
        assert.strictEqual(calls.filter((c) => c[0] === 'advance').pop()[2], 'arrived');
      });

      h.DASH.polling.stop();
    }

    // The phase history panel
    {
      const h = boot();
      // main.js kicks off an immediate poll on init, which resolves a tick
      // later and re-renders the timeline from the stubbed (empty) stops
      // list — tearing down the nodes these tests just built. Let it land
      // and stop the timer before rendering, so our render is the last word.
      h.DASH.polling.stop();
      await settle(h.window, 5);
      const calls = withRecordedApi(h);
      let history = [
        { id: 1, from_status: 'planned', to_status: 'arrived', action: 'advance', reason: '', occurred_at: '2026-08-01T09:14:00' },
        { id: 2, from_status: 'arrived', to_status: 'completed', action: 'advance', reason: '', occurred_at: '2026-08-01T09:31:00' },
      ];
      let historyCalls = 0;
      h.DASH.api.stopHistory = () => { historyCalls++; return Promise.resolve(history); };

      h.DASH.timeline.render([revertStop({ id: 20, execution_status: 'completed', can_revert: true })], null, null);
      const panel = () => h.window.document.querySelector('#timeline [data-history-for="20"]');

      test('the history panel is closed until asked for', () => {
        assert.strictEqual(panel().style.display, 'none');
        assert.strictEqual(historyCalls, 0, 'history must not be fetched for every stop on every poll');
      });

      click(h.window, '#timeline [data-history-toggle="20"]');
      await settle(h.window);

      test('opening it lists the phase changes in order', () => {
        const rows = panel().querySelectorAll('.timeline-history-row');
        assert.strictEqual(rows.length, 2);
        assert.match(rows[0].textContent, /planned/);
        assert.match(rows[0].textContent, /arrived/);
        assert.match(rows[1].textContent, /completed/);
      });

      test('a revert is labelled as one, not shown as an ordinary move', () => {
        history = history.concat([{
          id: 3, from_status: 'completed', to_status: 'arrived', action: 'revert',
          reason: '', occurred_at: '2026-08-01T09:32:00',
        }]);
        // An action on the stop must refresh the open panel — a log that
        // omits the change you just made is worse than no log.
        click(h.window, '#timeline [data-action="revert"]');
        return null;
      });

      await settle(h.window);

      test('an action on the stop refreshes the open panel', () => {
        assert.ok(historyCalls >= 2, `history was not refetched (${historyCalls} call(s))`);
        const rows = panel().querySelectorAll('.timeline-history-row');
        assert.strictEqual(rows.length, 3);
        assert.match(rows[2].textContent, /reverted/);
      });

      test('the revert itself still went out', () => {
        assert.ok(calls.some((c) => c[0] === 'revert'));
      });

      h.DASH.polling.stop();
    }

    // An empty log says so, and says which kind of empty
    {
      const h = boot();
      h.DASH.polling.stop();
      await settle(h.window, 5);
      withRecordedApi(h);
      h.DASH.api.stopHistory = () => Promise.resolve([]);
      h.DASH.timeline.render([revertStop({ id: 21, execution_status: 'planned' })], null, null);
      click(h.window, '#timeline [data-history-toggle="21"]');
      await settle(h.window);

      test('an empty log reads as empty rather than as a failure', () => {
        const text = h.window.document.querySelector('#timeline [data-history-for="21"]').textContent;
        assert.match(text, /No phase changes recorded/);
      });

      h.DASH.polling.stop();
    }

    // A failing history fetch must not look like an empty one
    {
      const h = boot();
      h.DASH.polling.stop();
      await settle(h.window, 5);
      withRecordedApi(h);
      h.DASH.api.stopHistory = () => Promise.reject(new Error('boom'));
      h.DASH.timeline.render([revertStop({ id: 22, execution_status: 'planned' })], null, null);
      click(h.window, '#timeline [data-history-toggle="22"]');
      await settle(h.window, 5);

      test('a failed history fetch reports the error', () => {
        const text = h.window.document.querySelector('#timeline [data-history-for="22"]').textContent;
        assert.match(text, /Failed to load history: boom/);
      });

      h.DASH.polling.stop();
    }

    // A refused revert must say so rather than look like it worked
    {
      const h = boot();
      withRecordedApi(h, { revertFails: true });
      h.DASH.timeline.render([revertStop({ id: 12, execution_status: 'completed', can_revert: true })], null, null);
      click(h.window, '#timeline [data-action="revert"]');
      await settle(h.window, 5);

      test('a rejected Revert reports the error', () => {
        assert.match(toastText(h.window), /Revert failed: stale/);
      });

      h.DASH.polling.stop();
    }

    // The pinned current-stop card, and retraction on poll
    {
      const h = boot();
      const calls = withRecordedApi(h);
      h.DASH.timeline.render([revertStop({ id: 13, execution_status: 'arrived', can_revert: true })], 13, null);
      const cardBtn = h.window.document.querySelector('#currentStopCard [data-action="revert"]');
      if (cardBtn) cardBtn.click();
      await settle(h.window);

      test('the pinned current-stop card carries Revert too', () => {
        assert.ok(cardBtn, 'no Revert on the current-stop card');
        assert.deepStrictEqual(calls[0], ['revert', 13, 'arrived']);
      });

      h.DASH.timeline.render([revertStop({ id: 13, execution_status: 'completed', can_revert: true })], null, null);
      test('the button is present while the server still allows it', () => {
        assert.ok(actionsOf(h.window, 13).includes('revert'));
      });

      h.DASH.timeline.render([revertStop({ id: 13, execution_status: 'completed', can_revert: false })], null, null);
      test('the poll that reports expiry retracts the button', () => {
        assert.ok(!actionsOf(h.window, 13).includes('revert'));
      });

      h.DASH.polling.stop();
    }
  }

  // ── Report ───────────────────────────────────────────────────
  let failed = 0;
  results.forEach(([ok, name, err]) => {
    if (ok) {
      console.log('  ✓ ' + name);
    } else {
      failed++;
      console.log('  ✗ ' + name);
      console.log('      ' + (err && err.message ? err.message.split('\n')[0] : err));
    }
  });
  console.log(`\n${results.length - failed}/${results.length} passed`);
  process.exit(failed === 0 ? 0 : 1);
})().catch((e) => { console.error(e); process.exit(1); });
