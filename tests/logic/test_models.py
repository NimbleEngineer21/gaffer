"""Run record serialization."""

from custom_components.gaffer.logic.models import (
    Ctx,
    Origin,
    RunRecord,
    ServiceCall,
    Snapshot,
    StateChange,
)


def test_device_report_is_a_context_without_parent_or_user() -> None:
    assert Ctx("a").is_device_report
    assert not Ctx("a", parent_id="p").is_device_report
    assert not Ctx("a", user_id="u").is_device_report


def test_to_dict_keeps_only_attributes_that_a_call_set() -> None:
    run = RunRecord("c1", Origin.AUTOMATION, "automation.a", 1.0)
    run.calls.append(
        ServiceCall(
            "media_player",
            "volume_set",
            {"volume_level": 0.4},
            ("media_player.m",),
            1.0,
            {"media_player.m": Snapshot("idle", {"volume_level": 0.1, "friendly_name": "M"})},
        )
    )
    run.changes.append(
        StateChange(
            "media_player.m", "idle", {"volume_level": 0.2, "friendly_name": "M"}, 2.0, "window"
        )
    )
    assert run.to_dict() == {
        "context_id": "c1",
        "origin": "automation",
        "source": "automation.a",
        "started_at": 1.0,
        "calls": [
            {
                "domain": "media_player",
                "service": "volume_set",
                "data": {"volume_level": 0.4},
                "entity_ids": ["media_player.m"],
                "at": 1.0,
                "prior": {"media_player.m": {"state": "idle", "attributes": {"volume_level": 0.1}}},
            }
        ],
        "changes": [
            {
                "entity_id": "media_player.m",
                "state": "idle",
                "attributes": {"volume_level": 0.2},
                "at": 2.0,
                "matched_by": "window",
            }
        ],
    }


def test_to_dict_keeps_brightness_for_a_brightness_pct_call() -> None:
    run = RunRecord("c1", Origin.AUTOMATION, None, 1.0)
    run.calls.append(ServiceCall("light", "turn_on", {"brightness_pct": 50}, ("light.l",), 1.0))
    run.changes.append(StateChange("light.l", "on", {"brightness": 128, "x": 1}, 2.0, "context"))
    assert run.to_dict()["changes"][0]["attributes"] == {"brightness": 128}
