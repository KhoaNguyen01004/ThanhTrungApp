#!/usr/bin/env python3
"""
Unified test harness for truck load planner.

Usage:
    python tests/test_all.py benchmark --mode <mode> [options]
    python tests/test_all.py diagnose --scenario <scenario> [--full]
    python tests/test_all.py debug --mode <mode>
    python tests/test_all.py query --mode <mode>
    python tests/test_all.py instrument --mode <mode>

Modes:
    benchmark:     distribution | floor_contact | real_data
    diagnose:      general | kbf_lc900 | candidates | stacking
    debug:         py3dbp | stats | validation | vehicles
    query:         vehicles | tables | db | shipments
    instrument:    trace | bug-trace

All output is saved to reports/{cmd}_{mode}_{timestamp}.txt
"""

import argparse, sys, os, time, sqlite3, json, math, random
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

REPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reports")
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "routing_system.db")

# ══════════════════════════════════════════════════════════════════
#  Shared helpers
# ══════════════════════════════════════════════════════════════════

_log_lines: list[str] = []

def log(*args, **kw):
    line = " ".join(str(a) for a in args)
    print(line)
    _log_lines.append(line)

def hr(title="", char="=", w=72):
    if title:
        pad = (w - len(title) - 2) // 2
        line = f"{char * pad} {title} {char * (w - pad - len(title) - 2)}"
    else:
        line = char * w
    log(line)

def save_report(cmd, mode):
    os.makedirs(REPORTS_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(REPORTS_DIR, f"{cmd}_{mode}_{ts}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(_log_lines))
    log(f"\nReport saved: {path}")

# ── DB helpers ────────────────────────────────────────────────────

def db_connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def load_vehicles_from_db():
    conn = db_connect()
    c = conn.cursor()
    c.execute("""
        SELECT v.id AS vehicle_id, v.plate_number, v.vehicle_type,
               cc.id AS cc_id, cc.name AS container_name,
               cc.cargo_length_mm, cc.cargo_width_mm, cc.cargo_height_mm, cc.payload_kg
        FROM vehicles v
        INNER JOIN container_configs cc ON cc.id = v.container_config_id
        ORDER BY v.plate_number
    """)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def load_packages_from_db():
    from truck_load_planner.engine.package import Package
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT * FROM tlp_packages ORDER BY id")
    pkgs = []
    for r in c.fetchall():
        pkgs.append(Package(
            id=r["id"], name=r["name"],
            length_mm=r["length"], width_mm=r["width"], height_mm=r["height"],
            weight_kg=r["weight_kg"],
            stackable=bool(r["allow_stacking"]),
            allow_rotation=bool(r["allow_rotation"]),
        ))
    conn.close()
    return pkgs

def make_vehicle_sessions(vehicle_rows):
    from truck_load_planner.session import LoadPlanningSession
    from truck_load_planner.models import ContainerConfig
    sessions = []
    for v in vehicle_rows:
        session = LoadPlanningSession()
        cc = ContainerConfig(
            id=v.get("cc_id"), name=v.get("container_name", ""),
            cargo_length_mm=v["cargo_length_mm"],
            cargo_width_mm=v["cargo_width_mm"],
            cargo_height_mm=v["cargo_height_mm"],
            payload_kg=v["payload_kg"],
        )
        session.select_container(cc)
        session.vehicle_id = v["vehicle_id"]
        sessions.append((v, session))
    return sessions

def avg(lst):
    return sum(lst) / len(lst) if lst else 0

# ══════════════════════════════════════════════════════════════════
#  BENCHMARK
# ══════════════════════════════════════════════════════════════════

def cmd_benchmark_distribution():
    from truck_load_planner.engine.package import Package
    from truck_load_planner.engine.distribution import distribute_across_vehicles

    pkg_defs = [
        {"name": "AWC 30", "l": 650, "w": 430, "h": 450, "wt": 12.0, "stk": True, "qty": 1},
        {"name": "AWC 30", "l": 420, "w": 150, "h": 420, "wt": 3.0, "stk": True, "qty": 3},
        {"name": "AWS 315-4E", "l": 490, "w": 490, "h": 200, "wt": 6.4, "stk": True, "qty": 1},
        {"name": "AWS 400-4E", "l": 600, "w": 600, "h": 240, "wt": 11.3, "stk": True, "qty": 2},
        {"name": "AWS 450-4E", "l": 650, "w": 630, "h": 240, "wt": 12.5, "stk": True, "qty": 1},
        {"name": "AWS 500-4E", "l": 710, "w": 700, "h": 260, "wt": 17.0, "stk": True, "qty": 3},
        {"name": "AWS 560-4D", "l": 790, "w": 790, "h": 270, "wt": 21.5, "stk": True, "qty": 2},
        {"name": "AWS 630-4D", "l": 870, "w": 870, "h": 260, "wt": 27.5, "stk": True, "qty": 2},
        {"name": "DVS 1200", "l": 700, "w": 520, "h": 390, "wt": 24.0, "stk": False, "qty": 1},
        {"name": "DVS 1900", "l": 700, "w": 520, "h": 390, "wt": 24.0, "stk": False, "qty": 3},
        {"name": "DVS 3000", "l": 700, "w": 520, "h": 390, "wt": 26.0, "stk": False, "qty": 1},
        {"name": "DVS 500", "l": 460, "w": 370, "h": 270, "wt": 8.0, "stk": False, "qty": 1},
        {"name": "CDF 225-4", "l": 700, "w": 580, "h": 610, "wt": 42.0, "stk": False, "qty": 1},
        {"name": "CDF 250-4", "l": 1220, "w": 680, "h": 620, "wt": 88.0, "stk": False, "qty": 2},
        {"name": "CDF 280-4", "l": 730, "w": 650, "h": 690, "wt": 47.0, "stk": False, "qty": 1},
        {"name": "CDF 315-4", "l": 860, "w": 790, "h": 800, "wt": 67.0, "stk": False, "qty": 2},
        {"name": "FCS 450C", "l": 1290, "w": 830, "h": 1030, "wt": 177.0, "stk": False, "qty": 2},
        {"name": "FCS 500C", "l": 1390, "w": 930, "h": 1110, "wt": 216.0, "stk": False, "qty": 2},
        {"name": "KBF 200F", "l": 1160, "w": 680, "h": 670, "wt": 83.0, "stk": False, "qty": 1},
        {"name": "KBF 200R", "l": 1020, "w": 1010, "h": 730, "wt": 98.0, "stk": False, "qty": 2},
        {"name": "KBF 280F", "l": 1310, "w": 850, "h": 860, "wt": 143.0, "stk": False, "qty": 1},
        {"name": "KBF 280R", "l": 1190, "w": 1130, "h": 910, "wt": 144.0, "stk": False, "qty": 1},
        {"name": "LC 1000-4/6TXA/20", "l": 980, "w": 1140, "h": 1200, "wt": 285.0, "stk": False, "qty": 1},
        {"name": "LC 710-4/12B/10", "l": 730, "w": 840, "h": 860, "wt": 105.0, "stk": False, "qty": 1},
        {"name": "LC 710-4/12B/22.5", "l": 730, "w": 840, "h": 860, "wt": 110.0, "stk": False, "qty": 1},
        {"name": "LC 800-4/12TXA/17.5", "l": 930, "w": 930, "h": 840, "wt": 146.0, "stk": False, "qty": 1},
        {"name": "LC 900-4/6TXA/22.5", "l": 940, "w": 1060, "h": 1110, "wt": 200.0, "stk": False, "qty": 2},
        {"name": "LC 900-4/6TXA/25", "l": 940, "w": 1060, "h": 1110, "wt": 200.0, "stk": False, "qty": 1},
        {"name": "LC 900-4/6TXA/27.5", "l": 940, "w": 1060, "h": 1110, "wt": 245.0, "stk": False, "qty": 3},
    ]
    pkgs = []
    nid = 0
    for d in pkg_defs:
        for _ in range(d["qty"]):
            nid += 1
            pkgs.append(Package(id=nid, name=d["name"],
                length_mm=d["l"], width_mm=d["w"], height_mm=d["h"],
                weight_kg=d["wt"], stackable=d["stk"], allow_rotation=True))

    vrows = load_vehicles_from_db()
    sessions = make_vehicle_sessions(vrows)
    log(f"Packages: {len(pkgs)}, Vehicles: {len(sessions)}")

    t0 = time.perf_counter()
    placed, failed, unplaced, _, _ = distribute_across_vehicles(pkgs, sessions, debug=False)
    elapsed = time.perf_counter() - t0
    active = sum(1 for _, s in sessions if len(s._planner.placements) > 0)

    log(f"\nDistribution: {elapsed:.3f}s | Vehicles active: {active} | Placed: {placed} | Failed: {failed}")
    for vinfo, session in sessions:
        pls = session._planner.placements
        if not pls:
            continue
        cont = session._planner.container
        stacks = sum(1 for pl in pls if pl.z > 0.001)
        pkg_names = list(dict.fromkeys(pl.package.name for pl in pls if pl.package))
        log(f"  V{vinfo['vehicle_id']} {vinfo.get('plate_number','?'):>8s}: {len(pls)} pkgs, {stacks} stacks — {', '.join(pkg_names[:5])}")
    save_report("benchmark", "distribution")

def cmd_benchmark_floor_contact():
    from truck_load_planner.engine.package import Package
    from truck_load_planner.engine.container import Container
    from truck_load_planner.engine.planner import Planner
    import truck_load_planner.engine.scorer as scorer_mod

    CONTAINER = Container(id=1, name="40ft", length=12000, width=2400, height=2700, payload_kg=28000)
    random.seed(42)
    RATIOS = [0.3, 0.5, 0.7, 0.9]
    PKG_COUNTS = [20, 35, 50]
    TRIALS_PER_CELL = 5

    def gen_shipment(n, ratio):
        pkgs = []
        for i in range(n):
            is_stk = random.random() < ratio
            size = random.random()
            if size < 0.2:
                l, w, h, wt = random.randint(1000,1400), random.randint(800,1200), random.randint(600,1000), random.randint(60,120)
            elif size < 0.8:
                l, w, h, wt = random.randint(600,1000), random.randint(500,800), random.randint(300,600), random.randint(20,60)
            else:
                l, w, h, wt = random.randint(300,600), random.randint(300,500), random.randint(200,400), random.randint(10,25)
            pkgs.append(Package(id=i, name=f"P{i}", length_mm=l, width_mm=w, height_mm=h, weight_kg=wt, stackable=is_stk))
        return pkgs

    def run_trial(pkgs):
        planner = Planner(CONTAINER)
        t0 = time.perf_counter()
        result = planner.auto_arrange(pkgs, debug=False)
        elapsed = time.perf_counter() - t0
        stack_count = sum(1 for pl in planner.placements if pl.z > 0)
        ns_on_floor = sum(1 for pl in planner.placements if pl.z < 0.001 and pl.package and not pl.package.stackable)
        s_on_floor = sum(1 for pl in planner.placements if pl.z < 0.001 and pl.package and pl.package.stackable)
        max_x = max((pl.x + (pl.package.length_mm if pl.rotation in (0,180) else pl.package.width_mm) for pl in planner.placements if pl.z < 0.001 and pl.package), default=0)
        total_vol = CONTAINER.length * CONTAINER.width * CONTAINER.height
        pkg_vol = sum(pl.package.length_mm * pl.package.width_mm * pl.package.height_mm for pl in planner.placements if pl.package)
        return {
            "placed": result.placed_packages, "failed": result.failed_packages,
            "stack_count": stack_count, "ns_on_floor": ns_on_floor, "s_on_floor": s_on_floor,
            "max_floor_x_mm": max_x, "utilization_pct": pkg_vol / total_vol * 100,
            "plan_score": result.total_score, "time_s": elapsed,
        }

    orig_w = dict(scorer_mod.SCORING_WEIGHTS)
    all_25, all_5 = [], []
    for n_pkgs in PKG_COUNTS:
        for ratio in RATIOS:
            for trial in range(TRIALS_PER_CELL):
                pkgs = gen_shipment(n_pkgs, ratio)
                scorer_mod.SCORING_WEIGHTS["floor_contact"] = 25
                all_25.append(run_trial(pkgs))
                scorer_mod.SCORING_WEIGHTS["floor_contact"] = 5
                all_5.append(run_trial(pkgs))
    scorer_mod.SCORING_WEIGHTS["floor_contact"] = orig_w["floor_contact"]

    hr("BENCHMARK: floor_contact weight 25 vs 5")
    log(f"Trials per config: {len(all_25)}")
    log(f"\n{'Metric':<30s} {'W=25':>12s} {'W=5':>12s} {'Change':>12s}")
    log("-" * 66)
    for name, key, fmt in [
        ("Placed (avg)", "placed", "{:.1f}"), ("Failed (avg)", "failed", "{:.1f}"),
        ("Stacks (avg)", "stack_count", "{:.1f}"), ("NS on floor (avg)", "ns_on_floor", "{:.1f}"),
        ("S on floor (avg)", "s_on_floor", "{:.1f}"), ("Utilization % (avg)", "utilization_pct", "{:.1f}"),
        ("Vehicles", "vehicles", "{:.2f}"), ("Time (s, avg)", "time_s", "{:.4f}"),
    ]:
        v25 = avg([r[key] for r in all_25])
        v5 = avg([r[key] for r in all_5])
        log(f"{name:<30s} {fmt.format(v25):>12s} {fmt.format(v5):>12s} {fmt.format(v5-v25):>12s}")
    save_report("benchmark", "floor_contact")

def cmd_benchmark_real_data():
    from truck_load_planner.engine.distribution import distribute_across_vehicles
    from truck_load_planner.session import LoadPlanningSession
    from truck_load_planner.models import ContainerConfig

    pkgs = load_packages_from_db()
    stackable = sum(1 for p in pkgs if p.stackable)
    log(f"Loaded {len(pkgs)} packages ({stackable} stackable, {len(pkgs)-stackable} non-stackable)")

    vrows = load_vehicles_from_db()
    log(f"Loaded {len(vrows)} vehicles")

    def build_sessions(rows):
        sessions = []
        for v in rows:
            session = LoadPlanningSession()
            cc = ContainerConfig(id=v.get("cc_id"), name=v.get("container_name",""),
                cargo_length_mm=v["cargo_length_mm"], cargo_width_mm=v["cargo_width_mm"],
                cargo_height_mm=v["cargo_height_mm"], payload_kg=v["payload_kg"])
            session.select_container(cc)
            session.vehicle_id = v["vehicle_id"]
            sessions.append((v, session))
        return sessions

    for weight_val in [25, 5]:
        import truck_load_planner.engine.scorer as scorer_mod
        scorer_mod.SCORING_WEIGHTS["floor_contact"] = weight_val

        sessions = build_sessions(vrows)
        t0 = time.perf_counter()
        placed, failed, unplaced, _, _ = distribute_across_vehicles(pkgs, sessions, debug=False)
        elapsed = time.perf_counter() - t0

        active = sum(1 for _, s in sessions if len(s._planner.placements) > 0)
        total_stack = sum(sum(1 for pl in s._planner.placements if pl.z > 0.001) for _, s in sessions)
        total_ns_floor = sum(sum(1 for pl in s._planner.placements if pl.package and not pl.package.stackable and pl.z < 0.001) for _, s in sessions)
        total_s_floor = sum(sum(1 for pl in s._planner.placements if pl.package and pl.package.stackable and pl.z < 0.001) for _, s in sessions)
        total_pkg_vol = sum(pl.package.length_mm * pl.package.width_mm * pl.package.height_mm for _, s in sessions for pl in s._planner.placements if pl.package)
        total_cont_vol = sum(s._planner.container.length * s._planner.container.width * s._planner.container.height for _, s in sessions)

        log(f"\nfloor_contact = {weight_val}:")
        log(f"  Vehicles: {active} | Placed: {placed} | Failed: {len(unplaced)}")
        log(f"  Stacks: {total_stack} | NS floor: {total_ns_floor} | S floor: {total_s_floor}")
        log(f"  Vol util: {total_pkg_vol/total_cont_vol*100:.1f}% | Time: {elapsed:.3f}s")

    save_report("benchmark", "real_data")

# ══════════════════════════════════════════════════════════════════
#  DIAGNOSE
# ══════════════════════════════════════════════════════════════════

def cmd_diagnose_general(full):
    from truck_load_planner.engine.package import Package
    from truck_load_planner.engine.container import Container
    from truck_load_planner.engine.planner import Planner

    CONTAINERS = {
        "truck": Container(id=10, name="Truck", length=9700, width=2370, height=2320, payload_kg=28000),
    }
    PACKAGES = {
        "KBF": Package(id=1, name="KBF 280R", length_mm=1050, width_mm=2370, height_mm=2320, weight_kg=2000, stackable=False, allow_rotation=False),
        "LC900": Package(id=2, name="LC 900", length_mm=900, width_mm=770, height_mm=1200, weight_kg=500, stackable=True, allow_rotation=True),
        "PKG_A": Package(id=3, name="PKG_A", length_mm=800, width_mm=600, height_mm=500, weight_kg=100, stackable=True, allow_rotation=True),
        "PKG_B": Package(id=4, name="PKG_B", length_mm=600, width_mm=500, height_mm=400, weight_kg=60, stackable=True, allow_rotation=True),
        "PKG_C": Package(id=5, name="PKG_C", length_mm=1200, width_mm=800, height_mm=600, weight_kg=200, stackable=False, allow_rotation=True),
    }

    c = CONTAINERS["truck"]
    planner = Planner(c)
    kbf = PACKAGES["KBF"]
    lc = PACKAGES["LC900"]
    r1 = planner.place_package(kbf, 0, 0, 0, 0)
    assert r1.valid, f"KBF failed: {r1.reasons}"
    pkgs = [lc, lc, lc]
    result = planner.auto_arrange(pkgs, debug=True)

    log("FINAL POSITIONS:")
    for pl in sorted(planner.placements, key=lambda p: p.x):
        pkg = pl.package
        dx = pkg.length_mm if pl.rotation in (0,180) else pkg.width_mm
        log(f"  {pkg.name:15s} @ ({pl.x:7.0f},{pl.y:7.0f},{pl.z:3.0f}) rot={pl.rotation} xmax={pl.x+dx:.0f}")

    log("\nGAP CHECK:")
    sorted_pl = sorted(planner.placements, key=lambda p: p.x)
    for i, pl in enumerate(sorted_pl):
        pkg = pl.package
        dx = pkg.length_mm if pl.rotation in (0,180) else pkg.width_mm
        if i == 0:
            log(f"  First: {pkg.name} @ x={pl.x:.0f}")
        else:
            prev = sorted_pl[i-1]
            prev_dx = prev.package.length_mm if prev.rotation in (0,180) else prev.package.width_mm
            gap = pl.x - (prev.x + prev_dx)
            cur_dy = pkg.width_mm if pl.rotation in (0,180) else pkg.length_mm
            prev_dy = prev.package.width_mm if prev.rotation in (0,180) else prev.package.length_mm
            y_overlap = max(0, min(pl.y+cur_dy, prev.y+prev_dy) - max(pl.y, prev.y))
            log(f"  {pkg.name} -> gap_from_prev={gap:.0f} y_overlap={y_overlap:.0f}")

    total = planner.evaluate_plan()
    valid = planner.validate()
    log(f"\nScore: {total.total:.1f} | Valid: {valid.valid}")
    save_report("diagnose", "general")

def cmd_diagnose_kbf_lc900(full):
    from truck_load_planner.engine.package import Package
    from truck_load_planner.engine.container import Container
    from truck_load_planner.engine.planner import Planner

    TRUCK = Container(id=10, name="Truck", length=9700, width=2370, height=2320, payload_kg=28000)
    KBF = Package(id=1, name="KBF 280R", length_mm=1050, width_mm=2370, height_mm=2320, weight_kg=2000, stackable=False, allow_rotation=False)
    LC900 = Package(id=2, name="LC 900", length_mm=900, width_mm=770, height_mm=1200, weight_kg=500, stackable=True, allow_rotation=True)

    planner = Planner(TRUCK)
    r1 = planner.place_package(KBF, 0, 0, 0, 0)
    assert r1.valid, f"KBF failed: {r1.reasons}"
    pkgs = [LC900, LC900, LC900]
    result = planner.auto_arrange(pkgs, debug=True)

    log("FINAL POSITIONS:")
    for pl in sorted(planner.placements, key=lambda p: p.x):
        pkg = pl.package; dx = pkg.length_mm if pl.rotation in (0,180) else pkg.width_mm
        log(f"  {pkg.name:15s} @ ({pl.x:7.0f},{pl.y:7.0f},{pl.z:3.0f}) xmax={pl.x+dx:.0f}")

    log("\nGAP CHECK:")
    kbf_pl = [pl for pl in planner.placements if pl.package_id == 1][0]
    log(f"  KBF right edge: x={kbf_pl.x+KBF.length_mm:.0f}")
    lc_sorted = sorted([pl for pl in planner.placements if pl.package_id == 2], key=lambda pl: pl.x)
    for i, pl in enumerate(lc_sorted):
        dx = pl.package.length_mm if pl.rotation in (0,180) else pl.package.width_mm
        if i == 0:
            log(f"  LC900[0] @ x={pl.x:.0f} gap_from_KBF={pl.x-(kbf_pl.x+KBF.length_mm):.0f}")
        else:
            prev = lc_sorted[i-1]; prev_dx = prev.package.length_mm if prev.rotation in (0,180) else prev.package.width_mm
            log(f"  LC900[{i}] @ x={pl.x:.0f} gap_from_prev={pl.x-(prev.x+prev_dx):.0f}")

    total = planner.evaluate_plan(); valid = planner.validate()
    log(f"\nScore: {total.total:.1f} | Valid: {valid.valid}")
    save_report("diagnose", "kbf_lc900")

def cmd_diagnose_candidates(full):
    from truck_load_planner.engine.container import Container
    from truck_load_planner.engine.package import Package
    from truck_load_planner.engine.planner import Planner

    CONTAINER = Container(name="Test", length=2000, width=1500, height=2000, payload_kg=5000)
    PKG_A = Package(id=1, name="FloorBox", length_mm=1000, width_mm=500, height_mm=500, weight_kg=50, stackable=True, allow_rotation=True)
    PKG_B = Package(id=2, name="StackableBox", length_mm=500, width_mm=400, height_mm=400, weight_kg=30, stackable=True, allow_rotation=True)

    planner = Planner(CONTAINER)
    result_a = planner.place_package(PKG_A, 0, 0, 0, 0)
    assert result_a.valid, f"PKG_A failed: {result_a.reasons}"
    log(f"Placed PKG_A @ (0,0,0) — {PKG_A.length_mm}x{PKG_A.width_mm}x{PKG_A.height_mm}\n")

    pkg = PKG_B
    base = list(planner.get_candidate_points())
    log(f"Extreme points ({len(base)}):")
    for pt in base:
        log(f"  ({pt[0]:6.0f},{pt[1]:6.0f},{pt[2]:6.0f}) {'FLOOR' if pt[2]==0 else 'STACKED'}")

    h_clr = 10.0; right_y = CONTAINER.width - pkg.width_mm - h_clr
    if right_y > h_clr:
        rc = (0, right_y, 0)
        if rc not in base:
            base = [rc] + list(base)
            log(f"\nAdded right-wall: (0,{right_y:.0f},0)")

    expanded = []
    seen = set()
    for pos in base:
        x,y,z = (pos.get("x",0),pos.get("y",0),pos.get("z",0)) if isinstance(pos,dict) else (pos[0],pos[1],pos[2])
        for rot in ([0,90] if pkg.allow_rotation else [0]):
            key = (x,y,z,rot)
            if key not in seen:
                seen.add(key); expanded.append({"x":x,"y":y,"z":z,"rotation":rot})

    log(f"\nCandidates ({len(expanded)} total):")
    validated = []
    for c in expanded:
        vr = planner.validate_position(pkg, c["x"], c["y"], c["z"], c["rotation"])
        if vr.valid:
            score = planner.evaluate_position(pkg, c["x"], c["y"], c["z"], c["rotation"])
            validated.append((c, score.total, dict(score.breakdown)))
        else:
            validated.append((c, None, vr.reasons))

    floor_v = sum(1 for c,s,_ in validated if s is not None and c["z"]==0)
    stack_v = sum(1 for c,s,_ in validated if s is not None and c["z"]>0)
    log(f"  Valid floor: {floor_v}, Valid stack: {stack_v}")

    scored = [(c,s,b) for c,s,b in validated if s is not None]
    scored.sort(key=lambda x: -x[1])
    log(f"\nTop 5 by score:")
    for rank, (c, s, bd) in enumerate(scored[:5]):
        pos_str = f"({c['x']:.0f},{c['y']:.0f},{c['z']:.0f}) r={c['rotation']}"
        top = sorted(bd.items(), key=lambda x: -x[1])[:3]
        log(f"  #{rank}: {pos_str} score={s:.2f} {'FLOOR' if c['z']==0 else 'STACK'} {', '.join(f'{k}={v:.1f}' for k,v in top)}")
    save_report("diagnose", "candidates")

def cmd_diagnose_stacking(full):
    from truck_load_planner.engine.package import Package
    from truck_load_planner.engine.container import Container
    from truck_load_planner.engine.planner import Planner

    CONTAINER = Container(id=1, name="40ft", length=12000, width=2400, height=2700, payload_kg=28000)

    def mkpkg(i, l, w, h, wt, stk=True, name=None):
        return Package(id=i, name=name or f"P{i}", length_mm=l, width_mm=w, height_mm=h, weight_kg=wt, stackable=stk, horizontal_clearance_mm=10.0, vertical_clearance_mm=0.0)

    pkgs = [
        mkpkg(1,1200,1000,800,120,False,"NS-Big"), mkpkg(2,1000,800,700,90,False,"NS-Med"),
        mkpkg(3,1100,900,600,80,True,"Lg-Stk"), mkpkg(4,1000,800,500,60,True,"Med-Stk-A"),
        mkpkg(5,800,700,500,50,True,"Med-Stk-B"), mkpkg(6,900,700,400,45,True,"Med-Stk-C"),
        mkpkg(7,700,600,400,35,True,"Sm-Stk-A"), mkpkg(8,600,500,400,30,True,"Sm-Stk-B"),
        mkpkg(9,600,500,350,25,True,"Sm-Stk-C"), mkpkg(10,500,500,300,20,True,"Sm-Stk-D"),
        mkpkg(11,800,600,500,40,True,"Stk-Tall"), mkpkg(12,800,600,400,35,True,"Stk-Short"),
        mkpkg(13,700,500,400,30,True,"Stk-Mid"), mkpkg(14,600,500,300,25,True,"Stk-Low"),
        mkpkg(15,500,400,300,20,True,"Stk-Sm"),
    ]
    sorted_pkgs = sorted(pkgs, key=lambda p: (p.stackable, -(p.length_mm*p.width_mm*p.height_mm), -(p.length_mm*p.width_mm), -p.weight_kg))

    planner = Planner(CONTAINER)
    pkg_decisions = []
    for idx, pkg in enumerate(sorted_pkgs):
        remaining = sorted_pkgs[idx+1:]
        base = list(planner.get_candidate_points())
        h_clr = 10.0; right_y = CONTAINER.width - pkg.width_mm - h_clr
        if right_y > h_clr:
            rc = (0, right_y, 0)
            if rc not in base:
                base = [rc] + list(base)
        expanded, seen = [], set()
        for pos in base:
            x,y,z = (pos.get("x",0),pos.get("y",0),pos.get("z",0)) if isinstance(pos,dict) else (pos[0],pos[1],pos[2])
            for rot in ([0,90] if pkg.allow_rotation else [0]):
                key = (x,y,z,rot)
                if key not in seen:
                    seen.add(key); expanded.append({"x":x,"y":y,"z":z,"rotation":rot})

        valid_cands = []
        for c in expanded:
            if not planner.validate_position(pkg, c["x"],c["y"],c["z"],c["rotation"]).valid:
                continue
            score = planner.evaluate_position(pkg, c["x"],c["y"],c["z"],c["rotation"], remaining_packages=remaining)
            valid_cands.append({"pos":(c["x"],c["y"],c["z"],c["rotation"]),"type":"STACK" if c["z"]>0 else "FLOOR","score":score.total,"breakdown":dict(score.breakdown)})

        if not valid_cands:
            pkg_decisions.append({"pkg":pkg.name,"placed":False,"total_valid":0,"stack_valid":0,"floor_valid":0,"chosen":None})
            continue

        valid_cands.sort(key=lambda c: -c["score"])
        best = valid_cands[0]
        has_stack = any(c["type"]=="STACK" for c in valid_cands)
        has_floor = any(c["type"]=="FLOOR" for c in valid_cands)
        pl_result = planner.place_package(pkg, *best["pos"])
        pkg_decisions.append({
            "pkg":pkg.name,"stackable":pkg.stackable,"placed":pl_result.valid,
            "total_valid":len(valid_cands),"stack_valid":sum(1 for c in valid_cands if c["type"]=="STACK"),
            "floor_valid":sum(1 for c in valid_cands if c["type"]=="FLOOR"),
            "chosen":best["pos"],"chosen_type":best["type"],"chosen_score":best["score"],
            "chosen_breakdown":best["breakdown"],"has_stack":has_stack,"has_floor":has_floor,
        })

    log(f"{'Pkg':12s} {'Stk?':5s} {'#Vld':5s} {'#Stk':5s} {'#Flr':5s} {'Chosen':28s} {'Type':5s} {'Score':7s}")
    log("-"*72)
    for e in pkg_decisions:
        if e["chosen"]:
            p=e["chosen"]; ps=f"({p[0]:.0f},{p[1]:.0f},{p[2]:.0f},r{p[3]})"
            log(f"{e['pkg']:12s} {str(e.get('stackable','?')):5s} {e['total_valid']:5d} {e['stack_valid']:5d} {e['floor_valid']:5d} {ps:28s} {e['chosen_type']:5s} {e['chosen_score']:7.2f}")
        else:
            log(f"{e['pkg']:12s} {'?':5s} {e['total_valid']:5d} {'?':5s} {'?':5s} {'(FAILED)':28s}")

    total = len(pkg_decisions); placed = sum(1 for e in pkg_decisions if e.get("placed"))
    log(f"\nTotal: {total} | Placed: {placed} | Failed: {total-placed}")
    with_stack = sum(1 for e in pkg_decisions if e.get("has_stack"))
    with_floor = sum(1 for e in pkg_decisions if e.get("has_floor"))
    log(f"Have stack candidates: {with_stack} | Have floor candidates: {with_floor}")
    save_report("diagnose", "stacking")

# ══════════════════════════════════════════════════════════════════
#  DEBUG
# ══════════════════════════════════════════════════════════════════

def cmd_debug_py3dbp():
    from manual_test import _load_db, _build_engine_packages
    from py3dbp import Packer, Bin, Item

    vehicle_data = _load_db(); packages = _build_engine_packages()
    log(f"Packages: {len(packages)}, Vehicles: {len(vehicle_data)}")
    v = vehicle_data[0]
    log(f"First vehicle: id={v['vehicle_id']}, {v['cargo_length_mm']}x{v['cargo_width_mm']}x{v['cargo_height_mm']}mm payload={v['payload_kg']}kg")

    packer = Packer()
    packer.add_bin(Bin(str(v["vehicle_id"]), float(v["cargo_width_mm"]), float(v["cargo_height_mm"]), float(v["cargo_length_mm"]), float(v["payload_kg"])))
    for p in packages:
        packer.add_item(Item(p.name, float(p.width_mm), float(p.height_mm), float(p.length_mm), float(p.weight_kg)))
    packer.pack(bigger_first=True, distribute_items=True, number_of_decimals=0)

    for b in packer.bins:
        log(f"\nBin: {b.string()} | Items placed: {len(b.items)} | Unfitted: {len(b.unfitted_items)}")
    save_report("debug", "py3dbp")

def cmd_debug_stats():
    from truck_load_planner.engines import get_engine
    from manual_test import _load_db, _build_engine_packages

    vehicle_data = _load_db(); packages = _build_engine_packages()
    engine = get_engine("py3dbp")
    result = engine.pack(vehicle_data, packages)
    s = result.statistics
    log(f"Statistics: {s}")
    log(f"Vehicles used: {s.get('vehicles_used')}")
    for vid, pls in result.vehicle_placements.items():
        if not pls: continue
        c = result.vehicle_containers.get(vid)
        if c:
            v = sum(p.package.length_mm * p.package.width_mm * p.package.height_mm for p in pls if p.package) / 1e9
            log(f"Vehicle {vid}: {c.length}x{c.width}x{c.height}mm = {c.volume_m3:.2f}m3 | {len(pls)} pkgs | util {v/c.volume_m3*100:.1f}%")
    save_report("debug", "stats")

def cmd_debug_validation():
    from truck_load_planner.engine.package import Package
    from truck_load_planner.engine.container import Container
    from truck_load_planner.engine.validation import validate_placement
    from truck_load_planner.engine.geometry import AABB
    from truck_load_planner.engine.boundary import check_boundary
    from truck_load_planner.engine.weight import check_weight
    from truck_load_planner.engine.support import check_support
    from truck_load_planner.engine.access import check_door_fit, check_door_sweep
    from manual_test import _load_db, _build_engine_packages

    vehicle_data = _load_db(); packages = _build_engine_packages()
    v = vehicle_data[0]; pkg = packages[0]
    container = Container(id=v.get("cc_id"), name=v.get("container_name",""),
        length=float(v["cargo_length_mm"]), width=float(v["cargo_width_mm"]),
        height=float(v["cargo_height_mm"]), payload_kg=float(v["payload_kg"]))

    log(f"Package: {pkg.name} {pkg.length_mm}x{pkg.width_mm}x{pkg.height_mm} {pkg.weight_kg}kg")
    log(f"Container: L={container.length} W={container.width} H={container.height} payload={container.payload_kg}kg")

    result = validate_placement([], pkg, 0.0, 0.0, 0.0, 0, container, [])
    log(f"Validation: valid={result.valid}{' reasons: '+str(result.reasons) if not result.valid else ''}")

    actual = AABB.from_dimensions(0,0,0,pkg.length_mm,pkg.width_mm,pkg.height_mm,0,clearance=0)
    cont_aabb = AABB(0,0,0,container.length,container.width,container.height)
    b = check_boundary(actual, cont_aabb)
    log(f"Boundary: pass={b['pass']}")
    log(f"Support (z=0): valid={check_support([], actual, package=pkg)['valid']}")
    save_report("debug", "validation")

def cmd_debug_vehicles():
    rows = load_vehicles_from_db()
    log(f"Total vehicles: {len(rows)}\n")
    for v in rows:
        vol = v["cargo_length_mm"] * v["cargo_width_mm"] * v["cargo_height_mm"]
        log(f"V{v['vehicle_id']:>3}: {v['plate_number']:>12} | L={v['cargo_length_mm']:>5} W={v['cargo_width_mm']:>4} H={v['cargo_height_mm']:>4} Payload={v['payload_kg']:>6}kg Vol={vol/1e9:.1f}m3")
    save_report("debug", "vehicles")

# ══════════════════════════════════════════════════════════════════
#  QUERY
# ══════════════════════════════════════════════════════════════════

def cmd_query_vehicles():
    rows = load_vehicles_from_db()
    sorted_v = sorted(rows, key=lambda v: -(v["cargo_length_mm"] * v["cargo_width_mm"] * v["cargo_height_mm"] * max(v["payload_kg"], 1)))
    log("=== VEHICLES SORTED BY CAPACITY ===")
    for vd in sorted_v:
        vol = vd["cargo_length_mm"] * vd["cargo_width_mm"] * vd["cargo_height_mm"]
        cap = vol * max(vd["payload_kg"], 1)
        log(f"  V{vd['vehicle_id']:3d} {vd['plate_number']:>8s} {vd['cargo_length_mm']}x{vd['cargo_width_mm']}x{vd['cargo_height_mm']}mm cap_idx={cap:.2e}")
    save_report("query", "vehicles")

def cmd_query_tables():
    conn = db_connect(); c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r[0] for r in c.fetchall()]
    for t in tables:
        c.execute(f'SELECT COUNT(*) FROM "{t}"')
        log(f"  {t:30s}: {c.fetchone()[0]} rows")
    conn.close()
    save_report("query", "tables")

def cmd_query_db():
    conn = db_connect(); c = conn.cursor()
    log("=== TABLES ===")
    c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    log(f"  {', '.join(r['name'] for r in c.fetchall())}")
    log("\n=== VEHICLES ===")
    c.execute("""SELECT v.id, v.plate_number, cc.name, cc.cargo_length_mm, cc.cargo_width_mm, cc.cargo_height_mm, cc.payload_kg
        FROM vehicles v JOIN container_configs cc ON cc.id=v.container_config_id ORDER BY v.id""")
    for r in c.fetchall():
        log(f"  id={r['id']} {r['plate_number']} {r['name']} {r['cargo_length_mm']}x{r['cargo_width_mm']}x{r['cargo_height_mm']} payload={r['payload_kg']}kg")
    log("\n=== PACKAGES (first 5) ===")
    c.execute("SELECT id, name, length, width, height, weight_kg FROM tlp_packages ORDER BY id LIMIT 5")
    for r in c.fetchall():
        log(f"  id={r['id']} {r['name']:20s} {r['length']}x{r['width']}x{r['height']} {r['weight_kg']}kg")
    log("\n=== TOTAL PACKAGES ===")
    c.execute("SELECT COUNT(*) FROM tlp_packages")
    log(f"  {c.fetchone()[0]}")
    log("\n=== LOAD PLANS (last 5) ===")
    c.execute("""SELECT lp.id, lp.name, lp.vehicle_id, lp.shipment_id, lp.status, COUNT(pl.id) as pc
        FROM tlp_load_plans lp LEFT JOIN tlp_placements pl ON pl.load_plan_id=lp.id
        GROUP BY lp.id ORDER BY lp.id DESC LIMIT 5""")
    for r in c.fetchall():
        log(f"  id={r['id']} name={r['name']} vehicle={r['vehicle_id']} shipment={r['shipment_id']} status={r['status']} placements={r['pc']}")
    conn.close()
    save_report("query", "db")

def cmd_query_shipments():
    conn = db_connect(); c = conn.cursor()
    log("=== SHIPMENTS ===")
    c.execute("SELECT id, customer_name, reference_number FROM tlp_shipments ORDER BY id")
    for r in c.fetchall():
        log(f"  id={r['id']} cust={r['customer_name']} ref={r['reference_number']}")
    log("\n=== SHIPMENT ITEMS ===")
    c.execute("SELECT DISTINCT shipment_id FROM tlp_shipment_items ORDER BY shipment_id")
    for sid in [r['shipment_id'] for r in c.fetchall()]:
        log(f"\n  Shipment {sid}:")
        c.execute("""SELECT si.quantity, p.id, p.name, p.length, p.width, p.height, p.weight_kg, p.allow_stacking, p.allow_rotation
            FROM tlp_shipment_items si JOIN tlp_packages p ON p.id=si.package_id
            WHERE si.shipment_id=? ORDER BY p.allow_stacking, p.length*p.width*p.height DESC""", (sid,))
        total = sum(r['quantity'] for r in c.fetchall())
        log(f"    Total packages: {total}")
    conn.close()
    save_report("query", "shipments")

# ══════════════════════════════════════════════════════════════════
#  INSTRUMENT
# ══════════════════════════════════════════════════════════════════

def cmd_instrument_trace():
    trace_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "instrument_trace.jsonl")
    if not os.path.exists(trace_path):
        log(f"Trace file not found: {trace_path}")
        log("Run manual_test.py with instrumentation first.")
        save_report("instrument", "trace")
        return
    traces = defaultdict(list)
    with open(trace_path) as f:
        for line in f:
            line = line.strip()
            if line:
                entry = json.loads(line)
                traces[entry["trace_id"]].append(entry)

    label_map = {1:"PLANNER RAW",2:"DB WRITES",3:"DB READS",4:"JSON TO FRONTEND",5:"CANVAS COORDS"}
    for tid in sorted(traces.keys()):
        log(f"\n{'='*80}")
        log(f"TRACE: {tid}")
        log(f"{'='*80}")
        by_rep = defaultdict(list)
        for e in traces[tid]:
            by_rep[e["rep"]].append(e)
        for rep in sorted(by_rep.keys()):
            for entry in by_rep[rep]:
                log(f"\n--- {label_map.get(rep, f'REP {rep}')} ({entry['label']}) ---")
                data = entry["data"]
                if "summary_lines" in data:
                    for l in data["summary_lines"]:
                        log(f"  {l}")
                    continue
                placements = data.get("placements") or data.get("placements_written") or data.get("placements_read") or data.get("packages", [])
                if data.get("vehicle_id"):
                    log(f"  Vehicle: {data['vehicle_id']} {data.get('plate_number','')}")
                for pl in placements[:20]:
                    name = str(pl.get('name') or pl.get('pkg_name') or '?')[:20]
                    x = str(pl.get('x', '')); y = str(pl.get('y', '')); z = str(pl.get('z', ''))
                    log(f"  {name:20s} x={x:>8s} y={y:>8s} z={z:>6s} rot={pl.get('rotation','')}")
                if len(placements) > 20:
                    log(f"  ... and {len(placements)-20} more")
    save_report("instrument", "trace")

def cmd_instrument_bug_trace():
    from truck_load_planner.engine.package import Package
    from truck_load_planner.engine.container import Container
    from truck_load_planner.engine.planner import Planner
    from truck_load_planner.engine.trace_mutations import M
    from truck_load_planner.engine.geometry import AABB
    from truck_load_planner.engine.support import check_support

    M.reset()
    container = Container(id=1, name="Test", length=5000, width=2500, height=2200, payload_kg=10000)
    packages = [
        Package(id=1,name="BASE_A",length_mm=1200,width_mm=1000,height_mm=500,weight_kg=300,stackable=True),
        Package(id=2,name="BASE_B",length_mm=1200,width_mm=1000,height_mm=500,weight_kg=300,stackable=True),
        Package(id=3,name="STACK_1",length_mm=800,width_mm=600,height_mm=400,weight_kg=100,stackable=True),
        Package(id=4,name="STACK_2",length_mm=800,width_mm=600,height_mm=400,weight_kg=100,stackable=True),
        Package(id=5,name="STACK_3",length_mm=600,width_mm=400,height_mm=300,weight_kg=50,stackable=True),
        Package(id=6,name="STACK_4",length_mm=600,width_mm=400,height_mm=300,weight_kg=50,stackable=True),
        Package(id=7,name="FILL_A",length_mm=1400,width_mm=1000,height_mm=600,weight_kg=400,stackable=False),
        Package(id=8,name="FILL_B",length_mm=1400,width_mm=1000,height_mm=600,weight_kg=400,stackable=False),
        Package(id=9,name="TOP_1",length_mm=800,width_mm=600,height_mm=400,weight_kg=80,stackable=True),
        Package(id=10,name="TOP_2",length_mm=800,width_mm=600,height_mm=400,weight_kg=80,stackable=True),
    ]
    planner = Planner(container, candidate_limit=80)
    result = planner.auto_arrange(packages, strategy="largest_first")

    log(f"Placed: {result.placed_packages}, Failed: {result.failed_packages}, Util: {result.utilization:.1f}%")
    log("\n=== SUPPORT INTEGRITY CHECK ===")
    unsupported = []
    for pl in planner.placements:
        if pl.package is None or pl.z < 0.001:
            continue
        aabb = AABB.from_dimensions(pl.x,pl.y,pl.z,pl.package.length_mm,pl.package.width_mm,pl.package.height_mm,pl.rotation,clearance=0)
        sr = check_support(planner.placements, aabb, package=pl.package, support_threshold=0.50)
        if not sr["valid"]:
            unsupported.append((pl.package.name, pl.x, pl.y, pl.z, sr["reasons"]))
            log(f"  *** UNSUPPORTED: {pl.package.name} @ ({pl.x:.0f},{pl.y:.0f},{pl.z:.0f}) — {sr['reasons']}")
        else:
            log(f"  OK: {pl.package.name} @ ({pl.x:.0f},{pl.y:.0f},{pl.z:.0f})")
    if not unsupported:
        log("  All packages have valid support.")
    save_report("instrument", "bug-trace")

# ══════════════════════════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Unified test harness")
    sub = parser.add_subparsers(dest="command", required=True)

    p_bench = sub.add_parser("benchmark", help="Run benchmarks")
    p_bench.add_argument("--mode", required=True, choices=["distribution", "floor_contact", "real_data"])

    p_diag = sub.add_parser("diagnose", help="Run diagnostics")
    p_diag.add_argument("--scenario", required=True, choices=["general", "kbf_lc900", "candidates", "stacking"])
    p_diag.add_argument("--full", action="store_true", help="Detailed output")

    p_debug = sub.add_parser("debug", help="Run debug checks")
    p_debug.add_argument("--mode", required=True, choices=["py3dbp", "stats", "validation", "vehicles"])

    p_query = sub.add_parser("query", help="Query database")
    p_query.add_argument("--mode", required=True, choices=["vehicles", "tables", "db", "shipments"])

    p_inst = sub.add_parser("instrument", help="Instrumentation tools")
    p_inst.add_argument("--mode", required=True, choices=["trace", "bug-trace"])

    args = parser.parse_args()

    cmd_map = {
        ("benchmark", "distribution"): cmd_benchmark_distribution,
        ("benchmark", "floor_contact"): cmd_benchmark_floor_contact,
        ("benchmark", "real_data"): cmd_benchmark_real_data,
        ("diagnose", "general"): lambda: cmd_diagnose_general(args.full),
        ("diagnose", "kbf_lc900"): lambda: cmd_diagnose_kbf_lc900(args.full),
        ("diagnose", "candidates"): lambda: cmd_diagnose_candidates(args.full),
        ("diagnose", "stacking"): lambda: cmd_diagnose_stacking(args.full),
        ("debug", "py3dbp"): cmd_debug_py3dbp,
        ("debug", "stats"): cmd_debug_stats,
        ("debug", "validation"): cmd_debug_validation,
        ("debug", "vehicles"): cmd_debug_vehicles,
        ("query", "vehicles"): cmd_query_vehicles,
        ("query", "tables"): cmd_query_tables,
        ("query", "db"): cmd_query_db,
        ("query", "shipments"): cmd_query_shipments,
        ("instrument", "trace"): cmd_instrument_trace,
        ("instrument", "bug-trace"): cmd_instrument_bug_trace,
    }

    fn = cmd_map.get((args.command, getattr(args, 'mode', None) or getattr(args, 'scenario', None)))
    if fn:
        _log_lines.clear()
        fn()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
