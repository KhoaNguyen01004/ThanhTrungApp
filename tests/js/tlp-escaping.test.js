/* ================================================================
 * Truck Load Planner — HTML escaping guard
 * ================================================================
 * The 2026-07-29 refactor moved every page onto UI.escapeHtml() and fixed a
 * real XSS bug in the process. truck-load-planner.js was missed: as of the
 * 2026-08-06 audit it had *zero* escapeHtml calls while interpolating package
 * names, customer names, plate numbers and driver names straight into
 * innerHTML. With no authentication on any endpoint (deliberate, see
 * CLAUDE.md), a package named `<img src=x onerror=...>` would have executed
 * in every dispatcher's browser.
 *
 * Deliberately dependency-free — no jsdom. This file needs to run anywhere,
 * including a checkout with no node_modules, because the value it provides is
 * catching a *re-introduction* years from now, and a test that needs setup is
 * a test that stops being run.
 *
 * Run:
 *     node tests/js/tlp-escaping.test.js
 */
'use strict';

const fs = require('fs');
const path = require('path');
const assert = require('assert');
const vm = require('vm');

const ROOT = path.resolve(__dirname, '..', '..');
const SRC = fs.readFileSync(
  path.join(ROOT, 'static', 'js', 'truck-load-planner.js'), 'utf8');

// ── Tiny runner (same shape as the other two suites) ───────────
const pending = [];
function test(name, fn) { pending.push([name, fn]); }

function run() {
  const results = [];
  for (const [name, fn] of pending) {
    try { fn(); results.push([true, name]); }
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

// ── The real UI.escapeHtml, lifted out of utils.js ──────────────
function loadEscapeHtml() {
  const utils = fs.readFileSync(path.join(ROOT, 'static', 'js', 'utils.js'), 'utf8');
  const sandbox = { window: {}, document: { addEventListener() {} }, console };
  sandbox.window.window = sandbox.window;
  vm.createContext(sandbox);
  // utils.js declares `const UI = {...}` at top level, and a top-level `const`
  // is not a property of the global object — so the value has to be handed
  // out explicitly rather than read off the sandbox.
  vm.runInContext(utils + '\n;globalThis.__UI = UI;', sandbox);
  const UI = sandbox.__UI;
  assert.ok(UI && typeof UI.escapeHtml === 'function',
    'UI.escapeHtml not found in utils.js — the TLP page depends on it');
  return UI.escapeHtml;
}

// ── The fields that carry operator-supplied text ───────────────
// Anything on this list reaches innerHTML and must go through escapeHtml.
// Numeric and boolean interpolations (${pkg.length}, ${item.quantity},
// ${p.id}) are deliberately absent: escaping them would be noise.
const TEXT_FIELDS = [
  'name', 'package_name', 'plate_number', 'vehicle_type', 'container_name',
  'current_driver', 'customer_name', 'reference_number', 'status', '_name',
];

test('every operator-supplied string field is escaped before innerHTML', () => {
  const offenders = [];
  const lines = SRC.split('\n');

  lines.forEach((line, i) => {
    if (!line.includes('${')) return;
    // Only lines that are building markup.
    if (!/<\w|<\/\w|class=|title=|value=/.test(line)) return;

    for (const m of line.matchAll(/\$\{([^}]*)\}/g)) {
      const expr = m[1];
      if (expr.includes('escapeHtml')) continue;
      // `a.b || "x"` -> `a.b` -> `b`
      const leaf = expr.replace(/\s*\|\|.*/, '').trim()
        .split('.').pop().split('[')[0];
      if (TEXT_FIELDS.includes(leaf)) {
        offenders.push(`  line ${i + 1}: \${${expr.trim()}}`);
      }
    }
  });

  assert.strictEqual(offenders.length, 0,
    'unescaped operator-supplied text reaching innerHTML:\n' + offenders.join('\n'));
});

test('utils.js is what the page actually loads', () => {
  const html = fs.readFileSync(
    path.join(ROOT, 'templates', 'truck-load-planner.html'), 'utf8');
  assert.ok(html.includes('/static/js/utils.js'),
    'truck-load-planner.html must load utils.js — escapeHtml comes from it');
  assert.ok(html.indexOf('/static/js/utils.js')
    < html.indexOf('/static/js/truck-load-planner.js'),
    'utils.js must load before truck-load-planner.js');
});

test('escapeHtml neutralises the payloads this page is exposed to', () => {
  const escapeHtml = loadEscapeHtml();

  const attacks = [
    '<img src=x onerror=alert(1)>',
    '<script>alert(1)</script>',
    '" onmouseover="alert(1)',
    "' onmouseover='alert(1)",
    '</div><script>alert(1)</script>',
  ];

  for (const raw of attacks) {
    const out = escapeHtml(raw);
    assert.ok(!out.includes('<'), `'<' survived escaping of ${raw}`);
    assert.ok(!out.includes('>'), `'>' survived escaping of ${raw}`);
    assert.ok(!/["']/.test(out), `a quote survived escaping of ${raw}`);
  }
});

test('escapeHtml leaves ordinary Vietnamese names alone', () => {
  const escapeHtml = loadEscapeHtml();
  // Real data: plates, container labels and driver names from this fleet.
  assert.strictEqual(escapeHtml('50E-18463'), '50E-18463');
  assert.strictEqual(escapeHtml('Nguyễn Việt Anh Khoa'), 'Nguyễn Việt Anh Khoa');
  assert.strictEqual(escapeHtml('LCS 560-2/5B/17.5°'), 'LCS 560-2/5B/17.5°');
  // & is escaped, which is correct and renders identically.
  assert.strictEqual(escapeHtml('Kho A & B'), 'Kho A &amp; B');
});

test('escapeHtml handles the null a missing field produces', () => {
  const escapeHtml = loadEscapeHtml();
  assert.strictEqual(escapeHtml(null), '');
  assert.strictEqual(escapeHtml(undefined), '');
});

run();
