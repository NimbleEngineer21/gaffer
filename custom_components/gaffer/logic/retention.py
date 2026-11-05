"""Bounds on stored runs, so Gaffer does not add to memory pressure."""

from typing import Any

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
    """Keep the newest runs inside the age, per-source, and total limits."""
    kept: list[dict[str, Any]] = []
    per: dict[str | None, int] = {}
    for run in sorted(runs, key=lambda r: r["started_at"], reverse=True):
        if now - run["started_at"] > max_age or len(kept) >= total:
            break
        key = run["source"] or run["origin"]
        if per.get(key, 0) >= per_source:
            continue
        per[key] = per.get(key, 0) + 1
        kept.append(run)
    kept.reverse()
    return kept
