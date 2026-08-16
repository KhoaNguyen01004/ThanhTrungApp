/* ================================================================
 * End of Day export page — jsdom drives
 * ================================================================
 * Frontend changes get no pytest coverage at all (CLAUDE.md, Definition of
 * Done). delivery-export.js is a closed IIFE with no exports, so everything
 * here goes through the DOM as the operator would: pick a driver, choose
 * files, and read the multipart body that was actually put on the wire.
 *
 * Written for the 2026-08-10 change that split loading photos per driver.
 * The server side of that is covered by test_delivery_routes.py; what only a
 * jsdom drive can catch is the half that lives in the browser — whether the
 * picker is populated at all, and whether its value reaches the POST. The
 * plan-builder bug this pattern was invented for was exactly that shape: a
 * value captured and rendered correctly, then simply left out of the request.
 *
 * Run:
 *     npm install jsdom          # once, anywhere on NODE_PATH
 *     node tests/js/export.test.js
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
function test(name, fn) { pending.push([name, fn]); }

async function run() {
  for (const [name, fn] of pending) {
    try { await fn(); results.push([true, name]); }
    catch (e) { results.push([false, name, e]); }
  }
  let failed = 0;
  for (const [ok, name, err] of results) {
    if (ok) { console.log('  ✓ ' + name); }
    else {
      failed++;
      console.log('  ✗ ' + name);
      console.log('      ' + String((err && err.message) || err).split('\n').join('\n      '));
    }
  }
  console.log(`\n${results.length - failed}/${results.length} passed`);
  process.exit(failed ? 1 : 0);
}

// ── Harness ────────────────────────────────────────────────────
// Two drivers, because one driver hides every folder-vs-name mix-up: with a
// single option a picker that never got populated still "works".
const SUMMARY = {
  stop_count: 2,
  incomplete_count: 0,
  drivers: [
    {
      folder: 'OriginalDriver_18463',
      driver_name: 'Original Driver',
      stops: [{ stop_id: 1, station_code: 'S1', missing: [], override_reason: '' }],
    },
    {
      folder: 'HuynhQuocTrong_79791',
      driver_name: 'Huỳnh Quốc Trọng',
      stops: [{ stop_id: 2, station_code: 'S2', missing: [], override_reason: '' }],
    },
  ],
  day_images: { loading: [], empty_container: [] },
};

function boot({ summary = SUMMARY } = {}) {
  let html = fs.readFileSync(path.join(ROOT, 'templates', 'delivery-export.html'), 'utf8');
  html = html.replace(/<script[\s\S]*?<\/script>/g, '');

  const dom = new JSDOM(html, {
    url: 'http://localhost/delivery/export',
    pretendToBeVisual: true,
    runScripts: 'outside-only',
  });
  const { window } = dom;
  global.window = window;
  global.document = window.document;
  global.localStorage = window.localStorage;

  const requests = [];
  window.fetch = async (url, opts) => {
    opts = opts || {};
    const method = (opts.method || 'GET').toUpperCase();
    requests.push({ url: String(url), method, body: opts.body });
    const payload = String(url).startsWith('/api/export/summary')
      ? summary
      : { id: 1 };
    return {
      ok: true, status: 200,
      json: async () => payload,
      text: async () => JSON.stringify(payload),
    };
  };

  window.eval(JS('utils.js') + '\n;window.UI = UI; window.ApiClient = ApiClient;');
  window.eval(JS('delivery-export.js'));

  // No manual DOMContentLoaded dispatch here, deliberately. `new JSDOM(html)`
  // leaves readyState at 'loading' and fires its own DOMContentLoaded a tick
  // later — after this eval — so dispatching one as well boots the page twice:
  // two listeners, two loadSummary() calls, and every later upload counted
  // double. That reads as a duplicate-request bug in the page under test and
  // is not one. The first `await flush()` in each test lets the real event
  // arrive.
  return { window, requests };
}

/** Drain the microtask/timer queue: each action chains fetch → json → render. */
async function flush(turns = 12) {
  for (let i = 0; i < turns; i++) await new Promise((r) => setTimeout(r, 0));
}
const $ = (w, id) => w.document.getElementById(id);

/** Choose files on a hidden <input type=file>, as the Add photos label does.
 *  jsdom's `files` is read-only, so it is redefined rather than assigned. */
function chooseFiles(w, inputId, names) {
  const input = $(w, inputId);
  const files = names.map((n) => new w.File(['bytes'], n, { type: 'image/jpeg' }));
  Object.defineProperty(input, 'files', { value: files, configurable: true });
  input.dispatchEvent(new w.Event('change', { bubbles: true }));
}

/** Make `el.innerHTML = …` reset scrollTop, the way a browser does.
 *
 *  jsdom has no layout: nothing is ever actually scrollable, `scrollTop` is a
 *  plain stored number, and replacing innerHTML leaves it untouched. A scroll
 *  test written against that passes whether or not the code preserves anything
 *  — verified by deleting the restore line and watching it stay green. So the
 *  one browser behaviour under test is emulated here rather than assumed.
 */
function resetsScrollOnRerender(w, el) {
  const desc = Object.getOwnPropertyDescriptor(w.Element.prototype, 'innerHTML');
  Object.defineProperty(el, 'innerHTML', {
    configurable: true,
    get() { return desc.get.call(this); },
    set(v) { desc.set.call(this, v); this.scrollTop = 0; },
  });
}

function uploadsOf(requests) {
  return requests.filter((r) => r.url === '/api/export/day-images' && r.method === 'POST');
}

// ── Tests ──────────────────────────────────────────────────────

test('the loading picker is populated with every driver', async () => {
  const { window } = boot();
  await flush();

  const options = Array.from($(window, 'loadingDriver').options);
  assert.deepStrictEqual(options.map((o) => o.value),
    ['OriginalDriver_18463', 'HuynhQuocTrong_79791']);
});

test('the loading picker offers folder names, the container picker driver names', async () => {
  // Not cosmetic. The loading label becomes a *folder* that has to match the
  // driver's HinhGiaoHang folder; the container label becomes a *filename*
  // prefix, where the human name is what reads well.
  const { window } = boot();
  await flush();

  assert.strictEqual($(window, 'loadingDriver').value, 'OriginalDriver_18463');
  assert.strictEqual($(window, 'containerDriver').value, 'Original Driver');
});

test('a loading upload carries the selected driver as its label', async () => {
  const { window, requests } = boot();
  await flush();

  $(window, 'loadingDriver').value = 'HuynhQuocTrong_79791';
  chooseFiles(window, 'loadingInput', ['pallet.jpg']);
  await flush();

  const [upload] = uploadsOf(requests);
  assert.ok(upload, 'no upload was sent');
  assert.strictEqual(upload.body.get('category'), 'loading');
  assert.strictEqual(upload.body.get('label'), 'HuynhQuocTrong_79791');
});

test('every file in one selection carries the same driver', async () => {
  const { window, requests } = boot();
  await flush();

  $(window, 'loadingDriver').value = 'OriginalDriver_18463';
  chooseFiles(window, 'loadingInput', ['a.jpg', 'b.jpg', 'c.jpg']);
  await flush(30);

  const labels = uploadsOf(requests).map((r) => r.body.get('label'));
  assert.deepStrictEqual(labels,
    ['OriginalDriver_18463', 'OriginalDriver_18463', 'OriginalDriver_18463']);
});

test('the container upload is unchanged and still sends the human name', async () => {
  const { window, requests } = boot();
  await flush();

  $(window, 'containerDriver').value = 'Huỳnh Quốc Trọng';
  chooseFiles(window, 'containerInput', ['truck.jpg']);
  await flush();

  const [upload] = uploadsOf(requests);
  assert.strictEqual(upload.body.get('category'), 'empty_container');
  assert.strictEqual(upload.body.get('label'), 'Huỳnh Quốc Trọng');
});

test('the structure preview nests both photo folders under each driver', async () => {
  const { window } = boot();
  await flush();

  const lines = $(window, 'structurePreview').textContent.split('\n');
  const i = lines.indexOf('  OriginalDriver_18463/');
  assert.ok(i >= 0, lines.join('\n'));
  assert.ok(lines[i + 1].startsWith('    HinhNhanHang_'), lines[i + 1]);
  assert.ok(lines[i + 2].startsWith('    HinhGiaoHang_'), lines[i + 2]);
  assert.strictEqual(lines[i + 3], '      S1/');
  // The second driver starts a fresh block rather than continuing the first.
  assert.strictEqual(lines[i + 4], '  HuynhQuocTrong_79791/');
});

test('the structure preview ends with the container folder and the manifest', async () => {
  const { window } = boot();
  await flush();

  const lines = $(window, 'structurePreview').textContent.split('\n');
  assert.deepStrictEqual(lines.slice(-2), ['  HinhThungTrong/', '  manifest.xlsx']);
});

test('an uploaded loading photo is listed with its driver', async () => {
  const withPhoto = JSON.parse(JSON.stringify(SUMMARY));
  withPhoto.day_images.loading = [
    { id: 9, label: 'OriginalDriver_18463', original_filename: 'pallet.jpg', filename: 'x.jpg' },
  ];
  const { window } = boot({ summary: withPhoto });
  await flush();

  const text = $(window, 'loadingList').textContent;
  assert.ok(text.includes('OriginalDriver_18463'), text);
  assert.ok(text.includes('pallet.jpg'), text);
});

test('only the loading list is the scrollable one', async () => {
  // A day's pallet shots run to dozens; HinhThungTrong is one per driver and
  // would gain a scrollbar it never fills.
  const { window } = boot();
  await flush();

  assert.ok($(window, 'loadingList').classList.contains('export-thumbs--scroll'));
  assert.ok(!$(window, 'containerList').classList.contains('export-thumbs--scroll'));
});

test('the loading list keeps its scroll position across a re-render', async () => {
  // Every upload re-runs loadSummary(), which replaces innerHTML and would
  // otherwise throw the operator back to the top of the list mid-check.
  const withPhotos = JSON.parse(JSON.stringify(SUMMARY));
  withPhotos.day_images.loading = Array.from({ length: 30 }, (_, i) => ({
    id: i + 1, label: 'OriginalDriver_18463',
    original_filename: `pallet${i}.jpg`, filename: `${i}.jpg`,
  }));
  const { window } = boot({ summary: withPhotos });
  await flush();

  const list = $(window, 'loadingList');
  resetsScrollOnRerender(window, list);
  list.scrollTop = 180;

  chooseFiles(window, 'loadingInput', ['one-more.jpg']);
  await flush(30);

  assert.strictEqual(list.scrollTop, 180);
});

test('a driver selection survives a reload of the same day', async () => {
  // renderDrivers reruns after every upload. Losing the selection there would
  // silently file the next batch under whoever sorts first.
  const { window, requests } = boot();
  await flush();

  $(window, 'loadingDriver').value = 'HuynhQuocTrong_79791';
  chooseFiles(window, 'loadingInput', ['a.jpg']);
  await flush(30);           // upload, then loadSummary() → renderDrivers()

  assert.strictEqual($(window, 'loadingDriver').value, 'HuynhQuocTrong_79791');

  chooseFiles(window, 'loadingInput', ['b.jpg']);
  await flush(30);
  const labels = uploadsOf(requests).map((r) => r.body.get('label'));
  assert.deepStrictEqual(labels, ['HuynhQuocTrong_79791', 'HuynhQuocTrong_79791']);
});

test('a selection that no longer exists is dropped rather than left stale', async () => {
  const { window } = boot();
  await flush();
  $(window, 'loadingDriver').value = 'HuynhQuocTrong_79791';

  // The operator moves to a date that driver did not work.
  const other = JSON.parse(JSON.stringify(SUMMARY));
  other.drivers = [SUMMARY.drivers[0]];
  window.fetch = async (url) => ({
    ok: true, status: 200,
    json: async () => (String(url).startsWith('/api/export/summary') ? other : {}),
    text: async () => '{}',
  });
  $(window, 'exportDate').dispatchEvent(new window.Event('change', { bubbles: true }));
  await flush();

  assert.strictEqual($(window, 'loadingDriver').value, 'OriginalDriver_18463');
});

run();
