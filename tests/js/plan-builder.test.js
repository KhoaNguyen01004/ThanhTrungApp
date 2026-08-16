/* ================================================================
 * Delivery Plan Builder — jsdom drives
 * ================================================================
 * Frontend changes get no pytest coverage at all (CLAUDE.md, Definition of
 * Done). The builder is a closed IIFE with no exports, so everything here
 * goes through the DOM exactly as a dispatcher would: type in the modal,
 * click Save, and read what was actually put on the wire.
 *
 * That is the point. The driver-name bug this file was written for was
 * invisible to inspection of any one function — the name was captured
 * correctly, rendered correctly, and then simply not included in the POST
 * body three hundred lines away.
 *
 * Run:
 *     npm install jsdom          # once, anywhere on NODE_PATH
 *     node tests/js/plan-builder.test.js
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
// Boots the real builder over the real template. fetch is stubbed and every
// request is recorded, so a test can assert on the exact payload the server
// would have received.
const VEHICLES = [
  { id: 1, plate_number: '50E-18463', vehicle_type: 'Box Truck', current_driver: 'Original Driver' },
  { id: 2, plate_number: '51C-99999', vehicle_type: 'Box Truck', current_driver: '' },
];

// Mirrors plan_service.list_drivers: real `drivers` rows carry an id, names
// that exist only as vehicles.current_driver are synthesised with id null.
// That null is the whole reason a name-only column had to exist.
const DRIVERS = [
  { id: 7, name: 'Registered Driver', phone: '', license_number: '' },
  { id: null, name: 'Original Driver', phone: '', license_number: '' },
];

function boot({ plan = null } = {}) {
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

  // jsdom has no layout, so showPanel()'s smooth scroll only produces noise.
  window.scrollTo = () => {};

  const requests = [];
  let nextId = 100;

  window.fetch = async (url, opts) => {
    opts = opts || {};
    const method = (opts.method || 'GET').toUpperCase();
    const body = opts.body ? JSON.parse(opts.body) : null;
    requests.push({ url: String(url), method, body });

    let payload = {};
    // The fleet endpoint is the one page on this app that *does* use the
    // {data: ...} envelope; the delivery ones return raw JSON.
    if (String(url).startsWith('/api/fleet/vehicles')) payload = { data: VEHICLES };
    else if (String(url).startsWith('/api/drivers')) payload = DRIVERS;
    else if (/^\/api\/plans\/\d+$/.test(String(url)) && method === 'GET') payload = plan;
    else if (String(url).startsWith('/api/assignments?')) payload = [];
    else if (method === 'POST') payload = { id: ++nextId };
    else payload = { ok: true };

    return {
      ok: true, status: 200,
      json: async () => payload,
      text: async () => JSON.stringify(payload),
    };
  };

  if (plan) window.document.body.dataset.editPlanId = String(plan.id);

  // utils.js declares `const UI`/`const ApiClient` at top level; each
  // window.eval() gets its own lexical environment, so promote them the way
  // separate <script> tags would.
  window.eval(JS('utils.js') + '\n;window.UI = UI; window.ApiClient = ApiClient;');
  window.eval(JS('delivery-plan-builder.js'));
  window.document.dispatchEvent(new window.Event('DOMContentLoaded'));

  return { window, requests };
}

/** Drain the microtask/timer queue. The builder chains several awaits per
 *  user action (fetch → json → render), so one turn is never enough. */
async function flush(turns = 12) {
  for (let i = 0; i < turns; i++) await new Promise((r) => setTimeout(r, 0));
}
const $ = (w, id) => w.document.getElementById(id);

function click(w, el) {
  el.dispatchEvent(new w.Event('click', { bubbles: true }));
}

function typeInto(w, el, value) {
  el.value = value;
  el.dispatchEvent(new w.Event('input', { bubbles: true }));
}

/** Pick a vehicle through its autocomplete, as a dispatcher does. */
function pickVehicle(w, plate) {
  const input = $(w, 'assignVehicle');
  typeInto(w, input, plate);
  const item = w.document.querySelector('#vehicleAutocompleteList .autocomplete-item');
  assert.ok(item, 'vehicle autocomplete offered nothing for ' + plate);
  click(w, item);
}

/** Add one assignment via the modal and return the driver field's value. */
function addAssignment(w, { plate = '50E-18463', driver = null } = {}) {
  click(w, $(w, 'addAssignmentBtn'));
  pickVehicle(w, plate);
  if (driver !== null) typeInto(w, $(w, 'assignDriver'), driver);
  click(w, $(w, 'assignmentModalSave'));
}

/** Fill step 1 and save, returning the POSTed assignment bodies. */
async function saveDraft(w, requests) {
  typeInto(w, $(w, 'planName'), 'Test Plan');
  typeInto(w, $(w, 'planDate'), '2026-08-02');
  const before = requests.length;
  click(w, $(w, 'step4SaveDraft'));
  await flush();
  return requests.slice(before).filter((r) => r.url === '/api/assignments' && r.method === 'POST');
}

// ── The template still matches the module ──────────────────────
test('the modal ids the module reaches for all exist in the template', async () => {
  const { window } = boot();
  await flush();
  for (const id of ['addAssignmentBtn', 'assignVehicle', 'assignDriver',
                    'assignmentModalSave', 'driverAutocompleteList',
                    'vehicleAutocompleteList', 'step4SaveDraft']) {
    assert.ok($(window, id), `#${id} is missing — renamed in the HTML but not the JS`);
  }
});

// ── The driver name reaches the wire ───────────────────────────
test('a typed driver name is included in the POST', async () => {
  const { window, requests } = boot();
  await flush();
  addAssignment(window, { driver: 'Nguyen Van Thay' });
  const posts = await saveDraft(window, requests);

  assert.strictEqual(posts.length, 1, 'expected exactly one assignment POST');
  assert.strictEqual(posts[0].body.driver_name, 'Nguyen Van Thay',
    'the name never left the browser — dispatch falls back to the vehicle default');
});

test('the name is sent even though driver_id is null', async () => {
  // The failure mode in production: drivers with no `drivers` row can only
  // travel as text, and driver_id alone silently dropped them.
  const { window, requests } = boot();
  await flush();
  addAssignment(window, { driver: 'Nguyen Van Thay' });
  const posts = await saveDraft(window, requests);

  assert.strictEqual(posts[0].body.driver_id, null);
  assert.strictEqual(posts[0].body.driver_name, 'Nguyen Van Thay');
});

test('selecting the vehicle prefills its default driver', async () => {
  const { window } = boot();
  await flush();
  click(window, $(window, 'addAssignmentBtn'));
  pickVehicle(window, '50E-18463');

  assert.strictEqual($(window, 'assignDriver').value, 'Original Driver');
});

test('the prefilled default is sent too, so dispatch never has to guess', async () => {
  const { window, requests } = boot();
  await flush();
  addAssignment(window);           // accept the prefill untouched
  const posts = await saveDraft(window, requests);

  assert.strictEqual(posts[0].body.driver_name, 'Original Driver');
});

test('a registered driver picked from the list travels as an id', async () => {
  const { window, requests } = boot();
  await flush();
  click(window, $(window, 'addAssignmentBtn'));
  pickVehicle(window, '50E-18463');
  typeInto(window, $(window, 'assignDriver'), 'Registered');
  const item = window.document.querySelector('#driverAutocompleteList .autocomplete-item');
  assert.ok(item, 'driver autocomplete offered nothing');
  click(window, item);
  click(window, $(window, 'assignmentModalSave'));

  const posts = await saveDraft(window, requests);
  assert.strictEqual(String(posts[0].body.driver_id), '7');
  assert.strictEqual(posts[0].body.driver_name, 'Registered Driver');
});

test('a vehicle with no default driver sends an empty name, not undefined', async () => {
  // JSON.stringify drops undefined keys entirely; the server would then see
  // no field at all rather than an explicit "nothing typed".
  const { window, requests } = boot();
  await flush();
  addAssignment(window, { plate: '51C-99999' });
  const posts = await saveDraft(window, requests);

  assert.ok('driver_name' in posts[0].body, 'key vanished from the payload');
  assert.strictEqual(posts[0].body.driver_name, '');
});

test('an edited name replaces the prefill rather than joining it', async () => {
  const { window, requests } = boot();
  await flush();
  click(window, $(window, 'addAssignmentBtn'));
  pickVehicle(window, '50E-18463');              // prefills "Original Driver"
  typeInto(window, $(window, 'assignDriver'), 'Stand In');
  click(window, $(window, 'assignmentModalSave'));

  const posts = await saveDraft(window, requests);
  assert.strictEqual(posts[0].body.driver_name, 'Stand In');
});

// ── Round-tripping an existing plan ────────────────────────────
test('reopening a plan keeps the stored name on the next save', async () => {
  // The look-back case: editing yesterday's plan must not quietly rewrite
  // its driver to whoever holds the truck today.
  const { window, requests } = boot({
    plan: {
      id: 42, plan_name: 'Yesterday', plan_date: '2026-08-01', status: 'draft',
      assignments: [{
        id: 9, vehicle_id: 1, driver_id: null,
        driver_name: 'Nguyen Van Thay', notes: '', stops: [],
      }],
    },
  });
  await flush();

  const posts = await saveDraft(window, requests);
  assert.strictEqual(posts.length, 1);
  assert.strictEqual(posts[0].body.driver_name, 'Nguyen Van Thay',
    'the day\'s record was overwritten with the vehicle default');
});

test('the stored name is shown when the plan is reopened', async () => {
  const { window } = boot({
    plan: {
      id: 42, plan_name: 'Yesterday', plan_date: '2026-08-01', status: 'draft',
      assignments: [{
        id: 9, vehicle_id: 1, driver_id: null,
        driver_name: 'Nguyen Van Thay', notes: '', stops: [],
      }],
    },
  });
  await flush();

  // The list lives on step 2 and is only rendered on arrival there.
  typeInto(window, $(window, 'planName'), 'Yesterday');
  typeInto(window, $(window, 'planDate'), '2026-08-01');
  click(window, $(window, 'step1Next'));
  await flush();

  const text = $(window, 'assignmentsList').textContent;
  assert.ok(text.includes('Nguyen Van Thay'),
    'dispatcher sees the wrong driver for that day: ' + JSON.stringify(text.trim()));
  assert.ok(!text.includes('(auto)'),
    'a stored name was rendered as an auto-filled guess');
});

run();
