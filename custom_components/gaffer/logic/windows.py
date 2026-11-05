"""Settle windows: how long a device may take to show the result of a command."""

DEFAULT = 5.0
BY_DOMAIN = {
    "light": 3.0,
    "switch": 3.0,
    "media_player": 10.0,
    "climate": 30.0,
    "cover": 60.0,
}


def settle_window(entity_id: str) -> float:
    """Return the settle window in seconds for an entity, from its domain."""
    return BY_DOMAIN.get(entity_id.partition(".")[0], DEFAULT)
