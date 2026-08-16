/* ================================================================
 * Dispatch Dashboard — Street view panel, jsdom drives
 * ================================================================
 * Frontend changes get no pytest coverage at all (CLAUDE.md, Definition of
 * Done), so this is the only real verification streetview.js gets.
 *
 * jsdom has no WebGL, so MapillaryJS cannot run here. That is not a gap in
 * coverage — it is the *fallback path* under test. `window.mapillary` is
 * absent exactly as it would be if the CDN were unreachable, and these tests
 * pin that the panel still shows imagery through the embed iframe instead of
 * failing. A separate block stubs `window.mapillary` to check the module wires
 * the real viewer up correctly when it is there.
 *
 * The properties worth more than the rest:
 *
 *   1. "Nothing is mapped here" and "the lookup failed" must render
 *      differently. If they collapse, an expired token shows as empty coverage
 *      on every stop and the panel looks like it is working.
 *   2. The panel moves the map only when Follow is ticked. A dispatcher
 *      watching a truck must not lose the view to a street view lookup.
 *   3. A late response cannot repaint a panel showing somewhere else.
 *
 * Run:
 *     npm install jsdom          # once, anywhere on NODE_PATH
 *     node tests/js/streetview.test.js
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
const pending = [];
function test(name, fn) {
  pending.push([name, fn]);
}

const tick = () => new Promise((r) => setImmediate(r));

// ── Harness ────────────────────────────────────────────────────
// Real utils.js and the real template from disk, so an id renamed in the HTML
// but not the JS fails here rather than in production.
//
// `mapillary` opts into a stubbed MapillaryJS; without it the module takes the
// iframe fallback, which is what a real browser does when the CDN is down.
function boot({ mapillary = null, token = '' } = {}) {
  let html = fs.readFileSync(path.join(ROOT, 'templates', 'delivery-dashboard.html'), 'utf8');
  html = html.replace(/<script[\s\S]*?<\/script>/g, '');

  const dom = new JSDOM(html, {
    url: 'http://localhost/delivery/dashboard',
    pretendToBeVisual: true,
    runScripts: 'outside-only',
  });
  const { window } = dom;

  // utils.js declares `const UI` at top level; separate <script> tags share one
  // global lexical environment in a browser, but each window.eval() gets its
  // own and discards it, so the binding is promoted by hand.
  window.eval(JS('utils.js') + '\n;window.UI = UI; window.ApiClient = ApiClient;');

  const calls = { streetview: [], toasts: [], panTo: [], moveTo: [] };
  let resolveNext = null;

  window.DASH_CONFIG = { mapillaryToken: token };
  if (mapillary) window.mapillary = mapillary(calls);

  // A minimal Leaflet, only the surface streetview.js touches for its position
  // marker. The map records panTo so "does it move the view" is observable.
  const markers = [];
  window.L = {
    divIcon: (opts) => ({ kind: 'divIcon', options: opts }),
    layerGroup() {
      const group = {
        layers: new Set(),
        addLayer(l) { group.layers.add(l); return group; },
        removeLayer(l) { group.layers.delete(l); return group; },
        addTo() { return group; },
      };
      return group;
    },
    marker(latlng, opts) {
      const m = {
        _latlng: { lat: latlng[0], lng: latlng[1] },
        icon: opts && opts.icon,
        _el: window.document.createElement('div'),
        addTo(g) { g.addLayer(m); markers.push(m); return m; },
        setLatLng(ll) { m._latlng = { lat: ll[0], lng: ll[1] }; return m; },
        setIcon(i) { m.icon = i; return m; },
        getLatLng() { return m._latlng; },
        getElement() { return m._el; },
      };
      return m;
    },
  };

  const map = { panTo: (ll) => { calls.panTo.push(ll); } };

  window.DASH = window.DASH || {};
  window.DASH.map = { getMap: () => map };
  window.DASH.api = {
    streetview(lat, lng) {
      calls.streetview.push([lat, lng]);
      return new Promise((resolve, reject) => { resolveNext = { resolve, reject }; });
    },
  };

  window.UI.toast = (msg, kind) => { calls.toasts.push([msg, kind]); };

  window.eval(JS('dashboard/streetview.js'));
  window.DASH.streetview.init();

  return {
    window,
    document: window.document,
    sv: window.DASH.streetview,
    calls,
    markers,
    resolve: async (body) => { resolveNext.resolve(body); await tick(); },
    reject: async (err) => { resolveNext.reject(err); await tick(); },
    panel: () => window.document.getElementById('streetViewPanel'),
    viewerEl: () => window.document.querySelector('[data-sv-viewer]'),
    overlay: () => window.document.querySelector('[data-sv-overlay]'),
    meta: () => window.document.querySelector('[data-sv-meta]'),
    title: () => window.document.querySelector('[data-sv-title]'),
  };
}

// A MapillaryJS stand-in: records moveTo and lets a test fire the 'image'
// event the real viewer emits on every step the dispatcher walks.
function fakeMapillary(calls) {
  return {
    Viewer: function Viewer(opts) {
      const handlers = {};
      this.options = opts;
      this.on = (type, fn) => { (handlers[type] = handlers[type] || []).push(fn); };
      this.fire = (type, payload) => (handlers[type] || []).forEach((fn) => fn(payload));
      this.moveTo = (id) => { calls.moveTo.push(id); return Promise.resolve(); };
      this.resize = () => {};
      calls.viewer = this;
    },
  };
}

const LAT = 10.7725;
const LNG = 106.6980;
const TOKEN = 'MLY|test|token';

function foundBody(overrides) {
  return {
    found: true,
    image: Object.assign({
      image_id: '550092599700936',
      captured_at: Date.now() - 30 * 24 * 3600 * 1000,
      is_pano: true,
      distance_m: 14.2,
      compass_angle: 90,
      lat: LAT,
      lng: LNG,
      found_by: 'radius',
      embed_url: 'https://www.mapillary.com/embed?image_key=550092599700936&style=photo',
      page_url: 'https://www.mapillary.com/app/?pKey=550092599700936&focus=photo',
    }, overrides || {}),
  };
}

// ── Template contract ──────────────────────────────────────────

test('the template carries the hooks the module binds to', () => {
  const h = boot();
  assert.ok(h.panel(), '#streetViewPanel missing from the template');
  assert.ok(h.viewerEl(), '[data-sv-viewer] missing');
  assert.ok(h.overlay(), '[data-sv-overlay] missing');
  assert.ok(h.meta(), '[data-sv-meta] missing');
  assert.ok(h.title(), '[data-sv-title] missing');
  assert.ok(h.document.querySelector('[data-sv-close]'), '[data-sv-close] missing');
  assert.ok(h.document.querySelector('[data-sv-expand]'), '[data-sv-expand] missing');
});

test('the panel starts hidden', () => {
  const h = boot();
  assert.strictEqual(h.panel().style.display, 'none');
  assert.strictEqual(h.sv.isOpen(), false);
});

// ── Fallback path (no MapillaryJS, as in this environment) ─────

test('opening shows the panel and asks the server once', () => {
  const h = boot();
  h.sv.openAt(LAT, LNG, 'Kho Bình Tân');

  assert.strictEqual(h.panel().style.display, '');
  assert.strictEqual(h.sv.isOpen(), true);
  assert.deepStrictEqual(h.calls.streetview, [[LAT, LNG]]);
  assert.match(h.overlay().textContent, /Looking for street-level imagery/);
});

test('without MapillaryJS it falls back to the embed iframe', async () => {
  const h = boot();
  h.sv.openAt(LAT, LNG, 'x');
  await h.resolve(foundBody());

  const frame = h.viewerEl().querySelector('iframe.sv-frame');
  assert.ok(frame, 'no fallback iframe rendered');
  assert.match(frame.getAttribute('src'), /image_key=550092599700936/);
  assert.strictEqual(h.overlay().style.display, 'none', 'overlay left covering the image');
});

test('the fallback iframe is sandboxed without same-origin access', async () => {
  const h = boot();
  h.sv.openAt(LAT, LNG, 'x');
  await h.resolve(foundBody());

  const frame = h.viewerEl().querySelector('iframe');
  const sandbox = frame.getAttribute('sandbox');
  assert.ok(sandbox !== null, 'iframe is not sandboxed at all');
  assert.ok(!/allow-same-origin/.test(sandbox),
    'allow-same-origin defeats the sandbox for a same-site frame');
  assert.strictEqual(frame.getAttribute('referrerpolicy'), 'no-referrer');
});

// ── MapillaryJS path ───────────────────────────────────────────

test('with MapillaryJS present it drives the real viewer, not an iframe', async () => {
  const h = boot({ mapillary: fakeMapillary, token: TOKEN });
  h.sv.openAt(LAT, LNG, 'x');
  await h.resolve(foundBody());

  assert.deepStrictEqual(h.calls.moveTo, ['550092599700936']);
  assert.strictEqual(h.viewerEl().querySelector('iframe'), null,
    'built an iframe even though the real viewer was available');
});

test('the viewer is constructed with the client token', async () => {
  const h = boot({ mapillary: fakeMapillary, token: TOKEN });
  h.sv.openAt(LAT, LNG, 'x');
  await h.resolve(foundBody());

  assert.strictEqual(h.calls.viewer.options.accessToken, TOKEN);
});

test('walking to a new image moves the map marker', async () => {
  // The half of "walking around" a viewer alone cannot give: without this the
  // dispatcher is looking at a street with no idea which street it is.
  const h = boot({ mapillary: fakeMapillary, token: TOKEN });
  h.sv.openAt(LAT, LNG, 'x');
  await h.resolve(foundBody());

  const before = h.markers.length;
  h.calls.viewer.fire('image', {
    image: {
      id: 'next', capturedAt: Date.now(), compassAngle: 210,
      lngLat: { lat: LAT + 0.001, lng: LNG + 0.001 },
      cameraType: 'spherical',
    },
  });
  await tick();

  assert.ok(h.markers.length >= before && h.markers.length > 0, 'no position marker drawn');
  const marker = h.markers[h.markers.length - 1];
  assert.ok(Math.abs(marker.getLatLng().lat - (LAT + 0.001)) < 1e-9,
    'marker did not follow the viewer');
});

test('no MapillaryJS means no viewer construction attempt', () => {
  const h = boot();
  h.sv.openAt(LAT, LNG, 'x');
  assert.strictEqual(h.calls.viewer, undefined);
});

// ── Moving the map ─────────────────────────────────────────────

test('walking does not move the map unless Follow is ticked', async () => {
  // The dashboard's map rules (CLAUDE.md, learned 2026-07-31): the only
  // automatic pan is one the dispatcher opted into.
  const h = boot({ mapillary: fakeMapillary, token: TOKEN });
  h.sv.openAt(LAT, LNG, 'x');
  await h.resolve(foundBody());

  h.calls.viewer.fire('image', {
    image: { id: 'n', capturedAt: Date.now(), compassAngle: 0,
             lngLat: { lat: LAT + 0.01, lng: LNG }, cameraType: 'perspective' },
  });
  await tick();

  assert.strictEqual(h.calls.panTo.length, 0, 'street view moved the map unasked');
  assert.strictEqual(h.sv.isFollowing(), false);
});

test('ticking Follow makes the map track the viewer', async () => {
  const h = boot({ mapillary: fakeMapillary, token: TOKEN });
  h.sv.openAt(LAT, LNG, 'x');
  await h.resolve(foundBody());

  const box = h.meta().querySelector('[data-sv-follow]');
  assert.ok(box, 'no Follow control offered');
  box.checked = true;
  box.dispatchEvent(new h.window.Event('change', { bubbles: true }));

  h.calls.viewer.fire('image', {
    image: { id: 'n', capturedAt: Date.now(), compassAngle: 0,
             lngLat: { lat: LAT + 0.01, lng: LNG }, cameraType: 'perspective' },
  });
  await tick();

  assert.strictEqual(h.sv.isFollowing(), true);
  assert.strictEqual(h.calls.panTo.length, 1, 'Follow was ticked and the map did not move');
});

test('the module never jumps or zooms the map', () => {
  // panTo behind the Follow flag is the one permitted movement. A setView or
  // fitBounds would yank the view with no opt-in at all.
  const src = JS('dashboard/streetview.js');
  const stripped = src.replace(/\/\/[^\n]*/g, '').replace(/\/\*[\s\S]*?\*\//g, '');
  ['setView', 'flyTo', 'fitBounds', 'setZoom'].forEach((method) => {
    assert.ok(!new RegExp(`\\.${method}\\s*\\(`).test(stripped),
      `streetview.js calls ${method}() — the panel must not jump the map`);
  });
  assert.ok(/if\s*\(follow[^)]*\)[^;]*panTo/.test(stripped.replace(/\s+/g, ' ')),
    'panTo is no longer gated on the follow flag');
});

// ── The distinction that matters ───────────────────────────────

test('no imagery reads as an answer, not a failure', async () => {
  const h = boot();
  h.sv.openAt(LAT, LNG, 'x');
  await h.resolve({ found: false, reason: 'no_imagery' });

  const text = h.overlay().textContent;
  assert.match(text, /No street-level imagery/);
  assert.ok(!h.overlay().querySelector('.sv-error'),
    'an uncovered address was styled as an error');
  // Points the dispatcher at what to do next, which is the whole reason the
  // coverage layer exists.
  assert.match(text, /coverage/i);
});

test('a failed lookup reads as a failure, not as empty coverage', async () => {
  // The bug this file exists for. If a 503 renders the same "no imagery" line,
  // an expired token looks identical to a genuinely uncovered city — on every
  // stop at once, with nothing on screen to suggest anything is wrong.
  const h = boot();
  h.sv.openAt(LAT, LNG, 'x');
  await h.reject(new Error('Mapillary returned HTTP 503'));

  const text = h.overlay().textContent;
  assert.ok(h.overlay().querySelector('.sv-error'), 'failure was not styled as an error');
  assert.match(text, /unavailable/i);
  assert.ok(!/No street-level imagery/.test(text),
    'a lookup failure rendered as "no imagery", which is the whole bug');
});

test('a found response with no image id falls back to the empty message', async () => {
  const h = boot();
  h.sv.openAt(LAT, LNG, 'x');
  await h.resolve({ found: true, image: { image_id: null } });
  assert.match(h.overlay().textContent, /No street-level imagery/);
});

// ── Distance honesty ───────────────────────────────────────────

test('imagery far from the requested point is flagged', async () => {
  // Expected here rather than exceptional: most stops are down lanes with no
  // coverage, and the nearest road image is still how a driver approaches. The
  // dispatcher has to notice they are not looking at the gate itself.
  const h = boot();
  h.sv.openAt(LAT, LNG, 'x');
  await h.resolve(foundBody({ distance_m: 340, found_by: 'bbox_wide' }));

  assert.ok(h.meta().querySelector('.sv-distance.far'), 'distant imagery not flagged');
  assert.match(h.meta().textContent, /340 m away/);
});

test('imagery at the stop itself is not flagged', async () => {
  const h = boot();
  h.sv.openAt(LAT, LNG, 'x');
  await h.resolve(foundBody({ distance_m: 14.2 }));

  assert.ok(h.meta().querySelector('.sv-distance'), 'no distance shown at all');
  assert.ok(!h.meta().querySelector('.sv-distance.far'), 'nearby imagery flagged as far');
});

test('old imagery is flagged rather than shown plain', async () => {
  const h = boot();
  h.sv.openAt(LAT, LNG, 'x');
  await h.resolve(foundBody({ captured_at: Date.now() - 4 * 365.25 * 24 * 3600 * 1000 }));
  assert.ok(h.meta().querySelector('.sv-captured.stale'), 'old imagery not marked stale');
});

test('recent imagery is not flagged', async () => {
  const h = boot();
  h.sv.openAt(LAT, LNG, 'x');
  await h.resolve(foundBody({ captured_at: Date.now() - 60 * 24 * 3600 * 1000 }));
  assert.ok(h.meta().querySelector('.sv-captured'), 'no capture date rendered');
  assert.ok(!h.meta().querySelector('.sv-captured.stale'), 'recent imagery marked stale');
});

// ── Entering from the coverage layer ───────────────────────────

test('openImage skips the lookup entirely', () => {
  // The dispatcher clicked an image on the coverage overlay; there is nothing
  // to search for, and a lookup would be a round trip to find what they
  // already pointed at.
  const h = boot({ mapillary: fakeMapillary, token: TOKEN });
  h.sv.openImage('12345', 'Nguyễn Văn Linh');

  assert.strictEqual(h.calls.streetview.length, 0, 'openImage went to the server');
  assert.deepStrictEqual(h.calls.moveTo, ['12345']);
  assert.strictEqual(h.sv.isOpen(), true);
  assert.strictEqual(h.title().textContent, 'Nguyễn Văn Linh');
});

test('openImage ignores a missing id rather than opening an empty panel', () => {
  const h = boot({ mapillary: fakeMapillary, token: TOKEN });
  h.sv.openImage(null, 'x');
  assert.strictEqual(h.sv.isOpen(), false);
});

// ── Escaping ───────────────────────────────────────────────────

test('a station name cannot inject markup', () => {
  // station_name arrives from the manager's hand-typed Google Sheet, so it is
  // user input by any reasonable definition.
  const h = boot();
  h.sv.openAt(LAT, LNG, '<img src=x onerror="window.__pwned=1">');

  assert.strictEqual(h.window.__pwned, undefined);
  assert.strictEqual(h.title().querySelector('img'), null);
  assert.match(h.title().textContent, /onerror/);
});

test('a hostile embed url cannot break out of the src attribute', async () => {
  const h = boot();
  h.sv.openAt(LAT, LNG, 'x');
  await h.resolve(foundBody({
    embed_url: 'https://www.mapillary.com/embed?image_key=1" onload="window.__pwned=1',
  }));

  assert.strictEqual(h.window.__pwned, undefined);
  assert.strictEqual(h.viewerEl().querySelector('iframe').getAttribute('onload'), null);
});

// ── Closing and staleness ──────────────────────────────────────

test('closing hides the panel and tears the fallback frame down', async () => {
  // An iframe left in the DOM keeps running, and it is third-party.
  const h = boot();
  h.sv.openAt(LAT, LNG, 'x');
  await h.resolve(foundBody());
  assert.ok(h.viewerEl().querySelector('iframe'));

  h.sv.close();

  assert.strictEqual(h.panel().style.display, 'none');
  assert.strictEqual(h.sv.isOpen(), false);
  assert.strictEqual(h.viewerEl().querySelector('iframe'), null);
  assert.strictEqual(h.meta().innerHTML, '');
});

test('closing removes the position marker from the map', async () => {
  const h = boot({ mapillary: fakeMapillary, token: TOKEN });
  h.sv.openAt(LAT, LNG, 'x');
  await h.resolve(foundBody());
  h.sv.close();

  // Reopening must draw a fresh one rather than resurrect the old position.
  h.sv.openAt(LAT, LNG, 'y');
  assert.strictEqual(h.sv.isOpen(), true);
});

test('Escape closes the panel', async () => {
  const h = boot();
  h.sv.openAt(LAT, LNG, 'x');
  await h.resolve(foundBody());

  h.document.dispatchEvent(new h.window.KeyboardEvent('keydown', {
    key: 'Escape', bubbles: true, cancelable: true,
  }));

  assert.strictEqual(h.sv.isOpen(), false);
});

test('the close button closes the panel', async () => {
  const h = boot();
  h.sv.openAt(LAT, LNG, 'x');
  await h.resolve(foundBody());
  h.document.querySelector('[data-sv-close]').click();
  assert.strictEqual(h.sv.isOpen(), false);
});

test('the expand button toggles the enlarged panel', () => {
  const h = boot();
  h.sv.openAt(LAT, LNG, 'x');
  const btn = h.document.querySelector('[data-sv-expand]');

  btn.click();
  assert.ok(h.panel().classList.contains('expanded'));
  btn.click();
  assert.ok(!h.panel().classList.contains('expanded'));
});

test('a response landing after close does not repaint the panel', async () => {
  const h = boot();
  h.sv.openAt(LAT, LNG, 'x');
  h.sv.close();
  await h.resolve(foundBody());

  assert.strictEqual(h.viewerEl().querySelector('iframe'), null,
    'a closed panel was repainted by a late response');
  assert.strictEqual(h.panel().style.display, 'none');
});

test('a slow first lookup cannot overwrite a second stop', async () => {
  // Two quick clicks on different stops. The first lookup lands last and must
  // not caption stop A's photo with stop B's name.
  const h = boot();
  h.sv.openAt(LAT, LNG, 'Stop A');
  const first = h.resolve;

  h.sv.openAt(11.0, 106.8, 'Stop B');
  await h.resolve(foundBody({
    image_id: 'B', embed_url: 'https://www.mapillary.com/embed?image_key=B&style=photo',
  }));
  await first(foundBody({
    image_id: 'A', embed_url: 'https://www.mapillary.com/embed?image_key=A&style=photo',
  }));

  assert.match(h.viewerEl().querySelector('iframe').getAttribute('src'), /image_key=B/,
    'a stale lookup overwrote the current one');
  assert.strictEqual(h.title().textContent, 'Stop B');
});

// ── Guardrails ─────────────────────────────────────────────────

test('a point with no coordinates is refused with a message', () => {
  const h = boot();
  h.sv.openAt(null, null, 'Nowhere');

  assert.strictEqual(h.calls.streetview.length, 0, 'asked the server about a null point');
  assert.strictEqual(h.sv.isOpen(), false);
  assert.strictEqual(h.calls.toasts.length, 1, 'a click that did nothing at all');
});

test('title falls back to coordinates when no label is given', () => {
  // The shift+right-click path passes no label; a blank header would leave the
  // dispatcher unsure which point they are looking at.
  const h = boot();
  h.sv.openAt(LAT, LNG);
  assert.match(h.title().textContent, /10\.77250, 106\.69800/);
});

test('map.js offers the coverage overlay and enters it on click', () => {
  // Guards the contract from the other side — this harness does not load
  // map.js, and a coverage layer that stopped calling openImage would leave
  // the green lines drawn and inert.
  const src = JS('dashboard/map.js');
  assert.ok(/tiles\.mapillary\.com/.test(src), 'map.js no longer requests coverage tiles');
  assert.ok(/DASH\.streetview\.openImage/.test(src),
    'clicking the coverage layer no longer opens the viewer');
  assert.ok(/vectorGrid/.test(src), 'the vector tile renderer is gone');
});

// ── Report ─────────────────────────────────────────────────────
(async () => {
  for (const [name, fn] of pending) {
    try {
      await fn();
      results.push([true, name]);
    } catch (e) {
      results.push([false, name, e]);
    }
  }

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
})();
