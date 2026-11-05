"""Config entry lifecycle."""

from typing import Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.gaffer.const import DOMAIN


async def test_setup_loads_empty_store(hass: HomeAssistant, loaded_entry: MockConfigEntry) -> None:
    assert loaded_entry.state is ConfigEntryState.LOADED
    assert loaded_entry.runtime_data.store.data == {"runs": [], "expectations": {}}


async def test_setup_reads_existing_store(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    saved = {"runs": [{"id": "r1"}], "expectations": {"a1": []}}
    hass_storage[DOMAIN] = {"version": 1, "minor_version": 1, "key": DOMAIN, "data": saved}
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    assert entry.runtime_data.store.data == saved


async def test_unload_writes_pending_data(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, hass_storage: dict[str, Any]
) -> None:
    loaded_entry.runtime_data.store.data["runs"].append({"id": "r1"})

    assert await hass.config_entries.async_unload(loaded_entry.entry_id)
    assert loaded_entry.state is ConfigEntryState.NOT_LOADED
    assert hass_storage[DOMAIN]["data"]["runs"] == [{"id": "r1"}]


async def test_remove_deletes_stored_data(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, hass_storage: dict[str, Any]
) -> None:
    await loaded_entry.runtime_data.store.async_save_now()
    assert DOMAIN in hass_storage

    assert await hass.config_entries.async_remove(loaded_entry.entry_id)
    await hass.async_block_till_done()
    assert DOMAIN not in hass_storage
