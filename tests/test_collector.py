"""Runs collected from a real Home Assistant core, one test per run origin."""

from typing import Any

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

A, B = "input_boolean.a", "input_boolean.b"


@pytest.fixture(autouse=True)
async def booleans(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, "input_boolean", {"input_boolean": {"a": {}, "b": {}}})
    assert await async_setup_component(hass, "light", {})


async def _automation(hass: HomeAssistant, actions: list[dict[str, Any]]) -> None:
    config = {
        "automation": [
            {
                "id": "t1",
                "alias": "t1",
                "triggers": [{"trigger": "event", "event_type": "go"}],
                "actions": actions,
            }
        ]
    }
    assert await async_setup_component(hass, "automation", config)
    await hass.async_block_till_done()


def _turn_on(target: dict[str, Any]) -> dict[str, Any]:
    return {"action": "input_boolean.turn_on", "target": target}


async def _runs(
    hass: HomeAssistant, entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> list[dict[str, Any]]:
    """Let every settle window pass, then return the stored runs."""
    await hass.async_block_till_done()
    freezer.tick(70)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    runs: list[dict[str, Any]] = entry.runtime_data.store.data["runs"]
    return runs


async def test_automation_run(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    await _automation(hass, [_turn_on({"entity_id": A})])
    hass.bus.async_fire("go")
    [run] = await _runs(hass, loaded_entry, freezer)
    assert (run["origin"], run["source"]) == ("automation", "automation.t1")
    assert [(c["service"], c["entity_ids"]) for c in run["calls"]] == [("turn_on", [A])]
    assert [(s["entity_id"], s["state"], s["matched_by"]) for s in run["changes"]] == [
        (A, "on", "context")
    ]


async def test_script_called_by_automation_is_one_run(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    script = {"script": {"s1": {"sequence": [_turn_on({"entity_id": A})]}}}
    assert await async_setup_component(hass, "script", script)
    await _automation(hass, [{"action": "script.s1"}])
    hass.bus.async_fire("go")
    [run] = await _runs(hass, loaded_entry, freezer)
    assert run["origin"] == "automation"
    assert [c["domain"] for c in run["calls"]] == ["script", "input_boolean"]
    assert [s["entity_id"] for s in run["changes"]] == [A]


async def test_scene_run(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    scene = {"scene": [{"name": "sc", "entities": {A: "on"}}]}
    assert await async_setup_component(hass, "scene", scene)
    # Platform entities are added after setup returns; wait for scene.sc to exist.
    await hass.async_block_till_done()
    await hass.services.async_call("scene", "turn_on", {"entity_id": "scene.sc"}, blocking=True)
    [run] = await _runs(hass, loaded_entry, freezer)
    assert run["origin"] == "scene"
    # The scene entity records its own activation; M3 sets no expectation on it.
    assert [s["entity_id"] for s in run["changes"]] == ["scene.sc", A]


async def test_homekit_bridge_run(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    ctx = Context()
    hass.bus.async_fire(
        "homekit_state_change",
        {"entity_id": A, "display_name": "a", "service": "turn_on", "value": 1},
        context=ctx,
    )
    await hass.services.async_call("input_boolean", "turn_on", {"entity_id": A}, context=ctx)
    [run] = await _runs(hass, loaded_entry, freezer)
    assert (run["origin"], run["source"]) == ("homekit", A)
    assert [s["entity_id"] for s in run["changes"]] == [A]


async def test_late_device_report_joins_by_window(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    await _automation(hass, [{"action": "light.turn_on", "target": {"entity_id": "light.slow"}}])
    hass.bus.async_fire("go")
    await hass.async_block_till_done()
    freezer.tick(2)
    hass.states.async_set("light.slow", "on", context=Context())
    freezer.tick(2)
    hass.states.async_set("light.slow", "off", context=Context())
    [run] = await _runs(hass, loaded_entry, freezer)
    assert [(s["state"], s["matched_by"]) for s in run["changes"]] == [("on", "window")]


async def test_ui_call_is_not_a_run_by_default(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    await hass.services.async_call(
        "input_boolean", "turn_on", {"entity_id": A}, context=Context(user_id="u1")
    )
    assert await _runs(hass, loaded_entry, freezer) == []


async def test_area_and_all_targets_resolve_to_entities(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    area = ar.async_get(hass).async_create("Den")
    registry = er.async_get(hass)
    registry.async_update_entity(A, area_id=area.id)
    # A sensor in the same area: an input_boolean action does not act on it.
    sensor = registry.async_get_or_create("sensor", "test", "den_temp")
    registry.async_update_entity(sensor.entity_id, area_id=area.id)
    await _automation(hass, [_turn_on({"area_id": area.id}), _turn_on({"entity_id": "all"})])
    hass.bus.async_fire("go")
    [run] = await _runs(hass, loaded_entry, freezer)
    assert [c["entity_ids"] for c in run["calls"]] == [[A], [A, B]]


async def test_call_without_target_is_kept(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    await _automation(hass, [{"action": "input_boolean.reload"}])
    hass.bus.async_fire("go")
    [run] = await _runs(hass, loaded_entry, freezer)
    assert run["calls"][0]["entity_ids"] == []


async def test_unload_stores_open_runs(hass: HomeAssistant, loaded_entry: MockConfigEntry) -> None:
    await _automation(hass, [_turn_on({"entity_id": A})])
    hass.bus.async_fire("go")
    await hass.async_block_till_done()
    store = loaded_entry.runtime_data.store
    assert await hass.config_entries.async_unload(loaded_entry.entry_id)
    [run] = store.data["runs"]
    assert run["source"] == "automation.t1"
    # Its settle window did not pass, so it has no verdict.
    assert (run["judged"], run["results"], run["verdict"]) == (False, [], None)


async def test_removed_entity_change_records_no_state(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    await _automation(hass, [{"action": "light.turn_on", "target": {"entity_id": "light.gone"}}])
    hass.states.async_set("light.gone", "off")
    hass.bus.async_fire("go")
    await hass.async_block_till_done()
    hass.states.async_remove("light.gone", context=Context())
    [run] = await _runs(hass, loaded_entry, freezer)
    assert [(s["state"], s["attributes"]) for s in run["changes"]] == [(None, {})]


async def test_closed_run_stores_prior_state_and_verdicts(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    await _automation(hass, [_turn_on({"entity_id": A})])
    hass.bus.async_fire("go")
    [run] = await _runs(hass, loaded_entry, freezer)
    assert run["calls"][0]["prior"] == {A: {"state": "off", "attributes": {}}}
    assert [(r["entity_id"], r["verdict"]) for r in run["results"]] == [(A, "confirmed")]
    assert (run["judged"], run["verdict"]) == (True, "confirmed")


async def test_already_on_entity_is_confirmed(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    await hass.services.async_call("input_boolean", "turn_on", {"entity_id": A}, blocking=True)
    await _automation(hass, [_turn_on({"entity_id": A})])
    hass.bus.async_fire("go")
    [run] = await _runs(hass, loaded_entry, freezer)
    assert run["changes"] == []
    assert run["verdict"] == "confirmed"


async def test_entity_that_ignores_the_call_is_no_effect(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    # A state with no light entity behind it: the call changes nothing.
    hass.states.async_set("light.stuck", "off")
    await _automation(hass, [{"action": "light.turn_on", "target": {"entity_id": "light.stuck"}}])
    hass.bus.async_fire("go")
    [run] = await _runs(hass, loaded_entry, freezer)
    assert [r["verdict"] for r in run["results"]] == ["no_effect"]


async def test_run_with_only_a_container_call_has_no_verdict(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    assert await async_setup_component(hass, "script", {"script": {"empty": {"sequence": []}}})
    await _automation(hass, [{"action": "script.empty"}])
    hass.bus.async_fire("go")
    [run] = await _runs(hass, loaded_entry, freezer)
    assert (run["judged"], run["results"], run["verdict"]) == (True, [], None)
