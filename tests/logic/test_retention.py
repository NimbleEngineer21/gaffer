"""Bounds on stored runs."""

from custom_components.gaffer.logic.outputs import DAY
from custom_components.gaffer.logic.retention import retain
from tests.runs import stored_run


def _run(source: str | None, at: float, origin: str = "automation") -> dict[str, object]:
    return {"source": source, "origin": origin, "started_at": at}


def test_keeps_newest_per_source_in_time_order() -> None:
    runs = [_run("a", t) for t in (1, 2, 3)] + [_run("b", 2.5)]
    kept = retain(runs, 10, per_source=2)
    assert [(r["source"], r["started_at"]) for r in kept] == [("a", 2), ("b", 2.5), ("a", 3)]


def test_runs_without_source_group_by_origin() -> None:
    runs = [_run(None, 1, "scene"), _run(None, 2, "scene"), _run(None, 3, "homekit")]
    kept = retain(runs, 10, per_source=1)
    assert [r["started_at"] for r in kept] == [2, 3]


def test_drops_old_runs_and_caps_total() -> None:
    runs = [_run(str(t), t) for t in range(10)]
    assert [r["started_at"] for r in retain(runs, 10, max_age=5)] == [5, 6, 7, 8, 9]
    assert [r["started_at"] for r in retain(runs, 10, total=3)] == [7, 8, 9]


def test_recent_failures_are_kept_past_the_per_source_limit() -> None:
    now = 2 * DAY
    old_fail = stored_run("no_effect", at=now - DAY - 10)
    fails = [stored_run("no_effect", at=now - 100 + i) for i in range(2)]
    passes = [stored_run("confirmed", at=now - 50 + i) for i in range(3)]
    kept = retain([old_fail, *fails, *passes], now, per_source=2)
    assert [r["started_at"] for r in kept] == [now - 100, now - 99, now - 49, now - 48]


def test_runs_group_by_the_output_name() -> None:
    runs = [stored_run(source=None, entity_id=e, at=t) for t, e in enumerate("abab")]
    runs = [r | {"origin": "user"} for r in runs]
    kept = retain(runs, 10, per_source=1)
    assert [r["calls"][0]["entity_ids"] for r in kept] == [["a"], ["b"]]
