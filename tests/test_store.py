"""Delayed writes."""

from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.gaffer.const import DOMAIN, SAVE_DELAY
from custom_components.gaffer.store import GafferStore


async def test_scheduled_save_waits_for_delay(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    store = GafferStore(hass)
    await store.async_load()
    store.data["runs"].append({"id": "r1"})
    store.async_schedule_save()
    await hass.async_block_till_done()
    assert DOMAIN not in hass_storage

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=SAVE_DELAY + 1))
    await hass.async_block_till_done()
    assert hass_storage[DOMAIN]["data"]["runs"] == [{"id": "r1"}]
