"""Inferred expectations: one test per row of plan section 4.4."""

from typing import Any

import pytest

from custom_components.gaffer.logic.expectations import infer, infer_run, own_targets
from custom_components.gaffer.logic.models import (
    STATE,
    Check,
    Comparator,
    Expectation,
    Origin,
    RunRecord,
    ServiceCall,
    Snapshot,
)


def _window(entity_id: str) -> float:
    return 3.0


def _call(
    domain: str, service: str, data: dict[str, Any] | None = None, prior: str | None = "off"
) -> ServiceCall:
    entity = f"{domain}.x"
    snaps = {} if prior is None else {entity: Snapshot(prior, {})}
    return ServiceCall(domain, service, data or {}, (entity,), 0.0, snaps)


def _checks(call: ServiceCall) -> tuple[Check, ...]:
    [exp] = infer(call, 0, _window)
    return exp.checks


def _eq(value: str) -> Check:
    return Check(STATE, Comparator.EQ, value)


@pytest.mark.parametrize(
    ("domain", "service", "state"),
    [
        ("light", "turn_off", "off"),
        ("switch", "turn_on", "on"),
        ("switch", "turn_off", "off"),
        ("fan", "turn_on", "on"),
        ("fan", "turn_off", "off"),
        ("input_boolean", "turn_on", "on"),
        ("input_boolean", "turn_off", "off"),
        ("media_player", "media_play", "playing"),
        ("media_player", "play_media", "playing"),
        ("media_player", "turn_off", "off"),
        ("lock", "lock", "locked"),
        ("lock", "unlock", "unlocked"),
    ],
)
def test_state_only_services(domain: str, service: str, state: str) -> None:
    assert _checks(_call(domain, service)) == (_eq(state),)


def test_light_turn_on_without_data_expects_on() -> None:
    assert _checks(_call("light", "turn_on")) == (_eq("on"),)


def test_light_turn_on_with_brightness_color_temp_and_rgb() -> None:
    data = {"brightness": 128, "color_temp_kelvin": 2700, "rgb_color": [255, 0, 0]}
    assert _checks(_call("light", "turn_on", data)) == (
        _eq("on"),
        Check("brightness", Comparator.APPROX, 128.0, 3.0),
        Check("color_temp_kelvin", Comparator.APPROX, 2700.0, 50.0),
        Check("rgb_color", Comparator.EQ, (255, 0, 0)),
    )


def test_light_brightness_pct_converts_to_brightness() -> None:
    checks = _checks(_call("light", "turn_on", {"brightness_pct": 50}))
    assert checks[1] == Check("brightness", Comparator.APPROX, 128.0, 3.0)


@pytest.mark.parametrize("data", [{"brightness": 0}, {"brightness_pct": 0}])
def test_light_brightness_zero_expects_off(data: dict[str, Any]) -> None:
    assert _checks(_call("light", "turn_on", data)) == (_eq("off"),)


@pytest.mark.parametrize(
    "data",
    [
        {"brightness_step": 10, "hs_color": [1, 2], "effect": "x"},
        {"brightness": "{{ 3 }}", "rgb_color": "red"},
        {"brightness": True},
    ],
)
def test_light_data_without_a_fixed_value_expects_on_only(data: dict[str, Any]) -> None:
    assert _checks(_call("light", "turn_on", data)) == (_eq("on"),)


def test_volume_set_expects_volume_level_only() -> None:
    assert _checks(_call("media_player", "volume_set", {"volume_level": 0.4})) == (
        Check("volume_level", Comparator.APPROX, 0.4, 0.02),
    )


def test_volume_set_without_a_number_is_unchecked() -> None:
    assert _checks(_call("media_player", "volume_set", {})) == ()


def test_media_player_turn_on_expects_not_off() -> None:
    assert _checks(_call("media_player", "turn_on")) == (
        Check(STATE, Comparator.NOT_IN, ("off", "unavailable", "unknown")),
    )


@pytest.mark.parametrize(
    ("service", "states"),
    [("open_cover", ("opening", "open")), ("close_cover", ("closing", "closed"))],
)
def test_cover_accepts_moving_or_done(service: str, states: tuple[str, ...]) -> None:
    assert _checks(_call("cover", service)) == (Check(STATE, Comparator.IN, states),)


def test_climate_set_temperature_and_mode() -> None:
    data = {"temperature": 21, "target_temp_low": 19, "target_temp_high": 24, "hvac_mode": "heat"}
    assert _checks(_call("climate", "set_temperature", data)) == (
        _eq("heat"),
        Check("temperature", Comparator.APPROX, 21.0, 0.5),
        Check("target_temp_low", Comparator.APPROX, 19.0, 0.5),
        Check("target_temp_high", Comparator.APPROX, 24.0, 0.5),
    )


def test_climate_with_odd_mode_and_no_temperature_is_unchecked() -> None:
    assert _checks(_call("climate", "set_temperature", {"hvac_mode": 3})) == ()


@pytest.mark.parametrize(("prior", "state"), [("on", "off"), ("off", "on")])
@pytest.mark.parametrize("domain", ["light", "switch", "fan", "input_boolean"])
def test_toggle_expects_the_opposite_of_the_prior_state(
    domain: str, prior: str, state: str
) -> None:
    assert _checks(_call(domain, "toggle", prior=prior)) == (_eq(state),)


@pytest.mark.parametrize("prior", ["unavailable", "unknown", None])
def test_toggle_on_an_unavailable_entity_expects_it_available(prior: str | None) -> None:
    assert _checks(_call("light", "toggle", prior=prior)) == (
        Check(STATE, Comparator.NOT_IN, ("unavailable", "unknown")),
    )


def test_toggle_from_an_odd_state_is_unchecked() -> None:
    assert _checks(_call("fan", "toggle", prior="auto")) == ()


@pytest.mark.parametrize(
    ("domain", "service"),
    [
        ("scene", "turn_on"),
        ("scene", "apply"),
        ("script", "turn_on"),
        ("script", "morning"),
        ("automation", "trigger"),
        ("homeassistant", "turn_on"),
        ("homeassistant", "turn_off"),
        ("homeassistant", "toggle"),
    ],
)
def test_container_calls_have_no_row(domain: str, service: str) -> None:
    assert infer(_call(domain, service), 0, _window) == []


def test_unknown_service_is_unchecked_per_target() -> None:
    call = ServiceCall("vacuum", "start", {}, ("vacuum.a", "vacuum.b"), 0.0)
    assert infer(call, 2, _window) == [
        Expectation("vacuum.a", 2, (), 3.0),
        Expectation("vacuum.b", 2, (), 3.0),
    ]


def test_call_without_target_is_one_unchecked_row() -> None:
    call = ServiceCall("notify", "notify", {"message": "hi"}, (), 0.0)
    assert infer(call, 0, _window) == [Expectation(None, 0, (), 0.0)]


def test_window_comes_from_the_entity() -> None:
    call = ServiceCall("cover", "open_cover", {}, ("cover.a",), 0.0)
    [exp] = infer(call, 0, lambda e: 60.0)
    assert exp.window == 60.0


def test_infer_run_numbers_calls_in_order() -> None:
    run = RunRecord("c", Origin.AUTOMATION, None, 0.0)
    run.calls += [_call("scene", "turn_on"), _call("light", "turn_on"), _call("lock", "lock")]
    assert [(e.entity_id, e.call_index) for e in infer_run(run, _window)] == [
        ("light.x", 1),
        ("lock.x", 2),
    ]


def test_window_includes_the_transition() -> None:
    [exp] = infer(_call("light", "turn_on", {"transition": 10}), 0, _window)
    assert exp.window == 13.0


def test_own_targets_keeps_the_call_domain_only() -> None:
    area = ("light.a", "sensor.t", "switch.f")
    assert own_targets("light", area) == ("light.a",)
    assert own_targets("homeassistant", area) == area
