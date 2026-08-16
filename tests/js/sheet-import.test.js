/* ================================================================
 * Google Sheet import button — jsdom drives
 * ================================================================
 * Frontend changes get no pytest coverage (CLAUDE.md, Definition of Done), and
 * the interesting behaviour here is entirely in the browser: the two-click
 * read-then-commit flow, the override that only appears for an in-progress
 * plan, and the commit button being disabled when a plate is unknown. None of
 * that is visible from the Python side.
 *
 * Everything goes through the DOM as a dispatcher would drive it, and every
 * request is recorded so a test can assert on the exact payload the server
 * would have received.
 *
 * Run:
 *     npm install jsdom          # once, anywhere on NODE_PATH
 *     node tests/js/sheet-import.test.js
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

// ── Fixtures ───────────────────────────────────────────────────
// Mirrors the /api/plans/import/sheet/preview response for the real 10-Aug
// rows: three trucks, one stop with no coordinates, one with no station code.
function previewResponse(overrides = {}) {
  return Object.assign({
    date: '2026-08-10',
    tab_name: 'TH08',
    warnings: [
      { sheet_row: 11, field: 'coordinates', station_code: 'Non HW Delivery-DU',
        message: 'lng \'999.9\' cannot be read as a coordinate inside Vietnam — imported without coordinates, so this stop has no map marker or ETA until it is filled in' },
      { sheet_row: 8, field: 'station_code', station_code: '',
        message: 'station code (TRẠM PHÁT) is empty' },
    ],
    existing_plans: [],
    replace_blocked: false,
    preview: {
      total_rows: 5,
      total_assignments: 2,
      has_errors: false,
      errors: [],
      unknown_vehicles: [],
      vehicles_checked: true,
      assignments: [
        {
          vehicle_identifier: '50H-939.63', resolved: true, vehicle_id: 13,
          resolved_plate: '50H-93963', matched_by: 'serial', stop_count: 2,
          stops: [
            { sequence: 1, station_code: 'STST28', station_name: 'STST28',
              address: 'Khóm 5, Phường Phú Lợi, Cần Thơ', lat: 9.585868, lng: 105.9744, product: '' },
            { sequence: 2, station_code: '', station_name: '',
              address: 'KDC Minh Châu', lat: 9.6301, lng: 105.9672, product: '' },
          ],
        },
        {
          vehicle_identifier: '50H-197.93', resolved: true, vehicle_id: 20,
          resolved_plate: '50E-19793', matched_by: 'serial', stop_count: 3,
          stops: [
            { sequence: 1, station_code: 'AGCT33', station_name: 'AGCT33',
              address: 'Ấp Phú An 1', lat: 10.4568, lng: 105.3117, product: '' },
            { sequence: 2, station_code: 'AGCT26', station_name: 'AGCT26',
              address: 'Ấp Phú Hòa 1', lat: null, lng: null, product: '' },
            { sequence: 3, station_code: 'Non HW Delivery-DU', station_name: 'Non HW Delivery-DU',
              address: 'ChâuThành, An Giang', lat: null, lng: null, product: '' },
          ],
        },
      ],
    },
  }, overrides);
}

// ── Harness ────────────────────────────────────────────────────
function boot({ responses = {}, editPlanId = null } = {}) {
  let html = fs.readFileSync(path.join(ROOT, 'templates', 'delivery-plan-builder.html'), 'utf8');
  html = html.replace(/<script[\s\S]*?<\/script>/g, '');

  const dom = new JSDOM(html, {
    url: 'http://localhost/delivery/new',
    pretendToBeVisual: true,
    runScripts: 'outside-only',
  });
  const { window } = dom;
  global.window = window;
  global.document = window.document;
  global.localStorage = window.localStorage;
  window.scrollTo = () => {};

  // The commit handler navigates on success, and that redirect is worth
  // asserting — landing on the wrong plan would be a real bug. jsdom 30 seals
  // Location completely: `window.location` is non-configurable and every one
  // of its properties is non-writable and non-configurable, so neither
  // defineProperty nor assignment can stub it.
  //
  // So instead of patching the window, the builder is loaded inside a function
  // whose `window` parameter shadows the global one. The proxy forwards
  // everything to the real window except `location`, which becomes a plain
  // recording object. Bare `document` references inside the builder still
  // resolve to the real document through the global scope, which is what we
  // want — only the navigation is intercepted.
  const nav = { href: '' };
  const windowProxy = new Proxy(window, {
    get(target, prop) {
      if (prop === 'location') return nav;
      const value = Reflect.get(target, prop);
      // Host functions (setTimeout, scrollTo, ...) need `this` to be the real
      // window, not the proxy.
      return typeof value === 'function' ? value.bind(target) : value;
    },
    set(target, prop, value) { target[prop] = value; return true; },
  });

  const requests = [];

  window.fetch = async (url, opts) => {
    opts = opts || {};
    const method = (opts.method || 'GET').toUpperCase();
    const body = opts.body ? JSON.parse(opts.body) : null;
    const key = String(url).split('?')[0];
    requests.push({ url: String(url), method, body });

    if (key.startsWith('/api/fleet/vehicles')) return jsonOk({ data: [] });
    if (key.startsWith('/api/drivers')) return jsonOk([]);

    const handler = responses[key];
    if (typeof handler === 'function') return handler({ method, body, requests });
    if (handler) return jsonOk(handler);
    return jsonOk({ ok: true });
  };

  function jsonOk(payload, status = 200) {
    return { ok: status < 400, status, json: async () => payload,
             text: async () => JSON.stringify(payload) };
  }

  if (editPlanId) window.document.body.dataset.editPlanId = String(editPlanId);

  window.eval(JS('utils.js') + '\n;window.UI = UI; window.ApiClient = ApiClient;');
  // See the windowProxy note above: the builder gets a shadowed `window`.
  window.Function('window', JS('delivery-plan-builder.js'))(windowProxy);
  window.document.dispatchEvent(new window.Event('DOMContentLoaded'));

  return { window, requests, location: nav, jsonOk };
}

async function flush(turns = 12) {
  for (let i = 0; i < turns; i++) await new Promise((r) => setTimeout(r, 0));
}
const $ = (w, id) => w.document.getElementById(id);
function click(w, el) {
  assert.ok(el, 'tried to click an element that is not there');
  el.dispatchEvent(new w.Event('click', { bubbles: true }));
}
function fail(payload, status) {
  return { ok: false, status, json: async () => payload,
           text: async () => JSON.stringify(payload) };
}

/** Read the sheet and wait for the preview to render. */
async function readSheet(ctx) {
  click(ctx.window, $(ctx.window, 'sheetImportBtn'));
  await flush();
}

// ── Tests ──────────────────────────────────────────────────────

test('the date defaults to tomorrow, in local time', async () => {
  const ctx = boot();
  await flush();
  const expected = new Date();
  expected.setDate(expected.getDate() + 1);
  const iso = [
    expected.getFullYear(),
    String(expected.getMonth() + 1).padStart(2, '0'),
    String(expected.getDate()).padStart(2, '0'),
  ].join('-');
  assert.strictEqual($(ctx.window, 'sheetImportDate').value, iso);
});

test('reading the sheet asks the preview endpoint for that date', async () => {
  const ctx = boot({ responses: { '/api/plans/import/sheet/preview': previewResponse() } });
  await flush();
  $(ctx.window, 'sheetImportDate').value = '2026-08-10';
  await readSheet(ctx);

  const req = ctx.requests.find((r) => r.url.includes('/import/sheet/preview'));
  assert.ok(req, 'no preview request was made');
  assert.strictEqual(req.method, 'GET');
  assert.ok(req.url.includes('date=2026-08-10'), req.url);
});

test('reading the sheet writes nothing on its own', async () => {
  const ctx = boot({ responses: { '/api/plans/import/sheet/preview': previewResponse() } });
  await flush();
  await readSheet(ctx);
  assert.strictEqual(
    ctx.requests.filter((r) => r.method === 'POST').length, 0,
    'a read should never POST');
});

test('the preview shows the trucks, stop count and tab', async () => {
  const ctx = boot({ responses: { '/api/plans/import/sheet/preview': previewResponse() } });
  await flush();
  await readSheet(ctx);

  const text = $(ctx.window, 'sheetImportResult').textContent;
  assert.ok(text.includes('TH08'), 'tab name missing');
  assert.ok(text.includes('50H-93963'), 'resolved plate missing');
  assert.ok(text.includes('AGCT33'), 'station code missing');
  assert.ok(/5\s*stop/.test(text), 'stop total missing: ' + text.slice(0, 200));
});

test('a plate the sheet writes differently shows both forms', async () => {
  // 50H-197.93 in the sheet is 50E-19793 in the fleet. The dispatcher has to
  // be able to see that, or a genuine plate error stays invisible.
  const ctx = boot({ responses: { '/api/plans/import/sheet/preview': previewResponse() } });
  await flush();
  await readSheet(ctx);
  const text = $(ctx.window, 'sheetImportResult').textContent;
  assert.ok(text.includes('50E-19793'), 'fleet plate missing');
  assert.ok(text.includes('50H-197.93'), 'sheet plate missing');
});

test('stops with no coordinates are called out, not quietly listed', async () => {
  const ctx = boot({ responses: { '/api/plans/import/sheet/preview': previewResponse() } });
  await flush();
  await readSheet(ctx);

  const box = $(ctx.window, 'sheetImportResult');
  const flagged = box.querySelectorAll('.sheet-stop-nocoord');
  // Two stops without coordinates, plus the summary counter.
  assert.strictEqual(flagged.length, 3, 'expected 2 flagged stops + 1 summary');
  assert.ok(box.textContent.includes('2 without coordinates'));
});

test('sheet warnings are listed for review', async () => {
  const ctx = boot({ responses: { '/api/plans/import/sheet/preview': previewResponse() } });
  await flush();
  await readSheet(ctx);

  const warnings = $(ctx.window, 'sheetImportResult').querySelector('.sheet-warnings');
  assert.ok(warnings, 'no warnings panel');
  assert.strictEqual(warnings.querySelectorAll('li').length, 2);
  assert.ok(warnings.textContent.includes('row 11'), warnings.textContent);
});

test('committing posts the date and no override', async () => {
  const ctx = boot({
    responses: {
      '/api/plans/import/sheet/preview': previewResponse(),
      '/api/plans/import/sheet/commit': () => ({
        ok: true, status: 201,
        json: async () => ({ plan_id: 42, stops_created: 5, assignments_created: 2 }),
      }),
    },
  });
  await flush();
  $(ctx.window, 'sheetImportDate').value = '2026-08-10';
  await readSheet(ctx);
  click(ctx.window, $(ctx.window, 'sheetCommitBtn'));
  await flush();

  const post = ctx.requests.find((r) => r.method === 'POST');
  assert.ok(post, 'no commit request');
  assert.deepStrictEqual(post.body, { date: '2026-08-10', override_in_progress: false });
});

test('a successful commit lands on the new plan', async () => {
  const ctx = boot({
    responses: {
      '/api/plans/import/sheet/preview': previewResponse(),
      '/api/plans/import/sheet/commit': () => ({
        ok: true, status: 201,
        json: async () => ({ plan_id: 42, stops_created: 5, assignments_created: 2 }),
      }),
    },
  });
  await flush();
  await readSheet(ctx);
  click(ctx.window, $(ctx.window, 'sheetCommitBtn'));
  await flush();
  assert.strictEqual(ctx.location.href, '/delivery/edit/42');
});

test('an in-progress plan offers an explicit override', async () => {
  let attempts = 0;
  const ctx = boot({
    responses: {
      '/api/plans/import/sheet/preview': previewResponse({
        existing_plans: [{ id: 9, plan_name: 'SINO_10_08_2026', status: 'confirmed', active_executions: 3 }],
        replace_blocked: true,
      }),
      '/api/plans/import/sheet/commit': ({ body }) => {
        attempts++;
        if (!body.override_in_progress) {
          return fail({ error: 'The plan for 2026-08-10 already has 3 stop(s) that drivers have started.', reason: 'in_progress' }, 409);
        }
        return { ok: true, status: 201,
                 json: async () => ({ plan_id: 51, stops_created: 5, assignments_created: 2 }) };
      },
    },
  });
  await flush();
  await readSheet(ctx);

  // The dispatcher is warned before committing.
  assert.ok($(ctx.window, 'sheetImportResult').textContent.includes('already in progress'));

  click(ctx.window, $(ctx.window, 'sheetCommitBtn'));
  await flush();
  assert.strictEqual(attempts, 1);
  assert.strictEqual(ctx.location.href, '', 'must not navigate on a refusal');

  const override = $(ctx.window, 'sheetOverrideBtn');
  assert.ok(override, 'no override offered');
  click(ctx.window, override);
  await flush();

  assert.strictEqual(attempts, 2);
  assert.strictEqual(ctx.requests.filter((r) => r.method === 'POST')[1].body.override_in_progress, true);
  assert.strictEqual(ctx.location.href, '/delivery/edit/51');
});

test('an unknown-vehicle refusal offers no override', async () => {
  // There is no override for this: an import never adds vehicles. Offering one
  // would promise something the server will always refuse.
  const ctx = boot({
    responses: {
      '/api/plans/import/sheet/preview': previewResponse(),
      '/api/plans/import/sheet/commit': () => fail({
        error: 'These vehicles are not in the fleet: \'50H-791.07\'.',
        reason: 'unknown_vehicles', unknown_vehicles: ['50H-791.07'],
      }, 409),
    },
  });
  await flush();
  await readSheet(ctx);
  click(ctx.window, $(ctx.window, 'sheetCommitBtn'));
  await flush();

  assert.strictEqual($(ctx.window, 'sheetOverrideBtn'), null, 'override must not be offered');
  assert.ok($(ctx.window, 'sheetImportResult').textContent.includes('not in the fleet'));
});

test('an unresolved plate in the preview disables committing', async () => {
  const preview = previewResponse();
  preview.preview.unknown_vehicles = ['50H-791.07'];
  preview.preview.assignments[0].resolved = false;
  preview.preview.assignments[0].resolved_plate = null;

  const ctx = boot({ responses: { '/api/plans/import/sheet/preview': preview } });
  await flush();
  await readSheet(ctx);

  const btn = $(ctx.window, 'sheetCommitBtn');
  assert.ok(btn.disabled, 'commit button should be disabled');
  click(ctx.window, btn);
  await flush();
  assert.strictEqual(ctx.requests.filter((r) => r.method === 'POST').length, 0);
});

test('a sheet error is shown instead of a preview', async () => {
  const ctx = boot({
    responses: {
      '/api/plans/import/sheet/preview': () => fail({
        error: 'No stops dated 2026-08-31 were found in the planning sheet.',
        reason: 'date_not_found',
      }, 404),
    },
  });
  await flush();
  await readSheet(ctx);

  const box = $(ctx.window, 'sheetImportResult');
  assert.ok(box.querySelector('.sheet-import-error'), 'no error panel');
  assert.ok(box.textContent.includes('were found in the planning sheet'));
  assert.strictEqual($(ctx.window, 'sheetCommitBtn'), null);
  // The button must come back so the dispatcher can retry another date.
  assert.strictEqual($(ctx.window, 'sheetImportBtn').disabled, false);
});

test('sheet text is escaped before it reaches the DOM', async () => {
  // The sheet is hand-typed by someone outside this system, so its cells are
  // untrusted input like any other.
  const preview = previewResponse();
  preview.preview.assignments[0].stops[0].station_code = '<img src=x onerror=alert(1)>';
  preview.warnings[0].message = "it's <script>alert(2)</script>";

  const ctx = boot({ responses: { '/api/plans/import/sheet/preview': preview } });
  await flush();
  await readSheet(ctx);

  const box = $(ctx.window, 'sheetImportResult');
  assert.strictEqual(box.querySelectorAll('img, script').length, 0, 'markup was injected');
  assert.ok(box.textContent.includes('<img src=x onerror=alert(1)>'), 'text was lost');
  assert.ok(box.textContent.includes("it's <script>alert(2)</script>"));
});

test('cancelling clears the preview without writing', async () => {
  const ctx = boot({ responses: { '/api/plans/import/sheet/preview': previewResponse() } });
  await flush();
  await readSheet(ctx);
  click(ctx.window, $(ctx.window, 'sheetCancelBtn'));
  await flush();

  assert.strictEqual($(ctx.window, 'sheetImportResult').style.display, 'none');
  assert.strictEqual(ctx.requests.filter((r) => r.method === 'POST').length, 0);
});

test('the importer is hidden when editing an existing plan', async () => {
  // Importing builds a plan from scratch; offering it mid-edit would imply it
  // merges into the plan on screen, which it does not.
  const ctx = boot({
    editPlanId: 7,
    responses: { '/api/plans/7': { id: 7, plan_name: 'X', plan_date: '2026-08-10', status: 'draft', assignments: [] } },
  });
  await flush();
  assert.strictEqual($(ctx.window, 'sheetImportBox').style.display, 'none');
});

run();
