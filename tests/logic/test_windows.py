"""Settle windows by domain."""

from typing import Any

import pytest

from custom_components.gaffer.logic.models import ServiceCall
from custom_components.gaffer.logic.windows import DEFAULT, call_window, settle_window


def test_known_domains_and_default() -> None:
    assert settle_window("light.kitchen") == 3.0
    assert settle_window("media_player.den") == 10.0
    assert settle_window("cover.garage") == 60.0
    assert settle_window("sensor.motion") == DEFAULT


@pytest.mark.parametrize(
    ("data", "window"),
    [
        ({}, 3.0),
        ({"transition": 10}, 13.0),
        ({"transition": 0.5}, 3.5),
        ({"transition": True}, 3.0),
        ({"transition": -4}, 3.0),
        ({"transition": "10"}, 3.0),
    ],
)
def test_call_window_adds_a_valid_transition(data: dict[str, Any], window: float) -> None:
    call = ServiceCall("light", "turn_on", data, ("light.a",), 0.0)
    assert call_window(call, "light.a", settle_window) == window
