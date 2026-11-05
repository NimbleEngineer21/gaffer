"""User-declared expectations: validation and the merge over inferred ones."""

from typing import Any

import pytest

from custom_components.gaffer.logic.declared import DeclaredExpectation, merge, parse
from custom_components.gaffer.logic.models import STATE, Check, Comparator, Expectation


def test_parse_full_declaration() -> None:
    raw = {
        "entity_id": "media_player.den",
        "checks": [
            {"key": "volume_level", "comparator": "approx", "value": 0.3, "tolerance": 0.05},
            {"key": "state", "comparator": "in", "value": ["playing", "buffering"]},
            {"key": "rgb_color", "value": [1, 2, 3]},
        ],
        "window": 15,
    }
    assert parse(raw) == DeclaredExpectation(
        "media_player.den",
        (
            Check("volume_level", Comparator.APPROX, 0.3, 0.05),
            Check(STATE, Comparator.IN, ("playing", "buffering")),
            Check("rgb_color", Comparator.EQ, (1, 2, 3)),
        ),
        15.0,
    )


def test_parse_defaults() -> None:
    parsed = parse({"entity_id": "light.a", "checks": [{"key": "state", "value": "on"}]})
    assert parsed == DeclaredExpectation("light.a", (Check(STATE, Comparator.EQ, "on"),), None)


def _check(**over: Any) -> dict[str, Any]:
    return {"entity_id": "light.a", "checks": [{"key": "state", "value": "on", **over}]}


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("light.a", "must be a mapping"),
        ({"entity_id": "kitchen", "checks": []}, "entity_id"),
        ({"entity_id": 3, "checks": []}, "entity_id"),
        ({"entity_id": "light.a", "checks": []}, "non-empty list"),
        ({"entity_id": "light.a"}, "non-empty list"),
        ({"entity_id": "light.a", "checks": ["x"]}, "each check"),
        ({"entity_id": "light.a", "checks": [{"value": 1}]}, "check key"),
        ({"entity_id": "light.a", "checks": [{"key": "", "value": 1}]}, "check key"),
        ({"entity_id": "light.a", "checks": [{"key": "state"}]}, "has no value"),
        (_check(comparator="gt"), "unknown comparator 'gt'"),
        (_check(comparator="in"), "non-empty list for in"),
        (_check(comparator="not_in", value=[]), "non-empty list for not_in"),
        (_check(comparator="approx"), "value must be a number"),
        (_check(tolerance="1"), "tolerance must be a number"),
        (_check(tolerance=True), "tolerance must be a number"),
        (_check(tolerance=-1), "tolerance must be zero or more"),
        ({**_check(), "window": 0}, "window must be more than zero"),
        ({**_check(), "window": -2}, "window must be more than zero"),
    ],
)
def test_parse_rejects_bad_shapes(raw: Any, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse(raw)


ON = Check(STATE, Comparator.EQ, "on")
OFF = Check(STATE, Comparator.EQ, "off")
B128 = Check("brightness", Comparator.APPROX, 128.0, 3.0)


def test_declared_check_replaces_same_key_and_adds_new_key() -> None:
    inferred = [Expectation("light.a", 0, (ON, B128), 3.0)]
    b200 = Check("brightness", Comparator.APPROX, 200.0, 10.0)
    temp = Check("color_temp_kelvin", Comparator.APPROX, 2700.0, 100.0)
    [exp] = merge(inferred, [DeclaredExpectation("light.a", (b200, temp), 8.0)])
    assert exp == Expectation("light.a", 0, (ON, b200, temp), 8.0)


def test_declared_applies_to_the_last_call_on_the_entity_only() -> None:
    inferred = [
        Expectation("light.a", 0, (ON,), 3.0),
        Expectation("light.b", 1, (ON,), 3.0),
        Expectation("light.a", 2, (OFF,), 3.0),
    ]
    merged = merge(inferred, [DeclaredExpectation("light.a", (ON,))])
    assert merged == [inferred[0], inferred[1], Expectation("light.a", 2, (ON,), 3.0)]


def test_declared_turns_an_unchecked_call_into_a_checked_one() -> None:
    inferred = [Expectation("vacuum.a", 0, (), 5.0)]
    docked = Check(STATE, Comparator.EQ, "cleaning")
    assert merge(inferred, [DeclaredExpectation("vacuum.a", (docked,))]) == [
        Expectation("vacuum.a", 0, (docked,), 5.0)
    ]


def test_declared_for_an_untargeted_entity_is_ignored() -> None:
    inferred = [Expectation("light.a", 0, (ON,), 3.0)]
    assert merge(inferred, [DeclaredExpectation("light.z", (OFF,))]) == inferred
