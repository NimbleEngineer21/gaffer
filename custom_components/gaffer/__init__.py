"""Gaffer: check that automations have the expected result."""

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .collector import Collector
from .store import GafferStore


@dataclass(slots=True)
class RuntimeData:
    """Objects that live for as long as the config entry is loaded."""

    store: GafferStore
    collector: Collector


type GafferConfigEntry = ConfigEntry[RuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: GafferConfigEntry) -> bool:
    """Load stored data and start collecting runs."""
    store = GafferStore(hass)
    await store.async_load()
    collector = Collector(hass, store)
    collector.async_start()
    entry.runtime_data = RuntimeData(store, collector)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: GafferConfigEntry) -> bool:
    """Stop collecting, then write pending data."""
    entry.runtime_data.collector.async_stop()
    await entry.runtime_data.store.async_save_now()
    return True


async def async_remove_entry(hass: HomeAssistant, entry: GafferConfigEntry) -> None:
    """Delete stored data when the user removes the integration."""
    await GafferStore(hass).async_remove()
