"""Verdicts: one test per row of plan section 4.5, plus the traps around them."""

from typing import Any, Literal

import pytest

from custom_components.gaffer.logic.declared import DeclaredExpectation
from custom_components.gaffer.logic.models import (
    STATE,
    ActionResult,
    Check,
    Comparator,
    Expectation,
    Origin,
    RunRecord,
    ServiceCall,
    Snapshot,
    StateChange,
    Verdict,
)
from custom_components.gaffer.logic.verdict import judge, met, worst

L, M = "light.x", "media_player.m"
WINDOWS = {"light": 3.0, "media_player": 10.0}


def _window(entity_id: str) -> float:
    return WINDOWS.get(entity_id.partition(".")[0], 5.0)


class Run:
    """Build a run record step by step."""

    def __init__(self) -> None:
        self.record = RunRecord("c", Origin.AUTOMATION, "automation.a", 0.0)

    def call(
        self,
        service: str,
        at: float,
        prior: Snapshot | None,
        entity: str = L,
        **data: Any,
    ) -> Run:
        domain = entity.partition(".")[0]
        snaps = {} if prior is None else {entity: prior}
        self.record.calls.append(ServiceCall(domain, service, data, (entity,), at, snaps))
        return self

    def change(
        self,
        at: float,
        state: str | None,
        entity: str = L,
        how: Literal["context", "window", "foreign"] = "context",
        **attributes: Any,
    ) -> Run:
        self.record.changes.append(StateChange(entity, state, attributes, at, how))
        return self

    def results(self, *declared: DeclaredExpectation) -> list[ActionResult]:
        return judge(self.record, _window, declared)

    def verdicts(self) -> list[Verdict]:
        return [r.verdict for r in self.results()]


OFF, ON = Snapshot("off", {}), Snapshot("on", {})
IDLE = Snapshot("idle", {"volume_level": 0.5})


def test_confirmed_when_the_value_arrives_inside_the_window() -> None:
    [result] = Run().call("turn_on", 0.0, OFF).change(1.0, "on").results()
    assert (result.verdict, result.at_action, result.at_run) == (
        Verdict.CONFIRMED,
        {STATE: "on"},
        {STATE: "on"},
    )


def test_already_on_light_is_confirmed_without_a_state_change() -> None:
    assert Run().call("turn_on", 0.0, ON).verdicts() == [Verdict.CONFIRMED]


def test_late_device_report_matched_by_window_is_judged() -> None:
    run = Run().call("turn_on", 0.0, OFF).change(2.5, "on", how="window")
    assert run.verdicts() == [Verdict.CONFIRMED]


def test_no_effect_when_the_value_never_arrives() -> None:
    [result] = Run().call("turn_on", 0.0, OFF).results()
    assert (result.verdict, result.failed) == (Verdict.NO_EFFECT, (STATE,))


def test_value_after_the_run_check_does_not_count() -> None:
    run = Run().call("turn_on", 0.0, OFF).change(3.5, "on", how="window")
    assert run.verdicts() == [Verdict.NO_EFFECT]


def test_reverted_when_the_value_arrives_and_then_changes() -> None:
    run = Run().call("turn_on", 0.0, OFF).change(1.0, "on").change(2.0, "off", how="window")
    [result] = run.results()
    assert (result.verdict, result.failed, result.at_run) == (
        Verdict.REVERTED,
        (STATE,),
        {STATE: "off"},
    )


def test_partial_when_state_is_right_and_an_attribute_is_wrong() -> None:
    run = Run().call("turn_on", 0.0, OFF, brightness=128).change(1.0, "on", brightness=110)
    [result] = run.results()
    assert (result.verdict, result.failed, result.at_run) == (
        Verdict.PARTIAL,
        ("brightness",),
        {STATE: "on", "brightness": 110},
    )


@pytest.mark.parametrize(("seen", "verdict"), [(131, Verdict.CONFIRMED), (132, Verdict.PARTIAL)])
def test_brightness_tolerance_edge(seen: int, verdict: Verdict) -> None:
    run = Run().call("turn_on", 0.0, OFF, brightness=128).change(1.0, "on", brightness=seen)
    assert run.verdicts() == [verdict]


@pytest.mark.parametrize("prior", [Snapshot("unavailable", {}), Snapshot("unknown", {}), None])
def test_target_unavailable_when_the_call_ran(prior: Snapshot | None) -> None:
    [result] = Run().call("turn_on", 0.0, prior).change(1.0, "on").results()
    assert result.verdict is Verdict.TARGET_UNAVAILABLE
    assert result.at_action == {STATE: None if prior is None else prior.state}


def test_entity_removed_before_the_call_is_target_unavailable() -> None:
    run = Run().call("turn_on", 0.0, Snapshot(None, {}))
    assert run.verdicts() == [Verdict.TARGET_UNAVAILABLE]


def test_toggle_on_an_unavailable_entity_is_target_unavailable() -> None:
    run = Run().call("toggle", 0.0, Snapshot("unavailable", {}))
    assert run.verdicts() == [Verdict.TARGET_UNAVAILABLE]


def test_unchecked_service_and_call_without_target() -> None:
    run = Run().call("start", 0.0, Snapshot("docked", {}), entity="vacuum.v")
    run.record.calls.append(ServiceCall("notify", "notify", {}, (), 0.5))
    assert run.verdicts() == [Verdict.UNCHECKED, Verdict.UNCHECKED]


def test_superseded_by_a_later_call_on_the_same_key() -> None:
    run = Run().call("turn_on", 0.0, OFF).change(0.1, "on").call("turn_off", 1.0, ON)
    run.change(1.1, "off")
    assert run.verdicts() == [Verdict.SUPERSEDED, Verdict.CONFIRMED]


def test_superseded_by_a_foreign_change_before_the_run_check() -> None:
    run = Run().call("turn_on", 0.0, OFF).change(0.5, "on").change(2.0, "off", how="foreign")
    assert run.verdicts() == [Verdict.SUPERSEDED]


def test_foreign_change_after_the_run_check_is_ignored() -> None:
    run = Run().call("turn_on", 0.0, OFF).change(0.5, "on").change(9.0, "off", how="foreign")
    assert run.verdicts() == [Verdict.CONFIRMED]


def test_volume_reset_by_play_is_reverted_not_superseded() -> None:
    """The original trap: volume_set, then play; the player resets the volume."""
    run = Run().call("volume_set", 0.0, IDLE, entity=M, volume_level=0.3)
    run.change(0.2, "idle", entity=M, volume_level=0.3)
    run.call("media_play", 0.5, Snapshot("idle", {"volume_level": 0.3}), entity=M)
    run.change(4.0, "playing", entity=M, how="window", volume_level=0.5)
    [volume, play] = run.results()
    assert (volume.verdict, volume.failed) == (Verdict.REVERTED, ("volume_level",))
    assert (volume.at_action, volume.at_run) == ({"volume_level": 0.5}, {"volume_level": 0.5})
    assert play.verdict is Verdict.CONFIRMED


def test_volume_never_applied_is_no_effect() -> None:
    run = Run().call("volume_set", 0.0, IDLE, entity=M, volume_level=0.3)
    run.call("media_play", 0.5, IDLE, entity=M).change(1.0, "playing", entity=M, volume_level=0.5)
    assert run.verdicts() == [Verdict.NO_EFFECT, Verdict.CONFIRMED]


def test_late_when_the_value_arrives_after_the_action_check() -> None:
    run = Run().call("volume_set", 0.0, IDLE, entity=M, volume_level=0.3)
    run.call("media_play", 2.0, IDLE, entity=M).change(3.0, "playing", entity=M)
    run.change(11.0, "playing", entity=M, how="window", volume_level=0.3)
    assert run.verdicts() == [Verdict.LATE, Verdict.CONFIRMED]


def test_changes_before_the_call_are_not_in_its_timeline() -> None:
    run = Run().call("turn_off", 0.0, ON).change(0.1, "off").call("turn_on", 1.0, OFF)
    # The second call's timeline starts at its own prior, not at the earlier "off".
    run.change(1.2, "on")
    assert run.verdicts() == [Verdict.SUPERSEDED, Verdict.CONFIRMED]


def test_rgb_list_from_storage_matches_tuple() -> None:
    run = Run().call("turn_on", 0.0, OFF, rgb_color=[255, 0, 0])
    run.change(1.0, "on", rgb_color=[255, 0, 0])
    assert run.verdicts() == [Verdict.CONFIRMED]


def test_cover_accepts_a_moving_state() -> None:
    run = Run().call("open_cover", 0.0, Snapshot("closed", {}), entity="cover.c")
    run.change(1.0, "opening", entity="cover.c")
    assert run.verdicts() == [Verdict.CONFIRMED]


def test_declared_expectation_overrides_inference() -> None:
    declared = DeclaredExpectation(L, (Check("brightness", Comparator.APPROX, 50.0, 5.0),))
    run = Run().call("turn_on", 0.0, OFF).change(1.0, "on", brightness=200)
    [result] = run.results(declared)
    assert (result.verdict, result.failed) == (Verdict.PARTIAL, ("brightness",))


@pytest.mark.parametrize(
    ("check", "snap", "expected"),
    [
        (Check(STATE, Comparator.NOT_IN, ("off",)), Snapshot("on", {}), True),
        (Check(STATE, Comparator.NOT_IN, ("off",)), Snapshot("off", {}), False),
        (Check(STATE, Comparator.IN, ("a", "b")), Snapshot("b", {}), True),
        (Check("v", Comparator.APPROX, 0.5, 0.02), Snapshot("on", {"v": 0.52}), True),
        (Check("v", Comparator.APPROX, 0.5, 0.02), Snapshot("on", {"v": 0.53}), False),
        (Check("v", Comparator.APPROX, 1.0, 0.0), Snapshot("on", {"v": None}), False),
        (Check("v", Comparator.APPROX, 1.0, 0.0), Snapshot("on", {"v": True}), False),
        (Check("v", Comparator.EQ, 1), Snapshot("on", {}), False),
    ],
)
def test_comparators(check: Check, snap: Snapshot, expected: bool) -> None:
    assert met(check, snap) is expected


def _result(verdict: Verdict) -> ActionResult:
    return ActionResult(Expectation(L, 0, (), 3.0), verdict)


def test_worst_follows_the_rank() -> None:
    results = [_result(v) for v in (Verdict.CONFIRMED, Verdict.LATE, Verdict.PARTIAL)]
    assert worst(results) is Verdict.PARTIAL
    unavailable = [_result(Verdict.NO_EFFECT), _result(Verdict.TARGET_UNAVAILABLE)]
    assert worst(unavailable) is Verdict.TARGET_UNAVAILABLE
    assert worst([_result(Verdict.UNCHECKED), _result(Verdict.SUPERSEDED)]) is Verdict.SUPERSEDED
    assert worst([]) is None


def test_result_to_dict() -> None:
    run = (
        Run().call("turn_on", 0.0, OFF, rgb_color=[1, 2, 3]).change(1.0, "on", rgb_color=[1, 2, 3])
    )
    [result] = run.results()
    assert result.to_dict() == {
        "entity_id": L,
        "call_index": 0,
        "window": 3.0,
        "checks": [
            {"key": "state", "comparator": "eq", "value": "on", "tolerance": 0.0},
            {"key": "rgb_color", "comparator": "eq", "value": [1, 2, 3], "tolerance": 0.0},
        ],
        "verdict": "confirmed",
        "at_action": {"state": "on", "rgb_color": (1, 2, 3)},
        "at_run": {"state": "on", "rgb_color": (1, 2, 3)},
        "failed": [],
    }
