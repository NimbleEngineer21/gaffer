"""Diagnostics download."""

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.gaffer.diagnostics import async_get_config_entry_diagnostics
from tests.runs import stored_run


async def test_diagnostics_counts_and_recent_runs(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    store = loaded_entry.runtime_data.store
    store.data["runs"] = [stored_run("no_effect", at=float(i)) for i in range(25)]
    store.data["expectations"] = {"t1": []}
    diag = await async_get_config_entry_diagnostics(hass, loaded_entry)
    assert diag["options"] == {}
    assert (diag["stored_runs"], diag["declared_expectations"], diag["open_runs"]) == (25, 1, 0)
    assert diag["verdicts"] == {"no_effect": 25}
    assert diag["origins"] == {"automation": 25}
    assert len(diag["recent"]) == 20
    assert diag["recent"][0]["started_at"] == 24.0
    assert diag["failures_24h"] == 0
