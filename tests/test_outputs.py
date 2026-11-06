"""Outputs from a real Home Assistant core: event, sensor, and Repairs issues."""

from typing import Any

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_fire_time_changed,
)

from custom_components.gaffer.const import DOMAIN, EVENT_RESULT
from tests.runs import stored_run

SENSOR = "sensor.gaffer_failures_24h"
STUCK = "light.stuck"
ISSUE = "runtime_automation.t1"


@pytest.fixture(autouse=True)
async def automation(hass: HomeAssistant) -> None:
    """An automation that turns on a light state with no entity behind it."""
    assert await async_setup_component(hass, "light", {})
    assert await async_setup_component(hass, "persistent_notification", {})
    hass.states.async_set(STUCK, "off")
    config = {
        "automation": [
            {
                "id": "t1",
                "alias": "t1",
                "triggers": [{"trigger": "event", "event_type": "go"}],
                "actions": [{"action": "light.turn_on", "target": {"entity_id": STUCK}}],
            },
            {
                "id": "t2",
                "alias": "t2",
                "triggers": [{"trigger": "event", "event_type": "go2"}],
                "actions": [{"action": "persistent_notification.create", "data": {"message": "m"}}],
            },
        ]
    }
    assert await async_setup_component(hass, "automation", config)
    await hass.async_block_till_done()


async def _run(hass: HomeAssistant, freezer: FrozenDateTimeFactory, event: str = "go") -> None:
    """Fire an automation and let its settle window pass."""
    hass.bus.async_fire(event)
    await hass.async_block_till_done()
    freezer.tick(10)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


def _issue(hass: HomeAssistant) -> ir.IssueEntry | None:
    return ir.async_get(hass).async_get_issue(DOMAIN, ISSUE)


async def test_failed_run_fires_one_event(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    events = async_capture_events(hass, EVENT_RESULT)
    await _run(hass, freezer)
    [event] = events
    assert (event.data["name"], event.data["verdict"]) == ("automation.t1", "no_effect")
    assert [f["entity_id"] for f in event.data["failed"]] == [STUCK]


async def test_confirmed_and_unchecked_runs_fire_no_event(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    events = async_capture_events(hass, EVENT_RESULT)
    hass.states.async_set(STUCK, "on")
    await _run(hass, freezer)
    await _run(hass, freezer, "go2")
    runs = loaded_entry.runtime_data.store.data["runs"]
    assert [r["verdict"] for r in runs] == ["confirmed", "unchecked"]
    assert events == []


async def test_sensor_counts_failures_and_decays_after_a_day(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    assert hass.states.get(SENSOR).state == "0"  # type: ignore[union-attr]
    await _run(hass, freezer)
    await _run(hass, freezer)
    state = hass.states.get(SENSOR)
    assert state is not None
    assert state.state == "2"
    assert [f["verdict"] for f in state.attributes["failures"]] == ["no_effect", "no_effect"]

    freezer.tick(24 * 3600 + 60)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(SENSOR).state == "0"  # type: ignore[union-attr]


async def test_three_failures_open_an_issue_and_three_passes_clear_it(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    for _ in range(2):
        await _run(hass, freezer)
    assert _issue(hass) is None
    await _run(hass, freezer)
    issue = _issue(hass)
    assert issue is not None
    assert issue.translation_key == "runtime_failure"
    assert issue.translation_placeholders == {
        "name": "automation.t1",
        "count": "3",
        "failures": f"{STUCK} (no_effect)",
    }

    hass.states.async_set(STUCK, "on")
    for _ in range(2):
        await _run(hass, freezer)
    assert _issue(hass) is not None
    await _run(hass, freezer)
    assert _issue(hass) is None


async def test_setup_rebuilds_the_sensor_and_issues_from_the_store(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    now = dt_util.utcnow().timestamp()
    runs = [stored_run("no_effect", at=now - i, source="automation.t1") for i in range(3)]
    data = {"runs": runs, "expectations": {}}
    hass_storage[DOMAIN] = {"version": 1, "minor_version": 1, "key": DOMAIN, "data": data}
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(SENSOR).state == "3"  # type: ignore[union-attr]
    assert _issue(hass) is not None
