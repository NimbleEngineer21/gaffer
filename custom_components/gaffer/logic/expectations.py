"""Infer what a service call should do to each entity it targets (plan section 4.4)."""

from collections.abc import Callable, Mapping
from typing import Any

from .models import STATE, Check, Comparator, Expectation, RunRecord, ServiceCall

WindowFor = Callable[[str], float]
Rule = Callable[[ServiceCall, str], tuple[Check, ...]]

UNAVAILABLE = ("unavailable", "unknown")

# Calls that only start other calls. Home Assistant fires the inner per-entity
# calls in the same context, so those carry the expectations.
_CONTAINERS = {
    ("scene", "turn_on"),
    ("scene", "apply"),
    ("automation", "trigger"),
    ("homeassistant", "turn_on"),
    ("homeassistant", "turn_off"),
    ("homeassistant", "toggle"),
}
_CONTAINER_DOMAINS = {"script"}

BRIGHTNESS_TOLERANCE = 3.0
KELVIN_TOLERANCE = 50.0
VOLUME_TOLERANCE = 0.02
TEMPERATURE_TOLERANCE = 0.5


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _state(value: str) -> Check:
    return Check(STATE, Comparator.EQ, value)


def _approx(key: str, value: Any, tolerance: float) -> list[Check]:
    number = _number(value)
    return [] if number is None else [Check(key, Comparator.APPROX, number, tolerance)]


def _fixed(*checks: Check) -> Rule:
    return lambda call, entity_id: checks


def _light_on(call: ServiceCall, entity_id: str) -> tuple[Check, ...]:
    data = call.data
    brightness = _number(data.get("brightness"))
    pct = _number(data.get("brightness_pct"))
    if brightness is None and pct is not None:
        brightness = float(round(pct * 255 / 100))
    if brightness == 0:
        return (_state("off"),)
    checks = [_state("on")]
    checks += _approx("brightness", brightness, BRIGHTNESS_TOLERANCE)
    checks += _approx("color_temp_kelvin", data.get("color_temp_kelvin"), KELVIN_TOLERANCE)
    rgb = data.get("rgb_color")
    if isinstance(rgb, list | tuple):
        checks.append(Check("rgb_color", Comparator.EQ, tuple(rgb)))
    return tuple(checks)


def _toggle(call: ServiceCall, entity_id: str) -> tuple[Check, ...]:
    prior = call.prior.get(entity_id)
    state = None if prior is None else prior.state
    if state == "on":
        return (_state("off"),)
    if state == "off":
        return (_state("on"),)
    if state is None or state in UNAVAILABLE:
        # The verdict is target_unavailable; this check only records the need.
        return (Check(STATE, Comparator.NOT_IN, UNAVAILABLE),)
    return ()


def _volume(call: ServiceCall, entity_id: str) -> tuple[Check, ...]:
    return tuple(_approx("volume_level", call.data.get("volume_level"), VOLUME_TOLERANCE))


def _climate(call: ServiceCall, entity_id: str) -> tuple[Check, ...]:
    checks: list[Check] = []
    mode = call.data.get("hvac_mode")
    if isinstance(mode, str):
        checks.append(_state(mode))
    for key in ("temperature", "target_temp_low", "target_temp_high"):
        checks += _approx(key, call.data.get(key), TEMPERATURE_TOLERANCE)
    return tuple(checks)


def _on_off_rules() -> dict[tuple[str, str], Rule]:
    rules: dict[tuple[str, str], Rule] = {}
    for domain in ("light", "switch", "fan", "input_boolean"):
        rules[domain, "turn_on"] = _fixed(_state("on"))
        rules[domain, "turn_off"] = _fixed(_state("off"))
        rules[domain, "toggle"] = _toggle
    rules["light", "turn_on"] = _light_on
    return rules


RULES: Mapping[tuple[str, str], Rule] = {
    **_on_off_rules(),
    ("media_player", "volume_set"): _volume,
    ("media_player", "media_play"): _fixed(_state("playing")),
    ("media_player", "play_media"): _fixed(_state("playing")),
    ("media_player", "turn_on"): _fixed(Check(STATE, Comparator.NOT_IN, ("off",))),
    ("media_player", "turn_off"): _fixed(_state("off")),
    ("cover", "open_cover"): _fixed(Check(STATE, Comparator.IN, ("opening", "open"))),
    ("cover", "close_cover"): _fixed(Check(STATE, Comparator.IN, ("closing", "closed"))),
    ("climate", "set_temperature"): _climate,
    ("lock", "lock"): _fixed(_state("locked")),
    ("lock", "unlock"): _fixed(_state("unlocked")),
}


def is_container(call: ServiceCall) -> bool:
    """Return True for a call that only starts other calls, such as a scene or a script."""
    return call.domain in _CONTAINER_DOMAINS or (call.domain, call.service) in _CONTAINERS


def infer(call: ServiceCall, index: int, window_for: WindowFor) -> list[Expectation]:
    """Return one expectation per target. An expectation with no checks is unchecked."""
    if is_container(call):
        return []
    if not call.entity_ids:
        return [Expectation(None, index, (), 0.0)]
    rule = RULES.get((call.domain, call.service))
    return [
        Expectation(
            entity_id, index, () if rule is None else rule(call, entity_id), window_for(entity_id)
        )
        for entity_id in call.entity_ids
    ]


def infer_run(run: RunRecord, window_for: WindowFor) -> list[Expectation]:
    """Return the expectations for every call in a run, in call order."""
    return [exp for i, call in enumerate(run.calls) for exp in infer(call, i, window_for)]
