"""
Manual test: define packages below, run full pipeline with instrumentation.

Usage:
  python manual_test.py                          (internal engine, existing behavior)
  python manual_test.py --engine internal        (internal engine via engine API)
  python manual_test.py --engine py3dbp          (py3dbp engine)
  python manual_test.py --compare                (both engines, side-by-side)
"""
import sys, os, json, uuid, datetime, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ═══════════════════════════════════════════════════════════════════════
# EDIT THIS SECTION — define your packages here
# ═══════════════════════════════════════════════════════════════════════

PACKAGES = [
    # ── HÀNG THÙNG (Hàng xếp chồng) ──
    {"name": "AWC 30", "length": 650, "width": 430, "height": 450, "weight": 12.0, "stackable": True, "qty": 1},
    {"name": "AWC 30", "length": 420, "width": 150, "height": 420, "weight": 3.0, "stackable": True, "qty": 3},
    {"name": "AWS 315-4E", "length": 490, "width": 490, "height": 200, "weight": 6.4, "stackable": True, "qty": 1},
    {"name": "AWS 400-4E", "length": 600, "width": 600, "height": 240, "weight": 11.3, "stackable": True, "qty": 2},
    {"name": "AWS 450-4E", "length": 650, "width": 630, "height": 240, "weight": 12.5, "stackable": True, "qty": 1},
    {"name": "AWS 500-4E", "length": 710, "width": 700, "height": 260, "weight": 17.0, "stackable": True, "qty": 3},
    {"name": "AWS 560-4D", "length": 790, "width": 790, "height": 270, "weight": 21.5, "stackable": True, "qty": 2},
    {"name": "AWS 630-4D", "length": 870, "width": 870, "height": 260, "weight": 27.5, "stackable": True, "qty": 2},

    # ── HÀNG CÓ PALLET (Hàng không xếp chồng) ──
    {"name": "DVS 1200", "length": 700, "width": 520, "height": 390, "weight": 24.0, "stackable": False, "qty": 1},
    {"name": "DVS 1900", "length": 700, "width": 520, "height": 390, "weight": 24.0, "stackable": False, "qty": 3},
    {"name": "DVS 3000", "length": 700, "width": 520, "height": 390, "weight": 26.0, "stackable": False, "qty": 1},
    {"name": "DVS 500", "length": 460, "width": 370, "height": 270, "weight": 8.0, "stackable": False, "qty": 1},
    {"name": "CDF 225-4", "length": 700, "width": 580, "height": 610, "weight": 42.0, "stackable": False, "qty": 1},
    {"name": "CDF 250-4", "length": 1220, "width": 680, "height": 620, "weight": 88.0, "stackable": False, "qty": 1},
    {"name": "CDF 250-4", "length": 1220, "width": 680, "height": 620, "weight": 88.0, "stackable": False, "qty": 1},
    {"name": "CDF 280-4", "length": 730, "width": 650, "height": 690, "weight": 47.0, "stackable": False, "qty": 1},
    {"name": "CDF 315-4", "length": 860, "width": 790, "height": 800, "weight": 67.0, "stackable": False, "qty": 1},
    {"name": "CDF 315-4", "length": 860, "width": 790, "height": 800, "weight": 67.0, "stackable": False, "qty": 1},
    {"name": "FCS 450C", "length": 1290, "width": 830, "height": 1030, "weight": 177.0, "stackable": False, "qty": 2},
    {"name": "FCS 500C", "length": 1390, "width": 930, "height": 1110, "weight": 216.0, "stackable": False, "qty": 2},
    {"name": "KBF 200F", "length": 1160, "width": 680, "height": 670, "weight": 83.0, "stackable": False, "qty": 1},
    {"name": "KBF 200R", "length": 1020, "width": 1010, "height": 730, "weight": 98.0, "stackable": False, "qty": 2},
    {"name": "KBF 280F", "length": 1310, "width": 850, "height": 860, "weight": 143.0, "stackable": False, "qty": 1},
    {"name": "KBF 280R", "length": 1190, "width": 1130, "height": 910, "weight": 144.0, "stackable": False, "qty": 1},

    # ── HÀNG KO PALLET (Hàng không xếp chồng) ──
    {"name": "LC 1000-4/6TXA/20°", "length": 980, "width": 1140, "height": 1200, "weight": 285.0, "stackable": False, "qty": 1},
    {"name": "LC 710-4/12B/10°", "length": 730, "width": 840, "height": 860, "weight": 105.0, "stackable": False, "qty": 1},
    {"name": "LC 710-4/12B/22.5°", "length": 730, "width": 840, "height": 860, "weight": 110.0, "stackable": False, "qty": 1},
    {"name": "LC 800-4/12TXA/17.5°", "length": 930, "width": 930, "height": 840, "weight": 146.0, "stackable": False, "qty": 1},
    {"name": "LC 900-4/6TXA/22.5°", "length": 940, "width": 1060, "height": 1110, "weight": 200.0, "stackable": False, "qty": 2},
    {"name": "LC 900-4/6TXA/25°", "length": 940, "width": 1060, "height": 1110, "weight": 200.0, "stackable": False, "qty": 1},
    {"name": "LC 900-4/6TXA/27.5°", "length": 940, "width": 1060, "height": 1110, "weight": 245.0, "stackable": False, "qty": 3},
]
# ═══════════════════════════════════════════════════════════════════════
# OPTIONAL: save results to the database (set to True to test Rep-2/Rep-3)
# ═══════════════════════════════════════════════════════════════════════

SAVE_TO_DB = False   # set True to also write/read from routing_system.db
PLAN_NAME = "Manual Test"

# ═══════════════════════════════════════════════════════════════════════
# END OF CONFIG — everything below runs automatically
# ═══════════════════════════════════════════════════════════════════════


def _log_instrument(trace_id, rep, label, data):
    logpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "instrument_trace.jsonl")
    entry = {
        "ts": datetime.datetime.now().isoformat(),
        "trace_id": trace_id,
        "rep": rep,
        "label": label,
        "data": data,
    }
    with open(logpath, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def _pp_placement(pl):
    """Normalise an engine Placement to a comparable dict."""
    if hasattr(pl, "x"):
        x, y, z = pl.x, pl.y, pl.z
        pkg = pl.package
        d = {
            "package_id": pl.package_id,
            "x": x, "y": y, "z": z,
            "rotation": pl.rotation,
            "load_sequence": pl.load_sequence,
        }
        if pkg:
            d.update({
                "pkg_name": pkg.name,
                "pkg_len": pkg.length_mm,
                "pkg_wid": pkg.width_mm,
                "pkg_hei": pkg.height_mm,
                "pkg_wt": pkg.weight_kg,
                "pkg_color": pkg.color,
                "pkg_stackable": pkg.stackable,
            })
        return d
    return dict(pl)


def build_placement_dict(pl, vehicle_id=None):
    """Match the _build_placement_dict from routes.py."""
    pkg = pl.package
    d = {
        "package_id": pl.package_id,
        "x": pl.x, "y": pl.y, "z": pl.z,
        "rotation": pl.rotation,
        "load_sequence": pl.load_sequence,
        "_package": {
            "id": pkg.id if pkg else None,
            "name": pkg.name if pkg else "",
            "length": pkg.length_mm if pkg else 0,
            "width": pkg.width_mm if pkg else 0,
            "height": pkg.height_mm if pkg else 0,
            "weight_kg": pkg.weight_kg if pkg else 0,
            "color": pkg.color if pkg else "#3b82f6",
            "stackable": pkg.stackable if pkg else False,
            "allow_stacking": pkg.stackable if pkg else False,
        } if pkg else None,
        "_name": pkg.name if pkg else "",
        "_length": pkg.length_mm if pkg else 0,
        "_width": pkg.width_mm if pkg else 0,
        "_height": pkg.height_mm if pkg else 0,
        "_weight_kg": pkg.weight_kg if pkg else 0,
        "_color": pkg.color if pkg else "#3b82f6",
    }
    if vehicle_id is not None:
        d["vehicle_id"] = vehicle_id
    return d


# ── Shared helpers (used by both old and new paths) ───────────────────

def _load_db():
    import sqlite3
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "routing_system.db")
    if not os.path.exists(db_path):
        print(f"ERROR: {db_path} not found")
        sys.exit(1)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT v.id AS vehicle_id, v.plate_number, v.vehicle_type,
               cc.id AS cc_id, cc.name AS container_name,
               cc.cargo_length_mm, cc.cargo_width_mm, cc.cargo_height_mm, cc.payload_kg
        FROM vehicles v
        INNER JOIN container_configs cc ON cc.id = v.container_config_id
        ORDER BY v.plate_number
    """)
    vrows = c.fetchall()
    conn.close()
    if not vrows:
        print("ERROR: No vehicles found")
        sys.exit(1)
    return [dict(vr) for vr in vrows]


def _build_engine_packages():
    from truck_load_planner.engine.package import Package as EnginePackage
    pkgs = []
    for pd in PACKAGES:
        qty = pd.get("qty", 1)
        ep = EnginePackage(
            id=pd.get("id", 0),
            name=pd["name"],
            length_mm=pd["length"],
            width_mm=pd["width"],
            height_mm=pd["height"],
            weight_kg=pd.get("weight", pd.get("weight_kg", 0)),
            stackable=bool(pd.get("stackable", pd.get("allow_stacking", False))),
            allow_rotation=bool(pd.get("allow_rotation", True)),
            fragile=bool(pd.get("fragile", False)),
            color=pd.get("color", "#3b82f6"),
            horizontal_clearance_mm=float(pd.get("clearance_mm", 10)),
        )
        for _ in range(qty):
            pkgs.append(ep)
    return pkgs


def _print_engine_stats(label, result, total_packages):
    s = result.statistics
    print(f"\n{label}")
    print("-" * len(label))
    print(f"  Runtime:              {result.runtime_ms} ms")
    print(f"  Vehicles:             {s.get('vehicles_used', 0)}")
    print(f"  Packages Placed:      {s.get('packages_placed', 0)}")
    print(f"  Packages Failed:      {total_packages - s.get('packages_placed', 0)}")
    print(f"  Stacks:               {s.get('stacks', 0)}")
    print(f"  Volume Utilization:   {s.get('volume_used_pct', 0)}%")
    print(f"  Weight Utilization:   {s.get('weight_used_pct', 0)}%")
    print(f"  Max Stack Height:     {s.get('max_stack_height_mm', 0)} mm")

    if result.validation_failures:
        vf = result.validation_failures
        print(f"\n  Validation Failures ({len(vf)}):")
        boundary = sum(1 for f in vf if "boundary" in f.reason.lower() or "extends beyond" in f.reason.lower())
        collision = sum(1 for f in vf if "collision" in f.reason.lower())
        support = sum(1 for f in vf if "support" in f.reason.lower() or "stack" in f.reason.lower())
        door = sum(1 for f in vf if "door" in f.reason.lower())
        weight = sum(1 for f in vf if "weight" in f.reason.lower())
        cg = sum(1 for f in vf if "centre" in f.reason.lower() or "center" in f.reason.lower())
        rotation = sum(1 for f in vf if "rotation" in f.reason.lower())
        py3dbp_fit = sum(1 for f in vf if "py3dbp_fit" in f.check or "fit" in f.reason.lower())
        other = len(vf) - boundary - collision - support - door - weight - cg - rotation - py3dbp_fit

        cats = [
            ("Boundary", boundary),
            ("Collision", collision),
            ("Support/Stacking", support),
            ("Door", door),
            ("Weight", weight),
            ("Center of Gravity", cg),
            ("Rotation", rotation),
            ("py3dbp Fit", py3dbp_fit),
        ]
        for name, count in cats:
            if count:
                print(f"    {name}: {count}")

    if result.unplaced_packages:
        print(f"\n  Unplaced ({len(result.unplaced_packages)}):")
        for name in result.unplaced_packages[:5]:
            print(f"    - {name}")
        if len(result.unplaced_packages) > 5:
            print(f"    ... and {len(result.unplaced_packages) - 5} more")


# ── Original run_test (unchanged, backward compat) ────────────────────

def run_test():
    if not PACKAGES:
        print("ERROR: No packages defined. Edit PACKAGES list in this script.")
        sys.exit(1)

    trace_id = str(uuid.uuid4())[:8]
    print(f"Trace ID: {trace_id}")
    print(f"Testing {sum(p.get('qty', 1) for p in PACKAGES)} packages...")

    # ── 1. Build EnginePackage objects ─────────────────────────────
    from truck_load_planner.engine.package import Package as EnginePackage

    engine_packages = []
    for pd in PACKAGES:
        qty = pd.get("qty", 1)
        ep = EnginePackage(
            id=pd.get("id", 0),
            name=pd["name"],
            length_mm=pd["length"],
            width_mm=pd["width"],
            height_mm=pd["height"],
            weight_kg=pd.get("weight", pd.get("weight_kg", 0)),
            stackable=bool(pd.get("stackable", pd.get("allow_stacking", False))),
            allow_rotation=bool(pd.get("allow_rotation", True)),
            fragile=bool(pd.get("fragile", False)),
            color=pd.get("color", "#3b82f6"),
            horizontal_clearance_mm=float(pd.get("clearance_mm", 10)),
        )
        for _ in range(qty):
            engine_packages.append(ep)

    print(f"  Engine packages: {len(engine_packages)}")
    s_cnt = sum(1 for p in engine_packages if p.stackable)
    ns_cnt = len(engine_packages) - s_cnt
    print(f"  Stackable: {s_cnt}, Non-stackable: {ns_cnt}")

    # ── 2. Load vehicles from database ────────────────────────────
    import sqlite3
    from truck_load_planner.session import LoadPlanningSession
    from truck_load_planner.models import ContainerConfig

    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "routing_system.db")
    if not os.path.exists(db_path):
        print(f"ERROR: {db_path} not found")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("""
        SELECT v.id AS vehicle_id, v.plate_number, v.vehicle_type,
               cc.id AS cc_id, cc.name AS container_name,
               cc.cargo_length_mm, cc.cargo_width_mm, cc.cargo_height_mm, cc.payload_kg
        FROM vehicles v
        INNER JOIN container_configs cc ON cc.id = v.container_config_id
        ORDER BY v.plate_number
    """)
    vrows = c.fetchall()
    conn.close()

    if not vrows:
        print("ERROR: No vehicles found")
        sys.exit(1)

    vehicle_sessions = []
    for vr in vrows:
        vinfo = dict(vr)
        cc = ContainerConfig(
            id=vinfo["cc_id"],
            name=vinfo.get("container_name", ""),
            cargo_length_mm=vinfo["cargo_length_mm"],
            cargo_width_mm=vinfo["cargo_width_mm"],
            cargo_height_mm=vinfo["cargo_height_mm"],
            payload_kg=vinfo["payload_kg"],
        )
        session = LoadPlanningSession()
        session.select_container(cc)
        session.vehicle_id = vinfo["vehicle_id"]
        vehicle_sessions.append((vinfo, session))

    print(f"  Vehicles loaded: {len(vehicle_sessions)}")

    # ── 3. Run distribution ───────────────────────────────────────
    from truck_load_planner.engine.distribution import distribute_across_vehicles
    from truck_load_planner.engine.trace_mutations import M
    M.reset()

    placed, failed, unplaced, _, _ = distribute_across_vehicles(
        engine_packages, vehicle_sessions, debug=False,
    )

    # ── 4. Log Rep-1: raw engine placements ───────────────────────
    for vinfo, session in vehicle_sessions:
        raw_pls = [_pp_placement(pl) for pl in session._planner.placements]
        _log_instrument(trace_id, 1, "planner-raw-placements", {
            "vehicle_id": vinfo["vehicle_id"],
            "plate_number": vinfo["plate_number"],
            "placements": raw_pls,
        })

    # ── 5. Log vehicle summary (same format as routes.py) ─────────
    summary_lines = []
    total_placed = 0
    for vinfo, session in vehicle_sessions:
        cnt = len(session._planner.placements) if session._planner else 0
        if cnt > 0:
            summary_lines.append(f"  Vehicle {vinfo['plate_number']}: {cnt} packages")
            total_placed += cnt
    _log_instrument(trace_id, 99, "vehicle-summary-before-save", {
        "summary_lines": summary_lines,
        "total_packages": total_placed,
        "vehicle_count": len(summary_lines),
    })
    print("VEHICLE ASSIGNMENT (manual_test.py):")
    for l in summary_lines:
        print(l)
    print(f"  Total: {total_placed} packages in {len(summary_lines)} vehicles")

    # ── 6. Build JSON response (Rep-4) ────────────────────────────
    per_vehicle = []
    all_placements = []
    used_vehicles = 0
    total_stack = 0

    for vinfo, session in vehicle_sessions:
        v_placements = [build_placement_dict(pl, vehicle_id=vinfo["vehicle_id"])
                        for pl in session._planner.placements]
        if v_placements:
            used_vehicles += 1
            # count stacks
            for pl in session._planner.placements:
                if getattr(pl, 'z', 0) > 0:
                    total_stack += 1
            per_vehicle.append({
                "vehicle_id": vinfo["vehicle_id"],
                "plate_number": vinfo["plate_number"],
                "package_count": len(v_placements),
            })
        all_placements.extend(v_placements)

    json_response = {
        "multi_vehicle": True,
        "success": len(all_placements) > 0,
        "summary": {
            "placed_packages": len(all_placements),
            "failed_packages": len(engine_packages) - len(all_placements),
            "utilization": 0.0,
            "warnings": [],
            "unplaced_packages": unplaced,
        },
        "per_vehicle": per_vehicle,
        "placements": all_placements,
    }

    _log_instrument(trace_id, 4, "json-sent-to-frontend", {
        "multi_vehicle": True,
        "per_vehicle": per_vehicle,
        "placements": [
            {
                "package_id": p["package_id"],
                "x": p["x"], "y": p["y"], "z": p["z"],
                "rotation": p["rotation"],
                "load_sequence": p["load_sequence"],
                "vehicle_id": p.get("vehicle_id"),
                "_name": p.get("_name"),
                "_length": p.get("_length"), "_width": p.get("_width"), "_height": p.get("_height"),
            }
            for p in all_placements
        ],
        "summary": json_response["summary"],
    })

    # ── 6. Optionally save to DB (Rep-2) and read back (Rep-3) ──
    if SAVE_TO_DB:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()

        # Create a plan for each vehicle
        plan_ids = []
        for vinfo, session in vehicle_sessions:
            v_placements = [p for p in all_placements if p.get("vehicle_id") == vinfo["vehicle_id"]]
            if not v_placements:
                continue

            c.execute("""
                INSERT INTO tlp_load_plans (name, vehicle_id, shipment_id, planner, notes, status)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (f"{PLAN_NAME} - {vinfo['plate_number']}", vinfo["vehicle_id"], None,
                  "manual_test", "", "draft"))
            plan_id = c.lastrowid
            plan_ids.append(plan_id)

            placements_to_insert = []
            for pl in v_placements:
                placement_row = (
                    plan_id, None, pl["package_id"],
                    pl["x"], pl["y"], pl.get("z", 0),
                    pl.get("rotation", 0), 0, pl.get("load_sequence"),
                )
                placements_to_insert.append(placement_row)
                c.execute("""
                    INSERT INTO tlp_placements (load_plan_id, shipment_item_id, package_id,
                      x, y, z, rotation, stack_level, load_sequence)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, placement_row)

            # Log Rep-2: DB write
            _log_instrument(trace_id, 2, "db-writes-insert", {
                "plan_id": plan_id,
                "vehicle_id": vinfo["vehicle_id"],
                "plate_number": vinfo["plate_number"],
                "placements_written": [
                    {"package_id": r[2], "x": r[3], "y": r[4], "z": r[5],
                     "rotation": r[6], "stack_level": r[7], "load_sequence": r[8]}
                    for r in placements_to_insert
                ],
            })

        conn.commit()

        # Read back (Rep-3)
        conn3 = sqlite3.connect(db_path)
        conn3.row_factory = sqlite3.Row
        for plan_id in plan_ids:
            prow = conn3.execute("""
                SELECT lp.*, v.plate_number, v.vehicle_type
                FROM tlp_load_plans lp
                LEFT JOIN vehicles v ON v.id = lp.vehicle_id
                WHERE lp.id = ?
            """, (plan_id,)).fetchone()
            if not prow:
                continue
            plan_row = dict(prow)

            placements_rows = conn3.execute("""
                SELECT pl.*, p.name AS package_name, p.length, p.width, p.height,
                       p.weight_kg, p.allow_stacking, p.color
                FROM tlp_placements pl
                LEFT JOIN tlp_packages p ON p.id = pl.package_id
                WHERE pl.load_plan_id = ?
                ORDER BY pl.load_sequence
            """, (plan_id,)).fetchall()
            placements_read = [dict(r) for r in placements_rows]

            _log_instrument(trace_id, 3, "db-reads-select", {
                "plan_id": plan_id,
                "vehicle_id": plan_row.get("vehicle_id"),
                "placements_read": placements_read,
            })

        conn3.close()
        conn.close()

        # Clean up created plans
        for plan_id in plan_ids:
            conn2 = sqlite3.connect(db_path)
            c2 = conn2.cursor()
            c2.execute("DELETE FROM tlp_placements WHERE load_plan_id = ?", (plan_id,))
            c2.execute("DELETE FROM tlp_load_plans WHERE id = ?", (plan_id,))
            conn2.commit()
            conn2.close()
        print(f"  Wrote+read+cleaned {len(plan_ids)} plans from DB")

    # ── 7. Dump mutation trace ────────────────────────────────────
    M.dump_all()

    # ── 8. Print summary ──────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"RESULTS (trace_id={trace_id})")
    print(f"{'='*70}")

    total_pkgs = sum(p.get('qty', 1) for p in PACKAGES)
    placed_cnt = len(all_placements)
    stack_cnt = sum(1 for pl in all_placements if pl.get("z", 0) > 0)
    floor_stackable = sum(1 for pl in all_placements if pl.get("z", 0) == 0 and pl.get("_package", {}).get("stackable"))
    floor_nonstackable = sum(1 for pl in all_placements if pl.get("z", 0) == 0 and not pl.get("_package", {}).get("stackable"))

    print(f"  Packages: {total_pkgs} total, {placed_cnt} placed, {failed} failed")
    print(f"  Vehicles: {used_vehicles}")
    print(f"  Stacks:   {stack_cnt}")
    print(f"  Floor (stackable):    {floor_stackable}")
    print(f"  Floor (non-stackable): {floor_nonstackable}")
    print(f"\n  Logged to instrument_trace.jsonl")

    if SAVE_TO_DB:
        print(f"\n  View all reps: python read_instrument_trace.py {trace_id}")
    else:
        print(f"\n  Re-run with SAVE_TO_DB=True to capture Rep-2 and Rep-3")
        print(f"  View reps 1 & 4: python read_instrument_trace.py {trace_id}")


# ── New engine-agnostic benchmark path ────────────────────────────────

def run_benchmark(engine_name: str):
    """Run the benchmark with the specified engine and print results."""
    from truck_load_planner.engines import get_engine

    vehicle_data = _load_db()
    packages = _build_engine_packages()
    total_pkgs = len(packages)

    s_cnt = sum(1 for p in packages if p.stackable)
    ns_cnt = total_pkgs - s_cnt

    print(f"Shipment: {total_pkgs} packages ({s_cnt} stackable, {ns_cnt} non-stackable)")
    print(f"Vehicles available: {len(vehicle_data)}")

    engine = get_engine(engine_name)
    result = engine.pack(vehicle_data, packages)

    _print_engine_stats(
        f"{engine_name.title()} Engine",
        result, total_pkgs,
    )

    return result


def run_comparison():
    """Run both engines and print side-by-side comparison."""
    vehicle_data = _load_db()
    packages = _build_engine_packages()
    total_pkgs = len(packages)

    s_cnt = sum(1 for p in packages if p.stackable)
    ns_cnt = total_pkgs - s_cnt

    print(f"{'='*70}")
    print(f"Shipment: {total_pkgs} packages ({s_cnt} stackable, {ns_cnt} non-stackable)")
    print(f"Vehicles available: {len(vehicle_data)}")
    print(f"{'='*70}")

    from truck_load_planner.engines import get_engine

    results = {}
    for engine_name in ["internal", "py3dbp"]:
        engine = get_engine(engine_name)
        result = engine.pack(vehicle_data, packages)
        results[engine_name] = result

    print(f"\n{'='*70}")
    print("COMPARISON")
    print(f"{'='*70}")

    labels = {
        "internal": "Internal Engine",
        "py3dbp": "py3dbp Engine",
    }

    for engine_name in ["internal", "py3dbp"]:
        result = results[engine_name]
        s = result.statistics
        label = labels[engine_name]
        print(f"\n{label}")
        print("-" * len(label))
        print(f"  Runtime:              {result.runtime_ms:>8} ms")
        print(f"  Vehicles:             {s.get('vehicles_used', 0):>8}")
        print(f"  Packages Placed:      {s.get('packages_placed', 0):>8}")
        print(f"  Packages Failed:      {total_pkgs - s.get('packages_placed', 0):>8}")
        print(f"  Stacks:               {s.get('stacks', 0):>8}")
        print(f"  Volume Utilization:   {s.get('volume_used_pct', 0):>7.1f}%")
        print(f"  Weight Utilization:   {s.get('weight_used_pct', 0):>7.1f}%")
        print(f"  Max Stack Height:     {s.get('max_stack_height_mm', 0):>8} mm")

        if result.validation_failures:
            vf = result.validation_failures
            print(f"  Validation Failures:  {len(vf):>8}")
            for f in vf[:5]:
                print(f"    - {f.package_name}: {f.reason}")
            if len(vf) > 5:
                print(f"    ... and {len(vf) - 5} more")

    print(f"\n{'='*70}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manual test / benchmark for Truck Load Planner")
    parser.add_argument("--engine", choices=["internal", "py3dbp"], default=None,
                        help="Packing engine to use (default: internal)")
    parser.add_argument("--compare", action="store_true",
                        help="Run both engines side-by-side")
    args = parser.parse_args()

    if args.compare:
        run_comparison()
    elif args.engine:
        run_benchmark(args.engine)
    else:
        run_test()
