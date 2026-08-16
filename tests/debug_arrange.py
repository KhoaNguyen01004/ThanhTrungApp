"""Debug auto-arrange placement (simplified — frontier/compaction removed).

Usage:
    python scripts/debug_arrange.py <scenario> [--full]

Scenarios:
    kbf_lc900     KBF 280R + 3x LC 900
    mixed         3x PKG_A + 3x PKG_B + 2x PKG_C
    column-test   Same packages, column strategy
    real          Full 46-package real shipment (from manual_test.py)
"""

import sys, os, json, math
from datetime import datetime
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from truck_load_planner.engine.package import Package
from truck_load_planner.engine.container import Container
from truck_load_planner.engine.planner import Planner
from truck_load_planner.engine.candidate_points import (
    tighten_position,
)

# ── log capture ────────────────────────────────────────────────────

_log_lines: list[str] = []


def log(text: str = ""):
    print(text)
    _log_lines.append(text)


def hr(title: str = "", char: str = "="):
    w = 72
    if title:
        pad = (w - len(title) - 2) // 2
        line = f"{char * pad} {title} {char * (w - pad - len(title) - 2)}"
    else:
        line = char * w
    log(line)


def subhr(title: str = ""):
    hr(title, "-")


# ── containers & packages ──────────────────────────────────────────

CONTAINERS = {
    "truck": Container(
        id=10, name="Truck 9700x2370x2320",
        length=9700, width=2370, height=2320, payload_kg=28000,
    ),
    "40ft": Container(
        id=1, name="40ft Container",
        length=12000, width=2400, height=2700, payload_kg=28000,
    ),
}

PACKAGES = {
    "KBF": Package(id=1, name="KBF 280R", length_mm=1050, width_mm=2370,
                   height_mm=2320, weight_kg=2000, stackable=False,
                   allow_rotation=False),
    "LC900": Package(id=2, name="LC 900-4/6TXA", length_mm=900, width_mm=770,
                     height_mm=1200, weight_kg=500, stackable=True,
                     allow_rotation=True),
    "PKG_A": Package(id=101, name="PKG_A", length_mm=1200, width_mm=1000,
                     height_mm=800, weight_kg=300, stackable=True,
                     allow_rotation=True),
    "PKG_B": Package(id=102, name="PKG_B", length_mm=800, width_mm=600,
                     height_mm=500, weight_kg=150, stackable=True,
                     allow_rotation=True),
    "PKG_C": Package(id=103, name="PKG_C", length_mm=600, width_mm=400,
                     height_mm=300, weight_kg=80, stackable=True,
                     allow_rotation=True),
}

# ── Real 46-package shipment (from manual_test.py) ─────────────────

REAL_SHIPMENT_SPEC = [
    {"name": "AWC 30", "length": 650, "width": 430, "height": 450, "weight": 12.0, "stackable": True, "qty": 1},
    {"name": "AWC 30", "length": 420, "width": 150, "height": 420, "weight": 3.0, "stackable": True, "qty": 3},
    {"name": "AWS 315-4E", "length": 490, "width": 490, "height": 200, "weight": 6.4, "stackable": True, "qty": 1},
    {"name": "AWS 400-4E", "length": 600, "width": 600, "height": 240, "weight": 11.3, "stackable": True, "qty": 2},
    {"name": "AWS 450-4E", "length": 650, "width": 630, "height": 240, "weight": 12.5, "stackable": True, "qty": 1},
    {"name": "AWS 500-4E", "length": 710, "width": 700, "height": 260, "weight": 17.0, "stackable": True, "qty": 3},
    {"name": "AWS 560-4D", "length": 790, "width": 790, "height": 270, "weight": 21.5, "stackable": True, "qty": 2},
    {"name": "AWS 630-4D", "length": 870, "width": 870, "height": 260, "weight": 27.5, "stackable": True, "qty": 2},
    {"name": "DVS 1200", "length": 700, "width": 520, "height": 390, "weight": 24.0, "stackable": False, "qty": 1},
    {"name": "DVS 1900", "length": 700, "width": 520, "height": 390, "weight": 24.0, "stackable": False, "qty": 3},
    {"name": "DVS 3000", "length": 700, "width": 520, "height": 390, "weight": 26.0, "stackable": False, "qty": 1},
    {"name": "DVS 500", "length": 460, "width": 370, "height": 270, "weight": 8.0, "stackable": False, "qty": 1},
    {"name": "CDF 225-4", "length": 700, "width": 580, "height": 610, "weight": 42.0, "stackable": False, "qty": 1},
    {"name": "CDF 250-4", "length": 1220, "width": 680, "height": 620, "weight": 88.0, "stackable": False, "qty": 2},
    {"name": "CDF 280-4", "length": 730, "width": 650, "height": 690, "weight": 47.0, "stackable": False, "qty": 1},
    {"name": "CDF 315-4", "length": 860, "width": 790, "height": 800, "weight": 67.0, "stackable": False, "qty": 2},
    {"name": "FCS 450C", "length": 1290, "width": 830, "height": 1030, "weight": 177.0, "stackable": False, "qty": 2},
    {"name": "FCS 500C", "length": 1390, "width": 930, "height": 1110, "weight": 216.0, "stackable": False, "qty": 2},
    {"name": "KBF 200F", "length": 1160, "width": 680, "height": 670, "weight": 83.0, "stackable": False, "qty": 1},
    {"name": "KBF 200R", "length": 1020, "width": 1010, "height": 730, "weight": 98.0, "stackable": False, "qty": 2},
    {"name": "KBF 280F", "length": 1310, "width": 850, "height": 860, "weight": 143.0, "stackable": False, "qty": 1},
    {"name": "KBF 280R", "length": 1190, "width": 1130, "height": 910, "weight": 144.0, "stackable": False, "qty": 1},
    {"name": "LC 1000-4/6TXA/20°", "length": 980, "width": 1140, "height": 1200, "weight": 285.0, "stackable": False, "qty": 1},
    {"name": "LC 710-4/12B/10°", "length": 730, "width": 840, "height": 860, "weight": 105.0, "stackable": False, "qty": 1},
    {"name": "LC 710-4/12B/22.5°", "length": 730, "width": 840, "height": 860, "weight": 110.0, "stackable": False, "qty": 1},
    {"name": "LC 800-4/12TXA/17.5°", "length": 930, "width": 930, "height": 840, "weight": 146.0, "stackable": False, "qty": 1},
    {"name": "LC 900-4/6TXA/22.5°", "length": 940, "width": 1060, "height": 1110, "weight": 200.0, "stackable": False, "qty": 2},
    {"name": "LC 900-4/6TXA/25°", "length": 940, "width": 1060, "height": 1110, "weight": 200.0, "stackable": False, "qty": 1},
    {"name": "LC 900-4/6TXA/27.5°", "length": 940, "width": 1060, "height": 1110, "weight": 245.0, "stackable": False, "qty": 3},
]


def build_real_shipment() -> list[Package]:
    """Build the real 46-package shipment list."""
    pkgs = []
    next_id = 1000
    for spec in REAL_SHIPMENT_SPEC:
        for _ in range(spec["qty"]):
            pkgs.append(Package(
                id=next_id,
                name=spec["name"],
                length_mm=spec["length"],
                width_mm=spec["width"],
                height_mm=spec["height"],
                weight_kg=spec["weight"],
                stackable=spec["stackable"],
                allow_rotation=True,
                horizontal_clearance_mm=10.0,
            ))
            next_id += 1
    return pkgs

# ── helpers ────────────────────────────────────────────────────────


def pl_dim(pl):
    pkg = pl.package
    if pl.rotation in (0, 180):
        return pkg.length_mm, pkg.width_mm, pkg.height_mm
    else:
        return pkg.width_mm, pkg.length_mm, pkg.height_mm


def fmt_pos(x, y, z, rot, name="", w=15):
    xmax = 0
    return f"{name:{w}}  @ ({x:7.0f}, {y:7.0f}, {z:3.0f})  rot={rot:3d}"


def fmt_breakdown(bd: dict) -> str:
    if not bd:
        return "      (no breakdown)"
    items = sorted(bd.items(), key=lambda x: -x[1])
    return "\n".join(f"      {k:30s} {v:8.2f}" for k, v in items)


def fmt_candidate_detail(d: dict, idx: int) -> str:
    lines = [f"    --- candidate #{idx} ---"]
    inp = d.get("input_pos", {})
    lines.append(f"    input:       ({inp.get('x',0):.0f}, {inp.get('y',0):.0f}, {inp.get('z',0):.0f}) rot={inp.get('rotation',0)}")
    if not d.get("valid", True):
        lines.append(f"    VALIDATION:  FAILED — {d.get('reason','?')}")
        return "\n".join(lines)
    tp = d.get("tightened_pos", {})
    lines.append(f"    tightened:   ({tp.get('x',0):.0f}, {tp.get('y',0):.0f}, {tp.get('z',0):.0f}) rot={tp.get('rotation',0)}")
    raw = d.get("raw_score", 0)
    gap = d.get("gap_penalty", 0)
    stk = d.get("stack_ceiling_penalty", 0)
    adj = d.get("adjusted_score", 0)
    gapd = d.get("gap_dist", 0)
    gapr = d.get("gap_ratio", 0)
    col = d.get("col_top", 0)
    lines.append(f"    raw_score={raw:6.1f}  gap_penalty={gap:6.1f} (dist={gapd:.0f} ratio={gapr:.3f}) "
                 f"stack_penalty={stk:6.1f} (col_top={col:.0f})  adjusted={adj:6.1f}")
    bd = d.get("breakdown", {})
    if bd:
        lines.append("    breakdown:")
        for k, v in sorted(bd.items(), key=lambda x: -x[1]):
            lines.append(f"      {k:30s} {v:8.2f}")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
#  Diagnostic engine
# ══════════════════════════════════════════════════════════════════


def run(planner: Planner,
        container: Container,
        package_list: list[Package],
        *,
        full: bool = False,
        label: str = "debug",
        strategy: str = "largest_first") -> str:
    """Run full detailed debug, log everything, save to file."""

    _log_lines.clear()
    saved_path = ""

    # ── Header ──
    log()
    hr(f" AUTO-ARRANGE DEBUG: {label} ")
    log(f"  Container: {container.name}")
    log(f"  Dimensions: {container.length} x {container.width} x {container.height}")
    log(f"  Strategy:   {strategy}")
    log(f"  Packages:   {len(package_list)} units")
    for p in package_list:
        log(f"    - {p.name:20s}  {p.length_mm:4.0f}x{p.width_mm:4.0f}x{p.height_mm:4.0f}  "
            f"{p.weight_kg:5.0f}kg  stackable={p.stackable}  rotate={p.allow_rotation}")
    log(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    hr()

    # ── 1. Sorting order ──
    log()
    hr(" SORTING ORDER ", "-")
    sorted_pkgs = sorted(
        package_list,
        key=lambda p: (
            0 if not p.stackable else 1,
            -(p.length_mm * p.width_mm * p.height_mm),
            -p.weight_kg,
            -(p.length_mm * p.width_mm),
        ),
    )
    for i, p in enumerate(sorted_pkgs):
        vol = p.length_mm * p.width_mm * p.height_mm
        log(f"  #{i+1}: {p.name:20s}  stackable={p.stackable}  "
            f"vol={vol:9.0f}mm3  weight={p.weight_kg:5.0f}kg  "
            f"footprint={p.length_mm*p.width_mm:8.0f}mm2")

    # ── 2. Run auto-arrange with debug ──
    log()
    hr(" AUTO-ARRANGE EXECUTION ")
    log(f"  Running {strategy} strategy...")
    result = planner.auto_arrange(package_list, debug=True, strategy=strategy)
    log(f"  Placed: {result.placed_packages}  Failed: {result.failed_packages}  "
        f"Score: {result.total_score}")

    # ── 3. Final positions ──
    log()
    hr(" FINAL POSITIONS ")
    log(f"  {'Package':20s}  {'Position':42s}  {'xmax':>7s}  {'Dimensions':>16s}")
    log("  " + "-" * 90)
    for pl in sorted(planner.placements, key=lambda p: p.x):
        pkg = pl.package
        dx, dy, dz = pl_dim(pl)
        xmax = pl.x + dx
        log(f"  {pkg.name:20s}  @ ({pl.x:7.0f}, {pl.y:7.0f}, {pl.z:3.0f})  "
            f"rot={pl.rotation:3d}  xmax={xmax:7.0f}  {dx:4.0f}x{dy:4.0f}x{dz:4.0f}")

    # ── 4. Per-package detailed debug ──
    if result.debug_log:
        log()
        hr(f" PER-PACKAGE DECISION LOG ({len(result.debug_log)} packages) ")

        for entry_idx, entry in enumerate(result.debug_log):
            pkg_name = entry.get("package_name", "?")
            found = entry.get("valid_candidates_found", False)
            score = entry.get("best_score", 0)
            pos = entry.get("chosen_position")
            slide = " (slide pass)" if entry.get("slide_pass") else ""
            tightened = " (tightened)" if entry.get("tightened") else ""

            log()
            subhr(f" Package #{entry_idx+1}: {pkg_name} ")
            log(f"  Status: {'PLACED' if found else 'FAILED'}  "
                f"best_score={score}{slide}{tightened}")
            if pos:
                log(f"  Final position: ({pos['x']:.0f}, {pos['y']:.0f}, "
                    f"{pos['z']:.0f}) rot={pos['rotation']}")

            # Main candidate details
            details = entry.get("all_candidate_details", [])
            slide_details = entry.get("slide_details", [])
            total_cands = entry.get("candidates_evaluated", 0)

            if details:
                log(f"  Main pass candidates evaluated: {len(details)}")
                log(f"  {'─' * 70}")
                for ci, cd in enumerate(details):
                    log(fmt_candidate_detail(cd, ci))
                    if ci >= 50:  # cap output at 50
                        log(f"    ... ({len(details) - 50} more candidates not shown)")
                        break

            if slide_details:
                log(f"  Y-slide fallback candidates evaluated: {len(slide_details)}")
                log(f"  {'─' * 70}")
                for ci, cd in enumerate(slide_details):
                    log(fmt_candidate_detail(cd, ci))

            # Score breakdown for chosen candidate
            bd = entry.get("score_breakdown", {})
            if bd:
                log(f"  Score breakdown (chosen):")
                log(fmt_breakdown(bd))

    # ── 5. Gap check ──
    log()
    hr(" GAP CHECK (adjacent, sorted by X) ")
    placements_sorted = sorted(planner.placements, key=lambda p: p.x)
    for i, pl in enumerate(placements_sorted):
        pkg = pl.package
        dx, dy, dz = pl_dim(pl)
        pl_xmax = pl.x + dx
        if i == 0:
            log(f"  [{pkg.name:20s}]  x={pl.x:7.0f}  xmax={pl_xmax:7.0f}  "
                f"(first package, gap_from_wall={pl.x:.0f})")
        else:
            prev = placements_sorted[i - 1]
            prev_pkg = prev.package
            prev_dx, prev_dy, _ = pl_dim(prev)
            prev_xmax = prev.x + prev_dx
            gap = pl.x - prev_xmax
            y_overlap = max(0, min(pl.y + dy, prev.y + prev_dy) - max(pl.y, prev.y))
            side = y_overlap <= 0
            log(f"  [{pkg.name:20s}]  x={pl.x:7.0f}  xmax={pl_xmax:7.0f}  "
                f"gap_from_prev={gap:+6.0f}  y_overlap={y_overlap:4.0f}  "
                f"{'SIDE_BY_SIDE' if side else 'IN_LINE'}")

    # ── 6. Tighten test (full only) ──
    if full:
        log()
        hr(" TIGHTEN TEST PER PACKAGE ")
        for pl in sorted(planner.placements, key=lambda p: p.x):
            pkg = pl.package
            tx, ty, tz, trot = tighten_position(
                planner, pkg, pl.x, pl.y, pl.z, pl.rotation, step=50.0)
            imp = abs(tx - pl.x) > 1.0
            log(f"  [{pkg.name}]  tighten: ({pl.x:.0f},{pl.y:.0f},{pl.z:.0f}) -> "
                f"({tx:.0f},{ty:.0f},{tz:.0f})  improved={imp}")

    # ── 7. Final positions ──
    log()
    hr(" FINAL POSITIONS (after all processing) ")
    log(f"  {'Package':20s}  {'Position':42s}  {'xmax':>7s}  {'Dimensions':>16s}")
    log("  " + "-" * 90)
    for pl in sorted(planner.placements, key=lambda p: p.x):
        pkg = pl.package
        dx, dy, dz = pl_dim(pl)
        xmax = pl.x + dx
        log(f"  {pkg.name:20s}  @ ({pl.x:7.0f}, {pl.y:7.0f}, {pl.z:3.0f})  "
            f"rot={pl.rotation:3d}  xmax={xmax:7.0f}  {dx:4.0f}x{dy:4.0f}x{dz:4.0f}")

    # ── 13. Validation ──
    log()
    hr(" VALIDATION ")
    total = planner.evaluate_plan()
    valid = planner.validate()
    log(f"  Score: {total.total:.1f}")
    log(f"  Valid: {valid.valid}")
    if not valid.valid:
        for r in valid.reasons[:20]:
            log(f"    - {r}")

    log()
    hr(" DEBUG COMPLETE ")

    # ── Save to file ──
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(out_dir, f"debug_{label}_{ts}.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(_log_lines))
    log(f"\nReport saved to: {out_path}")
    saved_path = out_path

    return saved_path


# ══════════════════════════════════════════════════════════════════
#  Scenarios
# ══════════════════════════════════════════════════════════════════


def scenario_kbf_lc900(full: bool, strategy: str):
    c = CONTAINERS["truck"]
    planner = Planner(c)
    kbf = PACKAGES["KBF"]
    lc = PACKAGES["LC900"]
    r1 = planner.place_package(kbf, 0, 0, 0, 0)
    assert r1.valid, f"KBF placement failed: {r1.reasons}"
    pkgs = [lc, lc, lc]
    return run(planner, c, pkgs, full=full, label="kbf_lc900", strategy=strategy)


def scenario_mixed(full: bool, strategy: str):
    c = CONTAINERS["truck"]
    planner = Planner(c)
    pkgs = [
        PACKAGES["PKG_A"], PACKAGES["PKG_A"], PACKAGES["PKG_A"],
        PACKAGES["PKG_B"], PACKAGES["PKG_B"], PACKAGES["PKG_B"],
        PACKAGES["PKG_C"], PACKAGES["PKG_C"],
    ]
    return run(planner, c, pkgs, full=full, label="mixed", strategy=strategy)


def scenario_column_test(full: bool, strategy: str):
    """Test column strategy on same packages."""
    c = CONTAINERS["40ft"]
    planner = Planner(c)
    pkgs = [
        PACKAGES["PKG_A"], PACKAGES["PKG_A"], PACKAGES["PKG_B"],
        PACKAGES["PKG_B"], PACKAGES["PKG_C"],
    ]
    return run(planner, c, pkgs, full=full, label="column_test", strategy="column")


def scenario_real(full: bool, strategy: str):
    """Full 46-package real shipment (from manual_test.py)."""
    c = CONTAINERS["truck"]
    planner = Planner(c)
    pkgs = build_real_shipment()
    return run(planner, c, pkgs, full=full, label="real_46pkgs", strategy=strategy)


# ══════════════════════════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════════════════════════

def main():
    scenarios = {
        "kbf_lc900": scenario_kbf_lc900,
        "mixed": scenario_mixed,
        "column-test": scenario_column_test,
        "real": scenario_real,
    }

    if len(sys.argv) < 2 or sys.argv[1] not in scenarios:
        print(__doc__)
        print("Available scenarios:")
        for k in scenarios:
            print(f"  {k}")
        sys.exit(1)

    full = "--full" in sys.argv
    strategy = "largest_first"
    # Override strategy per scenario or via flag
    for s in ["--column", "--largest-first"]:
        if s in sys.argv:
            strategy = s.replace("--", "").replace("-", "_")
            break

    scenario = sys.argv[1]
    saved = scenarios[scenario](full, strategy)

    print(f"\nDebug report: {saved}")
    print(f"View with: type {saved}")


if __name__ == "__main__":
    main()
