"""Judge each expectation against the entity's state timeline (plan section 4.5).

Each expectation has two checks:
- the action check, at the call time plus the settle window;
- the run check, at the latest end of any call's window on the same entity.

A window includes any transition that the call asked for.

A run closes only after both times have passed, so the verdict reads values from
the recorded timeline and needs no timers. The timeline starts with the state the
entity had when the call ran, because Home Assistant fires no state change when
an action leaves a value as it was.
"""

from collections.abc import Callable, Sequence
from typing import Any

from .declared import DeclaredExpectation, merge
from .expectations import UNAVAILABLE, infer_run
from .models import (
    STATE,
    ActionResult,
    Check,
    Comparator,
    Expectation,
    RunRecord,
    Snapshot,
    Verdict,
)

WindowFor = Callable[[str], float]

# Worst first. The run-level result is the first verdict in this order.
RANK = (
    Verdict.TARGET_UNAVAILABLE,
    Verdict.NO_EFFECT,
    Verdict.REVERTED,
    Verdict.PARTIAL,
    Verdict.LATE,
    Verdict.SUPERSEDED,
    Verdict.UNCHECKED,
    Verdict.CONFIRMED,
)
_EPSILON = 1e-9

Timeline = list[tuple[float, Snapshot]]


def _observed(snap: Snapshot, key: str) -> Any:
    value = snap.state if key == STATE else snap.attributes.get(key)
    return tuple(value) if isinstance(value, list) else value


def met(check: Check, snap: Snapshot) -> bool:
    """Return True when the snapshot has the value that the check expects."""
    value = _observed(snap, check.key)
    match check.comparator:
        case Comparator.EQ:
            return bool(value == check.value)
        case Comparator.IN:
            return value in check.value
        case Comparator.NOT_IN:
            return value not in check.value
    # Comparator.APPROX
    if isinstance(value, bool) or not isinstance(value, int | float):
        return False
    return bool(abs(value - check.value) <= check.tolerance + _EPSILON)


def _at(timeline: Timeline, t: float) -> Snapshot:
    """Return the last sample at or before t. The first sample is the call time."""
    current = timeline[0][1]
    for at, snap in timeline:
        if at > t:
            break
        current = snap
    return current


def _values(exp: Expectation, snap: Snapshot) -> dict[str, Any]:
    return {check.key: _observed(snap, check.key) for check in exp.checks}


def _judge(run: RunRecord, exp: Expectation, all_exps: Sequence[Expectation]) -> ActionResult:
    entity_id = exp.entity_id
    if entity_id is None or not exp.checks:
        return ActionResult(exp, Verdict.UNCHECKED)
    call = run.calls[exp.call_index]
    prior = call.prior.get(entity_id)
    if prior is None or prior.state is None or prior.state in UNAVAILABLE:
        state = None if prior is None else prior.state
        return ActionResult(exp, Verdict.TARGET_UNAVAILABLE, at_action={STATE: state})

    action_t = call.at + exp.window
    run_t = max(
        run.calls[other.call_index].at + other.window
        for other in all_exps
        if other.entity_id == entity_id
    )
    own = [c for c in run.changes if c.entity_id == entity_id and c.at >= call.at]
    timeline: Timeline = [(call.at, prior)]
    timeline += sorted(
        ((c.at, Snapshot(c.state, c.attributes)) for c in own if c.matched_by != "foreign"),
        key=lambda sample: sample[0],
    )
    at_action, at_run = _at(timeline, action_t), _at(timeline, run_t)

    def result(verdict: Verdict, failed: tuple[str, ...] = ()) -> ActionResult:
        return ActionResult(exp, verdict, _values(exp, at_action), _values(exp, at_run), failed)

    later_same_key = any(
        other.entity_id == entity_id and other.call_index > exp.call_index and other.keys & exp.keys
        for other in all_exps
    )
    foreign = any(c.matched_by == "foreign" and c.at <= run_t for c in own)
    if later_same_key or foreign:
        return result(Verdict.SUPERSEDED)

    states = [c for c in exp.checks if c.key == STATE]
    primary = states or list(exp.checks)

    def primary_met(snap: Snapshot) -> bool:
        return all(met(c, snap) for c in primary)

    if not any(primary_met(snap) for at, snap in timeline if at <= run_t):
        return result(Verdict.NO_EFFECT, _failed(primary, at_run))
    if not primary_met(at_run):
        return result(Verdict.REVERTED, _failed(primary, at_run))
    failed = _failed(exp.checks, at_run)
    if failed:
        return result(Verdict.PARTIAL, failed)
    if _failed(exp.checks, at_action):
        return result(Verdict.LATE)
    return result(Verdict.CONFIRMED)


def _failed(checks: Sequence[Check], snap: Snapshot) -> tuple[str, ...]:
    return tuple(c.key for c in checks if not met(c, snap))


def judge(
    run: RunRecord, window_for: WindowFor, declared: Sequence[DeclaredExpectation] = ()
) -> list[ActionResult]:
    """Return one result per expectation of every call in a closed run."""
    exps = merge(infer_run(run, window_for), declared)
    return [_judge(run, exp, exps) for exp in exps]


def worst(results: Sequence[ActionResult]) -> Verdict | None:
    """Return the run-level verdict: the worst action verdict, or None for no actions."""
    present = {result.verdict for result in results}
    return next((verdict for verdict in RANK if verdict in present), None)
