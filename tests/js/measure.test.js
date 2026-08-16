/* ================================================================
 * Dispatch Dashboard — Measure tool, jsdom drives
 * ================================================================
 * Frontend changes get no pytest coverage at all (CLAUDE.md, Definition of
 * Done), so this is the only real verification measure.js gets.
 *
 * This needs its own harness rather than joining dashboard.test.js: that file
 * *stubs* DASH.map, because map.js is the one module that reaches Leaflet.
 * measure.js is built on Leaflet too, so it gets a minimal fake L below and
 * the real template from disk — an id renamed in the HTML but not the JS
 * fails here rather than in production.
 *
 * Run:
 *     npm install jsdom          # once, anywhere on NODE_PATH
 *     node tests/js/measure.test.js
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

// ── Independent distance reference ─────────────────────────────
// Spherical law of cosines, same sphere radius but a different formula from
// the haversine under test. Asserting the module against a copy of its own
// formula would prove nothing; this catches a transcription error in either.
// (It is the numerically unstable one at very short distances, which is
// exactly why haversine is what ships — so the pairs compared here are all
// well clear of that regime.)
const R = 6371000;
const rad = (d) => (d * Math.PI) / 180;
function lawOfCosinesMeters(a, b) {
  return Math.acos(
    Math.sin(rad(a.lat)) * Math.sin(rad(b.lat))
    + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.cos(rad(b.lng) - rad(a.lng))
  ) * R;
}

// ── Minimal Leaflet fake ───────────────────────────────────────
// Only the surface measure.js actually touches. Layers record what was added
// and removed so the tests can assert teardown rather than trusting it.
function makeLeaflet() {
  function Evented() {
    this._handlers = {};
  }
  Evented.prototype.on = function (type, fn) {
    (this._handlers[type] = this._handlers[type] || []).push(fn);
    return this;
  };
  Evented.prototype.fire = function (type, payload) {
    (this._handlers[type] || []).forEach((fn) => fn(payload));
  };

  function Layer(kind, opts) {
    Evented.call(this);
    this.kind = kind;
    this.options = opts || {};
  }
  Layer.prototype = Object.create(Evented.prototype);
  Layer.prototype.addTo = function (group) { group.addLayer(this); return this; };

  const L = {
    divIcon: (opts) => ({ kind: 'divIcon', options: opts }),

    layerGroup() {
      const group = {
        kind: 'layerGroup',
        layers: new Set(),
        addLayer(l) { group.layers.add(l); return group; },
        removeLayer(l) { group.layers.delete(l); return group; },
        addTo(map) { map.addLayer(group); return group; },
        of(kind) { return Array.from(group.layers).filter((l) => l.kind === kind); },
      };
      return group;
    },

    marker(latlng, opts) {
      const m = new Layer('marker', opts);
      m._latlng = { lat: latlng[0], lng: latlng[1] };
      m.icon = opts && opts.icon;
      m.tooltip = null;
      m.getLatLng = () => m._latlng;
      m.setLatLng = (ll) => { m._latlng = { lat: ll[0], lng: ll[1] }; return m; };
      m.setIcon = (icon) => { m.icon = icon; return m; };
      m.bindTooltip = (text, opts2) => { m.tooltip = text; m.tooltipOptions = opts2; return m; };
      m.setTooltipContent = (text) => { m.tooltip = text; return m; };
      return m;
    },

    polyline(coords, opts) {
      const p = new Layer('polyline', opts);
      p.coords = coords;
      return p;
    },

    DomEvent: {
      preventDefault(e) { if (e && e.preventDefault) e.preventDefault(); },
    },
  };
  return L;
}

// ── Harness ────────────────────────────────────────────────────
function boot() {
  let html = fs.readFileSync(path.join(ROOT, 'templates', 'delivery-dashboard.html'), 'utf8');
  html = html.replace(/<script[\s\S]*?<\/script>/g, '');

  const dom = new JSDOM(html, {
    url: 'http://localhost/delivery/dashboard',
    pretendToBeVisual: true,
    runScripts: 'outside-only',
  });
  const { window } = dom;

  const L = makeLeaflet();

  // The Leaflet map itself: an event emitter with a DOM container, which is
  // all measure.js asks of it.
  const container = window.document.getElementById('dashboardMap');
  const map = {
    _handlers: {},
    layers: new Set(),
    on(type, fn) { (map._handlers[type] = map._handlers[type] || []).push(fn); return map; },
    fire(type, payload) { (map._handlers[type] || []).forEach((fn) => fn(payload)); },
    addLayer(l) { map.layers.add(l); return map; },
    getContainer: () => container,
  };

  window.L = L;
  window.DASH = { map: { getMap: () => map } };
  window.eval(JS('dashboard/measure.js'));
  window.DASH.measure.init();

  return { window, document: window.document, map, measure: window.DASH.measure, container };
}

// Gestures, named the way the dispatcher performs them.
const ll = (lat, lng) => ({ lat, lng });
const rightClick = (h, lat, lng) => h.map.fire('contextmenu', { latlng: ll(lat, lng) });
const leftClick = (h, lat, lng) => h.map.fire('click', { latlng: ll(lat, lng) });

function key(h, k, target) {
  const el = target || h.document;
  el.dispatchEvent(new h.window.KeyboardEvent('keydown', { key: k, bubbles: true, cancelable: true }));
}

function readout(h) {
  return h.document.getElementById('measureReadout').textContent;
}

function layerGroup(h) {
  // The single group measure.js created on the map.
  return Array.from(h.map.layers)[0];
}

const pins = (h) => layerGroup(h).of('marker');
const lines = (h) => layerGroup(h).of('polyline');

// Two points in HCMC roughly 10.9 km apart on the same parallel.
const A = ll(10.8231, 106.6297);
const B = ll(10.8231, 106.7297);
const C = ll(10.9231, 106.7297);

// ── Distance math ──────────────────────────────────────────────

test('identical points measure zero', () => {
  const h = boot();
  assert.strictEqual(h.measure.distanceMeters(A, A), 0);
});

test('one degree of longitude at the equator matches the analytic value', () => {
  const h = boot();
  const expected = (R * Math.PI) / 180; // 111194.93 m
  const got = h.measure.distanceMeters(ll(0, 0), ll(0, 1));
  assert.ok(Math.abs(got - expected) < 0.001, `got ${got}, expected ${expected}`);
});

test('equator to pole matches a quarter meridian', () => {
  const h = boot();
  const expected = (R * Math.PI) / 2; // 10007543.4 m
  const got = h.measure.distanceMeters(ll(0, 0), ll(90, 0));
  assert.ok(Math.abs(got - expected) < 0.001, `got ${got}, expected ${expected}`);
});

test('agrees with an independently-derived formula on real coordinates', () => {
  const h = boot();
  [[A, B], [A, C], [B, C], [A, ll(21.0278, 105.8342)]].forEach(([p, q]) => {
    const got = h.measure.distanceMeters(p, q);
    const ref = lawOfCosinesMeters(p, q);
    assert.ok(Math.abs(got - ref) < 0.5, `${JSON.stringify(p)}→${JSON.stringify(q)}: ${got} vs ${ref}`);
  });
});

test('distance is symmetric', () => {
  const h = boot();
  assert.ok(Math.abs(h.measure.distanceMeters(A, C) - h.measure.distanceMeters(C, A)) < 1e-9);
});

// ── Formatting ─────────────────────────────────────────────────

test('under a kilometre reads in whole metres', () => {
  const h = boot();
  assert.strictEqual(h.measure.formatDistance(0), '0 m');
  assert.strictEqual(h.measure.formatDistance(7.4), '7 m');
  assert.strictEqual(h.measure.formatDistance(412.6), '413 m');
  assert.strictEqual(h.measure.formatDistance(999), '999 m');
});

test('one to ten kilometres keeps two decimals', () => {
  const h = boot();
  assert.strictEqual(h.measure.formatDistance(1000), '1.00 km');
  assert.strictEqual(h.measure.formatDistance(2400), '2.40 km');
  assert.strictEqual(h.measure.formatDistance(9999), '10.00 km');
});

test('past ten kilometres drops to one decimal', () => {
  const h = boot();
  assert.strictEqual(h.measure.formatDistance(10000), '10.0 km');
  assert.strictEqual(h.measure.formatDistance(12345), '12.3 km');
});

test('nonsense input formats to nothing rather than NaN', () => {
  const h = boot();
  assert.strictEqual(h.measure.formatDistance(NaN), '');
  assert.strictEqual(h.measure.formatDistance(-5), '');
  assert.strictEqual(h.measure.formatDistance(Infinity), '');
});

// ── Gestures ───────────────────────────────────────────────────

test('the tool is idle until a right-click arms it', () => {
  const h = boot();
  assert.strictEqual(h.measure.isActive(), false);
  assert.strictEqual(h.measure.pointCount(), 0);
});

test('left-clicking while idle drops no pin', () => {
  const h = boot();
  leftClick(h, A.lat, A.lng);
  assert.strictEqual(h.measure.pointCount(), 0);
  assert.strictEqual(h.measure.isActive(), false);
});

test('right-click arms the tool and drops the first pin', () => {
  const h = boot();
  rightClick(h, A.lat, A.lng);
  assert.strictEqual(h.measure.isActive(), true);
  assert.strictEqual(h.measure.pointCount(), 1);
  assert.strictEqual(pins(h).length, 1);
});

test('left-clicks extend the path', () => {
  const h = boot();
  rightClick(h, A.lat, A.lng);
  leftClick(h, B.lat, B.lng);
  leftClick(h, C.lat, C.lng);
  assert.strictEqual(h.measure.pointCount(), 3);
  assert.strictEqual(pins(h).length, 3);
});

test('the total is the sum of the legs, not the straight line end to end', () => {
  const h = boot();
  rightClick(h, A.lat, A.lng);
  leftClick(h, B.lat, B.lng);
  leftClick(h, C.lat, C.lng);

  const expected = h.measure.distanceMeters(A, B) + h.measure.distanceMeters(B, C);
  assert.ok(Math.abs(h.measure.totalMeters() - expected) < 1e-6);
  // A dog-leg is longer than the direct hop it replaces — the assertion that
  // would fail if the total ever collapsed to first-to-last.
  assert.ok(h.measure.totalMeters() > h.measure.distanceMeters(A, C));
});

test('no line is drawn until there are two pins', () => {
  const h = boot();
  rightClick(h, A.lat, A.lng);
  assert.strictEqual(lines(h).length, 0);
  leftClick(h, B.lat, B.lng);
  // Path plus the white casing underneath it.
  assert.strictEqual(lines(h).length, 2);
});

test('the first pin is labelled Start and the rest carry cumulative distance', () => {
  const h = boot();
  rightClick(h, A.lat, A.lng);
  leftClick(h, B.lat, B.lng);
  const labels = pins(h).map((m) => m.tooltip);
  assert.strictEqual(labels[0], 'Start');
  assert.strictEqual(labels[1], h.measure.formatDistance(h.measure.distanceMeters(A, B)));
});

test('dragging a pin recomputes the total', () => {
  const h = boot();
  rightClick(h, A.lat, A.lng);
  leftClick(h, B.lat, B.lng);
  const before = h.measure.totalMeters();

  pins(h)[1].fire('drag', { latlng: C });
  const after = h.measure.totalMeters();

  assert.notStrictEqual(before, after);
  assert.ok(Math.abs(after - h.measure.distanceMeters(A, C)) < 1e-6);
});

// ── Readout ────────────────────────────────────────────────────

test('the readout is hidden until the tool is armed', () => {
  const h = boot();
  assert.strictEqual(h.document.getElementById('measureReadout').style.display, 'none');
});

test('one pin prompts for more rather than showing a total', () => {
  const h = boot();
  rightClick(h, A.lat, A.lng);
  assert.ok(/Click to add points/.test(readout(h)));
  assert.ok(!/km|\d+ m/.test(readout(h)));
});

test('the readout carries the total and the leg count', () => {
  const h = boot();
  rightClick(h, A.lat, A.lng);
  leftClick(h, B.lat, B.lng);
  assert.ok(readout(h).includes(h.measure.formatDistance(h.measure.totalMeters())));
  assert.ok(readout(h).includes('1 leg'), readout(h));

  leftClick(h, C.lat, C.lng);
  assert.ok(readout(h).includes('2 legs'), readout(h));
});

// ── Undo and teardown ──────────────────────────────────────────

test('Backspace removes the last pin only', () => {
  const h = boot();
  rightClick(h, A.lat, A.lng);
  leftClick(h, B.lat, B.lng);
  leftClick(h, C.lat, C.lng);

  key(h, 'Backspace');
  assert.strictEqual(h.measure.pointCount(), 2);
  assert.strictEqual(pins(h).length, 2);
  assert.strictEqual(h.measure.isActive(), true);
});

test('Backspace on the last remaining pin exits the tool', () => {
  const h = boot();
  rightClick(h, A.lat, A.lng);
  key(h, 'Backspace');
  assert.strictEqual(h.measure.pointCount(), 0);
  assert.strictEqual(h.measure.isActive(), false);
});

test('Backspace inside a text field still means backspace', () => {
  const h = boot();
  rightClick(h, A.lat, A.lng);
  leftClick(h, B.lat, B.lng);

  const input = h.document.createElement('input');
  h.document.body.appendChild(input);
  key(h, 'Backspace', input);

  assert.strictEqual(h.measure.pointCount(), 2);
});

test('a second right-click clears everything', () => {
  const h = boot();
  rightClick(h, A.lat, A.lng);
  leftClick(h, B.lat, B.lng);
  rightClick(h, C.lat, C.lng);

  assert.strictEqual(h.measure.isActive(), false);
  assert.strictEqual(h.measure.pointCount(), 0);
  assert.strictEqual(pins(h).length, 0);
  assert.strictEqual(lines(h).length, 0, 'the path and its casing must go too');
});

test('clear() leaves nothing behind on the map', () => {
  const h = boot();
  rightClick(h, A.lat, A.lng);
  leftClick(h, B.lat, B.lng);
  leftClick(h, C.lat, C.lng);
  h.measure.clear();

  assert.strictEqual(layerGroup(h).layers.size, 0);
  assert.strictEqual(h.document.getElementById('measureReadout').style.display, 'none');
});

test('selecting a different vehicle clears the measurement', () => {
  const h = boot();
  rightClick(h, A.lat, A.lng);
  leftClick(h, B.lat, B.lng);

  h.measure.onVehicleChange();
  assert.strictEqual(h.measure.isActive(), false);
  assert.strictEqual(layerGroup(h).layers.size, 0);
});

// ── Toolbar button and mode signalling ─────────────────────────

test('the toolbar button arms the tool for touch, with no pin yet', () => {
  const h = boot();
  h.document.getElementById('measureBtn').click();

  assert.strictEqual(h.measure.isActive(), true);
  assert.strictEqual(h.measure.pointCount(), 0);

  // The touch path: armed first, then the path starts on an ordinary tap.
  leftClick(h, A.lat, A.lng);
  assert.strictEqual(h.measure.pointCount(), 1);
});

test('the button toggles back off', () => {
  const h = boot();
  const btn = h.document.getElementById('measureBtn');
  btn.click();
  btn.click();
  assert.strictEqual(h.measure.isActive(), false);
});

test('armed state is reflected on the button and the map container', () => {
  const h = boot();
  const btn = h.document.getElementById('measureBtn');

  rightClick(h, A.lat, A.lng);
  assert.ok(btn.classList.contains('active'));
  assert.ok(h.container.classList.contains('measuring'), 'crosshair cursor hangs off this class');

  h.measure.clear();
  assert.ok(!btn.classList.contains('active'));
  assert.ok(!h.container.classList.contains('measuring'));
});

test('isActive() is exposed for map.js to gate the imagery popup on', () => {
  // map.js returns early from its click handler while this is true. If the
  // name ever drifts, every measuring click on satellite reopens an Esri
  // popup over the point being measured.
  const h = boot();
  assert.strictEqual(typeof h.measure.isActive, 'function');
  const mapSrc = fs.readFileSync(path.join(ROOT, 'static', 'js', 'dashboard', 'map.js'), 'utf8');
  assert.ok(/DASH\.measure\s*&&\s*DASH\.measure\.isActive\(\)/.test(mapSrc),
    'map.js no longer guards its click handler on DASH.measure.isActive()');
});

test('the template carries the ids the module binds to', () => {
  const h = boot();
  assert.ok(h.document.getElementById('measureBtn'), '#measureBtn missing from the template');
  assert.ok(h.document.getElementById('measureReadout'), '#measureReadout missing from the template');
});

// ── Sharing right-click with street view (2026-08-16) ──────────
// Street view is opened with shift+right-click (map.js). Both handlers are
// bound to the same Leaflet 'contextmenu' event, so without a guard here the
// gesture opens the panel AND arms the ruler — and the dispatcher's next
// left-click, meant for the street view panel, drops a measuring pin instead.

const shiftRightClick = (h, lat, lng) => h.map.fire('contextmenu', {
  latlng: ll(lat, lng),
  originalEvent: { shiftKey: true, preventDefault() {} },
});

test('shift+right-click does not arm the ruler', () => {
  const h = boot();
  shiftRightClick(h, A.lat, A.lng);
  assert.ok(!h.measure.isActive(), 'shift+right-click armed measure mode');
  assert.strictEqual(h.measure.pointCount(), 0, 'shift+right-click dropped a pin');
});

test('plain right-click still arms the ruler', () => {
  // The other half of the pair: a guard that swallowed every contextmenu
  // would pass the test above and silently delete the measure tool.
  const h = boot();
  rightClick(h, A.lat, A.lng);
  assert.ok(h.measure.isActive());
  assert.strictEqual(h.measure.pointCount(), 1);
});

test('shift+right-click during a measurement leaves it intact', () => {
  // The guard is checked before the `active` branch on purpose. If it were
  // after, this gesture would hit the "second right-click clears" path and
  // throw away a half-finished measurement on the way to opening street view.
  const h = boot();
  rightClick(h, A.lat, A.lng);
  leftClick(h, B.lat, B.lng);
  assert.strictEqual(h.measure.pointCount(), 2);

  shiftRightClick(h, C.lat, C.lng);

  assert.ok(h.measure.isActive(), 'measurement was cancelled by shift+right-click');
  assert.strictEqual(h.measure.pointCount(), 2, 'pins were discarded or added');
});

test('map.js opens street view on shift+right-click and only then', () => {
  // Guards the other side of the contract from measure.js's test harness,
  // which does not load map.js. A shiftKey check dropped from map.js would
  // leave the button working and the gesture silently dead.
  const mapSrc = fs.readFileSync(path.join(ROOT, 'static', 'js', 'dashboard', 'map.js'), 'utf8');
  assert.ok(/contextmenu/.test(mapSrc), 'map.js binds no contextmenu handler');
  assert.ok(/shiftKey/.test(mapSrc), 'map.js no longer tests shiftKey');
  assert.ok(/DASH\.streetview/.test(mapSrc), 'map.js no longer calls into DASH.streetview');
});

// ── Report ─────────────────────────────────────────────────────
let failed = 0;
results.forEach(([ok, name, err]) => {
  if (ok) {
    console.log(`  ok   ${name}`);
  } else {
    failed++;
    console.log(`  FAIL ${name}`);
    console.log(`       ${err && err.message}`);
  }
});
console.log(`\n${results.length - failed}/${results.length} passed`);
process.exit(failed ? 1 : 0);
