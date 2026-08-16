import logging
from datetime import date, datetime
from typing import Optional

from app.db import DatabaseManager

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = ("completed", "skipped", "cancelled")

#: Photo categories a stop must carry before it can be marked completed:
#: the goods off the truck, and the truck shut afterwards. Together they are
#: what actually answers a dispute — delivered, and secured.
#:
#: Deliberately *not* enforced as a category whitelist on upload. The route
#: sanitizes any category into a safe path segment instead (audit S-04, and
#: tests/test_delivery_routes.py::test_traversal_in_category_cannot_escape
#: depends on an unknown category still being accepted). The consequence is
#: the safe one: a mistyped category can never satisfy the gate.
PROOF_CATEGORIES = ("unload", "door")

#: Returned by :func:`advance_stop` in place of a prose message when a
#: completion is blocked for want of photos. The route turns it into a 422
#: the dashboard can recognise and answer with an override, rather than the
#: client having to pattern-match on English.
PROOF_REQUIRED = "proof_required"


def _get_plan_id_for_stop(conn, stop_id: int) -> Optional[int]:
    c = conn.cursor()
    c.execute("""
        SELECT va.plan_id FROM delivery_plan_stops s
        JOIN vehicle_assignments va ON va.id = s.vehicle_assignment_id
        WHERE s.id = ?
    """, (stop_id,))
    row = c.fetchone()
    return row["plan_id"] if row else None


def _get_plan_date_for_stop(conn, stop_id: int) -> Optional[str]:
    c = conn.cursor()
    c.execute("""
        SELECT dp.plan_date FROM delivery_plan_stops s
        JOIN vehicle_assignments va ON va.id = s.vehicle_assignment_id
        JOIN delivery_plans dp ON dp.id = va.plan_id
        WHERE s.id = ?
    """, (stop_id,))
    row = c.fetchone()
    return row["plan_date"] if row else None


def _maybe_complete_plan(conn, plan_id: Optional[int]):
    """Auto-completes a plan once every stop across every vehicle
    assignment under it has reached a terminal state — otherwise a plan
    never leaves the dashboard's active (confirmed/executing) view.
    """
    if plan_id is None:
        return
    c = conn.cursor()
    placeholders = ",".join("?" for _ in TERMINAL_STATUSES)
    c.execute(f"""
        SELECT COUNT(*) as remaining
        FROM stop_executions e
        JOIN delivery_plan_stops s ON s.id = e.stop_id
        JOIN vehicle_assignments va ON va.id = s.vehicle_assignment_id
        WHERE va.plan_id = ? AND e.status NOT IN ({placeholders})
    """, (plan_id, *TERMINAL_STATUSES))
    remaining = c.fetchone()["remaining"]
    if remaining == 0:
        c.execute(
            "UPDATE delivery_plans SET status = 'completed', updated_at = ? WHERE id = ? AND status != 'completed'",
            (datetime.now().isoformat(), plan_id),
        )


def _reopen_plan(conn, plan_id: Optional[int]):
    """Undo of :func:`_maybe_complete_plan` — a stop leaving a terminal status
    means the plan has work outstanding again, so it must come back into the
    dashboard's active view. Same UPDATE ``insert_temp_stop`` uses when a new
    stop lands on an already-completed plan.
    """
    if plan_id is None:
        return
    conn.cursor().execute(
        "UPDATE delivery_plans SET status = 'executing', updated_at = ? WHERE id = ? AND status = 'completed'",
        (datetime.now().isoformat(), plan_id),
    )


def _record_status_event(conn, stop_id: int, from_status: str, to_status: str,
                         action: str, reason: str = "", occurred_at: Optional[str] = None):
    """Append one phase change to the stop's log.

    Always called on the *same* connection as the UPDATE it describes, and
    only after that UPDATE reported a rowcount — so a refused or lost
    transition never leaves an event claiming it happened.
    """
    conn.cursor().execute("""
        INSERT INTO stop_status_events
            (stop_id, from_status, to_status, action, reason, occurred_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (stop_id, from_status or "", to_status, action, reason or "",
          occurred_at or datetime.now().isoformat()))


def list_status_events(db_path: str, stop_id: int) -> list:
    """The stop's phase log, oldest first — the order it happened in.

    Empty for any stop last touched before the log existed; nothing was
    backfilled, because inventing a history is exactly the thing a history
    is supposed to protect against.
    """
    with DatabaseManager(db_path).connect() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT id, stop_id, from_status, to_status, action, reason, occurred_at
            FROM stop_status_events WHERE stop_id = ? ORDER BY id
        """, (stop_id,))
        return [dict(r) for r in c.fetchall()]


def _last_forward_event(conn, stop_id: int, status: str):
    """The most recent event that *moved the stop into* ``status`` by going
    forward — an advance, skip or cancel.

    Reverts are excluded deliberately, and this is the subtle part. After
    planned → arrived → completed → revert, the newest event landing on
    'arrived' is the revert itself, whose ``from_status`` is 'completed'.
    Reading that would send the next revert *forward* to completed, turning
    a second undo into a redo. The question being asked is "how did this stop
    legitimately get here", and an undo is not how.
    """
    c = conn.cursor()
    c.execute("""
        SELECT * FROM stop_status_events
        WHERE stop_id = ? AND to_status = ? AND action != 'revert'
        ORDER BY id DESC LIMIT 1
    """, (stop_id, status))
    return c.fetchone()


def _missing_proof(conn, stop_id: int) -> list:
    """Which of PROOF_CATEGORIES this stop has no photo for, in order."""
    c = conn.cursor()
    c.execute("""
        SELECT DISTINCT category FROM delivery_stop_images WHERE stop_id = ?
    """, (stop_id,))
    have = {r["category"] for r in c.fetchall()}
    return [cat for cat in PROOF_CATEGORIES if cat not in have]


def missing_proof(db_path: str, stop_id: int) -> list:
    """Public read of the same question, for building an error message.

    Only called on the failure path, so the extra query costs nothing in the
    normal case.
    """
    with DatabaseManager(db_path).connect() as conn:
        return _missing_proof(conn, stop_id)


def get_current_stop(db_path: str, assignment_id: int) -> Optional[dict]:
    with DatabaseManager(db_path).connect() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT s.*, e.id as execution_id, e.execution_sequence, e.status as execution_status,
                   e.skip_reason, e.cancel_reason, e.actual_arrival_at, e.actual_departure_at, e.completed_at
            FROM delivery_plan_stops s
            JOIN stop_executions e ON e.stop_id = s.id
            WHERE s.vehicle_assignment_id = ?
              AND e.status IN ('planned', 'enroute', 'arrived')
            ORDER BY e.execution_sequence
            LIMIT 1
        """, (assignment_id,))
        row = c.fetchone()
        return dict(row) if row else None


def get_stop_execution(db_path: str, stop_id: int) -> Optional[dict]:
    with DatabaseManager(db_path).connect() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM stop_executions WHERE stop_id = ?", (stop_id,))
        row = c.fetchone()
        return dict(row) if row else None


def _update_execution(db_path: str, stop_id: int, _event_action: str = "",
                      _event_reason: str = "", **kwargs):
    """Patch a stop's execution row.

    ``_event_action`` names the operation for the phase log. When given, the
    prior status is read on the same connection immediately before the
    UPDATE, so the recorded ``from_status`` is the one actually replaced
    rather than whatever a caller believed it to be.
    """
    allowed = {"status", "execution_sequence", "skip_reason", "cancel_reason",
               "actual_arrival_at", "actual_departure_at", "completed_at"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False
    updates["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [stop_id]
    with DatabaseManager(db_path).connect() as conn:
        c = conn.cursor()

        previous_status = ""
        if _event_action and updates.get("status"):
            c.execute("SELECT status FROM stop_executions WHERE stop_id = ?", (stop_id,))
            row = c.fetchone()
            previous_status = row["status"] if row else ""

        c.execute(f"UPDATE stop_executions SET {set_clause} WHERE stop_id = ?", vals)
        ok = c.rowcount > 0
        if ok and _event_action and updates.get("status"):
            _record_status_event(conn, stop_id, previous_status, updates["status"],
                                 _event_action, _event_reason,
                                 occurred_at=updates["updated_at"])
        if ok and updates.get("status") in TERMINAL_STATUSES:
            _maybe_complete_plan(conn, _get_plan_id_for_stop(conn, stop_id))
        return ok


#: Advancing is a two-step walk: planned → arrived → completed.
_ADVANCE_TRANSITIONS = {"planned": "arrived", "arrived": "completed"}


def advance_stop(db_path: str, stop_id: int, expected_status: Optional[str] = None,
                 override_reason: str = ""):
    """Move a stop one step along planned → arrived → completed.

    Completing a stop requires proof: one photo of the goods unloaded and one
    of the door (or gate) shut afterwards. ``override_reason`` completes it
    without them — a driver with a dead phone must not be stranded — and the
    reason is written into the stop's phase history, so an exception is a
    permanent part of the record rather than a message in a chat somewhere.

    Only the final step is gated. Arriving somewhere is not a claim about
    what happened there, so there is nothing yet to prove.

    ``expected_status`` is the status the caller believes the stop is in —
    the one the dispatcher could actually see when they pressed the button.
    When supplied and it no longer matches, the request is refused.

    Both guards exist because this is not idempotent and a double-click sent
    two requests: the first moved planned → arrived, the second arrived →
    completed, so **one accidental double-tap marked a stop delivered with no
    arrival record**, stamping arrival and departure in the same second and
    destroying dwell time (audit C-07). On a mobile dispatch UI that is a
    routine mis-tap, not an edge case.

    The UPDATE additionally carries ``AND status = ?``, so if two requests do
    arrive together only one can affect a row — the loser sees rowcount 0 and
    reports the conflict rather than double-stepping.
    """
    with DatabaseManager(db_path).connect() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM stop_executions WHERE stop_id = ?", (stop_id,))
        execution = c.fetchone()
        if not execution:
            return False, "Stop execution not found"

        status = execution["status"]

        if expected_status is not None and status != expected_status:
            return False, (
                f"This stop is already '{status}', not '{expected_status}' — "
                f"someone else may have advanced it. Refresh to see the current state."
            )

        target = _ADVANCE_TRANSITIONS.get(status)
        if target is None:
            return False, f"Cannot advance stop in status '{status}'"

        override = (override_reason or "").strip()
        if target == "completed" and not override and _missing_proof(conn, stop_id):
            return False, PROOF_REQUIRED

        now = datetime.now().isoformat()

        if target == "arrived":
            c.execute("""
                UPDATE stop_executions SET status = 'arrived', actual_arrival_at = ?,
                    updated_at = ? WHERE stop_id = ? AND status = 'planned'
            """, (now, now, stop_id))
        else:
            c.execute("""
                UPDATE stop_executions SET status = 'completed', actual_departure_at = ?,
                    completed_at = ?, updated_at = ? WHERE stop_id = ? AND status = 'arrived'
            """, (now, now, now, stop_id))

        if c.rowcount == 0:
            # Another request won the transition between our SELECT and UPDATE.
            return False, "This stop was just advanced by another request. Refresh to see the current state."

        # The override reason rides on the event, which is the only place it
        # is kept — nothing on stop_executions records "completed without
        # proof", and inventing a column for it would duplicate the log.
        _record_status_event(conn, stop_id, status, target, "advance",
                             reason=override, occurred_at=now)

        if target == "completed":
            _maybe_complete_plan(conn, _get_plan_id_for_stop(conn, stop_id))
            return True, "completed"

        return True, "advanced"


#: The statuses an accidental button press can be walked back out of, and
#: where each lands. ``skipped``/``cancelled`` are resolved at runtime by
#: :func:`_revert_target` — see there.
_REVERT_TRANSITIONS = {
    "arrived": "planned",
    "completed": "arrived",
    "skipped": "planned",
    "cancelled": "planned",
}

def _parse_ts(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _parse_plan_date(value) -> Optional[date]:
    """``delivery_plans.plan_date`` as a date. Stored as ``YYYY-MM-DD`` text."""
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def can_revert(status: Optional[str], plan_date=None, today: Optional[date] = None) -> bool:
    """Whether a stop in ``status`` may still be corrected.

    Single source of truth for the rule: the dashboard renders its Revert
    button from this (via the ``can_revert`` flag on ``GET /api/stops``) and
    :func:`revert_stop` re-checks it on the way in, so a button left open on
    a stale screen can't act after the day it was rendered in.

    **The rule is the plan's own day, not a stopwatch.** This replaced a
    15-minute window on 2026-08-01: a correction is bookkeeping, and
    bookkeeping is finished at the end of a shift, not within a quarter of an
    hour of the mistake. A plan dated today or later is live work and stays
    correctable; once its date has passed, the record is closed.

    Two consequences worth being explicit about:

    - ``today`` comes from the server clock, which is UTC unless the
      deployment says otherwise, while ``plan_date`` is a business date typed
      by a dispatcher on Vietnam time (+7). Corrections therefore stay open
      roughly seven hours into the next local day. That is the lenient
      direction — a night shift can finish its paperwork — and never the
      direction that freezes work still in progress.
    - A plan with no readable date is *not* correctable. Unknown reads as
      closed, the same conservative choice made everywhere else here.
    """
    if status not in _REVERT_TRANSITIONS:
        return False
    day = _parse_plan_date(plan_date)
    if day is None:
        return False
    return day >= (today or datetime.now().date())


def _revert_target(conn, status: str, execution, stop_id: int) -> Optional[str]:
    """Where a revert from ``status`` lands.

    Prefers the **recorded** previous phase: the newest event whose
    ``to_status`` is where the stop actually is names the ``from_status`` it
    came from, so a revert returns the stop to where it genuinely was rather
    than to where a table says it probably was.

    Falls back to the static map for stops with no log — everything last
    touched before 2026-08-01, since nothing was backfilled. In that path
    ``skipped``/``cancelled`` are still *inferred*: an ``actual_arrival_at``
    can only have been written by an advance, so a stop skipped after the
    driver had already arrived returns to ``arrived``. Inference is the
    reason the log exists; it is not wrong here, just unverifiable.
    """
    if status not in _REVERT_TRANSITIONS:
        return None

    event = _last_forward_event(conn, stop_id, status)
    if event is not None and event["from_status"]:
        return event["from_status"]

    if status in ("skipped", "cancelled") and execution["actual_arrival_at"]:
        return "arrived"
    return _REVERT_TRANSITIONS.get(status)


def revert_stop(db_path: str, stop_id: int, expected_status: Optional[str] = None):
    """Walk a stop one step *back*: the undo for Advance, Skip and Cancel.

    Exists because Advance is a single tap with no confirmation, sitting next
    to Skip and Cancel on a panel used on a phone in a moving vehicle — a
    mis-tap marked a stop arrived (or delivered) and the only remedy was
    editing the database by hand.

    Guards mirror :func:`advance_stop` exactly, and for the same reasons: the
    ``expected_status`` token refuses a revert aimed at a status the stop has
    since left, and ``AND status = ?`` on the UPDATE means two racing requests
    can't step the stop back twice.

    Each transition clears the timestamps its forward step wrote, so a
    reverted stop is indistinguishable from one that was never advanced —
    a stop left holding an arrival time it had "un-arrived" from would
    corrupt dwell time exactly the way the double-tap bug (C-07) did.
    """
    with DatabaseManager(db_path).connect() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM stop_executions WHERE stop_id = ?", (stop_id,))
        execution = c.fetchone()
        if not execution:
            return False, "Stop execution not found"

        status = execution["status"]

        if expected_status is not None and status != expected_status:
            return False, (
                f"This stop is already '{status}', not '{expected_status}' — "
                f"someone else may have changed it. Refresh to see the current state."
            )

        target = _revert_target(conn, status, execution, stop_id)
        if target is None:
            return False, f"Cannot revert a stop in status '{status}'"

        if not can_revert(status, plan_date=_get_plan_date_for_stop(conn, stop_id)):
            return False, (
                "This stop belongs to a plan whose date has passed, so its record "
                "is closed and can no longer be corrected here."
            )

        now = datetime.now().isoformat()

        if status == "arrived":
            c.execute("""
                UPDATE stop_executions SET status = 'planned', actual_arrival_at = NULL,
                    updated_at = ? WHERE stop_id = ? AND status = 'arrived'
            """, (now, stop_id))
        elif status == "completed":
            c.execute("""
                UPDATE stop_executions SET status = 'arrived', actual_departure_at = NULL,
                    completed_at = NULL, updated_at = ? WHERE stop_id = ? AND status = 'completed'
            """, (now, stop_id))
        else:
            # skipped / cancelled — the reason belonged to the action being
            # undone, so it goes with it.
            c.execute("""
                UPDATE stop_executions SET status = ?, skip_reason = '', cancel_reason = '',
                    completed_at = NULL, updated_at = ? WHERE stop_id = ? AND status = ?
            """, (target, now, stop_id, status))

        if c.rowcount == 0:
            # Another request won the transition between our SELECT and UPDATE.
            return False, "This stop was just changed by another request. Refresh to see the current state."

        _record_status_event(conn, stop_id, status, target, "revert", occurred_at=now)

        if status in TERMINAL_STATUSES:
            _reopen_plan(conn, _get_plan_id_for_stop(conn, stop_id))

        return True, target


def annotate_revertible(stops: list, today: Optional[date] = None) -> list:
    """Stamp ``can_revert`` onto rows shaped like ``plan_service.list_stops``
    output, whose status column is aliased ``execution_status``.

    Computed server-side so the dashboard renders the Revert button from the
    same calendar that enforces it — a browser on a different date would
    otherwise show a button the API refuses, or hide one it would accept.
    """
    reference = today or datetime.now().date()
    for stop in stops:
        stop["can_revert"] = can_revert(
            stop.get("execution_status"),
            plan_date=stop.get("plan_date"),
            today=reference,
        )
    return stops


def skip_stop(db_path: str, stop_id: int, reason: str = ""):
    now = datetime.now().isoformat()
    return _update_execution(db_path, stop_id,
                             _event_action="skip", _event_reason=reason,
                             status="skipped", skip_reason=reason,
                             completed_at=now)


def cancel_stop(db_path: str, stop_id: int, reason: str = ""):
    now = datetime.now().isoformat()
    return _update_execution(db_path, stop_id,
                             _event_action="cancel", _event_reason=reason,
                             status="cancelled", cancel_reason=reason,
                             completed_at=now)


def reorder_stops(db_path: str, assignment_id: int, stop_ids_in_order: list[int]):
    """Renumber an assignment's stops. Returns ``(ok, message)``.

    The supplied list must name every stop of the assignment exactly once.
    Previously any list was accepted and applied stop-by-stop, so:

      - a **partial** list renumbered only the stops it named, leaving the
        others on their old sequence — three stops reordered with two ids
        produced execution_sequences ``[1, 1, 2]``. Nothing enforces
        uniqueness on that column, so ``ORDER BY execution_sequence`` became
        non-deterministic and ``get_current_stop``'s ``LIMIT 1`` could return
        either of the tied stops — i.e. the dashboard could show the wrong
        next stop.
      - ids belonging to a **different** assignment matched no row (the
        subquery filtered them out) yet the function still returned success,
        so a caller got a silent no-op.
    """
    requested = list(stop_ids_in_order or [])

    with DatabaseManager(db_path).connect() as conn:
        c = conn.cursor()
        c.execute(
            "SELECT id FROM delivery_plan_stops WHERE vehicle_assignment_id = ?",
            (assignment_id,)
        )
        actual = {r["id"] for r in c.fetchall()}

        if not actual:
            return False, "Assignment has no stops to reorder"
        if len(set(requested)) != len(requested):
            return False, "Duplicate stop ids in the requested order"
        if set(requested) != actual:
            missing = sorted(actual - set(requested))
            unknown = sorted(set(requested) - actual)
            problems = []
            if missing:
                problems.append(f"missing stop(s) {missing}")
            if unknown:
                problems.append(f"stop(s) {unknown} not in this assignment")
            return False, (
                "Reorder must list every stop of the assignment exactly once — "
                + "; ".join(problems)
            )

        now = datetime.now().isoformat()
        for idx, stop_id in enumerate(requested, start=1):
            c.execute("""
                UPDATE stop_executions SET execution_sequence = ?, updated_at = ?
                WHERE stop_id = ?
            """, (idx, now, stop_id))
        return True, "reordered"


def insert_temp_stop(db_path: str, assignment_id: int, after_sequence: int,
                     station_code: str = "", station_name: str = "",
                     address: str = "", lat: Optional[float] = None, lng: Optional[float] = None,
                     manager_name: str = "", manager_phone: str = "",
                     product_description: str = "", note: str = ""):
    with DatabaseManager(db_path).connect() as conn:
        c = conn.cursor()

        c.execute("""
            SELECT MAX(planned_sequence) as max_seq FROM delivery_plan_stops
            WHERE vehicle_assignment_id = ?
        """, (assignment_id,))
        max_seq = c.fetchone()["max_seq"] or 0
        new_seq = max_seq + 1

        c.execute("""
            INSERT INTO delivery_plan_stops
                (vehicle_assignment_id, planned_sequence, station_code, station_name,
                 address, lat, lng, manager_name, manager_phone, product_description, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (assignment_id, new_seq, station_code, station_name,
              address, lat, lng, manager_name, manager_phone, product_description, note))
        stop_id = c.lastrowid

        insert_seq = after_sequence + 1
        c.execute("""
            UPDATE stop_executions SET execution_sequence = execution_sequence + 1
            WHERE stop_id IN (
                SELECT id FROM delivery_plan_stops WHERE vehicle_assignment_id = ?
            ) AND stop_id != ? AND execution_sequence > ?
        """, (assignment_id, stop_id, after_sequence))

        c.execute("""
            INSERT INTO stop_executions (stop_id, execution_sequence, status)
            VALUES (?, ?, 'planned')
        """, (stop_id, insert_seq))

        # If the plan had already auto-completed, this new pending stop
        # must not stay silently hidden from the dashboard's active view.
        plan_id = _get_plan_id_for_stop(conn, stop_id)
        if plan_id is not None:
            c.execute(
                "UPDATE delivery_plans SET status = 'executing', updated_at = ? WHERE id = ? AND status = 'completed'",
                (datetime.now().isoformat(), plan_id),
            )

        return stop_id


def _progress_from_counts(counts: dict) -> dict:
    """Build the progress block from a status → count mapping.

    Single home for this computation, which previously existed twice —
    verbatim, including its bug — in get_assignment_progress and
    get_dashboard_data (audit duplicate-logic cluster 5).

    The bug: ``total = sum(counts.values()) or 1`` guarded against
    ZeroDivisionError by falsifying the total, so an assignment with no stops
    reported ``total: 1, remaining: 1`` and a dispatcher went looking for a
    stop that did not exist (audit C-09). Only the division needs guarding.
    """
    total = sum(counts.values())
    completed = counts.get("completed", 0) + counts.get("skipped", 0) + counts.get("cancelled", 0)
    return {
        "total": total,
        "completed": completed,
        "remaining": total - completed,
        "progress_pct": round(completed / total * 100, 1) if total else 0.0,
        "breakdown": counts,
    }


def get_assignment_progress(db_path: str, assignment_id: int) -> dict:
    with DatabaseManager(db_path).connect() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT e.status, COUNT(*) as count
            FROM delivery_plan_stops s
            JOIN stop_executions e ON e.stop_id = s.id
            WHERE s.vehicle_assignment_id = ?
            GROUP BY e.status
        """, (assignment_id,))
        counts = {r["status"]: r["count"] for r in c.fetchall()}
        return _progress_from_counts(counts)


def get_dashboard_data(db_path: str):
    """Return all active (confirmed/executing) assignments with their
    current stop and progress breakdown.

    Fixed N+1: previously issued 1 query for assignments plus 2 more
    per assignment (current-stop + status-counts) — 101 queries for 50
    assignments. Now issues exactly 3 queries total regardless of N:
    assignments, current-stop-per-assignment (via a window function to
    pick the earliest active stop per assignment in one pass), and
    status-counts-per-assignment (via GROUP BY on both columns).
    """
    with DatabaseManager(db_path).connect() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT
                va.id as assignment_id,
                va.plan_id,
                va.vehicle_id,
                va.driver_id,
                v.plate_number,
                COALESCE(NULLIF(va.driver_name_override, ''), NULLIF(d.name, ''), v.current_driver) as current_driver,
                dp.plan_name,
                dp.plan_date,
                dp.status as plan_status
            FROM vehicle_assignments va
            JOIN delivery_plans dp ON dp.id = va.plan_id
            LEFT JOIN vehicles v ON v.id = va.vehicle_id
            LEFT JOIN drivers d ON d.id = va.driver_id
            WHERE dp.status IN ('confirmed', 'executing')
            ORDER BY dp.plan_date DESC, va.sequence
        """)
        assignments = [dict(r) for r in c.fetchall()]

        if not assignments:
            return []

        assignment_ids = [a["assignment_id"] for a in assignments]
        placeholders = ",".join("?" for _ in assignment_ids)

        # One query for the current (earliest active) stop of every assignment.
        c.execute(f"""
            SELECT * FROM (
                SELECT s.*, e.id as execution_id, e.execution_sequence, e.status as execution_status,
                       e.skip_reason, e.cancel_reason, e.actual_arrival_at, e.actual_departure_at, e.completed_at,
                       ROW_NUMBER() OVER (
                           PARTITION BY s.vehicle_assignment_id ORDER BY e.execution_sequence
                       ) AS rn
                FROM delivery_plan_stops s
                JOIN stop_executions e ON e.stop_id = s.id
                WHERE s.vehicle_assignment_id IN ({placeholders})
                  AND e.status IN ('planned', 'enroute', 'arrived')
            ) WHERE rn = 1
        """, assignment_ids)
        current_stop_by_aid = {}
        for r in c.fetchall():
            d = dict(r)
            d.pop("rn", None)
            current_stop_by_aid[d["vehicle_assignment_id"]] = d

        # One query for status counts of every assignment.
        c.execute(f"""
            SELECT s.vehicle_assignment_id AS aid, e.status, COUNT(*) as count
            FROM delivery_plan_stops s
            JOIN stop_executions e ON e.stop_id = s.id
            WHERE s.vehicle_assignment_id IN ({placeholders})
            GROUP BY s.vehicle_assignment_id, e.status
        """, assignment_ids)
        counts_by_aid = {}
        for r in c.fetchall():
            counts_by_aid.setdefault(r["aid"], {})[r["status"]] = r["count"]

        result = []
        for a in assignments:
            aid = a["assignment_id"]
            a["current_stop"] = current_stop_by_aid.get(aid)
            a["progress"] = _progress_from_counts(counts_by_aid.get(aid, {}))
            result.append(a)

        return result
