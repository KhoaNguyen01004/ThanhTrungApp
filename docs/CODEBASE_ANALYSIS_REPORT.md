# Codebase Analysis Report — Fleet Fuel Management System

**Generated:** 2026-07-29 · **Last reviewed:** 2026-08-15 (addendum 2026-08-15)  
**Scope:** Full codebase scan of `D:\ChiTuyen\Solution`  
**Project:** Fleet Fuel Management (Flask + Vanilla JS + SQLite)

> This report accumulates **dated addenda** at the end of §9 rather than being rewritten.
> Read the newest addendum first — it carries the corrections to everything above it.

> **Implementation status (2026-07-29):** Most of Sections 6.1–6.4's proposals below have
> since been built — see [§9 Priority Action Items](#9-priority-action-items) for the
> item-by-item Status column and `CHANGELOG.md`'s 2026-07-29 entry for full detail. The
> problem descriptions and code sketches in Section 6 are kept as-written (historical
> record of the analysis); don't assume something is still missing just because its
> "Problem" paragraph is phrased in the present tense.

---

## Table of Contents
1. [Executive Summary](#1-executive-summary)
2. [Redundant Files & Dead Code](#2-redundant-files--dead-code)
3. [Python Backend Redundancies](#3-python-backend-redundancies)
4. [JavaScript Frontend Redundancies](#4-javascript-frontend-redundancies)
5. [Database & Query Redundancies](#5-database--query-redundancies)
6. [Architectural Refactoring Roadmap — 4 Pillars](#6-architectural-refactoring-roadmap--4-pillars)
   - 6.1 [Pillar 1: Encapsulation & Data Integrity](#61-pillar-1-encapsulation--data-integrity)
   - 6.2 [Pillar 2: Polymorphism & Geometry Unification](#62-pillar-2-polymorphism--geometry-unification)
   - 6.3 [Pillar 3: Inheritance & Adapter Patterns for Legacy Code](#63-pillar-3-inheritance--adapter-patterns-for-legacy-code)
   - 6.4 [Pillar 4: Modular Split & AI Token Optimization](#64-pillar-4-modular-split--ai-token-optimization)
7. [Scalability Concerns](#7-scalability-concerns)
8. [Cleanup Actions Taken](#8-cleanup-actions-taken)
9. [Priority Action Items](#9-priority-action-items)
10. [AI Context & Token Optimization Strategy](#10-ai-context--token-optimization-strategy)

---

## 1. Executive Summary

This project is a **~35,000-line** full-stack fleet fuel management application with **~140 source files** (68 Python, 17 JS, 10 HTML, 3 CSS, 8 MD). The analysis identified:

- **15+ instances** of duplicated logic across Python backend files
- **10+ instances** of duplicated JavaScript functions (6 different `showToast` implementations alone)
- **A full legacy module** (`truck_load_planner/logistics/`) that is redundant with the newer `engine/` module
- **Two separate AABB classes** (`geometry/aabb.py` vs `engine/geometry.py`) that should be unified
- **5 dead functions** in `tracking_service.py`
- **An N+1 query pattern** causing up to 101 DB queries per dashboard load
- **A 3,625-line monolith** (`app.py`) that should be split into modules
- **A 1,014-line route file** (`truck_load_planner/routes.py`) mixing CRUD, business logic, and data conversion

---

## 2. Redundant Files & Dead Code

### 2.1 Legacy `truck_load_planner/logistics/` Module

All 5 files in this module are **fully redundant** with the newer `engine/` module:

| File | Lines | Engine Equivalent | Status |
|------|-------|-------------------|--------|
| `logistics/boundary.py` | 29 | `engine/boundary.py` (24 lines) | Byte-for-byte duplicate |
| `logistics/weight.py` | 25 | `engine/weight.py` (33 lines) | Near-identical |
| `logistics/volume.py` | 40 | `engine/statistics.py` (lines 37-47) | Math duplicated inline |
| `logistics/placement.py` | 100 | `engine/validation.py` (176 lines) | Primitive duplicate |
| `logistics/constraints.py` | 118 | `engine/access.py` (227 lines) | Partial overlap |

**Impact:** `session.py` imports from *both* worlds (line 18-19), meaning door-status queries bypass the sophisticated engine checks.

### 2.2 `truck_load_planner/geometry/aabb.py` vs `engine/geometry.py`

Two separate AABB (Axis-Aligned Bounding Box) classes exist:
- `geometry/aabb.py` — basic AABB (73 lines)
- `engine/geometry.py` — superset AABB with clearance support, overlap area, point containment (108 lines)

The engine version also duplicates coordinate transforms from `geometry/transform.py`. Bug fixes must be applied in two places.

### 2.3 Dead Functions in `services/delivery/tracking_service.py`

4 out of 5 functions are **never called** from any other file:

| Function | Lines | Status |
|----------|-------|--------|
| `get_ttas_vehicles()` | 10-16 | Dead |
| `update_ttas_cache()` | 19-21 | Dead |
| `find_vehicle_by_plate()` | 24-30 | Dead |
| `find_vehicle_by_id()` | 33-37 | Dead |
| `normalize_gps_position()` | 40-48 | **Used** (by `routes.py`) |

### 2.4 Dead Code in `app.py`

| Lines | Code | Why Dead |
|-------|------|----------|
| 702-708 | `get_routing_profile(vehicle_type)` | All 3 branches return `"driving-hgv"` — branching is entirely useless |
| 1082 | `import re` inside for-loop | `re` already imported at module level |
| 1179 | `pass  # stale data from bg thread` | Silent ignore with no logging |

### 2.5 Shadowed Functions in `static/js/map.js`

Three functions defined in `map.js` are **byte-for-byte identical** to versions already in `utils.js`:

| Function | `map.js` Lines | `utils.js` Lines |
|----------|---------------|------------------|
| `normalizeText` | 44-51 | 223-230 |
| `getDistanceMeters` | 417-426 | 178-187 |
| `isPointInPolygon` | 428-443 | 196-216 |
| `escapeHtml` | 53-61 | (should be in utils.js) |

### 2.6 Untracked Temporary/Generated Files

See [Section 8 — Cleanup Actions Taken](#8-cleanup-actions-taken).

---

## 3. Python Backend Redundancies

### 3.1 Duplicated Database Connection Code (4 copies)

**Severity: Medium**

The same 4-line `get_conn(db_path)` pattern is copy-pasted across:
- `services/delivery/plan_service.py:9-13`
- `services/delivery/execution_service.py:9-13`
- `services/delivery/image_service.py:14-17` (missing `PRAGMA foreign_keys = ON` — data integrity bug!)
- `truck_load_planner/routes.py:19-22`

**Fix:** Extract into a shared `services/delivery/db.py` / `truck_load_planner/db_conn.py`.

### 3.2 Duplicated Stop + Execution JOIN Query (5 copies)

**Severity: High**

Same SQL pattern joins `delivery_plan_stops s` with `stop_executions e` across 5 locations:
- `plan_service.py:84-91`, `239-246`, `256-263`
- `execution_service.py:20-29`, `232-240`

Any schema change requires updating all 5.

### 3.3 Duplicated Stop-Insert + Execution-Create (3 copies)

**Severity: Medium**

`plan_service.py:279-291`, `333-355`, `519-541` — same pair of INSERTs with 11 column bindings.

### 3.4 Duplicated Progress Calculation (2 copies)

**Severity: Low**

`execution_service.py:190-199` and `252-260` — identical arithmetic for computing `completed`, `remaining`, `progress_pct`.

### 3.5 Duplicated Vehicle + Container Config Query (3 copies)

**Severity: Medium**

`truck_load_planner/routes.py:648-655`, `814-820`, `919-927` — same multi-table JOIN on `vehicles` + `container_configs`.

### 3.6 Duplicated Container Features Query (6 copies)

**Severity: Medium**

`SELECT * FROM container_features WHERE container_config_id = ?` at lines 41, 88, 467, 563, 680, 835 in `truck_load_planner/routes.py`.

### 3.7 Duplicated Placement Dict Conversion (2 copies)

- `truck_load_planner/session.py:66-88` (`_engine_placement_to_dict`)
- `truck_load_planner/routes.py:711-742` (`_build_placement_dict`)

Near-identical field mapping.

### 3.8 Duplicated EnginePackage Conversion (3 copies)

- `truck_load_planner/session.py:22-42`, `45-63`
- `truck_load_planner/routes.py:745-806` (inline)

All map the same fields from various source formats.

### 3.9 Duplicated TTAS Headers & Payload (2 copies)

- `app.py:45-53` (TTAS payload + headers)
- `main.py:35-42, 170` (same payload + headers verbatim)

### 3.10 App.py: `get_routing_profile()` Always Returns Same Value

**`app.py:702-708`** — All three branches return `"driving-hgv"`. The `vehicle_type` parameter and branching logic are entirely dead.

### 3.11 App.py: Duplicate Route Registration

**`app.py:1501-1502`** — `/api/trips/history` and `/api/trip-history` both route to the same function. No redirect — both are live endpoints.

### 3.12 App.py: Duplicated Oil-Metrics Query Loop

**`app.py:2176-2181` vs `2203-2208`** — The same `SELECT ... FROM oil_km_log WHERE license_plate = ?` loop is used in both `api_oil_maintenance_list()` and `api_oil_maintenance_export()`.

---

## 4. JavaScript Frontend Redundancies

### 4.1 Six Different `showToast` Implementations

**Severity: HIGH** — Different parameter orders, different animations, inconsistent dismiss durations.

| File | Lines | Signature |
|------|-------|-----------|
| `static/js/utils.js` | 13-30 | `(message, type, duration)` |
| `static/js/fuel-efficiency.js` | 908-919 | `(type, message, duration)` |
| `static/js/fuel-sync.js` (IIFE) | 12-26 | `(message, type, duration)` |
| `static/js/vehicle-management.js` | 359-366 | `(type, msg)` |
| `static/js/oil-change.js` | 494-507 | `(type, _icon, message, duration)` |
| `static/js/truck-load-planner.js` | 25-32 | `(msg, type)` |

### 4.2 Three Identical `apiFetch` Wrappers

**Severity: HIGH**

- `static/js/fuel-efficiency.js:130-137`
- `static/js/vehicle-management.js:23-30`
- `static/js/oil-change.js:25-32`

All implement the same `async function apiFetch(url, opts)` pattern.

### 4.3 Four Different `escapeHtml` / `escHtml` Implementations

**Severity: HIGH** — Some don't escape single quotes (XSS gap).

| File | Function | Escapes `'`? |
|------|----------|-------------|
| `static/js/map.js:53-61` | `escapeHtml` | Yes |
| `static/js/fuel-efficiency.js:900-902` | `escHtml` | **No** |
| `static/js/oil-change.js:510-517` | `escHtml` | Yes |
| `static/js/vehicle-management.js:86` | `escHtml` | **No** |

### 4.4 Duplicated Utility Functions in `fuel-efficiency.js` & `oil-change.js`

| Function | `fuel-efficiency.js` | `oil-change.js` | Should Be In |
|----------|---------------------|-----------------|-------------|
| `todayISO()` | 35-38 | 530-536 | `utils.js` |
| `formatDate()` | 886-890 | 524-528 | `utils.js` |
| `fmtNum()` | 904-906 | 519-522 | `utils.js` |

### 4.5 Triplicated `isContainerV` Check

**`fuel-efficiency.js`** defines this function three times:
- Line 488-490: Named function
- Line 595: Inline arrow inside `onVehicleInput`
- Line 781: Inline arrow inside `renderProfiles`

### 4.6 Duplicated Sort Comparison Logic

**Severity: Low**

`fuel-efficiency.js:217-221` and `oil-change.js:137-145` — nearly identical generic sort logic with string vs numeric comparison.

### 4.7 Duplicated Autocomplete Pattern (3 files)

- `fuel-efficiency.js:592-608`
- `oil-change.js:177-202`
- `delivery-plan-builder.js:285-360`

All implement vehicle autocomplete with ~70% shared structure (input handler, dropdown render, click handler, outside-close).

### 4.8 Duplicated Modal Open/Close Pattern (3 files)

- `fuel-efficiency.js:626-677`
- `oil-change.js:210-250`
- `vehicle-management.js:184-220`

All use the same overlay/modal structure with same class names (`modal-overlay`, `open`).

### 4.9 Inconsistent API Error Handling (4 Patterns)

- **Pattern A:** `apiFetch` wrapper (checks `data.success`)
- **Pattern B:** `fetchJSON` in `delivery-plan-builder.js` (checks `resp.ok`)
- **Pattern C:** Raw fetch in `map.js` / `truck-load-planner.js`
- **Pattern D:** `truck-load-planner.js` `API` object (no error handling)

---

## 5. Database & Query Redundancies

### 5.1 N+1 Query in `get_dashboard_data()`

**Severity: HIGH**

`execution_service.py:205-265` — After fetching all assignments with 1 query, iterates over results and executes **2 additional queries per assignment** (current stop + progress counts). For 50 assignments: **101 queries total**.

### 5.2 App.py Opens N+1 DB Connections in Fuel Log Loop

`app.py:2740-2803` — `_compute_fuel_entry()` opens a new `sqlite3.connect()` for **every call**. When `api_fuel_log_list()` iterates over N rows, it opens N+1 connections.

### 5.3 Dynamic SQL Injection Risk

**Severity: Medium**

`plan_service.py:120, 211, 305` and `execution_service.py:54` — Column names are string-interpolated into SQL via f-strings:
```python
set_clause = ", ".join(f"{k} = ?" for k in updates)
```
Currently filtered through `allowed` sets, but fragile.

### 5.4 Migrations Not Reusable

`app.py:249-613` (365 lines) — `init_db()` mixes schema creation, column migrations, and data backfill in one function. Uses bare `except: pass` for column additions, silently swallowing real failures.

---

## 6. Architectural Refactoring Roadmap — 4 Pillars

This section replaces the prior flat list of actions with a structured plan organized around Core OOP Principles (Encapsulation, Polymorphism, Inheritance, Adapters) and AI-readiness. Every proposed change derives directly from the metrics and redundancies documented in Sections 2-5 above.

---

### 6.1 Pillar 1: Encapsulation & Data Integrity

**Goal:** Centralize database access and frontend API/UI helpers into single-authority classes, eliminating scattered connections, duplicated fetch wrappers, and XSS-vulnerable toast functions.

#### 6.1.1 `app/db.py` — `DatabaseManager` Context Manager

**Problem:** 4 copies of `get_conn(db_path)` across `plan_service.py`, `execution_service.py`, `image_service.py`, and `truck_load_planner/routes.py`. One copy (`image_service.py`) omits `PRAGMA foreign_keys = ON`, creating a silent data-integrity bug. Every call opens/closes a raw `sqlite3.Connection`.

**Proposed Solution:**

```python
# app/db.py
from contextlib import contextmanager
import sqlite3

class DatabaseManager:
    """Encapsulates SQLite connections, enforces FK pragma, supports nesting."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._local = threading.local()

    @contextmanager
    def connect(self, enable_fk: bool = True):
        """Yield a connection with PRAGMA foreign_keys = ON (default)."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        if enable_fk:
            conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
```

**Migration Steps:**
1. Create `app/db.py` with `DatabaseManager` class (as above).
2. Create a module-level singleton `db = DatabaseManager(settings.DB_PATH)` in `app/__init__.py`.
3. Replace all 4 `get_conn` functions with `db.connect()` context manager calls.
4. Each route becomes:
   ```python
   with db.connect() as conn:
       rows = conn.execute("SELECT ...").fetchall()
   ```
5. Remove `PRAGMA foreign_keys = ON` from individual migration blocks — it is now enforced globally.
6. Remove the individual `get_conn`/`_get_db` helpers from `plan_service.py`, `execution_service.py`, `image_service.py`, and `truck_load_planner/routes.py`.

**Files affected:** `services/delivery/plan_service.py:9-13`, `execution_service.py:9-13`, `image_service.py:14-17`, `truck_load_planner/routes.py:19-22`, `app.py:249-613` (migration blocks).

#### 6.1.2 `static/js/utils.js` — `ApiClient` & `UI.toast()` Namespace

**Problem:** 6 `showToast` implementations (different parameter orders, inconsistent XSS handling). 3 `apiFetch` wrappers. 4 `escapeHtml` variants (2 missing single-quote escaping). 5 shared utility functions (`todayISO`, `formatDate`, `fmtNum`, `normalizeText`, `getDistanceMeters`) defined independently in 2-3 files each.

**Proposed Solution:**

```javascript
// static/js/utils.js — Encapsulated namespaces

const ApiClient = {
  BASE: '/api',

  async fetch(url, opts = {}) {
    const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
    const resp = await fetch(this.BASE + url, { ...opts, headers });
    const data = await resp.json();
    if (!data.success) throw new Error(data.message || 'Request failed');
    return data;
  },

  async get(path) { return this.fetch(path, { method: 'GET' }); },
  async post(path, body) { return this.fetch(path, { method: 'POST', body: JSON.stringify(body) }); },
  async put(path, body) { return this.fetch(path, { method: 'PUT', body: JSON.stringify(body) }); },
  async del(path) { return this.fetch(path, { method: 'DELETE' }); },
};

const UI = {
  toast(message, type = 'info', duration = 3000) {
    const container = document.getElementById('toast-container')
      || (() => { const d = document.createElement('div'); d.id = 'toast-container'; document.body.append(d); return d; })();
    const el = document.createElement('div');
    el.className = `toast toast-${type}`;
    el.textContent = message;  // Safe: textContent, not innerHTML
    container.appendChild(el);
    setTimeout(() => el.remove(), duration);
  },

  escapeHtml(str) {
    const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
    return String(str).replace(/[&<>"']/g, ch => map[ch]);
  },
};
```

**Migration Steps:**
1. Add `ApiClient` and `UI` objects to `static/js/utils.js`.
2. In each consumer file, replace `apiFetch(...)` → `await ApiClient.fetch(...)` or the shorthand `ApiClient.get/post/put/del`.
3. Replace all `showToast(...)` calls with `UI.toast(message, type, duration)` — standardize parameter order.
4. Replace all `escHtml(...)` / `escapeHtml(...)` calls with `UI.escapeHtml(...)`.
5. Delete local copies of `apiFetch`, `showToast`, `escapeHtml`, `todayISO`, `formatDate`, `fmtNum`, `normalizeText`, `getDistanceMeters`, `isPointInPolygon`.
6. Add `API_BASE = '/api'` constant (prefixed to all `ApiClient.fetch()` calls so URL strings across 6+ files become maintainable).

**Files affected:** `static/js/fuel-efficiency.js`, `oil-change.js`, `vehicle-management.js`, `map.js`, `fuel-sync.js`, `truck-load-planner.js`, `delivery-plan-builder.js`, and `static/js/utils.js` itself.

---

### 6.2 Pillar 2: Polymorphism & Geometry Unification

**Goal:** Replace dead branching with an abstract strategy hierarchy, and merge the two incompatible AABB classes into a single polymorphic type.

#### 6.2.1 `BaseRoutingStrategy` — Polymorphic Profile Resolution

**Problem:** `app.py:702-708` — `get_routing_profile(vehicle_type)` has three branches that all return `"driving-hgv"`. The routing profile cannot be extended for different vehicle types (box truck vs container truck vs reefer) without adding yet another dead branch.

**Proposed Solution:**

```python
# app/routing/strategy.py
from abc import ABC, abstractmethod

class BaseRoutingStrategy(ABC):
    @abstractmethod
    def profile_name(self) -> str: ...
    @abstractmethod
    def max_payload_kg(self) -> float: ...
    @abstractmethod
    def height_restriction_m(self) -> float | None: ...

class HGVStrategy(BaseRoutingStrategy):
    def profile_name(self) -> str: return "driving-hgv"
    def max_payload_kg(self) -> float: return 25000.0
    def height_restriction_m(self) -> float | None: return None

class ContainerStrategy(BaseRoutingStrategy):
    def profile_name(self) -> str: return "driving-hgv"  # same ORS profile
    def max_payload_kg(self) -> float: return 28000.0
    def height_restriction_m(self) -> float | None: return 4.2

# Factory / registry
_strategies: dict[str, type[BaseRoutingStrategy]] = {
    "container": ContainerStrategy,
    "default":   HGVStrategy,
}

def resolve_strategy(vehicle_type: str | None) -> BaseRoutingStrategy:
    cls = _strategies.get((vehicle_type or "").lower(), HGVStrategy)
    return cls()
```

**Migration Steps:**
1. Create `app/routing/__init__.py` and `app/routing/strategy.py`.
2. Replace the hardcoded `get_routing_profile()` function at `app.py:702-708` with a call to `resolve_strategy(vehicle_type).profile_name()`.
3. Extend `_strategies` registry as new vehicle types are introduced — no more `if/elif/else` dead branches.

**Files affected:** `app.py:700-710` (delete `get_routing_profile`), `app.py:720` (ORS call site).

#### 6.2.2 Unified Polymorphic `AABB` Class

**Problem:** Two incompatible AABB classes — `geometry/aabb.py` (basic) and `engine/geometry.py` (superset with clearance, overlap, point containment). Cannot pass one where the other is expected. Transform utilities (`mm_to_px`, `px_to_mm`, `rotate_dimensions`) duplicated in `engine/geometry.py` and `geometry/transform.py`.

**Proposed Solution:**

```python
# truck_load_planner/geometry/aabb.py — SINGLE polymorphic AABB

class AABB:
    __slots__ = ('x_min', 'y_min', 'z_min', 'x_max', 'y_max', 'z_max',
                 'clearance', 'clearance_xy', 'clearance_z')

    def __init__(self, x_min, y_min, z_min, x_max, y_max, z_max,
                 clearance=0, clearance_xy=0, clearance_z=0):
        self.x_min = x_min; self.y_min = y_min; self.z_min = z_min
        self.x_max = x_max; self.y_max = y_max; self.z_max = z_max
        self.clearance = clearance
        self.clearance_xy = clearance_xy
        self.clearance_z = clearance_z

    @classmethod
    def from_dimensions(cls, x, y, z, w, d, h, **kw):
        return cls(x, y, z, x + w, y + d, z + h, **kw)

    def intersects(self, other: 'AABB') -> bool: ...
    def contains(self, other: 'AABB') -> bool: ...
    def contains_point(self, x, y, z) -> bool: ...
    def strictly_contains_point(self, x, y, z) -> bool: ...
    def overlap_area_xy(self, other: 'AABB') -> float: ...
    def translate(self, dx=0, dy=0, dz=0) -> 'AABB': ...
    @property
    def width(self) -> float: return self.x_max - self.x_min
    @property
    def depth(self) -> float: return self.y_max - self.y_min
    @property
    def height(self) -> float: return self.z_max - self.z_min
```

```python
# truck_load_planner/geometry/transform.py — shared transforms (no AABB logic)
def mm_to_px(mm, scale): ...
def px_to_mm(px, scale): ...
def compute_scale(container_mm, container_px): ...
def rotate_dimensions(w, d, h, rotation): ...
```

**Migration Steps:**
1. Merge all methods from `engine/geometry.py` AABB into `geometry/aabb.py`.
2. Delete `engine/geometry.py` AABB class; make `engine/geometry.py` a thin re-export: `from truck_load_planner.geometry.aabb import AABB` + keep only transform functions (later move those to `geometry/transform.py`).
3. Update all imports: `from truck_load_planner.engine.geometry import AABB` → `from truck_load_planner.geometry.aabb import AABB`.
4. Remove duplicated transform functions from `engine/geometry.py` once all callers are migrated.

**Files affected:** `truck_load_planner/geometry/aabb.py`, `engine/geometry.py`, `geometry/transform.py`, plus every file that imports AABB (~15 files in `engine/`, `logistics/`, `session.py`).

---

### 6.3 Pillar 3: Inheritance & Adapter Patterns for Legacy Code

**Goal:** Eliminate the 3 copies of EnginePackage conversion via a factory method, and keep the legacy `logistics/` module operational during migration by wrapping it behind Adapter classes — without modifying active features.

#### 6.3.1 `EnginePackage.from_legacy()` Factory Method

**Problem:** Three separate code paths construct `EnginePackage` with identical field mappings (session.py lines 22-42, session.py lines 45-63, routes.py lines 745-806). Adding a new field (e.g., `hazardous_class`) requires editing all three.

**Proposed Solution:**

```python
# truck_load_planner/engine/package.py (add to existing class)

class EnginePackage:
    # ... existing fields ...

    @classmethod
    def from_legacy(cls, source: dict, *, prefix: str = "") -> 'EnginePackage':
        """Single factory for all dict-to-package conversions.
        
        Supports both 'length_mm' and 'length' naming conventions,
        making it source-format agnostic.
        """
        def _val(*keys: str) -> Any:
            for k in keys:
                v = source.get(prefix + k) or source.get(k)
                if v is not None:
                    return v
            return None

        return cls(
            name=_val("name") or "Unnamed",
            length_mm=_val("length_mm", "length"),
            width_mm=_val("width_mm", "width"),
            height_mm=_val("height_mm", "height"),
            weight_kg=_val("weight_kg", "weight", "weight_kg"),
            stackable=_val("stackable") or True,
            allow_rotation=_val("allow_rotation", "allowRotation"),
            fragile=_val("fragile") or False,
            color=_val("color") or "#3b82f6",
            horizontal_clearance_mm=_val("horizontal_clearance_mm", "clearance") or 10,
            max_top_weight_kg=_val("max_top_weight_kg", "max_top_weight"),
            max_stack_layers=_val("max_stack_layers", "maxStackLayers") or 0,
        )
```

**Migration Steps:**
1. Add the `from_legacy` classmethod to `truck_load_planner/engine/package.py`.
2. Replace the inline construction in `session.py:_to_engine_pkg()` and `_from_legacy_dict()` with `EnginePackage.from_legacy(d)`.
3. Replace the inline construction in `routes.py:_get_packages_from_request()` with `EnginePackage.from_legacy(pkg_dict)`.
4. Delete the now-unnecessary wrapper functions after verifying no other callers.

**Files affected:** `truck_load_planner/engine/package.py` (add method), `session.py:22-63` (simplify), `routes.py:745-806` (simplify).

#### 6.3.2 Adapter Wrappers for `truck_load_planner/logistics/`

**Problem:** The entire `logistics/` module (5 files, 312 lines) is redundant with `engine/`, but `session.py` actively imports from it (lines 18-19). Deleting `logistics/` outright would break `session.py`. Features that depend on legacy dict-based validation paths would fail.

**Proposed Solution — Adapter Pattern:**

```python
# truck_load_planner/logistics/adapters.py — NEW FILE

from truck_load_planner.engine.boundary import check_boundary as _engine_check_boundary
from truck_load_planner.engine.weight import calculate_total_weight as _engine_calc_weight
from truck_load_planner.engine.validation import validate_placement as _engine_validate

# --- Boundary Adapter ---
def check_boundary(placement: dict, container_aabb) -> list[str]:
    """Adapter: legacy dict → engine object, then delegate."""
    from truck_load_planner.engine.placement import Placement
    # ... convert dict to Placement, delegate to _engine_check_boundary ...
    return _engine_check_boundary(engine_placement, container_aabb)

# --- Weight Adapter ---
def calculate_total_weight(packages: list[dict]) -> float:
    """Adapter: list[dict] → list[EnginePackage], then delegate."""
    from truck_load_planner.engine.package import EnginePackage
    engine_pkgs = [EnginePackage.from_legacy(p) for p in packages]
    return _engine_calc_weight(engine_pkgs)
```

**Migration Steps:**
1. Create `truck_load_planner/logistics/adapters.py` with thin Adapter classes/functions.
2. Update each legacy file (`boundary.py`, `weight.py`, `volume.py`, `placement.py`, `constraints.py`) to import from `adapters.py` and delegate to `engine/` under the hood.
3. The public API (function signatures, return types) remains identical — `session.py` and any other callers continue working without changes.
4. Once no code outside `logistics/` imports directly from legacy files (only from `adapters.py` or `engine/`), the legacy files can be deprecated with a `warnings.warn("Use engine/ module", DeprecationWarning)`.
5. After a full cycle of verification, delete the 5 legacy files and rename `adapters.py` → `__init__.py` to complete the migration.

**Files affected:** NEW `truck_load_planner/logistics/adapters.py`. Legacy files `boundary.py`, `weight.py`, `volume.py`, `placement.py`, `constraints.py` — internal delegation changed, public API preserved.

---

### 6.4 Pillar 4: Modular Split & AI Token Optimization

**Goal:** Break down the two largest monolith files (`app.py` at 3,625 lines and `truck_load_planner/routes.py` at 1,014 lines) into focused sub-packages so that AI agents and human developers can load only the module they need — reducing per-task token consumption and improving navigation.

#### 6.4.1 Extract `app/` Sub-Package from `app.py`

**Current state:** A single file containing 65+ routes, database initialization, 10+ helper functions, geocoding, TTAS integration, CSV export, and background thread management.

**Step-by-step extraction plan:**

| Phase | New File | Content Extracted | Est. Lines Removed from `app.py` |
|-------|----------|-------------------|----------------------------------|
| 1 | `app/__init__.py` | App factory `create_app()`, blueprint registration, secret key, CORS | ~30 |
| 2 | `app/config.py` | All env var reads, constants, hardcoded defaults (oil interval, anomaly multipliers, distance thresholds) | ~50 |
| 3 | `app/db.py` | `DatabaseManager` class (see §6.1.1) | ~40 |
| 4 | `app/database/schema.py` | All `CREATE TABLE IF NOT EXISTS` statements | ~100 |
| 5 | `app/database/migrations.py` | Column migration blocks, data backfill (vehicle_trips rename, fuel_log → vehicles) | ~150 |
| 6 | `app/utils/geo.py` | `get_distance_meters`, `calculate_polygon_centroid`, `is_point_in_polygon`, `get_location_centroid`, `safe_float`, `clean_text` | ~150 |
| 7 | `app/utils/export.py` | CSV export helper (reusable for oil + fuel endpoints) | ~40 |
| 8 | `app/services/ttas_client.py` | TTAS login, session cookie fetch, `_fetch_ttas_report_page`, `_parse_ttas_total_km` (shared with `main.py`) | ~120 |
| 9 | `app/routes/fleet.py` | Vehicle CRUD (`api_vehicles_list`, `api_vehicles_get`, `api_vehicles_create`, `api_vehicles_update`, `api_vehicles_delete`, `api_vehicle_types_list`) | ~120 |
| 10 | `app/routes/fuel.py` | Fuel log CRUD + sync (`api_fuel_log_list`, `api_fuel_log_create`, `api_fuel_log_update`, `api_fuel_log_delete`, `api_fuel_log_export`, `api_fuel_sync`) | ~250 |
| 11 | `app/routes/oil.py` | Oil maintenance CRUD (`api_oil_maintenance_list`, `api_oil_maintenance_create`, `api_oil_maintenance_update`, `api_oil_maintenance_delete`, `api_oil_maintenance_export`, `api_oil_maintenance_fetch_km`) | ~200 |
| 12 | `app/routes/trips.py` | Trip management (`set_destination`, `api_advance_trip`, `api_cancel_trip`, `api_trip_history`, `do_refresh_route_data`) | ~350 |

**After all phases:** `app.py` shrinks from ~3,625 lines to ~1,500 lines (app factory + remaining route files that can be extracted in future iterations). Each sub-module is independently loadable — AI agents editing fuel logic only need `app/routes/fuel.py` + `app/db.py` + `app/config.py`, not the entire 3,625-line file.

#### 6.4.2 Extract `truck_load_planner/routes.py` (1,014 lines)

| Phase | New File | Content |
|-------|----------|---------|
| 1 | `tlp/db.py` | Shared `get_conn()` / `DatabaseManager` instance (see §6.1.1) |
| 2 | `tlp/routes/__init__.py` | Blueprint creation, shared error handlers |
| 3 | `tlp/routes/container_configs.py` | Container config + features CRUD |
| 4 | `tlp/routes/packages.py` | Package + shipment + shipment item CRUD |
| 5 | `tlp/routes/load_plans.py` | Load plan CRUD, placement CRUD, session validation |
| 6 | `tlp/routes/auto_arrange.py` | Auto-arrange endpoint, fleet distribution, cost computation |
| 7 | `tlp/services/auto_arrange_service.py` | Business logic extracted from auto_arrange route |

#### 6.4.3 Extract `plan_service.py` Excel Pipeline

Move `parse_excel_rows()`, `confirm_import()`, and related Excel logic from `services/delivery/plan_service.py` (551 lines) into `services/delivery/import_service.py`. The core `plan_service.py` retains plan/assignment/stop CRUD.

---

## 7. Scalability Concerns

### 7.1 No Connection Pooling

Every route opens/closes `sqlite3.connect()` manually. Under concurrent users, this creates contention on the single SQLite file. **Recommendation:** Use a connection factory with `check_same_thread=False` or migrate to PostgreSQL.

**Update 2026-07-31 — the contention is currently masked, not absent.** `render.yaml` runs
`gunicorn wsgi:app` with no `--workers`/`--threads`, so production is a *single synchronous
worker*: requests queue rather than contend, and this concern has never actually been
exercised. That queueing is itself a user-visible problem — `/api/execution/dashboard`
performs a blocking TTAS HTTP fetch inside the request, so a dispatcher action landing
mid-poll waits behind it (see the 2026-07-31 CHANGELOG entry on click latency).

The trap: raising worker or thread count is a one-line `startCommand` change that
immediately converts that latency into the contention described above, because no
`PRAGMA journal_mode=WAL` is configured anywhere. **WAL first, concurrency second** — they
are one decision, not two, and item 23 below should be read that way.

### 7.2 Global Mutable State

- `truck_load_planner/routes.py:15` — `DB_PATH = None` module-level global
- `tracking_service.py:6-7` — Module-level cache globals (`_ttas_vehicles_cache`, `_cache_timestamp`)

Neither is thread-safe.

### 7.3 No Dependency Injection

Every service function takes `db_path: str` and creates its own connection. This makes unit testing difficult (requires a real SQLite file) and prevents connection pooling.

### 7.4 12-Second Polling (No WebSockets/SSE)

The delivery dashboard polls every 12 seconds. For 10 concurrent users, this generates **50 requests/minute** just for dashboard updates. **Recommendation:** Implement Server-Sent Events or WebSocket for real-time updates.

### 7.5 Monolithic CSS

`static/css/style.css` (1,270+ lines) — all styles in one file. Should be split into partials as the app grows.

### 7.6 No Build Step

All 17 JS files are served as individual script tags. No bundling, no tree-shaking. Should consider Vite or esbuild.

### 7.7 `app.py` Bare `except:` Blocks

Multiple locations use bare `except:` (catches `SystemExit`, `KeyboardInterrupt`):

| Line | Pattern |
|------|---------|
| 943 | `try: waypoints = json.loads(waypoints_raw) except: waypoints = []` |
| 949 | `try: db_phase = int(...) except: db_phase = 1` |
| 1087 | `try: current_speed = float(...) except: pass` |
| 1102 | `try: ... except: waypoints = []` |

### 7.8 Hardcoded Values That Should Be Configurable

| Value | Location | Recommended Env Var |
|-------|----------|-------------------|
| `timeout=30` (ORS) | `eta_service.py:30` | `ORS_TIMEOUT` |
| `"dev-secret-key-change-in-production"` | `app.py:1202` | `SECRET_KEY` (required in production) |
| `2000` (distance warning) | `app.py:3131` | `MAX_DISTANCE_WARNING_KM` |
| `1.50` / `1.20` (anomaly multipliers) | `app.py:2884` | `ANOMALY_MULTIPLIER_*` |
| `5000` (default oil interval) | `app.py:74, 2140` | `DEFAULT_OIL_INTERVAL_KM` |

---

## 8. Cleanup Actions Taken

The following temporary/test-generated files were removed:

| File | Reason |
|------|--------|
| `test_app3.log` | Test run log output |
| `test_app3_err.log` | Test run error log |
| `instrument_trace.jsonl` | Instrumentation trace from manual tests |
| `stash_diff.txt` | Git stash diff artifact |
| `DeliveryPlans/2026/07/26/TEST-01/` (18 JPGs, 3 dirs) | Test delivery plan upload artifacts (plan name is "TEST-01") |
| `__pycache__/` (project `__pycache__` dirs) | Python bytecode cache (1.2GB in .venv/venv left untouched) |
| `.pytest_cache/` | Pytest cache directory |

**Not removed** (intentionally):
- `venv/` and `.venv/` — Python virtual environments
- `tests/` directory — contains actual test source code
- `reports/` directory — empty, kept for future use
- `truck_load_planner/logistics/` — legacy code reviewed but not deleted (needs migration plan)

---

## 9. Priority Action Items

All items below map to the [4 Pillar Framework](#6-architectural-refactoring-roadmap--4-pillars). Each carries an estimated effort, pillar alignment, and token-optimization benefit.

**Status as of 2026-07-29**: Phases 1–3 and most of Phase 4 are done — see `CHANGELOG.md`'s 2026-07-29 entry for exactly what was built, what was verified, and 2 real bugs the work caught before they hit production. Items marked ⬜ Pending are still open; a few (9, 10, 12, 16, 21, 22) were deliberately left out of the sessions that did 1–8/13–15/17–20, not forgotten.

**Addendum 2026-07-31**: none of the items in this table moved, but three things happened
around them that change how they should be read.

- **Item 23 (concurrency) is now blocked on WAL, and the blocker is documented in §7.1.** Production
  turned out to be a single synchronous Gunicorn worker, which hides the pooling problem
  behind request queueing and produces a user-visible latency problem instead.
- **A route-layer test suite now exists** (`tests/test_delivery_routes.py`). This
  report's §5 testing analysis predates it; the delivery module is no longer service-tested
  only.
- **Authentication was added and then removed the same day.** The delivery module is
  deliberately unauthenticated — see `docs/DELIVERY_MODULE.md` § Key Design Decisions #7
  before treating that as a finding. It is the one item in this codebase where the "obvious
  improvement" has already been made, reverted, and recorded.

**Addendum 2026-08-03**: still no movement in the table, but two things bear on §3.9
(duplicated TTAS handling) and on how §5's testing analysis should be read.

- **The duplicated TTAS speed extraction was a live bug, not just duplication.**
  `tracking_service._parse_speed_kmh` and `app/routes/trips.py` (the `current_speed`
  block, line 403 as of 2026-08-06) both took the first
  number out of TTAS's speed *phrase*. For a stopped vehicle that phrase counts parking
  time (`Dừng 3h30'`), so the dashboard reported a parked truck as doing 3 km/h, rising
  the longer it sat. Fixed in `tracking_service`; **`trips.py` still has it**. Worth
  raising above "housekeeping" — the two copies had already drifted in their `None`
  vs `0` semantics, which is exactly how one got fixed and the other did not.
- **Test totals in this report are point-in-time and go stale fast.** `pytest tests/` is
  491 as of 2026-08-03 (was 254 when this was written). Treat any count here as an
  artefact of its date; `README.md` § Running Tests carries the current figures.

The wider audit that drove that work is `docs/DELIVERY_AUDIT_2026-07-31.md`, which is a
separate, delivery-specific document; this report remains the whole-codebase view.

**Addendum 2026-08-06** (documentation pass; no code changed): still no movement in the
Priority Action Items table. Three corrections and one new observation.

- **`pytest tests/` is 491 and passes clean**, re-run 2026-08-06. Breakdown:
  `test_delivery.py` 223, `test_delivery_routes.py` 135, `test_vehicle_specs.py` 40,
  `test_vehicle_core_data.py` 36, `test_scorer.py` 26, `test_routing.py` 15,
  `test_fleet_routes.py` 11, `test_auto_arrange_e2e.py` 5. `test_all.py` collects but
  asserts nothing — it is an argparse CLI that happens to match pytest's discovery glob.
- **`test_delivery_routes.py` has an undeclared hard dependency on `playwright`.** It
  reaches the app through `main.py`, which imports `playwright` at module level, so
  without the package installed all 135 tests error on import rather than failing on
  anything real. Worth noting next to §5's testing analysis: the route suite is the one
  that catches handler-level bugs, and it is also the one that silently disappears on a
  fresh environment.
- **The frontend jsdom suites are 122 + 10, not 112 + 10.** Counts in `README.md`,
  `CLAUDE.md` and `DELIVERY_MODULE.md` had drifted; corrected 2026-08-06. One dashboard
  ETA case is time-of-day dependent — it asserts a 36-hour ETA renders `+1d`, but
  `UI.etaClock()` counts calendar days crossed, so from 12:00 local onwards it correctly
  renders `+2d` and the assertion fails. The test is wrong, not the code; the fix is the
  injectable clock §7 has wanted for other reasons.
- **§2.6 (untracked temporary/generated files) has grown a new instance.** The working
  tree carries whole-file diffs on ~40 source files that are pure CRLF/LF line-ending
  churn, which buries the two real uncommitted changes. A `.gitattributes` with
  `* text=auto` would settle it. Noted, not actioned — outside this pass's scope.

**Addendum 2026-08-06b** (whole-workspace audit; code changed). Full findings in
`docs/AUDIT_2026-08-06.md`, plan in `docs/BUGFIX_PLAN_2026-08-06.md`, concurrency
measurements in `docs/CONCURRENCY_PLAN_2026-08-06.md`. Still no movement in the Priority
Action Items table — none of these were table items. Six fixes landed:

- **Two Criticals, both inside a request handler.** `POST /api/tlp/auto-arrange` with a
  `shipment_id` returned an unhandled 500 for the endpoint's whole life (aliased column
  vs. `Package.from_row`'s `row["name"]`), with a wrong-`package_id` defect hidden behind
  it. And `app/routes/trips.py`'s geofence loop opened an explicit `BEGIN` inside a
  per-trip `for`, which cannot work — the driver-name `UPDATE` above it had already opened
  an implicit transaction, and on the non-arrival path nothing committed, so the next
  iteration collided too. The per-trip `except` swallowed both, so trips silently stopped
  advancing. **Both lived where a service-level suite is structurally blind**, which is the
  same lesson §5 and `DELIVERY_AUDIT_2026-07-31.md` already record.
- **`static/js/truck-load-planner.js` had zero HTML escaping.** Item 1 in the Phase 1 table
  above is marked "✅ Done — Eliminates XSS gap". That was true of every page *except* this
  one, which the 2026-07-29 refactor missed: 0 `escapeHtml` calls against 28 in
  `delivery-plan-builder.js`, while interpolating package and customer names into
  `innerHTML`. Now 13 sites escaped, guarded by a dependency-free `tests/js/tlp-escaping.test.js`.
  **Item 1's status is accurate about what was built and misleading about the outcome**; read
  it as "the utilities exist and are adopted on 11 of 12 files".
- **22 write handlers leaked their connection on the exception path** (`conn.close()` after
  the happy path, skipped by the `except`). Fixed with `finally` for write handlers only;
  read-only handlers deliberately left alone (operator's scope call). Relevant to item 7:
  `app/routes/*.py` still uses raw `sqlite3.connect()` and was still not migrated to
  `DatabaseManager` — that split remains deliberate.
- **`GET /api/fuel-log` opened ~1,900 connections per request.** Four helpers per row, each
  opening its own. Measured on live data: 1,900 connections / 591 ms → 1 / 31 ms. This is a
  second instance of item 8's N+1 pattern, in a module item 8 never looked at.
- **`DELETE /api/tlp/packages/<id>` left orphaned rows** — no `ON DELETE CASCADE` and
  `enable_fk=False`, both deliberate, so the cascade has to be manual and wasn't.

**Testing.** `pytest tests/` is now **548** (was 491), all passing. Four new route-layer
files: `test_write_handler_connections.py` (36), `test_tlp_routes.py` (8),
`test_trips_geofence.py` (7), `test_fuel_routes.py` (6). Before them the truck load
planner, `app/routes/trips.py` and `app/routes/fuel.py` had no coverage that issued a
request. JS drives are now 137 (122 + 10 + 5).

**Corrections to the previous addendum:**

- `playwright` is **not** an undeclared dependency — it is pinned in `requirements.txt`
  (`playwright==1.61.0`). The file is UTF-16, so `grep` finds nothing and reports the
  opposite, which is how the claim got in. The failure mode it describes is real; the
  cause is a stale environment, not a missing declaration.
- The CRLF churn noted under §2.6 is confirmed and **larger than stated**: 105 files, not
  ~40, and it affects the whole tree rather than a subset. `core.autocrlf` is unset and
  there is no `.gitattributes`. Still not actioned — a repo-wide renormalisation is its
  own deliberate commit.

**One §2.6-adjacent finding worth recording:** git cannot create commits through the
agent's mount, because it can create its `*.lock` files but not unlink them, leaving each
one to block the next command. `scripts/commit_audit_fixes.py` exists so the commits can
be made from Windows instead. Any future automation that writes to `.git` from that side
will hit the same wall.

**Addendum 2026-08-15** (documentation pass; no code changed). Still no movement in the
Priority Action Items table. Numbers re-measured against the working tree, not carried
forward:

- **`pytest tests/` collects 676.** Breakdown: `test_delivery.py` 223,
  `test_delivery_routes.py` 143, `test_sheet_import.py` 79, `test_vehicle_specs.py` 40,
  `test_vehicle_core_data.py` 36, `test_write_handler_connections.py` 36,
  `test_sheet_import_routes.py` 26, `test_scorer.py` 26, `test_routing.py` 15,
  `test_trips_geofence.py` 14, `test_fleet_routes.py` 11, `test_tlp_routes.py` 8,
  `test_wsgi_routes.py` 8, `test_fuel_routes.py` 6, `test_auto_arrange_e2e.py` 5.
  `test_all.py` still collects zero — 5 argparse subcommands over 17 modes, no `def
  test_`. JS drives are **194** across six suites.
- **129 HTTP endpoints** over 7 blueprints: `delivery` 44, `tlp` 28, `fuel` 18, `core` 14,
  `fleet` 12, `oil` 9, `trips` 4. 11 page routes over 9 templates.
- **§7.2's global mutable state grew.** `app/state.py` gained `route_refresh_lock`,
  `route_cache_refreshed_at` and `route_refresh_attempted_at` for the on-demand route
  rebuild that `GET /api/route-data` now performs. The reason is the one §7.2 already
  names: state is process-global and the background refresher only runs under `python
  app.py`, so under Gunicorn nothing filled the cache on a cold start. Three locks now
  have to be settled before `--workers`, not two.
- **The `trips.py` geofence loop is gone** (deleted 2026-08-10), so the transaction bug
  recorded in addendum 2026-08-06b is no longer reachable. `tests/test_trips_geofence.py`
  grew 7 → 14 and its job is now to assert the code stays deleted; the file name is
  historical.
- **The `current_speed` first-number-wins regex is still there**, now at
  `app/routes/trips.py:410`. Unchanged since 2026-08-06 and still the only remaining copy
  of the bug fixed in `tracking_service`.
- **`database.sql` no longer mirrors the live database.** Schema still matches (25 tables),
  and so do `vehicles` (36) and `fuel_log` (323), but `delivery_plan_stops` holds 52 rows
  in the dump against several hundred live. It is a 2026-08-03 snapshot. §2.6's point
  about it carrying real operational data in a tracked file stands.
- **`graphify-out/graph.json` is behind HEAD** — `built_at_commit` `569c0fe`, five commits
  back, with uncommitted work on top. 3,131 nodes · 5,997 edges · 137 files.

### Phase 1: Immediate Wins (Pillars 1 & 3) — High Impact, Low Effort

| # | Action | Pillar | Effort | Impact | Status |
|---|--------|--------|--------|--------|--------|
| 1 | Create `ApiClient` + `UI.toast()` in `utils.js`; remove 6 toast / 3 fetch / 4 escapeHtml copies | Encapsulation | 1.5h | Eliminates XSS gap, standardizes all frontend API calls | ✅ Done |
| 2 | Add `EnginePackage.from_legacy()` factory; replace 3 inline construction sites | Inheritance | 1h | Single source of truth for package mapping | ✅ Done (4 sites — session.py had 2, not 1) |
| 3 | Delete 4 dead functions in `tracking_service.py` | (housekeeping) | 15m | Removes confusion, reduces token waste | ✅ Done |
| 4 | Remove 4 shadowed functions from `map.js` (rely on `utils.js`) | (housekeeping) | 15m | Eliminates dead code, reduces file size | ✅ Done |
| 5 | Move shared JS utils (`todayISO`, `formatDate`, `fmtNum`, `normalizeText`, `getDistanceMeters`) to `utils.js` | Encapsulation | 1h | Single import for all utility needs | ✅ Done |
| 6 | Add `API_BASE = '/api'` constant; update 6+ files | Encapsulation | 30m | API prefix becomes configurable in one place | ✅ Done |

### Phase 2: Structural Foundations (Pillars 1 & 4) — High Impact, Medium Effort

| # | Action | Pillar | Effort | Impact | Status |
|---|--------|--------|--------|--------|--------|
| 7 | Create `app/db.py` `DatabaseManager`; replace 4 raw `get_conn()` copies | Encapsulation | 2h | FK enforcement globally, data integrity bug fixed, connection logic centralized | ✅ Done — `truck_load_planner/routes.py` connections deliberately keep `enable_fk=False` (see §6.1.1 note); `app/routes/*.py` (new in Phase 4) still use raw `sqlite3.connect()`, not migrated |
| 8 | Fix N+1 query in `get_dashboard_data()` (101 queries → 3) | (performance) | 2h | 100x query reduction under load | ✅ Done — verified 13→3 queries on real data |
| 9 | Extract 5 copies of stop+execution JOIN into shared helper | Encapsulation | 2h | One place to update for schema changes | ⬜ Pending |
| 10 | Extract 3 copies of stop-insert + execution-create into `create_stop_with_execution()` | Encapsulation | 1h | Eliminates triple-maintenance | ⬜ Pending |
| 11 | Create `BaseRoutingStrategy` + `resolve_strategy()`; replace dead `get_routing_profile()` | Polymorphism | 1h | Dead branch eliminated, vehicle profiles extensible | ⬜ Pending — `get_routing_profile()` moved to `app/services/routing.py` as-is; still has the dead branches |
| 12 | Extract Excel import from `plan_service.py` → `import_service.py` | Modular Split | 2h | plan_service drops ~150 lines, clearer separation | ⬜ Pending |

### Phase 3: Geometry & Legacy (Pillars 2 & 3) — High Impact, Higher Effort

| # | Action | Pillar | Effort | Impact | Status |
|---|--------|--------|--------|--------|--------|
| 13 | Unify AABB: merge `engine/geometry.py` features into `geometry/aabb.py`; thin re-export | Polymorphism | 3h | Single AABB class with clearance, overlap, point containment | ✅ Done — zero import-site changes needed, verified against the real-data benchmark before/after |
| 14 | Create Adapter wrappers in `logistics/adapters.py` delegating to `engine/` | Inheritance | 3h | Legacy callers keep working; migration path opened | ✅ Done for `check_boundary`/`calculate_total_weight`/`check_weight` only — `volume.py` and `constraints.py::get_door_status` have no engine equivalent to delegate to (see adapters.py's own docstring for why), `placement.py::try_place` is confirmed dead code |
| 15 | Consolidate duplicated transform functions into `geometry/transform.py` | Polymorphism | 1h | Eliminates `mm_to_px`/`px_to_mm` duplication | ✅ Done (bundled into item 13's `engine/geometry.py` re-export) |
| 16 | Extract autocomplete + modal open/close patterns into reusable helpers | Encapsulation | 3h | Eliminates 3x pattern duplication across JS files | ⬜ Pending |

### Phase 4: Modular Split (Pillar 4) — Foundation for AI Optimization

| # | Action | Pillar | Effort | Token Savings | Status |
|---|--------|--------|--------|---------------|--------|
| 17 | Extract `app/config.py`, `app/utils/geo.py`, `app/utils/helpers.py` from `app.py` | Modular Split | 3h | ~240 lines removed from monolithic context | ✅ Done — `app/utils/export.py` instead of `helpers.py` (holds the new shared `csv_response()` helper) |
| 18 | Extract `app/database/schema.py` + `app/database/migrations.py` from `app.py` | Modular Split | 2h | ~250 lines removed | ✅ Done — verified byte-identical DB output vs. the original `init_db()` on a fresh DB and a real production copy |
| 19 | Extract `app/services/ttas_client.py` from `app.py` (share with `main.py`) | Modular Split | 2h | ~120 lines removed | ✅ Done |
| 20 | Extract `app/routes/fleet.py` + `fuel.py` + `oil.py` + `trips.py` from `app.py` | Modular Split | 6h | ~920 lines moved to focused route files | ✅ Done — `app.py` went 3,625 → 225 lines (more than planned: `app/state.py` and `app/services/locations.py` also had to be split out, and the location/geocoding/index routes stayed in `app.py` as the "core" remainder, matching this table's own original wording) |
| 21 | Split `truck_load_planner/routes.py` into `tlp/routes/` sub-modules | Modular Split | 4h | 1,014-line file → 5 focused ~200-line files | ⬜ Pending — only its connection management was migrated (item 7), not a module split |
| 22 | Retire `logistics/` legacy files after Adapter migration confirmed | Inheritance | 1h | 5 files, 312 lines of dead code eliminated | ⬜ Pending — intentionally not done; 2 of the 5 files (`volume.py`, `constraints.py`) are still the live, un-adapted implementation (see item 14) |

### Phase 5: Long-Term Architecture

| # | Action | Pillar | Effort | Impact | Status |
|---|--------|--------|--------|--------|--------|
| 23 | Add connection pooling or migrate from SQLite | Encapsulation | 1-2w | Concurrent user support | ⬜ Pending — **premise corrected 2026-08-06.** This cell said raising worker count would "convert queueing latency straight into lock errors" and that WAL was the prerequisite. Measured: `database is locked` is writer-vs-writer and **WAL does not fix it**; a held write lock does not block readers at all. WAL is worth enabling for throughput (2.3× reads), and the actual blocker on `--workers` is that `app/state.py` is process-global. See `docs/CONCURRENCY_PLAN_2026-08-06.md` |
| 24 | Implement SSE/WebSocket for dashboard | (performance) | 1w | Eliminates polling overhead | ⬜ Pending |
| 25 | Add JS build step (Vite/esbuild) | (tooling) | 2d | Bundling, tree-shaking, ES modules | ⬜ Pending |
| 26 | Split CSS into partials | (tooling) | 1d | Maintainability | ⬜ Pending |
| 27 | Secure dynamic UPDATE SQL with query builder | Encapsulation | 1d | Eliminates SQL injection risk | ⬜ Pending — **no live injection exists.** All 26 dynamically-built queries were inspected individually 2026-08-06: every interpolated fragment is composed from literals or `','.join('?' * n)` placeholder runs, and user values always arrive as `?` parameters. This item is about defence in depth, not an open vulnerability |
| 28 | Write `CLAUDE.md` and directory-level `README.md` files | AI Ops | 2h | Reduces token waste — see §10 | ✅ Done — root `CLAUDE.md` only; directory-level `README.md` files (§10.2) not written |

## 10. AI Context & Token Optimization Strategy

**Problem:** AI agents (Claude, Copilot, etc.) load entire files into context. A 3,625-line `app.py` consumes ~8,000-10,000 tokens just for navigation overhead. When an agent needs to edit a fuel-log route, it wastes tokens processing trip management, oil maintenance, geocoding helpers, and TTAS scraping code that are irrelevant to the task.

**Goal:** Structure the project so that an AI agent can understand and edit any single domain by loading **<500 lines of context** (the domain module + shared base classes), instead of the current 3,000+.

### 10.1 Lean Root `CLAUDE.md` (<150 lines)

Create a `CLAUDE.md` at the project root that gives an AI agent **only** what it needs to navigate:

```markdown
# Fleet Fuel Management — AI Context

## Project structure (key dirs)
- `app/` — Flask application (routes, db, utils, services)
- `truck_load_planner/` — 3D cargo packing engine (geometry, engine, logistics)
- `services/delivery/` — Delivery plan management (CRUD, execution, tracking)
- `static/js/` — Frontend JS (utils.js: ApiClient + UI namespace)
- `templates/` — Jinja2 HTML templates
- `tests/` — Pytest test suite

## Key architectural decisions
- SQLite with `DatabaseManager` context manager (see app/db.py)
- No ORM — raw SQL with row factory
- Blueprint-based Flask routes in app/routes/
- Frontend uses ApiClient.fetch() for all API calls (see static/js/utils.js)

## How to run
- `python app.py` — development server on port 5000
- `pytest tests/` — run all tests
- Environment variables in .env (ORS_API_KEY, DB_PATH, etc.)

## Common tasks
- Adding a DB column: update app/database/schema.py + migrations.py
- Adding an API route: add to app/routes/<domain>.py
- Modifying the packing engine: work within truck_load_planner/engine/
- Legacy module: truck_load_planner/logistics/ — prefer engine/ equivalents

## Token optimization
- Each route module in app/routes/ is independently editable (~200-300 lines)
- Utils in app/utils/ are pure functions with no side effects
- See CODEBASE_ANALYSIS_REPORT.md for full refactoring roadmap
```

### 10.2 Directory-Level README.md Files

Place concise `README.md` in each major sub-package so AI agents can discover the module's purpose without scanning every file:

| Directory | README Content |
|-----------|----------------|
| `truck_load_planner/engine/` | Lists each module's responsibility (boundary, collision, scorer, etc.) and the dependency DAG |
| `truck_load_planner/geometry/` | Explains the unified AABB class, transform utilities, and how clearance parameters work |
| `truck_load_planner/logistics/` | Deprecation warning + link to `engine/` equivalent + `adapters.py` documentation |
| `services/delivery/` | Entity relationship: Plan → Assignment → Stop → Execution. Lists which service owns which query |
| `app/routes/` | Maps each route file to its URL prefix and the template it serves |
| `tests/` | Explains test organization: `test_all.py` (integration), `test_scorer.py` (unit), `test_delivery.py` (unit) |
| `static/js/` | Documents the `ApiClient` and `UI` namespace contracts so new JS files import from `utils.js` instead of redefining |

### 10.3 Module Isolation Guidelines

1. **Maximum file size target:** 300 lines per module. Any file exceeding 500 lines should be split.
   - Current violations: `app.py` (3,625), `truck_load_planner/routes.py` (1,014), `services/delivery/plan_service.py` (551), `static/js/truck-load-planner.js` (3,126+).
2. **One domain per route file:** No route file should handle entities from different aggregates (e.g., fuel CRUD and oil CRUD belong in separate files).
3. **Shared utilities in `utils/` only:** No duplicated helper functions across domain files — if a helper is used in two places, it belongs in `app/utils/` or `static/js/utils.js`.
4. **Flat import chains:** A module should import from at most one level of abstraction above it (route → service → engine, never route → engine → route).
5. **AI-first naming:** Use explicit names over abbreviations (`validate_placement` rather than `val_pl`), because AI models match semantic meaning better than abbreviated tokens.

### 10.4 Token Budget for Common AI Tasks

| Task | Files Needed (After Refactor) | Est. Token Cost |
|------|-------------------------------|-----------------|
| Add fuel-log column | `app/db.py` + `app/routes/fuel.py` + `app/database/schema.py` | ~800 tokens |
| Fix delivery N+1 query | `app/db.py` + `services/delivery/execution_service.py` | ~500 tokens |
| Add vehicle type | `app/db.py` + `app/routes/fleet.py` | ~400 tokens |
| Modify packing scorer | `truck_load_planner/geometry/aabb.py` + `engine/scorer.py` | ~350 tokens |
| Add new JS page | `static/js/utils.js` + new page file + template | ~600 tokens |
| Current (before refactor): load entire `app.py` | 1 file | **~8,000-10,000 tokens** |

**Token savings after Phase 4:** **~90%** reduction in per-task context (from 10K to ~500-800 tokens).
