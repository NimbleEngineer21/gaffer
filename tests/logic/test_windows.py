"""Settle windows by domain."""

from custom_components.gaffer.logic.windows import DEFAULT, settle_window


def test_known_domains_and_default() -> None:
    assert settle_window("light.kitchen") == 3.0
    assert settle_window("media_player.den") == 10.0
    assert settle_window("cover.garage") == 60.0
    assert settle_window("sensor.motion") == DEFAULT
