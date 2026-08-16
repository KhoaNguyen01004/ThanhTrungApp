# Graph Report - Solution  (2026-08-07)

## Corpus Check
- 141 files · ~582,208 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 3131 nodes · 5997 edges · 200 communities (174 shown, 26 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 140 edges (avg confidence: 0.53)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `569c0fe9`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- truck_load_planner/routes.py
- delivery/routes.py
- Package
- _create_plan
- Container
- GoogleSheetService
- delivery-plan-builder.js
- TestRevertEndpoint
- fuel.py
- auto_arrange.py
- oil.py
- js/map.js
- LoadPlannerApp
- trips.py
- fuel-efficiency.js
- vehicle-management.js
- test_all.py
- AABB
- LoadPlanningSession
- TestDayExport
- normalize_plate
- Bug-fix plan — findings of `docs/AUDIT_2026-08-06.md`
- PlanningState
- models/__init__.py
- app/__init__.py
- Planner
- TestEtaService
- main.js
- timeline.js
- app.py
- locations.js
- fleet.py
- with_gps
- Vehicle-Constrained Routing — Plan
- patch
- UI
- api.js
- dashboard/map.js
- migrations.py
- _MutationLogger
- vehicle-list.js
- Delivery Module — Documentation
- TestPlanDriverOverride
- Truck Load Planner — Algorithm, API & Frontend Reference
- Delivery / Dispatch Module — Architecture & Bug Audit
- ContainerConfig
- fuel-sync.js
- grid.py
- polling.js
- opencode.json
- vehicle_identity.py
- graphify.js
- routes/__init__.py
- app/services/__init__.py
- utils/__init__.py
- profile.py
- DatabaseManager
- Changelog
- BÁO CÁO KIẾN TẬP THỰC TẾ
- ttas_client.py
- 3. Phase 0 — frontend only, no schema change  ✅ shipped
- vehicle_cost.py
- Fleet Fuel Management — AI Context
- execution_service.py
- Added
- 6. Architectural Refactoring Roadmap — 4 Pillars
- Added
- 3. Python Backend Redundancies
- Added
- Changed
- Added
- Changed
- Codebase Analysis Report — Fleet Fuel Management System
- 4. JavaScript Frontend Redundancies
- Fleet Fuel Management
- BÁO CÁO KIẾN TẬP THỰC TẾ
- Added
- plan-builder.test.js
- 7. Scalability Concerns
- debug_arrange.py
- 1.1. Tổng quan cơ sở lý thuyết
- 4.1. Mô tả chi tiết giải pháp phần mềm
- 4.2. Học hỏi từ nơi thực tập
- 2026-07-30 — Dispatch Module Post-Phase-3: Plan Auto-Completion + Live Speed Signal
- TestProofRequired
- Phụ lục A: Cấu trúc cơ sở dữ liệu
- Changed
- 2026-07-30 — Dispatch Module Phase 3: Operational Workspace
- 2. Redundant Files & Dead Code
- CHƯƠNG 2: MÔ TẢ CƠ QUAN THỰC TẬP THỰC TẾ
- KẾT LUẬN VÀ KIẾN NGHỊ
- 2026-07-30 — Dispatch Module Phase 2: Route Intelligence
- 2026-07-30 — Site-Wide Navigation: Fixed Dispatch Dropdown Bug + Reorganized Structure
- 9. Priority Action Items
- 5. Database & Query Redundancies
- test_write_handler_connections.py
- _add_shipment
- 2026-07-31 — Delivery Module Phase 2: Vehicle Identity Service
- _raw_ttas
- export_service.py
- delivery-export.js
- 2026-07-30 — Truck Load Planner Phase 4: Vehicle Candidate Selection to Minimize Truck Count
- Agent Instructions
- distribution.py
- TestRevertStop
- dashboard.test.js
- normalize_vehicle
- test_delivery_routes.py
- 2026-07-31 — Removed dispatcher authentication; stop reordering on the dashboard; Plans panel positioning
- test_delivery.py
- _upload
- parametrize
- TestExecutionLifecycle
- _row
- test_vehicle_core_data.py
- FakeFileStorage
- ._stop
- TestExportNaming
- 9. Confirmed Bugs
- 18. Phased Refactoring Roadmap
- TestImportRoute
- TestReorderValidation
- 2026-07-31 — Core Fleet Data Is Now Read-Only to Background Processes
- 2026-07-31 — Removed the Trip Management / Trip History pages (superseded by Dispatch)
- ApiClient
- 2026-07-31 — Delivery Module Phase 1: GPS Pipeline Repair + Security Hardening
- 2026-07-31 — Delivery Module Phases 4 & 5: Frontend Hardening + Route-Layer Test Suite
- 17. Future Architecture Proposal
- _apply_anomaly_flag
- TestCargoConsistency
- 2026-07-31 — Dispatch board UX, phase 0: GPS trust, graded severity, density, quick filters, keyboard
- 2026-07-31 — Delivery Module Phase 3: Execution Correctness (and one retracted audit finding)
- 5. Vehicle Identity Flow
- adapters.py
- 2026-07-30 — Dispatch Module Phase 1: Incremental Live Updates
- Recommendation
- 3. Request Flow Diagram
- 2. System Architecture Diagram
- 4. GPS Flow Diagram
- 6. Database Relationship Diagram
- test_fuel_routes.py
- 1. Executive Summary
- TestAssignmentDriverName
- test_vehicle_specs.py
- 2026-07-31 — Vehicle-constrained routing, phase A: POST migration, border avoidance, failure-mode split
- 2026-07-31 — Vehicle-constrained routing, phase B: envelope schema, form, validation, type fallbacks
- TestResolveEnvelope
- 2026-07-31 — Vehicle-constrained routing, phase C: restrictions applied, degraded-route path
- 2026-08-01 — Advance, Skip and Cancel can be undone
- 2026-08-01 — GPS timestamps are parsed server-side; "GPS stale 4920h"
- 2026-08-01 — Stop phases are recorded, and corrections last the day
- 2026-08-02 — Completing a stop requires photographic proof
- 2026-08-02 — End-of-day export, and a persistent disk
- TestOrsVehicleType
- TestBuildOrsOptions
- 2026-07-31 — Gross vehicle weights loaded from the fleet spreadsheet (data, not code)
- TestSpeedPhraseParsing
- TestLostSignal
- TestCoerceEnvelopeValue
- TestRestrictionsFingerprint
- TestToOrsRestrictions
- _raw_ttas
- 2026-07-31 — Ages refresh on a 15s clock; ETA no longer drifts on repaint
- 2026-08-02 — The driver named in a plan is the driver dispatch shows
- TestPlausibilityWarnings
- utils.js
- conftest.py
- api_fuel_log_create
- config.py
- TestOpenAccess
- tlp-escaping.test.js
- csv_response
- TestStopCrud
- TestEtaEndpoint
- 2026-08-03 — A parked truck's speed was its parking time
- TestReorderValidation
- 2026-07-19 — Dead Space Quality (Future-Packability Estimation)
- 2026-07-30 — Truck Load Planner Phase 2: Fixed Empty-Space/Utilization Scoring
- db_path
- 2026-08-03 — A truck TTAS says it has lost is now in the No GPS list
- Workspace Bug Audit — 2026-08-06
- api_fuel_log_profiles_list
- 2026-07-30 — Truck Load Planner Phase 1: Fixed Stacking Scoring Bias + Hard Height Cap
- 2026-08-06 — Audit fixes: TLP shipment arrange, geofence transactions, TLP escaping
- 2026-08-06 — A confirmed plan is editable, and reachable from the board
- TestTransactions
- 2026-07-30 — Dispatch Module Phase 3 QA Pass: Two Bugs Fixed
- 2026-07-30 — Documentation Reorganization: Consolidated into docs/
- 10. Likely Bugs

## God Nodes (most connected - your core abstractions)
1. `LoadPlannerApp` - 133 edges
2. `DatabaseManager` - 119 edges
3. `UI` - 90 edges
4. `Package` - 82 edges
5. `Planner` - 59 edges
6. `Changelog` - 57 edges
7. `Container` - 56 edges
8. `_create_plan()` - 51 edges
9. `AABB` - 48 edges
10. `_db()` - 43 edges

## Surprising Connections (you probably didn't know these)
- `get_current_stop()` --calls--> `DatabaseManager`  [EXTRACTED]
  services/delivery/execution_service.py → app/db.py
- `get_stop_execution()` --calls--> `DatabaseManager`  [EXTRACTED]
  services/delivery/execution_service.py → app/db.py
- `delete_day_image()` --calls--> `DatabaseManager`  [EXTRACTED]
  services/delivery/export_service.py → app/db.py
- `delete_image()` --calls--> `DatabaseManager`  [EXTRACTED]
  services/delivery/image_service.py → app/db.py
- `UploadRejected` --uses--> `DatabaseManager`  [INFERRED]
  services/delivery/image_service.py → app/db.py

## Import Cycles
- 3-file cycle: `app.py -> app/routes/trips.py -> app/services/routing.py -> app.py`

## Communities (200 total, 26 thin omitted)

### Community 0 - "truck_load_planner/routes.py"
Cohesion: 0.10
Nodes (43): add_feature(), auto_arrange(), _build_placement_dict(), clear_all_packages(), create_container_config(), create_package(), create_plan(), create_shipment() (+35 more)

### Community 1 - "delivery/routes.py"
Cohesion: 0.12
Nodes (47): advance_stop(), batch_delete_plans(), cancel_stop(), clear_plans(), confirm_plan(), create_assignment(), create_driver(), create_plan() (+39 more)

### Community 2 - "Package"
Cohesion: 0.13
Nodes (40): _make(), Package, Placement, test_auto_arrange_uses_remaining_packages_for_rotation_choice(), test_determinism(), test_empty_placements_list(), test_generate_candidates_adds_rotation_aware_right_wall_anchor(), test_optimized_strategy_registered_and_restores_weights() (+32 more)

### Community 3 - "_create_plan"
Cohesion: 0.11
Nodes (18): _create_plan(), _create_stop(), _create_vehicle_assignment(), Tests for execution_service.py: progress calculation., An assignment with no stops has no stops. This test previously asserted `total…, Yesterday's route is a finished record. Correcting a stop is bookkeeping, and…, They already carry a typed reason, and photographing a delivery that never…, list_stops aliases the column to execution_status; reading 'status' here would… (+10 more)

### Community 4 - "Container"
Cohesion: 0.05
Nodes (53): End-to-end regression tests for auto-arrange. Unlike test_scorer.py's narrow…, test_single_vehicle_realistic_shipment_all_placed_with_reasonable_utilization(), test_stack_depth_hard_cap_is_enforced(), test_stacking_used_when_floor_alone_is_insufficient(), check_door_access(), check_door_fit(), check_door_sweep(), check_rear_door() (+45 more)

### Community 5 - "GoogleSheetService"
Cohesion: 0.09
Nodes (25): GoogleSheetService, parse_date_ngay(), parse_float(), parse_int(), parse_time_gio(), Any, Google Sheets Fuel Log Synchronization Service Reads fuel records from a Google…, Parse a spreadsheet date to ``YYYY-MM-DD``. Accepts ``DD/MM/YYYY`` (the… (+17 more)

### Community 6 - "delivery-plan-builder.js"
Cohesion: 0.11
Nodes (48): applyStation(), _bindDriverAutocomplete(), _bindVehicleAutocomplete(), clearAllValidation(), clearValidation(), closeMapPicker(), confirmPlan(), deleteStop() (+40 more)

### Community 7 - "TestRevertEndpoint"
Cohesion: 0.06
Nodes (20): _age_execution(), _give_proof(), Attach the photos a completion requires, without touching the disk. The gate…, Push a stop's action timestamps into the past. Used to show correctability is…, Undo for a mis-tapped Advance/Skip/Cancel. Route-layer coverage matters here…, One step back, not all the way. The driver really did arrive; only the second…, The point of the feature: a mis-advanced stop moves the dashboard on to the…, A stop skipped once the driver was already there has a real arrival time.… (+12 more)

### Community 8 - "fuel.py"
Cohesion: 0.13
Nodes (21): api_fuel_log_days(), api_fuel_log_delete(), api_fuel_log_last_km(), api_fuel_log_months(), api_fuel_log_profile_delete(), api_fuel_log_profile_update(), api_fuel_sync(), api_fuel_sync_history() (+13 more)

### Community 9 - "auto_arrange.py"
Cohesion: 0.15
Nodes (18): AutoArrangeResult, AutoArrangeStrategy, _footprint(), _largest_first_order(), LargestFirstStrategy, OptimizedStrategy, Package, Protocol (+10 more)

### Community 10 - "oil.py"
Cohesion: 0.11
Nodes (24): api_oil_fetch_progress(), api_oil_maintenance_create(), api_oil_maintenance_delete(), api_oil_maintenance_export(), api_oil_maintenance_list(), api_oil_maintenance_mark_done(), api_oil_maintenance_update(), _compute_oil_metrics() (+16 more)

### Community 11 - "js/map.js"
Cohesion: 0.10
Nodes (43): allLocationLabels, allLocationPolygons, applyFilters(), buildPopup(), buildStatusFilters(), buildTypeFilters(), cancelTripFromMap(), createIcon() (+35 more)

### Community 13 - "trips.py"
Cohesion: 0.11
Nodes (28): api_advance_trip(), api_cancel_trip(), api_refresh_routes(), do_refresh_route_data(), get_route_data(), route, Live trip routing for the main fleet map: route geometry, phase advancement,…, Cancel an active or queued trip. (+20 more)

### Community 14 - "fuel-efficiency.js"
Cohesion: 0.10
Nodes (45): allEntries, allVehicles, applyFilters(), availableDays, changeDay(), changeMonth(), clearNormal(), closeModal() (+37 more)

### Community 15 - "vehicle-management.js"
Cohesion: 0.09
Nodes (41): allTypes, allVehicles, animate3D(), animateCamera(), attachPreviewListeners(), buildFeaturesFromForm(), bulkDelete(), closeModal() (+33 more)

### Community 16 - "test_all.py"
Cohesion: 0.25
Nodes (28): _build_engine_packages(), _load_db(), avg(), cmd_benchmark_distribution(), cmd_benchmark_floor_contact(), cmd_benchmark_real_data(), cmd_debug_py3dbp(), cmd_debug_stats() (+20 more)

### Community 17 - "AABB"
Cohesion: 0.05
Nodes (33): Placement, 3D uniform grid for fast AABB overlap queries. Cell size is auto-tuned from…, Register a placement and its AABB in the grid., Remove a placement (linear scan — only called on user operations)., Return (placement, aabb) pairs whose cells overlap *aabb*. Returns each…, Fast check whether anything overlaps *aabb* (early exit)., Return all grid cell keys that *aabb* overlaps., UniformGrid (+25 more)

### Community 18 - "LoadPlanningSession"
Cohesion: 0.10
Nodes (13): EnginePackage, _engine_placement_to_dict(), _from_legacy_dict(), LoadPlanningSession, Placement, Run auto-arrange for a set of packages. Accepts either a list of shipment items…, Convert a legacy Package (from models) to engine Package., Build an engine Package from a legacy dict (underscore keys). (+5 more)

### Community 19 - "TestDayExport"
Cohesion: 0.15
Nodes (7): _ddmm(), `2026-08-02` → `02_08`, the operator's subfolder date format., The end-of-day handover. The photos are already on disk, organised the way they…, An 'extra' shot is not evidence of anything and must not be filed alongside the…, It is free text from a form and becomes a path. S-04 all over again if it were…, An empty ZIP with a manifest beats an error at 6pm., TestDayExport

### Community 20 - "normalize_plate"
Cohesion: 0.11
Nodes (24): get_dashboard(), _gps_by_plate_key(), Live GPS for the whole fleet, normalized. Returns ``(positions, source,…, Index GPS positions by 5-digit plate serial. ``normalize_plate`` collapses the…, _ttas_vehicles(), normalize_gps_position(), _parse_speed_kmh(), GPS telemetry normalization for the delivery dashboard. Input contract… (+16 more)

### Community 21 - "Bug-fix plan — findings of `docs/AUDIT_2026-08-06.md`"
Cohesion: 0.08
Nodes (24): Acceptance criteria, Acceptance criteria, Acceptance criteria, Acceptance criteria, Acceptance criteria, Approach, Approach, Approach (+16 more)

### Community 23 - "PlanningState"
Cohesion: 0.08
Nodes (25): PlanningState, Package, Placement, setter, Insert a placement at *index* and rebuild extreme points + grid., Return extreme points sorted by z, x, y — no regeneration., Replace all placements from saved data and rebuild indices., Return (placement, aabb) pairs whose grid cells overlap *aabb*. Used by the… (+17 more)

### Community 24 - "models/__init__.py"
Cohesion: 0.09
Nodes (8): _extract_doors(), Extract rear_door from features list (side doors ignored)., ContainerFeature, LoadPlan, Package, Placement, Shipment, ShipmentItem

### Community 25 - "app/__init__.py"
Cohesion: 0.13
Nodes (19): init_db(), Database initialization orchestrator. init_db() preserves app.py's original…, create_tables(), Table definitions (CREATE TABLE IF NOT EXISTS statements). Extracted from…, create_app(), Flask app factory (Section 6.4.1, Phase 1). app.py (the project's entry point,…, load_known_locations(), create_fleet_session() (+11 more)

### Community 27 - "Planner"
Cohesion: 0.09
Nodes (12): test_placement_score_to_dict(), Deprecated: kept for backward compatibility during migration., Planner, Package, setter, Score a single placement position. This is the preferred API for external…, Coordinates all subsystems for a single loading session., Score and rank candidate positions for a package. Each candidate is a dict or… (+4 more)

### Community 28 - "TestEtaService"
Cohesion: 0.11
Nodes (3): patch, Tests for eta_service.py: Haversine fallback and ORS integration., TestEtaService

### Community 29 - "main.js"
Cohesion: 0.14
Nodes (35): applyFilters(), applyFocusRing(), assignmentsExpectingGps(), bindFilterEvents(), bindFiltersDisclosure(), bindKeyboard(), bindManagePlansEvents(), bindMapControls() (+27 more)

### Community 30 - "timeline.js"
Cohesion: 0.14
Nodes (30): bindActionDelegation(), bindHistoryToggle(), bindPhotosToggle(), bindUpload(), buildActionsHtml(), buildDetailHtml(), buildUploadHtml(), clear() (+22 more)

### Community 31 - "app.py"
Cohesion: 0.20
Nodes (20): api_clear_all_locations(), api_delete_location(), api_geocode(), api_known_locations(), api_manual_locations(), api_save_location(), api_update_location(), api_vehicles() (+12 more)

### Community 32 - "locations.js"
Cohesion: 0.29
Nodes (18): clearAllLocations(), clearMapLayers(), clearPendingCorners(), closeEditPanel(), deleteLocation(), escapeHtml(), getDistanceMeters(), handleMapClick() (+10 more)

### Community 34 - "fleet.py"
Cohesion: 0.05
Nodes (59): api_vehicle_set_container(), api_vehicle_types_create(), api_vehicle_types_delete(), api_vehicle_types_list(), api_vehicles_bulk_delete(), api_vehicles_create(), api_vehicles_delete(), api_vehicles_list() (+51 more)

### Community 35 - "with_gps"
Cohesion: 0.18
Nodes (7): C-01: `from app import fetch_vehicle_data` raised ImportError on every request,…, C-02: the normalizer read normalize_vehicle()'s *output* names off a *raw* TTAS…, The dashboard computes GPS age from this field. Reading the raw day-first text…, C-03: matching was `.strip().lower()` on both sides., 0,0 is the Gulf of Guinea, not a vehicle position., TestDashboardGps, with_gps()

### Community 36 - "Vehicle-Constrained Routing — Plan"
Cohesion: 0.09
Nodes (22): 1. What ORS supports, 2. Three blockers in the current code, 3.1 The fleet master data does not contain vehicle dimensions, 3.2 Why the cargo numbers cannot stand in, 3. The data gap — this is the real work, 4. Phasing, 5. When no compliant route exists, 6. What this will and will not prevent (+14 more)

### Community 37 - "patch"
Cohesion: 0.17
Nodes (7): _error_response(), _ok_response(), patch, Tests for app/services/routing.py — the shared ORS transport. Covers the two…, The trips.py entry point. Its three original keys must not change shape — a…, TestGetRouteCoords, TestRequestDirections

### Community 39 - "api.js"
Cohesion: 0.20
Nodes (18): advance(), cancel(), clearPlans(), dashboard(), deletePlans(), drivers(), eta(), fetchJSON() (+10 more)

### Community 40 - "dashboard/map.js"
Cohesion: 0.13
Nodes (17): addBasemaps(), attr(), identifyImagery(), imageryInfoHtml(), init(), parseImageryDate(), pickBestImageryResult(), readSavedBasemap() (+9 more)

### Community 41 - "migrations.py"
Cohesion: 0.12
Nodes (19): add_missing_fuel_columns(), add_missing_vehicle_trips_columns(), add_vehicle_envelope_columns(), backfill_vehicles_from_fuel_log(), migrate_legacy_vehicle_trips_schema(), migrate_tlp_extensions(), Column migrations and data backfill for existing databases. Extracted from…, Physical envelope of the vehicle itself, for ORS routing restrictions. Distinct… (+11 more)

### Community 42 - "_MutationLogger"
Cohesion: 0.10
Nodes (16): git(), main(), preflight(), Record files that have been moved out of the tree as deleted., Stop tracking a path without removing it from disk. Used for the generated…, tests/test_tlp_routes.py as it should look in commit 1. The file arrives with…, Stage `path` as its HEAD content plus the selected hunks., split_hunks() (+8 more)

### Community 43 - "vehicle-list.js"
Cohesion: 0.22
Nodes (18): attentionLabel(), attentionReasonText(), _bindAttentionToggle(), _bindCompactToggle(), computeAttention(), createCard(), formatDuration(), _formatTime() (+10 more)

### Community 44 - "Delivery Module — Documentation"
Cohesion: 0.05
Nodes (40): API Endpoints, Architecture Overview, Assignments, Configuration, Dashboard Panels, Database Schema, Delivery Module — Documentation, `delivery_plan_stops` (+32 more)

### Community 45 - "TestPlanDriverOverride"
Cohesion: 0.08
Nodes (13): The predicate the dashboard's Revert button is drawn from. It runs server-side…, Routes are built ahead of the day they run., The behaviour that replaced the 15-minute window: nothing about how long ago…, Unknown is treated as closed rather than open — the same conservative choice…, The driver typed during plan creation is who drove *that day*. Drivers mostly…, An empty box means "no opinion", not "no driver" — whitespace has to reduce to…, Both set means the dispatcher edited the prefilled name — the edit is the newer…, A one-off stand-in must not accumulate in the drivers list. (+5 more)

### Community 46 - "Truck Load Planner — Algorithm, API & Frontend Reference"
Cohesion: 0.06
Nodes (33): 10. Step Animation & 3D Controls, 11. Frontend: Arrange Results & Validation, 12. 2D Canvas View Coordinates, 13. Engine Architecture (`truck_load_planner/engine/`), 14. Database, 15. API: Auto-Arrange Endpoint, 1. Package Sort Order (Pre-Processing), 2. Vehicle Selection (Multi-Vehicle Distribution) (+25 more)

### Community 47 - "Delivery / Dispatch Module — Architecture & Bug Audit"
Cohesion: 0.12
Nodes (16): 11. Technical Debt, 12. Performance Bottlenecks, 13. Security Observations, 14. Duplicate Logic Inventory, 15. Highest-Risk Areas, 16. Improvement Opportunities, 19. Recommended Implementation Order, 20. Files Most Likely to Change (+8 more)

### Community 48 - "ContainerConfig"
Cohesion: 0.09
Nodes (28): ABC, build_placement_dict(), _log_instrument(), _pp_placement(), _print_engine_stats(), Manual test: define packages below, run full pipeline with instrumentation.…, Match the _build_placement_dict from routes.py., Run the benchmark with the specified engine and print results. (+20 more)

### Community 49 - "fuel-sync.js"
Cohesion: 0.60
Nodes (5): fmtDuration(), loadLastSync(), refreshDashboard(), triggerSync(), updateSyncBadge()

### Community 50 - "grid.py"
Cohesion: 0.40
Nodes (5): Grid snapping utilities. Pure geometry — no business logic., Snap both x and y coordinates to the grid., Snap a coordinate to the nearest grid step., snap_point(), snap_to_grid()

### Community 51 - "polling.js"
Cohesion: 0.57
Nodes (6): bindVisibility(), refreshNow(), runTick(), setStatus(), start(), stop()

### Community 52 - "opencode.json"
Cohesion: 0.50
Nodes (3): plugin, $schema, .opencode/plugins/graphify.js

### Community 53 - "vehicle_identity.py"
Cohesion: 0.15
Nodes (14): get_conn(), migrate(), Migration script: export old vehicle_trips data into the new delivery schema.…, canonical_plate(), _is_bare_serial(), Centralized vehicle identity resolution. Why this exists --------------- The…, Resolve any plate-ish string to a vehicle, or None. Strictest match first so an…, # NOTE: this module has no write path, by design. There is intentionally no (+6 more)

### Community 59 - "DatabaseManager"
Cohesion: 0.08
Nodes (39): DatabaseManager, Centralized SQLite connection management. Replaces the duplicated…, Encapsulates SQLite connections for a single database file. Each `connect()`…, bulk_create_stops(), clear_plans(), confirm_import(), create_assignment(), create_driver() (+31 more)

### Community 60 - "Changelog"
Cohesion: 0.07
Nodes (29): 2026-07-11 — Refinements, 2026-07-13 — Container Fuel, Anomaly Detection, Vehicle Management, 2026-07-18 — Door Rendering Fixes, 2026-07-18 — Gravity, Stacking & Engine Refinement, 2026-07-18 — Inline Package Editor & Canvas UX, 2026-07-18 — Phase 3: Placement Evaluation Engine, 2026-07-18 — Phase 4: Auto Arrange Engine (v1), 2026-07-30 — Dispatch Module Phase 0: Bug Fixes (+21 more)

### Community 69 - "BÁO CÁO KIẾN TẬP THỰC TẾ"
Cohesion: 0.10
Nodes (20): 1.1. Tổng quan cơ sở lý thuyết, 1.2. Chủ đề thực tập, 1.3. Các kết quả và mục tiêu kỳ vọng, 2.1. Thông tin cơ quan, 2.2. Lịch sử hình thành và phát triển, 2.3. Cơ cấu tổ chức, nhiệm vụ chức năng của các phòng ban, 2.4. Chức năng, nhiệm vụ, phạm vi ngành nghề hoạt động, 2.5. Quy mô nhân sự và năng lực dịch vụ (+12 more)

### Community 70 - "ttas_client.py"
Cohesion: 0.18
Nodes (18): api_oil_maintenance_fetch_km(), Scrape the TTAS report for all vehicles from their last oil change date to…, ensure_session(), fetch_live_vehicle_data(), _fetch_ttas_report_page(), fetch_vehicle_data(), get_session_cookies(), LiveVehicleFetchError (+10 more)

### Community 71 - "3. Phase 0 — frontend only, no schema change  ✅ shipped"
Cohesion: 0.11
Nodes (18): 0.1 GPS trust badge  *(correctness — do this first)*, 0.2 Graded severity, 0.3 Density mode, 0.4 Quick filters, 0.5 Keyboard, 0.6 Verification, 1. Reference practice, 2. Current state (+10 more)

### Community 72 - "vehicle_cost.py"
Cohesion: 0.18
Nodes (12): compute_fleet_cost(), compute_vehicle_floor_mm2(), compute_vehicle_volume_mm3(), _get_fuel_consumption(), Vehicle Cost Model — computes estimated transportation cost for a vehicle. Kept…, Quick pre-packing feasibility check. Returns (is_feasible, reason) where reason…, Compute actual transportation cost for a vehicle after packing. Uses actual…, Compute total transportation cost for a fleet solution. Sums the post-packing… (+4 more)

### Community 73 - "Fleet Fuel Management — AI Context"
Cohesion: 0.10
Nodes (19): AI Working Workflow, Architecture, Architecture Decision Rules, Coding Standards, Dashboard map conventions (learned the hard way, 2026-07-31), Decision Making, Definition of Done, Directory Structure (+11 more)

### Community 74 - "execution_service.py"
Cohesion: 0.07
Nodes (44): date, advance_stop(), annotate_revertible(), can_revert(), cancel_stop(), get_assignment_progress(), get_current_stop(), get_dashboard_data() (+36 more)

### Community 75 - "Added"
Cohesion: 0.14
Nodes (14): 2026-07-29 — Architecture Refactor: Frontend Namespace, DatabaseManager, AABB Unification, `app/` Package Extraction, Added, `app/db.py` — `DatabaseManager`, `app/` package — extracted from the `app.py` monolith, Changed, `CLAUDE.md` (project root), `EnginePackage.from_legacy()` (`truck_load_planner/engine/package.py`), Fixed (+6 more)

### Community 76 - "6. Architectural Refactoring Roadmap — 4 Pillars"
Cohesion: 0.14
Nodes (14): 6.1.1 `app/db.py` — `DatabaseManager` Context Manager, 6.1.2 `static/js/utils.js` — `ApiClient` & `UI.toast()` Namespace, 6.1 Pillar 1: Encapsulation & Data Integrity, 6.2.1 `BaseRoutingStrategy` — Polymorphic Profile Resolution, 6.2.2 Unified Polymorphic `AABB` Class, 6.2 Pillar 2: Polymorphism & Geometry Unification, 6.3.1 `EnginePackage.from_legacy()` Factory Method, 6.3.2 Adapter Wrappers for `truck_load_planner/logistics/` (+6 more)

### Community 77 - "Added"
Cohesion: 0.15
Nodes (13): 2026-07-19 — Y-Balance, X-Preference, Rear-Proximity Scoring; Combined-Support Stacking; Rear-Door Routing; Y-Slide Fallback, Added, Candidate Priority — Removed Y Bias, Changed, Clearance Margin, Combined-Support Stacking Model, Fixed, Phase 3 — Rear-Door Redirect (Vehicle Distribution) (+5 more)

### Community 78 - "3. Python Backend Redundancies"
Cohesion: 0.15
Nodes (13): 3.10 App.py: `get_routing_profile()` Always Returns Same Value, 3.11 App.py: Duplicate Route Registration, 3.12 App.py: Duplicated Oil-Metrics Query Loop, 3.1 Duplicated Database Connection Code (4 copies), 3.2 Duplicated Stop + Execution JOIN Query (5 copies), 3.3 Duplicated Stop-Insert + Execution-Create (3 copies), 3.4 Duplicated Progress Calculation (2 copies), 3.5 Duplicated Vehicle + Container Config Query (3 copies) (+5 more)

### Community 79 - "Added"
Cohesion: 0.17
Nodes (12): 2026-07-19 — Best-Fit Decreasing, Candidate Priority, Stacking Defaults, 3D Fullscreen & Labels, 3D View Toolbar & Fullscreen, Added, Back-to-Front Loading, Best-Fit Decreasing (Vehicle Selection), Candidate Point Rotation, Candidate Priority (Pre-Validation Ranking), Changed (+4 more)

### Community 80 - "Changed"
Cohesion: 0.10
Nodes (21): 2026-07-26 — Phase 1: Delivery Plan Management Rewrite, Added, Changed, Changed, Consolidated Test Files, Fixed, Migration Script (`scripts/migrate_to_delivery.py`), New Database Schema (6 tables, coexists with legacy `vehicle_trips`) (+13 more)

### Community 81 - "Added"
Cohesion: 0.20
Nodes (10): 2026-07-18 — Multi-Vehicle Distribution, Door Access Validation, Step Animation, Added, Arrange Results Panel, Changed, Door Access Validation (`engine/access.py` — new module), Fixed, Multi-Vehicle Distribution (First-Fit Decreasing), Step Animation (Frontend) (+2 more)

### Community 82 - "Changed"
Cohesion: 0.20
Nodes (10): 2026-07-21 — Load Profile Stability Metric Fix, Floor Anchors, Local Rearrangement, Benchmark Correction, Added, Benchmark Correction, Changed, Floor Anchor Candidates, Load Profile Stability Metric, Local Rearrangement, Repair Optimizer (+2 more)

### Community 83 - "Codebase Analysis Report — Fleet Fuel Management System"
Cohesion: 0.20
Nodes (9): 10.1 Lean Root `CLAUDE.md` (<150 lines), 10.2 Directory-Level README.md Files, 10.3 Module Isolation Guidelines, 10.4 Token Budget for Common AI Tasks, 10. AI Context & Token Optimization Strategy, 1. Executive Summary, 8. Cleanup Actions Taken, Codebase Analysis Report — Fleet Fuel Management System (+1 more)

### Community 84 - "4. JavaScript Frontend Redundancies"
Cohesion: 0.20
Nodes (10): 4.1 Six Different `showToast` Implementations, 4.2 Three Identical `apiFetch` Wrappers, 4.3 Four Different `escapeHtml` / `escHtml` Implementations, 4.4 Duplicated Utility Functions in `fuel-efficiency.js` & `oil-change.js`, 4.5 Triplicated `isContainerV` Check, 4.6 Duplicated Sort Comparison Logic, 4.7 Duplicated Autocomplete Pattern (3 files), 4.8 Duplicated Modal Open/Close Pattern (3 files) (+2 more)

### Community 85 - "Fleet Fuel Management"
Cohesion: 0.15
Nodes (12): Delivery Management Tests (358 tests), Fleet Fuel Management, Frontend Tests (137 drives, non-pytest), Pages, Project Structure, Route-layer Tests (57 tests), Running Tests, Tech Stack (+4 more)

### Community 86 - "BÁO CÁO KIẾN TẬP THỰC TẾ"
Cohesion: 0.22
Nodes (8): 3.1. Quy trình điều vận xe tải thùng kín và Container thực tế, 3.2. Nhận diện nút thắt (Bottlenecks), 3.3. Phân tích chất lượng dữ liệu hiện tại, BÁO CÁO KIẾN TẬP THỰC TẾ, CHƯƠNG 3: BÀI TOÁN THỰC TẾ VÀ KHẢO SÁT NGHIỆP VỤ LOGISTICS CHI TIẾT, Lý do chọn đề tài, MỞ ĐẦU, Mục đích kiến tập

### Community 87 - "Added"
Cohesion: 0.22
Nodes (9): 2026-07-22 — Frontier-Based Gap Prevention, Gap-Filling Pass, Debug Instrumentation, Added, Detailed Debug Instrumentation (`engine/auto_arrange.py`), Duplicate-Name Bug in Gap-Filling Pass, Fixed, Frontier Gap-Filling Pass (`fill_frontier_gaps` in `engine/distribution.py`), FrontierTracker (`engine/frontier.py`), Removed (+1 more)

### Community 88 - "plan-builder.test.js"
Cohesion: 0.16
Nodes (17): addAssignment(), assert, boot(), click(), DRIVERS, flush(), fs, { JSDOM } (+9 more)

### Community 89 - "7. Scalability Concerns"
Cohesion: 0.22
Nodes (9): 7.1 No Connection Pooling, 7.2 Global Mutable State, 7.3 No Dependency Injection, 7.4 12-Second Polling (No WebSockets/SSE), 7.5 Monolithic CSS, 7.6 No Build Step, 7.7 `app.py` Bare `except:` Blocks, 7.8 Hardcoded Values That Should Be Configurable (+1 more)

### Community 90 - "debug_arrange.py"
Cohesion: 0.18
Nodes (19): build_real_shipment(), fmt_breakdown(), fmt_candidate_detail(), hr(), log(), main(), pl_dim(), Package (+11 more)

### Community 91 - "1.1. Tổng quan cơ sở lý thuyết"
Cohesion: 0.25
Nodes (8): 1.1.1. Bài toán Tối ưu hóa lộ trình (Vehicle Routing Problem — VRP), 1.1.2. Thuật toán hình học không gian áp dụng trong Định vị (Geofencing), 1.1.3. Học máy thống kê áp dụng trong Phát hiện bất thường (Anomaly Detection), 1.1.4. Kỹ nghệ dữ liệu (Data Engineering) và Tự động hóa thu thập, 1.1. Tổng quan cơ sở lý thuyết, 1.2. Chủ đề thực tập, 1.3. Các kết quả và mục tiêu kỳ vọng, CHƯƠNG 1: GIỚI THIỆU TỔNG QUAN VỀ CƠ SỞ LÝ THUYẾT VÀ CHỦ ĐỀ KIẾN TẬP

### Community 92 - "4.1. Mô tả chi tiết giải pháp phần mềm"
Cohesion: 0.25
Nodes (8): 4.1.1. Xác thực và đồng bộ dữ liệu với TTAS, 4.1.2. Cơ chế Geofencing và tự động chuyển phase, 4.1.3. Tích hợp định tuyến với OpenRouteService, 4.1.4. Mô hình phát hiện bất thường nhiên liệu, 4.1.5. Pipeline bảo dưỡng tự động, 4.1.6. Giao diện và kết quả tổng thể, 4.1.7. Tối ưu hiệu năng và hạn chế kỹ thuật, 4.1. Mô tả chi tiết giải pháp phần mềm

### Community 93 - "4.2. Học hỏi từ nơi thực tập"
Cohesion: 0.25
Nodes (8): 4.2.1. Nhận thức về khoảng cách giữa lý thuyết và thực tế, 4.2.2. Kỹ năng chuyên môn, 4.2.3. Tác phong công nghiệp và văn hóa doanh nghiệp, 4.2. Học hỏi từ nơi thực tập, 4.3.1. Tương quan giữa giảng đường và doanh nghiệp, 4.3.2. Khoảng cách lý thuyết và thực tiễn, 4.3. Đánh giá mối liên hệ giữa lý thuyết và thực tiễn, CHƯƠNG 4: KẾT QUẢ THỰC TẾ - XÂY DỰNG HỆ THỐNG PHẦN MỀM THÔNG MINH "FLEET FUEL MANAGEMENT"

### Community 94 - "2026-07-30 — Dispatch Module Post-Phase-3: Plan Auto-Completion + Live Speed Signal"
Cohesion: 0.50
Nodes (4): 2026-07-30 — Dispatch Module Post-Phase-3: Plan Auto-Completion + Live Speed Signal, Added, Deferred (explicit decision, not forgotten), Testing

### Community 95 - "TestProofRequired"
Cohesion: 0.19
Nodes (6): A stop cannot be marked completed without photographic proof: the goods off the…, Arriving somewhere is not a claim about what happened there, so there is…, Categories are sanitized rather than whitelisted on upload (audit S-04), so a…, The only place it lives. Nothing on stop_executions records that a completion…, Whitespace would record that proof was waived while saying nothing about why —…, TestProofRequired

### Community 96 - "Phụ lục A: Cấu trúc cơ sở dữ liệu"
Cohesion: 0.29
Nodes (7): A.1. Bảng `vehicle_trips` — lưu trữ chuyến hàng, A.2. Bảng `geofence_events` — nhật ký sự kiện geofence, A.3. Bảng `vehicles` — danh mục phương tiện, A.4. Bảng `fuel_log` — nhật ký đổ nhiên liệu, A.5. Bảng `oil_km_log` — lịch sử KM bảo dưỡng, A.6. Bảng `fuel_vehicle_profile` — định mức nhiên liệu, Phụ lục A: Cấu trúc cơ sở dữ liệu

### Community 97 - "Changed"
Cohesion: 0.29
Nodes (7): 2026-07-20 — Largest-Vehicle-First Fleet Distribution, Strict Unstackable Enforcement, Door-Aware Animation, Changed, Door-Used Propagation (Animation), Fleet Distribution: Best-Fit Decreasing → Largest-Vehicle-First, Package Sort: Priority-Grouped → Strict Volume Descending, Removed, Strict Unstackable Enforcement

### Community 98 - "2026-07-30 — Dispatch Module Phase 3: Operational Workspace"
Cohesion: 0.29
Nodes (7): 2026-07-30 — Dispatch Module Phase 3: Operational Workspace, Added, Changed, Fixed (self-consistency issue caught during implementation), Out of Scope, Remaining Technical Debt / Deferred, Testing

### Community 99 - "2. Redundant Files & Dead Code"
Cohesion: 0.29
Nodes (7): 2.1 Legacy `truck_load_planner/logistics/` Module, 2.2 `truck_load_planner/geometry/aabb.py` vs `engine/geometry.py`, 2.3 Dead Functions in `services/delivery/tracking_service.py`, 2.4 Dead Code in `app.py`, 2.5 Shadowed Functions in `static/js/map.js`, 2.6 Untracked Temporary/Generated Files, 2. Redundant Files & Dead Code

### Community 100 - "CHƯƠNG 2: MÔ TẢ CƠ QUAN THỰC TẬP THỰC TẾ"
Cohesion: 0.33
Nodes (6): 2.1. Thông tin cơ quan, 2.2. Lịch sử hình thành và phát triển, 2.3. Cơ cấu tổ chức, nhiệm vụ chức năng của các phòng ban, 2.4. Chức năng, nhiệm vụ, phạm vi ngành nghề hoạt động, 2.5. Quy mô nhân sự và năng lực dịch vụ, CHƯƠNG 2: MÔ TẢ CƠ QUAN THỰC TẬP THỰC TẾ

### Community 101 - "KẾT LUẬN VÀ KIẾN NGHỊ"
Cohesion: 0.33
Nodes (6): Kiến nghị, Kết luận, KẾT LUẬN VÀ KIẾN NGHỊ, Phụ lục B: Danh sách API endpoints, Phụ lục C: Cấu hình biến môi trường (`.env`), Phụ lục D: Cấu trúc thư mục mã nguồn

### Community 102 - "2026-07-30 — Dispatch Module Phase 2: Route Intelligence"
Cohesion: 0.33
Nodes (6): 2026-07-30 — Dispatch Module Phase 2: Route Intelligence, Added, Changed, Out of Scope, Remaining Technical Debt / Deferred, Testing

### Community 103 - "2026-07-30 — Site-Wide Navigation: Fixed Dispatch Dropdown Bug + Reorganized Structure"
Cohesion: 0.33
Nodes (6): 2026-07-30 — Site-Wide Navigation: Fixed Dispatch Dropdown Bug + Reorganized Structure, Changed — nav reorganization (applied identically across 9 templates: `index.html`, `delivery-dashboard.html`, `delivery-plan-builder.html`, `manage-trips.html`, `trip-history.html`, `locations.html`, `oil-change.html`, `vehicle-management.html`, `fuel-efficiency.html`), Considered and explicitly not done, Fixed, Remaining Technical Debt, Testing

### Community 104 - "9. Priority Action Items"
Cohesion: 0.33
Nodes (6): 9. Priority Action Items, Phase 1: Immediate Wins (Pillars 1 & 3) — High Impact, Low Effort, Phase 2: Structural Foundations (Pillars 1 & 4) — High Impact, Medium Effort, Phase 3: Geometry & Legacy (Pillars 2 & 3) — High Impact, Higher Effort, Phase 4: Modular Split (Pillar 4) — Foundation for AI Optimization, Phase 5: Long-Term Architecture

### Community 105 - "5. Database & Query Redundancies"
Cohesion: 0.40
Nodes (5): 5.1 N+1 Query in `get_dashboard_data()`, 5.2 App.py Opens N+1 DB Connections in Fuel Log Loop, 5.3 Dynamic SQL Injection Risk, 5.4 Migrations Not Reusable, 5. Database & Query Redundancies

### Community 106 - "test_write_handler_connections.py"
Cohesion: 0.13
Nodes (14): app(), client(), db(), exploding(), ExplodingConnection, opened_at_least_one(), fixture, parametrize (+6 more)

### Community 107 - "_add_shipment"
Cohesion: 0.18
Nodes (12): _add_package(), _add_shipment(), items: list of (package_id, quantity)., The audit's Critical #1. Every test here fails against the pre-fix query., The defect hiding behind the KeyError. ``si.*`` exposed the shipment *item* id…, The two payload shapes must not drift apart again. The frontend picks between…, A LEFT JOIN miss must not become a zero-dimension package. Without the guard,…, The audit's §5 orphan finding. This schema runs with ``enable_fk=False`` and… (+4 more)

### Community 108 - "2026-07-31 — Delivery Module Phase 2: Vehicle Identity Service"
Cohesion: 0.29
Nodes (7): 2026-07-31 — Delivery Module Phase 2: Vehicle Identity Service, Added, Changed, Fixed, Notes, Still open: other paths that auto-create vehicles, Testing

### Community 109 - "_raw_ttas"
Cohesion: 0.22
Nodes (13): _add_trip(), A raw TTAS DevList item, the shape fetch_vehicle_data returns., Three trips, none arrived, all with a changed driver name. Against the pre-fix…, The third trip arrives; the first two have not. Pre-fix, iterations 2 and 3…, The leftover open transaction is what held a RESERVED lock across this…, Pins the branch whose `continue` the restructure removed., Two stops: arriving at the waypoint advances to phase 2, and the trip stays…, The per-trip handler stays deliberately broad. A trip whose waypoint JSON is… (+5 more)

### Community 110 - "export_service.py"
Cohesion: 0.08
Nodes (37): BytesIO, add_day_image(), build_day_zip(), day_image_folder(), day_summary(), _ddmm(), delete_day_image(), driver_folder_name() (+29 more)

### Community 111 - "delivery-export.js"
Cohesion: 0.33
Nodes (9): ddmm(), download(), fetchJSON(), loadSummary(), renderDayImages(), renderDrivers(), renderStructure(), renderSummary() (+1 more)

### Community 112 - "2026-07-30 — Truck Load Planner Phase 4: Vehicle Candidate Selection to Minimize Truck Count"
Cohesion: 0.50
Nodes (4): 2026-07-30 — Truck Load Planner Phase 4: Vehicle Candidate Selection to Minimize Truck Count, Fixed, Fixed during verification (not part of the original plan, found while testing), Testing

### Community 114 - "distribution.py"
Cohesion: 0.15
Nodes (13): _vehicle_capacity(), _cheap_could_fit_all(), LargestVehicleFirstStrategy, Package, Protocol, Original behaviour: largest-capacity vehicles first., Fast necessary-condition check, no arrangement attempted. Rejects a vehicle…, Protocol for vehicle-selection strategies. ``select_vehicles`` receives the… (+5 more)

### Community 115 - "TestRevertStop"
Cohesion: 0.11
Nodes (8): _backdate(), Push a stop's action timestamps into the past. Used to prove correctability is…, Advance is one unconfirmed tap sitting beside Skip and Cancel, pressed on a…, Nothing records what a stop was before it was skipped, but an arrival timestamp…, The mirror of _maybe_complete_plan. Without this the corrected plan stays…, The rule that replaced the original 15-minute window. An advance made hours ago…, Plans are built ahead. A stop actioned early on tomorrow's route must not be…, TestRevertStop

### Community 116 - "dashboard.test.js"
Cohesion: 0.14
Nodes (11): assert, boot(), fs, { JSDOM }, makeAssignment(), makeGps(), path, pill() (+3 more)

### Community 117 - "normalize_vehicle"
Cohesion: 0.14
Nodes (12): normalize_vehicle(), parse_ttas_timestamp(), Parse a TTAS position timestamp into an ISO 8601 string. Returns ``None`` when…, clean_text(), safe_float(), TTAS writes dates day-first (`01/08/2026` is 1 August). Before this was parsed…, The silent case. `13/08/2026` has no month 13, so `new Date()` returned Invalid…, `12/08/2026` read month-first as 8 December — a date in the *future*, giving a… (+4 more)

### Community 118 - "test_delivery_routes.py"
Cohesion: 0.14
Nodes (12): _add_missing_columns(), init_delivery_tables(), app(), client(), db(), isolated_upload_root(), fixture, Route-layer tests for the delivery/dispatch HTTP API. Why this file exists… (+4 more)

### Community 119 - "2026-07-31 — Removed dispatcher authentication; stop reordering on the dashboard; Plans panel positioning"
Cohesion: 0.14
Nodes (14): 2026-07-31 — Removed dispatcher authentication; stop reordering on the dashboard; Plans panel positioning, Added — click the satellite map for the imagery capture date, Added — clicking a stop locates it on the map, Added — reorder stops from the dashboard, Added — switchable basemap, satellite by default, Fixed — clicking a vehicle took ~15 seconds to update the right panel, Fixed — map control buttons became unreadable on hover, Fixed — the map snapped back to the selected vehicle on every poll (+6 more)

### Community 120 - "test_delivery.py"
Cohesion: 0.16
Nodes (10): _add_vehicle(), _clear_status_events(), _count_vehicles(), Erase a stop's phase log, standing in for every stop last touched before the…, confirm_import must resolve plate variants onto existing rows instead of…, There is no override. An unknown plate always aborts, and no keyword argument…, Variants of the same unknown plate collapse to one entry, so the dispatcher…, Used to return success while the plan silently stayed 'draft' and never reached… (+2 more)

### Community 121 - "_upload"
Cohesion: 0.16
Nodes (7): parametrize, S-05: send_file infers Content-Type from the extension, so an uploaded .html…, S-04: category and station_code were interpolated into the upload path, so…, C-08: filenames were `{unix_seconds}{ext}`, so the second photo silently…, TestImageServing, TestImageUpload, _upload()

### Community 122 - "parametrize"
Cohesion: 0.18
Nodes (6): parametrize, services/vehicle_identity.py — the resolver that replaces five mutually…, The exact duplicate shape merge_duplicate_vehicles.py cleans up: a stray…, Two different full plates sharing a 5-digit serial must not be silently…, Adding a vehicle is a Vehicle Management action. This module must never grow a…, TestVehicleIdentity

### Community 123 - "TestExecutionLifecycle"
Cohesion: 0.18
Nodes (3): C-07: two taps took a stop planned -> arrived -> completed, marking it…, C-09: `total = sum(...) or 1` made an empty assignment claim it had one…, TestExecutionLifecycle

### Community 124 - "_row"
Cohesion: 0.29
Nodes (3): _row(), TestCreate, TestUpdate

### Community 125 - "test_vehicle_core_data.py"
Cohesion: 0.09
Nodes (17): core_data(), fleet_db(), fixture, parametrize, Core fleet data is never created or altered in the background. `vehicles` —…, app/database/migrations.py runs on every startup., Static guarantee, so a future edit can't quietly reintroduce this., plate_number / vehicle_type / current_driver identify a vehicle and describe… (+9 more)

### Community 126 - "FakeFileStorage"
Cohesion: 0.24
Nodes (4): FakeFileStorage, Mimics Werkzeug's FileStorage for testing. Now exposes ``.stream`` because that…, Tests for image_service.py: upload, list, get, delete., TestImageService

### Community 127 - "._stop"
Cohesion: 0.11
Nodes (12): _give_proof(), Attach the photos a completion requires, without touching the disk. The gate…, A stop must not be walked two steps by one accidental double-tap (audit C-07).…, The damage wasn't only the status — arrival and departure were stamped in the…, The guard must not break the normal flow: a dispatcher advancing twice, each…, expected_status is optional — older callers keep working., Every phase change is recorded, and revert returns the stop to the phase it is…, The event is written on the same connection as the UPDATE and only after it… (+4 more)

### Community 128 - "TestExportNaming"
Cohesion: 0.20
Nodes (4): Driver folder names, which are the fiddly part of the handover. The operator's…, đ/Đ is a distinct letter, not d-plus-diacritic, so NFD leaves it alone — the…, Same reduction the GPS matching uses (audit C-03), so the number in the folder…, TestExportNaming

### Community 129 - "9. Confirmed Bugs"
Cohesion: 0.20
Nodes (10): 9. Confirmed Bugs, C-01 · GPS pipeline dead — wrong import module, C-02 · `normalize_gps_position` consumes the wrong dict schema, C-03 · Plate matching uses `.lower()` against a field that is always absent, C-04 · No authentication on any delivery endpoint, C-05 · Excel import creates duplicate vehicle rows, ~~C-06 · Stop reordering never updates the UI~~ — **RETRACTED 2026-07-31**, C-07 · Double-click on "Advance" skips the "arrived" state (+2 more)

### Community 130 - "18. Phased Refactoring Roadmap"
Cohesion: 0.22
Nodes (9): 18. Phased Refactoring Roadmap, Phase 0 — Verify deployment reality (½ day), Phase 1 — Stop the bleeding (2-3 days), Phase 2 — Vehicle Identity Service (3-4 days), Phase 3 — GPS Adapter + Sync Layer (4-5 days), Phase 4 — Execution correctness (2-3 days), Phase 5 — Frontend hardening & performance (2-3 days), Phase 6 — Debt & documentation (2 days) (+1 more)

### Community 133 - "2026-07-31 — Core Fleet Data Is Now Read-Only to Background Processes"
Cohesion: 0.29
Nodes (7): 2026-07-31 — Core Fleet Data Is Now Read-Only to Background Processes, Added, Changed — unknown vehicle now prompts instead of failing, Fixed, Note, Reviewed and left alone, Testing

### Community 134 - "2026-07-31 — Removed the Trip Management / Trip History pages (superseded by Dispatch)"
Cohesion: 0.29
Nodes (7): 2026-07-31 — Removed the Trip Management / Trip History pages (superseded by Dispatch), Consequence worth knowing, Documentation, Kept, deliberately, Not touched, Removed, Testing

### Community 135 - "ApiClient"
Cohesion: 0.12
Nodes (23): populateMonthSelect(), selectVehicle(), allVehicles, closeModal(), deleteVehicle(), fetchKmData(), filteredVehicles, filterTable() (+15 more)

### Community 136 - "2026-07-31 — Delivery Module Phase 1: GPS Pipeline Repair + Security Hardening"
Cohesion: 0.33
Nodes (6): 2026-07-31 — Delivery Module Phase 1: GPS Pipeline Repair + Security Hardening, Added, Deployment note, Fixed, Known limitations / deliberately not fixed here, Testing

### Community 137 - "2026-07-31 — Delivery Module Phases 4 & 5: Frontend Hardening + Route-Layer Test Suite"
Cohesion: 0.33
Nodes (6): 2026-07-31 — Delivery Module Phases 4 & 5: Frontend Hardening + Route-Layer Test Suite, Added — route-layer test suite (T-01), Fixed — frontend, Fixed — test isolation, Still open (not in scope for these phases), Testing

### Community 138 - "17. Future Architecture Proposal"
Cohesion: 0.33
Nodes (6): 17.1 Vehicle Identity Service — `services/vehicle_identity.py`, 17.2 GPS Adapter — `services/gps/`, 17.3 Synchronization Layer — background GPS refresher, 17.4 Shared Vehicle Resolver (frontend), 17.5 Truck Load Planner ↔ Delivery Execution integration, 17. Future Architecture Proposal

### Community 139 - "_apply_anomaly_flag"
Cohesion: 0.19
Nodes (18): api_fuel_log_list(), api_fuel_log_stats(), api_fuel_log_summary(), _apply_anomaly_flag(), _compute_baseline(), _compute_fuel_entry(), _db(), _enrich_fuel_entry() (+10 more)

### Community 141 - "2026-07-31 — Dispatch board UX, phase 0: GPS trust, graded severity, density, quick filters, keyboard"
Cohesion: 0.25
Nodes (8): 2026-07-31 — Dispatch board UX, phase 0: GPS trust, graded severity, density, quick filters, keyboard, Added — compact density for the vehicle list, Added — keyboard navigation, Changed — attention severity is graded, not binary, Changed — quick filters in front, field filters behind a disclosure, Fixed — "Attention first" sorted by the wrong key, Fixed — the "Live" pill made a claim it had not checked, Verification

### Community 142 - "2026-07-31 — Delivery Module Phase 3: Execution Correctness (and one retracted audit finding)"
Cohesion: 0.40
Nodes (5): 2026-07-31 — Delivery Module Phase 3: Execution Correctness (and one retracted audit finding), Already done, Fixed, Retracted — audit findings C-06 and F-01 were wrong, Testing

### Community 143 - "5. Vehicle Identity Flow"
Cohesion: 0.40
Nodes (5): 5. Vehicle Identity Flow, Authoritative identifier — determination, Complete identity call-site inventory, Documented mismatch scenarios, Evidence this is not hypothetical

### Community 144 - "adapters.py"
Cohesion: 0.14
Nodes (16): check_boundary(), Boundary validation — checks whether a package fits inside the container., calculate_total_weight(), check_weight(), Weight validation — tracks running total and checks against payload. No…, calculate_total_weight(), check_boundary(), check_weight() (+8 more)

### Community 145 - "2026-07-30 — Dispatch Module Phase 1: Incremental Live Updates"
Cohesion: 0.50
Nodes (4): 2026-07-30 — Dispatch Module Phase 1: Incremental Live Updates, Fixed, Out of Scope, Remaining Technical Debt / Deferred

### Community 146 - "Recommendation"
Cohesion: 0.20
Nodes (9): 1. Enable WAL — worth doing, low risk, 2. Set `busy_timeout` explicitly, 3. `--workers` — yes, but that is a *different* problem, First, a correction to the audit, How to reproduce, Recommendation, Suggested order, WAL and `--workers` — measurements and recommendation (+1 more)

### Community 147 - "3. Request Flow Diagram"
Cohesion: 0.50
Nodes (4): 3.1 Dashboard open → first paint, 3.2 Select a vehicle → complete a stop, 3. Request Flow Diagram, Cache inventory

### Community 148 - "2. System Architecture Diagram"
Cohesion: 0.67
Nodes (3): 2. System Architecture Diagram, Architectural observations, Component responsibilities

### Community 149 - "4. GPS Flow Diagram"
Cohesion: 0.67
Nodes (3): 4. GPS Flow Diagram, Additional GPS-path defects, The four-layer failure, in order

### Community 150 - "6. Database Relationship Diagram"
Cohesion: 0.67
Nodes (3): 6. Database Relationship Diagram, Data flow through the tables, Schema findings

### Community 151 - "test_fuel_routes.py"
Cohesion: 0.14
Nodes (14): app(), client(), count_connections(), db(), fixture, Route-layer tests for the fuel log API. Why this file exists…, The payload must be byte-identical to what the per-helper-connection version…, O(1), not O(rows). The exact number is not the point and would make this a… (+6 more)

### Community 154 - "test_vehicle_specs.py"
Cohesion: 0.25
Nodes (3): Tests for app/services/vehicle_specs.py — the vehicle envelope. The case these…, TestRelaxDimensions, TestTypeDefaultsAreSelfConsistent

### Community 155 - "2026-07-31 — Vehicle-constrained routing, phase A: POST migration, border avoidance, failure-mode split"
Cohesion: 0.29
Nodes (7): 2026-07-31 — Vehicle-constrained routing, phase A: POST migration, border avoidance, failure-mode split, Added — `avoid_borders: "all"` on every routing request, Changed — one ORS transport instead of two, Fixed — advanced routing options were structurally unreachable, Fixed — "no route exists" was indistinguishable from "ORS is broken", Not done, Verification

### Community 156 - "2026-07-31 — Vehicle-constrained routing, phase B: envelope schema, form, validation, type fallbacks"
Cohesion: 0.29
Nodes (7): 2026-07-31 — Vehicle-constrained routing, phase B: envelope schema, form, validation, type fallbacks, Added — form and table, Added — per-type fallbacks, and provenance that travels with them, Added — validation that catches the mistake this feature exists to prevent, Added — vehicle envelope columns, Fixed — `pytest tests/` was running migrations against the production database, Verification

### Community 158 - "2026-07-31 — Vehicle-constrained routing, phase C: restrictions applied, degraded-route path"
Cohesion: 0.33
Nodes (6): 2026-07-31 — Vehicle-constrained routing, phase C: restrictions applied, degraded-route path, Added — restrictions on every delivery routing request, Added — the degraded-route ladder, Added — the route says when it cannot be trusted, Fixed — the ETA cache would have served routes under superseded specs, Verification

### Community 159 - "2026-08-01 — Advance, Skip and Cancel can be undone"
Cohesion: 0.33
Nodes (6): 2026-08-01 — Advance, Skip and Cancel can be undone, Added — a bounded, one-step revert, Added — `POST /api/execution/revert`, and `can_revert` on `GET /api/stops`, Added — Revert button and an Undo toast, Not done, Verification

### Community 160 - "2026-08-01 — GPS timestamps are parsed server-side; "GPS stale 4920h""
Cohesion: 0.33
Nodes (6): 2026-08-01 — GPS timestamps are parsed server-side; "GPS stale 4920h", Added — "GPS age unknown", a third state, Fixed — TTAS dates were being read month-first in the browser, The test fixtures were the reason this survived, Unrelated pre-existing failure noticed, Verification

### Community 161 - "2026-08-01 — Stop phases are recorded, and corrections last the day"
Cohesion: 0.33
Nodes (6): 2026-08-01 — Stop phases are recorded, and corrections last the day, Added — `GET /api/stops/<id>/history` and an in-stop panel, Added — `stop_status_events`, one row per phase change, Changed — revert returns to the *recorded* phase, Changed — the 15-minute window is now the plan's day, Verification

### Community 162 - "2026-08-02 — Completing a stop requires photographic proof"
Cohesion: 0.33
Nodes (6): 2026-08-02 — Completing a stop requires photographic proof, Added — a stop cannot be completed without proof, Added — an override, because a hard block strands drivers, Added — the upload control that did not exist, Changed — 422, not 400, for a blocked completion, Verification

### Community 163 - "2026-08-02 — End-of-day export, and a persistent disk"
Cohesion: 0.33
Nodes (6): 2026-08-02 — End-of-day export, and a persistent disk, Added — `delivery_day_images` for photos that belong to a day, Added — `export_service`, rebuilding the operator's folder shape, Added — the End of Day page, Fixed — runtime data was on ephemeral storage, Verification

### Community 166 - "2026-07-31 — Gross vehicle weights loaded from the fleet spreadsheet (data, not code)"
Cohesion: 0.40
Nodes (5): 2026-07-31 — Gross vehicle weights loaded from the fleet spreadsheet (data, not code), How it was applied, The 4 container tractors were not touched, Three vehicles were being routed under the wrong profile, What the source file actually contained

### Community 167 - "TestSpeedPhraseParsing"
Cohesion: 0.11
Nodes (7): `_parse_speed_kmh` — TTAS sends no numeric speed field, only a Vietnamese…, `None` blanks the reading on the dashboard. TTAS saying "Dừng" is positive…, The symptom that gave this away: one payload yielding "stopped" and a non-zero…, Guards the ordering: the unit-anchored match is tried before the stopped-phrase…, TTAS is a Vietnamese-locale system; "37,5" must not become 375., Not 0 — the dispatcher must be able to tell "stopped" from "we have no reading"., TestSpeedPhraseParsing

### Community 168 - "TestLostSignal"
Cohesion: 0.14
Nodes (8): is_lost_signal(), True when TTAS is reporting the tracker as having lost signal. Written…, TTAS writes `MTH:6h48'` — *mất tín hiệu*, and how long for. Operator-reported…, Not "unknown" — that means a phrase we could not read, and the two want…, Guessing "lost signal" from a phrase we simply do not understand would put…, The marker stays on the map — where the truck was last seen is the most useful…, `MTH:6h48'` would have read as 6 km/h under the pre-2026-08-03 first-number-…, TestLostSignal

### Community 172 - "_raw_ttas"
Cohesion: 0.22
Nodes (5): A raw TTAS DevList item — the actual input contract of…, Tests for tracking_service.py. These previously fed hand-written dicts keyed on…, The field every age computation reads. `last_update` stays raw for display;…, _raw_ttas(), TestTrackingService

### Community 173 - "2026-07-31 — Ages refresh on a 15s clock; ETA no longer drifts on repaint"
Cohesion: 0.50
Nodes (4): 2026-07-31 — Ages refresh on a 15s clock; ETA no longer drifts on repaint, Fixed — arrival times crept later on every repaint, Fixed — displayed ages were only as fresh as the last successful poll, Verification

### Community 174 - "2026-08-02 — The driver named in a plan is the driver dispatch shows"
Cohesion: 0.50
Nodes (4): 2026-08-02 — The driver named in a plan is the driver dispatch shows, Fixed — the typed name never left the browser, Note — a new column needs the ALTER, not just the schema, Verification

### Community 176 - "utils.js"
Cohesion: 0.24
Nodes (7): calculateMultiPolygonCentroid(), calculatePolygonCentroid(), getDistanceMeters(), getLocationCentroid(), isPointInLocation(), isPointInPolygon(), showToast()

### Community 178 - "api_fuel_log_create"
Cohesion: 0.29
Nodes (8): api_fuel_log_create(), api_fuel_log_update(), One-shot resolution. Prefer ``build_index()`` when resolving several…, Best-effort canonical display form for a plate the user just typed.…, Body for a request that named a vehicle which isn't in the fleet. The system…, resolve(), suggest_plate_format(), unknown_vehicle_response()

### Community 179 - "config.py"
Cohesion: 0.20
Nodes (9): Application configuration — environment variable reads and constants. Extracted…, Shared mutable runtime state. Not one of the report's named modules — added…, db(), isolated_state(), no_network(), fixture, Tests for the background route refresher's geofence advance. Why this file…, `state` is process-global and the refresher writes the route cache. (+1 more)

### Community 180 - "TestOpenAccess"
Cohesion: 0.29
Nodes (3): A 401 or 503 here means a gate came back. Anything else — 200, 400 for a bad…, The most destructive endpoint: cascade-deletes everything. It is deliberately…, TestOpenAccess

### Community 181 - "tlp-escaping.test.js"
Cohesion: 0.17
Nodes (8): assert, fs, path, pending, ROOT, SRC, TEXT_FIELDS, vm

### Community 182 - "csv_response"
Cohesion: 0.33
Nodes (5): api_fuel_log_export(), csv_response(), CSV export helper. Extracted from the duplicated io.StringIO + csv.writer +…, Build a CSV download response from a header row and data rows. Uses utf-8-sig…, Response

### Community 185 - "2026-08-03 — A parked truck's speed was its parking time"
Cohesion: 0.40
Nodes (5): 2026-08-03 — A parked truck's speed was its parking time, Changed — the `reported_stopped` chip now fires when it should, Fixed — the number came out of the wrong part of the phrase, Not fixed — the same bug survives in `app/routes/trips.py`, Verification

### Community 187 - "2026-07-19 — Dead Space Quality (Future-Packability Estimation)"
Cohesion: 0.50
Nodes (4): 2026-07-19 — Dead Space Quality (Future-Packability Estimation), Added, Changed, Dead Space Quality Scoring

### Community 188 - "2026-07-30 — Truck Load Planner Phase 2: Fixed Empty-Space/Utilization Scoring"
Cohesion: 0.50
Nodes (4): 2026-07-30 — Truck Load Planner Phase 2: Fixed Empty-Space/Utilization Scoring, Fixed, Fixed during verification (not part of the original plan, found while testing), Testing

### Community 189 - "db_path"
Cohesion: 0.40
Nodes (5): db_path(), isolated_upload_root(), fixture, Keep uploaded test images out of the repository. image_service derives…, Create a fresh SQLite database with all delivery + vehicles tables.

### Community 190 - "2026-08-03 — A truck TTAS says it has lost is now in the No GPS list"
Cohesion: 0.50
Nodes (4): 2026-08-03 — A truck TTAS says it has lost is now in the No GPS list, Added — `MTH` is read as a state, not left as "unknown", Fixed — the filter tested for a position, not for reachability, Verification

### Community 191 - "Workspace Bug Audit — 2026-08-06"
Cohesion: 0.22
Nodes (8): 1. Critical — `auto-arrange` from a shipment returns HTTP 500, 2. Critical — background trip refresh: `BEGIN` inside a loop leaves an open transaction, 3. High — `static/js/truck-load-planner.js` has zero XSS escaping, 4. Medium — connection leak on the error path in `app/routes/*.py`, 5. Low / latent, 6. Checked and clean — do not re-audit, Verification notes, Workspace Bug Audit — 2026-08-06

### Community 192 - "api_fuel_log_profiles_list"
Cohesion: 0.50
Nodes (4): api_fuel_log_profiles_list(), _get_anomaly_multiplier(), Return the anomaly threshold multiplier for a vehicle. Default: 1.50 if vehicle…, Return all vehicle fuel profiles with their normal L/100km.

### Community 193 - "2026-07-30 — Truck Load Planner Phase 1: Fixed Stacking Scoring Bias + Hard Height Cap"
Cohesion: 0.50
Nodes (4): 2026-07-30 — Truck Load Planner Phase 1: Fixed Stacking Scoring Bias + Hard Height Cap, Changed, Fixed, Testing

### Community 194 - "2026-08-06 — Audit fixes: TLP shipment arrange, geofence transactions, TLP escaping"
Cohesion: 0.18
Nodes (11): 2026-08-06 — Audit fixes: TLP shipment arrange, geofence transactions, TLP escaping, Added — three test files, covering three modules that had none, Changed — `GET /api/fuel-log` opened 1,900 connections per request, Documentation, Fixed — 22 write handlers leaked their connection on the exception path, Fixed — `DELETE /api/tlp/packages/<id>` left orphaned rows, Fixed — `POST /api/tlp/auto-arrange` with a `shipment_id` returned 500, Fixed — `static/js/truck-load-planner.js` had no HTML escaping at all (+3 more)

### Community 195 - "2026-08-06 — A confirmed plan is editable, and reachable from the board"
Cohesion: 0.50
Nodes (4): 2026-08-06 — A confirmed plan is editable, and reachable from the board, Added — plan names in the dashboard's Plans panel link to the editor, Changed — `readOnly` is no longer derived from `confirmed`, The design decision this reverses

### Community 197 - "2026-07-30 — Dispatch Module Phase 3 QA Pass: Two Bugs Fixed"
Cohesion: 0.50
Nodes (4): 2026-07-30 — Dispatch Module Phase 3 QA Pass: Two Bugs Fixed, Fixed, Remaining Known Limitations (unchanged from Phase 3), Verified, no changes needed

### Community 198 - "2026-07-30 — Documentation Reorganization: Consolidated into docs/"
Cohesion: 0.50
Nodes (4): 2026-07-30 — Documentation Reorganization: Consolidated into docs/, Changed, Not touched (explicitly out of scope), Removed

## Knowledge Gaps
- **619 isolated node(s):** `$schema`, `.opencode/plugins/graphify.js`, `allEntries`, `filteredEntries`, `allVehicles` (+614 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **26 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `DatabaseManager` connect `DatabaseManager` to `TestExportNaming`, `truck_load_planner/routes.py`, `_create_plan`, `TestReorderValidation`, `TestEtaService`, `TestSpeedPhraseParsing`, `TestLostSignal`, `_raw_ttas`, `TestPlanDriverOverride`, `TestTransactions`, `execution_service.py`, `TestProofRequired`, `export_service.py`, `TestRevertStop`, `normalize_vehicle`, `test_delivery.py`, `parametrize`, `test_vehicle_core_data.py`, `FakeFileStorage`, `._stop`?**
  _High betweenness centrality (0.088) - this node is a cross-community bridge._
- **Why does `Package` connect `Package` to `truck_load_planner/routes.py`, `Container`, `GoogleSheetService`, `auto_arrange.py`, `ContainerConfig`, `test_all.py`, `distribution.py`, `LoadPlanningSession`, `PlanningState`, `debug_arrange.py`, `Planner`?**
  _High betweenness centrality (0.057) - this node is a cross-community bridge._
- **Why does `UI` connect `UI` to `._getViewDims`, `.updateStatus`, `delivery-plan-builder.js`, `ApiClient`, `vehicle-list.js`, `js/map.js`, `LoadPlannerApp`, `fuel-efficiency.js`, `delivery-export.js`, `utils.js`, `fuel-sync.js`, `vehicle-management.js`, `.update3DScene`, `main.js`, `timeline.js`?**
  _High betweenness centrality (0.023) - this node is a cross-community bridge._
- **Are the 30 inferred relationships involving `DatabaseManager` (e.g. with `UploadRejected` and `_NullIndex`) actually correct?**
  _`DatabaseManager` has 30 INFERRED edges - model-reasoned connections that need verification._
- **Are the 21 inferred relationships involving `Package` (e.g. with `AutoArrangeResult` and `AutoArrangeStrategy`) actually correct?**
  _`Package` has 21 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `Planner` (e.g. with `AutoArrangeResult` and `StrategyRegistry`) actually correct?**
  _`Planner` has 10 INFERRED edges - model-reasoned connections that need verification._
- **What connects `$schema`, `.opencode/plugins/graphify.js`, `allEntries` to the rest of the system?**
  _619 weakly-connected nodes found - possible documentation gaps or missing edges._