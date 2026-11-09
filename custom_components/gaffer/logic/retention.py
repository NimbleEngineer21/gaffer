"""Bounds on stored runs, so Gaffer does not add to memory pressure."""

from typing import Any

from .outputs import DAY, is_failure, name

PER_SOURCE = 50
TOTAL = 5000
MAX_AGE = 7 * 24 * 3600.0


def retain(
    runs: list[dict[str, Any]],
    now: float,
    *,
    per_source: int = PER_SOURCE,
    total: int = TOTAL,
    max_age: float = MAX_AGE,
) -> list[dict[str, Any]]:
    """Keep the newest runs inside the age, per-source, and total limits.

    A failed run from the last 24 hours is kept past the per-source limit, so the
    24 h failure count and the Repairs rules see every failure. The total limit
    still applies. Runs group by the same name that the outputs use.
    """
    kept: list[dict[str, Any]] = []
    per: dict[str, int] = {}
    for run in sorted(runs, key=lambda r: r["started_at"], reverse=True):
        if now - run["started_at"] > max_age or len(kept) >= total:
            break
        key = name(run)
        recent_failure = is_failure(run) and now - run["started_at"] <= DAY
        if per.get(key, 0) >= per_source and not recent_failure:
            continue
        per[key] = per.get(key, 0) + 1
        kept.append(run)
    kept.reverse()
    return kept
