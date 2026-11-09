"""Admin-only WebSocket commands."""

from collections.abc import Awaitable, Callable
from typing import Any

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.runs import stored_run

WsClient = Callable[..., Awaitable[Any]]


def _seed(entry: MockConfigEntry) -> None:
    entry.runtime_data.store.data["runs"] = [
        stored_run("no_effect", at=1.0, context_id="a"),
        stored_run("confirmed", at=2.0, context_id="b"),
        stored_run("late", at=3.0, context_id="c", source="script.s"),
    ]


async def test_runs_returns_summaries_newest_first(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, hass_ws_client: WsClient
) -> None:
    _seed(loaded_entry)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "gaffer/runs"})
    msg = await client.receive_json()
    assert msg["success"]
    assert [r["context_id"] for r in msg["result"]["runs"]] == ["c", "b", "a"]

    await client.send_json_auto_id(
        {"type": "gaffer/runs", "failures_only": True, "since": 0, "limit": 5}
    )
    msg = await client.receive_json()
    assert [r["context_id"] for r in msg["result"]["runs"]] == ["a"]

    await client.send_json_auto_id(
        {"type": "gaffer/runs", "source": "script.s", "verdicts": ["late"]}
    )
    msg = await client.receive_json()
    assert [r["context_id"] for r in msg["result"]["runs"]] == ["c"]


async def test_runs_rejects_a_bad_limit(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, hass_ws_client: WsClient
) -> None:
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "gaffer/runs", "limit": 0})
    msg = await client.receive_json()
    assert msg["error"]["code"] == "invalid_format"


async def test_run_returns_the_full_record_or_not_found(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, hass_ws_client: WsClient
) -> None:
    _seed(loaded_entry)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "gaffer/run", "context_id": "b"})
    msg = await client.receive_json()
    assert msg["result"] == stored_run("confirmed", at=2.0, context_id="b")

    await client.send_json_auto_id({"type": "gaffer/run", "context_id": "zzz"})
    msg = await client.receive_json()
    assert msg["error"]["code"] == "not_found"


async def test_commands_need_an_admin(
    hass: HomeAssistant,
    loaded_entry: MockConfigEntry,
    hass_ws_client: WsClient,
    hass_read_only_access_token: str,
) -> None:
    client = await hass_ws_client(hass, hass_read_only_access_token)
    for command in ({"type": "gaffer/runs"}, {"type": "gaffer/run", "context_id": "a"}):
        await client.send_json_auto_id(command)
        msg = await client.receive_json()
        assert msg["error"]["code"] == "unauthorized"


async def test_commands_report_when_gaffer_is_not_loaded(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, hass_ws_client: WsClient
) -> None:
    assert await hass.config_entries.async_unload(loaded_entry.entry_id)
    client = await hass_ws_client(hass)
    for command in ({"type": "gaffer/runs"}, {"type": "gaffer/run", "context_id": "a"}):
        await client.send_json_auto_id(command)
        msg = await client.receive_json()
        assert msg["error"]["code"] == "not_loaded"
