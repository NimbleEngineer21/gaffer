"""Shared fixtures for tests that run a real Home Assistant core."""

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.gaffer.const import DOMAIN

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def custom_integration(enable_custom_integrations: None) -> None:
    """Let Home Assistant load the integration from this checkout."""


@pytest.fixture
async def loaded_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Return a Gaffer config entry that has finished setup."""
    entry = MockConfigEntry(domain=DOMAIN, title="Gaffer", data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry
