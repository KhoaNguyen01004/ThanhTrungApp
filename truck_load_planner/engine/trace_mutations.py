"""
Placement mutation tracer.

Assigns every Placement a unique _uid at creation and logs every change
to x, y, z, rotation, insertion, or removal.  Provides integrity
checks and per-package trace dumps for debugging support-integrity bugs.

Usage:
    from .trace_mutations import M
    M.log("function_name", pl, old_pos, new_pos, "reason")
    M.check_integrity(placements, "after stage X")
    M.dump_for("Package #44")

Enable by setting M.enabled = True (default) or False to bypass.
"""

from typing import Optional


class _MutationLogger:
    def __init__(self):
        self.enabled = True
        self._log: list[dict] = []
        self._stage_uid_snapshots: dict[str, set[tuple[int, str]]] = {}

    def reset(self) -> None:
        self._log.clear()
        self._stage_uid_snapshots.clear()

    # ── Logging ─────────────────────────────────────────────────────

    def log(
        self,
        func_name: str,
        placement,
        old_pos: Optional[tuple] = None,
        new_pos: Optional[tuple] = None,
        reason: str = "",
    ) -> None:
        if not self.enabled:
            return
        uid = -1
        pkg_name = "?"
        if placement is not None:
            uid = getattr(placement, '_uid', -1)
            if hasattr(placement, 'package'):
                pkg_name = placement.package.name if placement.package else "None"
            elif hasattr(placement, 'name'):
                pkg_name = placement.name
        old_str = f"({old_pos[0]:.1f},{old_pos[1]:.1f},{old_pos[2]:.1f},r{old_pos[3]})" if old_pos else "---"
        new_str = f"({new_pos[0]:.1f},{new_pos[1]:.1f},{new_pos[2]:.1f},r{new_pos[3]})" if new_pos else "---"
        self._log.append({
            "func": func_name or "(info)",
            "uid": uid,
            "package": pkg_name,
            "old": old_str,
            "new": new_str,
            "reason": reason,
        })

    def log_direct_x(self, func_name: str, placement, old_x: float, new_x: float, reason: str = "") -> None:
        if not self.enabled:
            return
        uid = getattr(placement, '_uid', -1)
        pkg_name = placement.package.name if placement.package else "None"
        self._log.append({
            "func": func_name,
            "uid": uid,
            "package": pkg_name,
            "old": f"({old_x:.1f},?,?,?)",
            "new": f"({new_x:.1f},?,?,?)",
            "reason": f"X-only {reason}",
        })

    def log_remove(self, func_name: str, placement, reason: str = "") -> None:
        if not self.enabled:
            return
        uid = getattr(placement, '_uid', -1)
        pkg_name = placement.package.name if placement.package else "None"
        self._log.append({
            "func": func_name,
            "uid": uid,
            "package": pkg_name,
            "old": f"({placement.x:.1f},{placement.y:.1f},{placement.z:.1f},r{placement.rotation})",
            "new": "REMOVED",
            "reason": reason,
        })

    def log_insert(self, func_name: str, placement, reason: str = "") -> None:
        if not self.enabled:
            return
        uid = getattr(placement, '_uid', -1)
        pkg_name = placement.package.name if placement.package else "None"
        self._log.append({
            "func": func_name,
            "uid": uid,
            "package": pkg_name,
            "old": "---",
            "new": f"({placement.x:.1f},{placement.y:.1f},{placement.z:.1f},r{placement.rotation})",
            "reason": reason,
        })

    # ── Integrity snapshots ─────────────────────────────────────────

    def stage(self, label: str) -> None:
        """Log a stage marker for readability in the trace."""
        if not self.enabled:
            return
        self._log.append({
            "func": "=== STAGE ===",
            "uid": -1,
            "package": label,
            "old": "",
            "new": "",
            "reason": "",
        })

    def snapshot(self, placements, stage_label: str) -> None:
        if not self.enabled:
            return
        uids = set()
        for pl in placements:
            uid = getattr(pl, '_uid', -1)
            name = pl.package.name if pl.package else "None"
            uids.add((uid, name))
        self._stage_uid_snapshots[stage_label] = uids

    def check_integrity(self, placements, stage_label: str) -> None:
        if not self.enabled:
            return
        current = set()
        for pl in placements:
            uid = getattr(pl, '_uid', -1)
            name = pl.package.name if pl.package else "None"
            current.add((uid, name))
        self._stage_uid_snapshots[stage_label] = current

        # Compare with previous stage to find unlogged changes
        prev_key = None
        for key in self._stage_uid_snapshots:
            if key == stage_label:
                break
            prev_key = key
        if prev_key:
            prev_uids = self._stage_uid_snapshots[prev_key]
            new_uids = current - prev_uids
            removed_uids = prev_uids - current
            if removed_uids:
                for uid, name in sorted(removed_uids):
                    # Check log for matching removal
                    found = any(
                        e["uid"] == uid and "REMOVED" in str(e.get("new"))
                        for e in self._log
                    )
                    if not found:
                        print(f"  *** UNLOGGED REMOVAL: uid={uid} pkg={name}")

    # ── Reporting ───────────────────────────────────────────────────

    def dump_for(self, package_name: str) -> None:
        matching = [e for e in self._log if e["package"] == package_name]
        if not matching:
            print(f"No trace entries for '{package_name}'")
            return
        print(f"\n=== Mutation trace for '{package_name}' ({len(matching)} entries) ===")
        print(f"  {'#':>3} {'Function':40s} {'UID':>5} {'Old':30s} {'New':30s} Reason")
        print(f"  {'-'*3} {'-'*40} {'-'*5} {'-'*30} {'-'*30} {'-'*20}")
        for i, e in enumerate(matching):
            print(f"  {i:3d} {e['func']:40s} {e['uid']:5d} {e['old']:30s} {e['new']:30s} {e['reason']}")

    def dump_all(self) -> None:
        if not self._log:
            print("No mutation events logged.")
            return
        print(f"\n=== Full mutation trace ({len(self._log)} entries) ===")
        print(f"  {'#':>3} {'Function':40s} {'UID':>5} {'Package':20s} {'Old':30s} {'New':30s} Reason")
        print(f"  {'-'*3} {'-'*40} {'-'*5} {'-'*20} {'-'*30} {'-'*30} {'-'*20}")
        for i, e in enumerate(self._log):
            print(f"  {i:3d} {e['func']:40s} {e['uid']:5d} {e['package']:20s} {e['old']:30s} {e['new']:30s} {e['reason']}")


M = _MutationLogger()
