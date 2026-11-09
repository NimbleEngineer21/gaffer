"""What Gaffer reports about stored runs.

Every function takes stored run dicts (the shape the collector writes) and
returns plain data. Only judged runs whose run-level verdict is a failure are
reported; a run stored before its windows passed is never a failure.
"""

from collections import Counter
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .models import FAILURES

Run = Mapping[str, Any]

DAY = 24 * 3600.0
RECENT = 10
ISSUE_OPEN_AT = 3
ISSUE_CLEAR_AFTER = 3
ISSUE_PREFIX = "runtime_"

_FAILURE_VALUES = frozenset(verdict.value for verdict in FAILURES)


def is_failure(run: Run) -> bool:
    """Return True for a judged run whose worst action verdict is a failure."""
    return bool(run.get("judged")) and run.get("verdict") in _FAILURE_VALUES


def name(run: Run) -> str:
    """Return what the run belongs to: its source, else its first target, else its origin."""
    source = run.get("source")
    if source:
        return str(source)
    for call in run.get("calls", ()):
        if call["entity_ids"]:
            return str(call["entity_ids"][0])
    return str(run["origin"])


def _failed_results(run: Run) -> list[dict[str, Any]]:
    calls = run.get("calls", ())
    failed = []
    for result in run.get("results", ()):
        if result["verdict"] not in _FAILURE_VALUES:
            continue
        call = calls[result["call_index"]]
        failed.append(
            {
                "entity_id": result["entity_id"],
                "action": f"{call['domain']}.{call['service']}",
                "verdict": result["verdict"],
                "keys": list(result["failed"]),
                "expected": {check["key"]: check["value"] for check in result["checks"]},
                "observed": dict(result["at_run"]),
            }
        )
    return failed


def summary(run: Run) -> dict[str, Any]:
    """Return the compact form of a run for the event, the sensor, and the API."""
    return {
        "context_id": run["context_id"],
        "origin": run["origin"],
        "source": run.get("source"),
        "name": name(run),
        "started_at": run["started_at"],
        "judged": bool(run.get("judged")),
        "verdict": run.get("verdict"),
        "failed": _failed_results(run),
    }


def newest_first(runs: Iterable[Run]) -> list[Run]:
    """Return runs sorted by start time, newest first."""
    return sorted(runs, key=lambda run: run["started_at"], reverse=True)


def failures_since(runs: Iterable[Run], since: float) -> list[Run]:
    """Return the failed runs that started at or after since, newest first."""
    return [run for run in newest_first(runs) if is_failure(run) and run["started_at"] >= since]


def select(
    runs: Iterable[Run],
    *,
    source: str | None = None,
    verdicts: Collection[str | None] | None = None,
    since: float | None = None,
    failures_only: bool = False,
    limit: int = 50,
) -> list[Run]:
    """Filter runs for the API, newest first."""
    selected: list[Run] = []
    for run in newest_first(runs):
        if len(selected) >= limit:
            break
        if source is not None and name(run) != source:
            continue
        if verdicts is not None and run.get("verdict") not in verdicts:
            continue
        if since is not None and run["started_at"] < since:
            continue
        if failures_only and not is_failure(run):
            continue
        selected.append(run)
    return selected


@dataclass(frozen=True, slots=True)
class Issue:
    """One Repairs issue for repeated failures of one run source."""

    issue_id: str
    name: str
    count: int
    failures: str


@dataclass(frozen=True, slots=True)
class IssuePlan:
    """Issues to create or refresh, and issue ids to delete."""

    upsert: tuple[Issue, ...]
    delete: tuple[str, ...]


def issue_id(run_name: str) -> str:
    """Return the Repairs issue id for a run source."""
    return ISSUE_PREFIX + run_name


def _describe(failed_runs: Sequence[Run]) -> str:
    """List each failed entity once with its verdicts, in first-seen order."""
    seen: dict[str, list[str]] = {}
    for run in failed_runs:
        for result in _failed_results(run):
            verdicts = seen.setdefault(str(result["entity_id"]), [])
            if result["verdict"] not in verdicts:
                verdicts.append(result["verdict"])
    return ", ".join(f"{entity} ({', '.join(v)})" for entity, v in seen.items())


def plan_issues(runs: Iterable[Run], now: float, open_ids: Collection[str]) -> IssuePlan:
    """Decide which issues to open, refresh, and clear.

    An issue opens when a source has ISSUE_OPEN_AT or more failed runs in 24 h. It
    stays open until the source has no failed run in 24 h, or its last
    ISSUE_CLEAR_AFTER judged runs all passed. The gap between the two rules keeps
    an automation that fails now and then from opening and closing on each run.
    """
    by_name: dict[str, list[Run]] = {}
    for run in newest_first(runs):
        if run.get("judged"):
            by_name.setdefault(name(run), []).append(run)

    upsert: list[Issue] = []
    keep: set[str] = set()
    for run_name, judged in by_name.items():
        key = issue_id(run_name)
        recent = [run for run in judged if is_failure(run) and run["started_at"] >= now - DAY]
        last = judged[:ISSUE_CLEAR_AFTER]
        cleared = not recent or (
            len(last) == ISSUE_CLEAR_AFTER and not any(is_failure(run) for run in last)
        )
        if cleared or (key not in open_ids and len(recent) < ISSUE_OPEN_AT):
            continue
        keep.add(key)
        upsert.append(Issue(key, run_name, len(recent), _describe(recent)))
    delete = tuple(sorted(i for i in open_ids if i.startswith(ISSUE_PREFIX) and i not in keep))
    return IssuePlan(tuple(upsert), delete)


def counts(runs: Iterable[Run]) -> dict[str, dict[str, int]]:
    """Count runs by verdict and by origin, for diagnostics."""
    verdicts: Counter[str] = Counter()
    origins: Counter[str] = Counter()
    for run in runs:
        if not run.get("judged"):
            verdicts["unjudged"] += 1
        else:
            verdicts[run.get("verdict") or "no_expectations"] += 1
        origins[str(run["origin"])] += 1
    return {"verdicts": dict(verdicts), "origins": dict(origins)}
