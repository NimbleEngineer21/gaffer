"""Stored run dicts in the shape the collector writes, for output tests."""

from typing import Any


def result(
    entity_id: str, verdict: str, *, call_index: int = 0, failed: tuple[str, ...] = ("state",)
) -> dict[str, Any]:
    """Return one stored action result that expects state on."""
    return {
        "entity_id": entity_id,
        "call_index": call_index,
        "window": 3.0,
        "checks": [{"key": "state", "comparator": "eq", "value": "on", "tolerance": 0.0}],
        "verdict": verdict,
        "at_action": {"state": "off"},
        "at_run": {"state": "off"},
        "failed": list(failed) if verdict != "confirmed" else [],
    }


def stored_run(
    verdict: str | None = "confirmed",
    *,
    at: float = 0.0,
    source: str | None = "automation.hall",
    entity_id: str = "light.hall",
    origin: str = "automation",
    judged: bool = True,
    context_id: str | None = None,
    results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return a stored run with one light.turn_on call and one result."""
    if results is None:
        results = [] if verdict is None else [result(entity_id, verdict)]
    return {
        "context_id": context_id or f"ctx-{source}-{at}",
        "origin": origin,
        "source": source,
        "started_at": at,
        "calls": [
            {
                "domain": "light",
                "service": "turn_on",
                "data": {"entity_id": entity_id},
                "entity_ids": [entity_id],
                "at": at,
                "prior": {entity_id: {"state": "off", "attributes": {}}},
            }
        ],
        "changes": [],
        "judged": judged,
        "results": results if judged else [],
        "verdict": verdict if judged else None,
    }
