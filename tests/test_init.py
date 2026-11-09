"""Config entry lifecycle."""

from typing import Any
from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.gaffer.const import DOMAIN
from tests.runs import stored_run


async def test_setup_loads_empty_store(hass: HomeAssistant, loaded_entry: MockConfigEntry) -> None:
    assert loaded_entry.state is ConfigEntryState.LOADED
    assert loaded_entry.runtime_data.store.data == {"runs": [], "expectations": {}}


async def test_setup_reads_existing_store(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    saved = {"runs": [stored_run()], "expectations": {"a1": []}}
    hass_storage[DOMAIN] = {"version": 1, "minor_version": 1, "key": DOMAIN, "data": saved}
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    assert entry.runtime_data.store.data == saved


async def test_unload_writes_pending_data(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, hass_storage: dict[str, Any]
) -> None:
    loaded_entry.runtime_data.store.data["runs"].append(stored_run())

    assert await hass.config_entries.async_unload(loaded_entry.entry_id)
    assert loaded_entry.state is ConfigEntryState.NOT_LOADED
    assert hass_storage[DOMAIN]["data"]["runs"] == [stored_run()]


async def test_remove_deletes_stored_data(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, hass_storage: dict[str, Any]
) -> None:
    await loaded_entry.runtime_data.store.async_save_now()
    assert DOMAIN in hass_storage

    assert await hass.config_entries.async_remove(loaded_entry.entry_id)
    await hass.async_block_till_done()
    assert DOMAIN not in hass_storage


async def test_unload_stops_when_a_platform_fails_to_unload(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    with patch.object(hass.config_entries, "async_unload_platforms", return_value=False):
        assert not await hass.config_entries.async_unload(loaded_entry.entry_id)
    # Core marks the entry FAILED_UNLOAD; stop the timers so none linger.
    loaded_entry.runtime_data.collector.async_stop()
    loaded_entry.runtime_data.outputs.async_stop()


async def test_remove_deletes_gaffer_issues_only(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    for domain, issue_id in ((DOMAIN, "runtime_automation.a"), ("other", "x")):
        ir.async_create_issue(
            hass,
            domain,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="x",
        )
    assert await hass.config_entries.async_remove(loaded_entry.entry_id)
    await hass.async_block_till_done()
    registry = ir.async_get(hass)
    assert registry.async_get_issue(DOMAIN, "runtime_automation.a") is None
    assert registry.async_get_issue("other", "x") is not None
