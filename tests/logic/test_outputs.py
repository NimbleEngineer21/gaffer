"""What Gaffer reports: failures, summaries, the API filter, and Repairs decisions."""

import pytest

from custom_components.gaffer.logic.outputs import (
    DAY,
    Issue,
    counts,
    failures_since,
    is_failure,
    name,
    plan_issues,
    select,
    summary,
)
from tests.runs import result, stored_run


@pytest.mark.parametrize(
    ("verdict", "expected"),
    [
        ("no_effect", True),
        ("reverted", True),
        ("partial", True),
        ("target_unavailable", True),
        ("late", False),
        ("superseded", False),
        ("unchecked", False),
        ("confirmed", False),
        (None, False),
    ],
)
def test_only_failure_verdicts_are_failures(verdict: str | None, expected: bool) -> None:
    assert is_failure(stored_run(verdict)) is expected


def test_unjudged_run_is_never_a_failure() -> None:
    run = stored_run("no_effect") | {"judged": False}
    assert not is_failure(run)
    assert not is_failure(stored_run("no_effect", judged=False))


def test_name_falls_back_to_first_target_then_origin() -> None:
    assert name(stored_run()) == "automation.hall"
    assert name(stored_run(source=None, entity_id="scene.night")) == "scene.night"
    no_targets = stored_run(source=None) | {
        "calls": [{"domain": "notify", "service": "x", "entity_ids": []}]
    }
    assert name(no_targets) == "automation"
    assert name(stored_run(source=None) | {"calls": []}) == "automation"


def test_summary_lists_failed_results_only() -> None:
    run = stored_run(
        "no_effect",
        results=[result("light.hall", "no_effect"), result("light.hall", "confirmed")],
    )
    assert summary(run) == {
        "context_id": run["context_id"],
        "origin": "automation",
        "source": "automation.hall",
        "name": "automation.hall",
        "started_at": 0.0,
        "judged": True,
        "verdict": "no_effect",
        "failed": [
            {
                "entity_id": "light.hall",
                "action": "light.turn_on",
                "verdict": "no_effect",
                "keys": ["state"],
                "expected": {"state": "on"},
                "observed": {"state": "off"},
            }
        ],
    }


def test_failures_since_is_newest_first_inside_the_window() -> None:
    runs = [
        stored_run("no_effect", at=1.0),
        stored_run("confirmed", at=5.0),
        stored_run("reverted", at=10.0),
        stored_run("partial", at=20.0),
    ]
    assert [r["started_at"] for r in failures_since(runs, 2.0)] == [20.0, 10.0]


def test_select_filters_and_limits() -> None:
    runs = [
        stored_run("no_effect", at=1.0),
        stored_run("late", at=2.0),
        stored_run("confirmed", at=3.0, source="script.s"),
        stored_run(None, at=4.0),
    ]
    assert [r["started_at"] for r in select(runs)] == [4.0, 3.0, 2.0, 1.0]
    assert [r["started_at"] for r in select(runs, source="script.s")] == [3.0]
    assert [r["started_at"] for r in select(runs, verdicts=["late", None])] == [4.0, 2.0]
    assert [r["started_at"] for r in select(runs, since=2.0)] == [4.0, 3.0, 2.0]
    assert [r["started_at"] for r in select(runs, failures_only=True)] == [1.0]
    assert [r["started_at"] for r in select(runs, limit=2)] == [4.0, 3.0]


def test_counts_by_verdict_and_origin() -> None:
    runs = [
        stored_run("no_effect"),
        stored_run("no_effect", origin="homekit"),
        stored_run(None),
        stored_run("confirmed", judged=False),
    ]
    assert counts(runs) == {
        "verdicts": {"no_effect": 2, "no_expectations": 1, "unjudged": 1},
        "origins": {"automation": 3, "homekit": 1},
    }


NOW = 2 * DAY
KEY = "runtime_automation.hall"


def _runs(*verdicts: str, start: float = NOW - 100) -> list[dict[str, object]]:
    """Runs of one source, one second apart, oldest first."""
    return [stored_run(v, at=start + i) for i, v in enumerate(verdicts)]


def test_issue_opens_at_three_failures_in_a_day() -> None:
    assert plan_issues(_runs("no_effect", "no_effect"), NOW, set()).upsert == ()
    plan = plan_issues(_runs("no_effect", "reverted", "no_effect"), NOW, set())
    assert plan.upsert == (Issue(KEY, "automation.hall", 3, "light.hall (no_effect, reverted)"),)
    assert plan.delete == ()


def test_failures_older_than_a_day_do_not_count() -> None:
    runs = _runs("no_effect", "no_effect", start=NOW - DAY - 10) + _runs("no_effect")
    assert plan_issues(runs, NOW, set()).upsert == ()


def test_open_issue_stays_while_failures_continue_below_the_threshold() -> None:
    runs = _runs("no_effect", "confirmed", "confirmed")
    [issue] = plan_issues(runs, NOW, {KEY}).upsert
    assert issue.count == 1


def test_open_issue_clears_after_three_passing_runs() -> None:
    runs = _runs("no_effect", "no_effect", "no_effect", "confirmed", "late", "unchecked")
    plan = plan_issues(runs, NOW, {KEY})
    assert (plan.upsert, plan.delete) == ((), (KEY,))


def test_open_issue_clears_with_no_failure_in_a_day() -> None:
    runs = _runs("no_effect", start=NOW - DAY - 10) + _runs("confirmed")
    assert plan_issues(runs, NOW, {KEY}).delete == (KEY,)


def test_alternating_results_keep_the_issue_open_without_flapping() -> None:
    runs = _runs("no_effect", "no_effect", "no_effect")
    open_ids: set[str] = set()
    for i, verdict in enumerate(["confirmed", "no_effect"] * 3):
        runs.append(stored_run(verdict, at=NOW - 50 + i))
        plan = plan_issues(runs, NOW, open_ids)
        open_ids = {issue.issue_id for issue in plan.upsert}
        assert open_ids == {KEY}


def test_issue_with_no_runs_left_is_deleted_and_other_ids_are_kept() -> None:
    plan = plan_issues([], NOW, {KEY, "static_ov001"})
    assert plan.delete == (KEY,)


def test_unjudged_runs_are_left_out_of_issues() -> None:
    runs = [stored_run("no_effect", at=NOW - 10 + i, judged=False) for i in range(3)]
    assert plan_issues(runs, NOW, set()).upsert == ()
