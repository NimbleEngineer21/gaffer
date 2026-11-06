"""Settle windows: how long a device may take to show the result of a command."""

from collections.abc import Callable

from .models import ServiceCall

DEFAULT = 5.0
BY_DOMAIN = {
    "light": 3.0,
    "switch": 3.0,
    "media_player": 10.0,
    "climate": 30.0,
    "cover": 60.0,
}

WindowFor = Callable[[str], float]


def settle_window(entity_id: str) -> float:
    """Return the settle window in seconds for an entity, from its domain."""
    return BY_DOMAIN.get(entity_id.partition(".")[0], DEFAULT)


def call_window(call: ServiceCall, entity_id: str, window_for: WindowFor) -> float:
    """Return the settle window for one target of one call.

    A call that asks for a transition (a light fade, also sent by a scene) ends
    that many seconds later, so the window starts when the transition ends.
    """
    value = call.data.get("transition")
    if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
        value = 0.0
    return window_for(entity_id) + float(value)
