"""Gaffer: check that automations have the expected result."""

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from . import websocket_api
from .collector import Collector
from .const import DOMAIN
from .outputs import Outputs, remove_issues
from .store import GafferStore

PLATFORMS = [Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass(slots=True)
class RuntimeData:
    """Objects that live for as long as the config entry is loaded."""

    store: GafferStore
    collector: Collector
    outputs: Outputs


type GafferConfigEntry = ConfigEntry[RuntimeData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the WebSocket commands once per Home Assistant session."""
    websocket_api.async_register(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: GafferConfigEntry) -> bool:
    """Load stored data, rebuild the outputs, and start collecting runs."""
    store = GafferStore(hass)
    await store.async_load()
    outputs = Outputs(hass, store)
    collector = Collector(hass, store, outputs.on_stored)
    entry.runtime_data = RuntimeData(store, collector, outputs)
    outputs.async_start()
    collector.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: GafferConfigEntry) -> bool:
    """Stop collecting, then write pending data."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    entry.runtime_data.collector.async_stop()
    entry.runtime_data.outputs.async_stop()
    await entry.runtime_data.store.async_save_now()
    return True


async def async_remove_entry(hass: HomeAssistant, entry: GafferConfigEntry) -> None:
    """Delete stored data and Gaffer's Repairs issues when the user removes the integration."""
    remove_issues(hass)
    await GafferStore(hass).async_remove()
