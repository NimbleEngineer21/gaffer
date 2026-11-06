"""sensor.gaffer_failures_24h: failed runs in the last 24 hours."""

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import GafferConfigEntry
from .const import DOMAIN, NAME, SIGNAL_UPDATED
from .outputs import Outputs


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GafferConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the one failures sensor."""
    async_add_entities([FailuresSensor(entry.entry_id, entry.runtime_data.outputs)])


class FailuresSensor(SensorEntity):
    """Count of failed runs in 24 h. The last 10 failures are its attributes."""

    _attr_has_entity_name = True
    _attr_translation_key = "failures_24h"
    _attr_should_poll = False
    # The list changes on each failure and can be large; keep it out of the recorder.
    _unrecorded_attributes = frozenset({"failures"})

    def __init__(self, entry_id: str, outputs: Outputs) -> None:
        """Read from the entry's outputs."""
        self._outputs = outputs
        self._attr_unique_id = f"{entry_id}_failures_24h"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=NAME,
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        """Update when the outputs change."""
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_UPDATED, self._on_update))

    @callback
    def _on_update(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> int:
        """Return the number of failed runs in the last 24 hours."""
        return self._outputs.failure_count

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the last 10 failures, newest first."""
        return {"failures": self._outputs.recent}
