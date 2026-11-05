"""Gaffer: check that automations have the expected result."""

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .store import GafferStore


@dataclass(slots=True)
class RuntimeData:
    """Objects that live for as long as the config entry is loaded."""

    store: GafferStore


type GafferConfigEntry = ConfigEntry[RuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: GafferConfigEntry) -> bool:
    """Load stored data. Nothing is watched yet."""
    store = GafferStore(hass)
    await store.async_load()
    entry.runtime_data = RuntimeData(store)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: GafferConfigEntry) -> bool:
    """Write pending data before the entry goes away."""
    await entry.runtime_data.store.async_save_now()
    return True


async def async_remove_entry(hass: HomeAssistant, entry: GafferConfigEntry) -> None:
    """Delete stored data when the user removes the integration."""
    await GafferStore(hass).async_remove()
