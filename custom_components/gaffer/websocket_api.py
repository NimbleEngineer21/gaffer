"""Admin-only WebSocket commands that read stored runs."""

from typing import Any

import probatio as vol
from homeassistant.components.websocket_api import async_register_command
from homeassistant.components.websocket_api.connection import ActiveConnection
from homeassistant.components.websocket_api.const import ERR_NOT_FOUND
from homeassistant.components.websocket_api.decorators import require_admin, websocket_command
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN
from .logic.outputs import select, summary
from .store import GafferStore

MAX_LIMIT = 500


@callback
def async_register(hass: HomeAssistant) -> None:
    """Register the commands. Home Assistant keeps them for the whole session."""
    async_register_command(hass, ws_runs)
    async_register_command(hass, ws_run)


def _store(hass: HomeAssistant) -> GafferStore | None:
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    return entries[0].runtime_data.store if entries else None


def _not_loaded(connection: ActiveConnection, msg: dict[str, Any]) -> None:
    connection.send_error(msg["id"], "not_loaded", "Gaffer is not loaded")


@websocket_command(
    {
        vol.Required("type"): "gaffer/runs",
        vol.Optional("source"): str,
        vol.Optional("verdicts"): [vol.Any(str, None)],
        vol.Optional("since"): vol.Coerce(float),
        vol.Optional("failures_only", default=False): bool,
        vol.Optional("limit", default=50): vol.All(int, vol.Range(min=1, max=MAX_LIMIT)),
    }
)
@require_admin
@callback
def ws_runs(hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]) -> None:
    """Return run summaries, newest first."""
    store = _store(hass)
    if store is None:
        _not_loaded(connection, msg)
        return
    runs = select(
        store.data["runs"],
        source=msg.get("source"),
        verdicts=msg.get("verdicts"),
        since=msg.get("since"),
        failures_only=msg["failures_only"],
        limit=msg["limit"],
    )
    connection.send_result(msg["id"], {"runs": [summary(run) for run in runs]})


@websocket_command({vol.Required("type"): "gaffer/run", vol.Required("context_id"): str})
@require_admin
@callback
def ws_run(hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]) -> None:
    """Return one full stored run."""
    store = _store(hass)
    if store is None:
        _not_loaded(connection, msg)
        return
    run = next((r for r in store.data["runs"] if r["context_id"] == msg["context_id"]), None)
    if run is None:
        connection.send_error(msg["id"], ERR_NOT_FOUND, "No stored run")
        return
    connection.send_result(msg["id"], run)
