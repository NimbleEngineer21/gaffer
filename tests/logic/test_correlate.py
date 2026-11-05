"""Grouping calls and state changes into runs."""

from custom_components.gaffer.logic.correlate import RunTracker
from custom_components.gaffer.logic.models import Ctx, Origin, ServiceCall, StateChange

AUTO = Ctx("run1", parent_id="trigger1")


def _tracker(*, track_user: bool = False) -> RunTracker:
    return RunTracker(lambda entity_id: 3.0, track_user=track_user)


def _call(entity: str, at: float, domain: str = "light", service: str = "turn_on") -> ServiceCall:
    return ServiceCall(domain, service, {"entity_id": entity}, (entity,), at)


def _change(entity: str, at: float) -> StateChange:
    return StateChange(entity, "on", {}, at, "context")


def test_calls_and_changes_join_the_run_by_context() -> None:
    t = _tracker()
    t.start(AUTO, Origin.AUTOMATION, "automation.a", 0.0)
    t.on_call(AUTO, _call("light.x", 0.1))
    t.on_state(AUTO, _change("light.x", 0.2))
    [run] = t.open_runs
    assert (run.origin, run.source, len(run.calls)) == (Origin.AUTOMATION, "automation.a", 1)
    assert [c.matched_by for c in run.changes] == ["context"]


def test_first_start_wins() -> None:
    t = _tracker()
    t.start(AUTO, Origin.AUTOMATION, "automation.a", 0.0)
    t.start(AUTO, Origin.SCRIPT, "script.s", 0.1)
    assert t.open_runs[0].origin is Origin.AUTOMATION


def test_context_change_on_untargeted_entity_is_ignored() -> None:
    t = _tracker()
    t.start(AUTO, Origin.AUTOMATION, None, 0.0)
    t.on_call(AUTO, _call("light.x", 0.1))
    t.on_state(AUTO, _change("script.s", 0.2))
    assert t.open_runs[0].changes == []


def test_late_device_report_matches_by_window() -> None:
    t = _tracker()
    t.start(AUTO, Origin.AUTOMATION, None, 0.0)
    t.on_call(AUTO, _call("light.x", 1.0))
    t.on_state(Ctx("fresh"), _change("light.x", 3.9))
    t.on_state(Ctx("fresh2"), _change("light.x", 4.5))
    assert [(c.at, c.matched_by) for c in t.open_runs[0].changes] == [(3.9, "window")]


def test_window_match_prefers_newest_run() -> None:
    t = _tracker()
    older, newer = Ctx("r1", "t1"), Ctx("r2", "t2")
    t.start(older, Origin.AUTOMATION, None, 0.0)
    t.on_call(older, _call("light.x", 0.0))
    t.start(newer, Origin.AUTOMATION, None, 1.0)
    t.on_call(newer, _call("light.x", 1.0))
    t.on_state(Ctx("fresh"), _change("light.x", 2.0))
    assert [len(r.changes) for r in t.open_runs] == [0, 1]


def test_changes_with_a_cause_are_foreign_not_window_matches() -> None:
    t = _tracker()
    t.start(AUTO, Origin.AUTOMATION, None, 0.0)
    t.on_call(AUTO, _call("light.x", 0.0))
    t.on_state(Ctx("other", parent_id="p"), _change("light.x", 1.0))
    t.on_state(Ctx("ui", user_id="u"), _change("light.x", 1.5))
    t.on_state(Ctx("fresh"), _change("light.y", 1.0))
    [run] = t.open_runs
    assert [(c.at, c.matched_by) for c in run.changes] == [(1.0, "foreign"), (1.5, "foreign")]
    # A foreign change does not keep the run open.
    assert run.last_activity == 0.0


def test_change_by_one_run_is_foreign_to_another_run_on_the_same_entity() -> None:
    t = _tracker()
    other = Ctx("run2", parent_id="trigger2")
    t.start(AUTO, Origin.AUTOMATION, None, 0.0)
    t.on_call(AUTO, _call("light.x", 0.0))
    t.start(other, Origin.AUTOMATION, None, 1.0)
    t.on_call(other, _call("light.x", 1.0))
    t.on_state(other, _change("light.x", 1.1))
    first, second = t.open_runs
    assert [c.matched_by for c in first.changes] == ["foreign"]
    assert [c.matched_by for c in second.changes] == ["context"]


def test_own_change_on_untargeted_entity_is_not_foreign_elsewhere() -> None:
    t = _tracker()
    other = Ctx("run2", parent_id="trigger2")
    t.start(AUTO, Origin.AUTOMATION, None, 0.0)
    t.on_call(AUTO, _call("light.x", 0.0))
    t.start(other, Origin.AUTOMATION, None, 0.0)
    t.on_state(other, _change("light.y", 0.5))
    assert [r.changes for r in t.open_runs] == [[], []]


def test_state_change_with_no_open_runs_is_ignored() -> None:
    t = _tracker()
    t.on_state(Ctx("fresh"), _change("light.x", 1.0))
    assert t.open_runs == []


def test_root_scene_call_starts_a_scene_run() -> None:
    t = _tracker()
    root = Ctx("root")
    t.on_call(root, _call("scene.s", 0.0, "scene", "turn_on"))
    t.on_call(root, _call("light.x", 0.0))
    [run] = t.open_runs
    assert (run.origin, len(run.calls)) == (Origin.SCENE, 2)


def test_other_root_and_child_calls_do_not_start_runs() -> None:
    t = _tracker()
    t.on_call(Ctx("root"), _call("light.x", 0.0))
    t.on_call(Ctx("child", parent_id="p"), _call("scene.s", 0.0, "scene", "turn_on"))
    assert t.open_runs == []


def test_ui_runs_need_track_user() -> None:
    ui = Ctx("ui", user_id="u1")
    off = _tracker()
    off.on_call(ui, _call("light.x", 0.0))
    off.start(ui, Origin.SCRIPT, "script.s", 0.0)
    assert off.open_runs == []

    on = _tracker(track_user=True)
    on.on_call(ui, _call("light.x", 0.0))
    assert on.open_runs[0].origin is Origin.USER


def test_close_expired_uses_longest_target_window() -> None:
    t = RunTracker(lambda e: 10.0 if e.startswith("cover.") else 3.0)
    t.start(AUTO, Origin.AUTOMATION, None, 0.0)
    t.on_call(AUTO, _call("light.x", 0.0))
    t.on_call(AUTO, _call("cover.y", 0.0))
    assert t.close_expired(5.0) == []
    [closed] = t.close_expired(10.5)
    assert closed.context_id == "run1"
    assert t.open_runs == []


def test_run_without_targets_closes_at_once() -> None:
    t = _tracker()
    t.start(AUTO, Origin.AUTOMATION, None, 0.0)
    assert len(t.close_expired(0.1)) == 1
