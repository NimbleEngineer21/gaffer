"""Plain records of what happened during a run."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal


class Origin(StrEnum):
    """What started a run."""

    AUTOMATION = "automation"
    SCRIPT = "script"
    SCENE = "scene"
    HOMEKIT = "homekit"
    USER = "user"


@dataclass(frozen=True, slots=True)
class Ctx:
    """The parts of a Home Assistant context that correlation needs."""

    id: str
    parent_id: str | None = None
    user_id: str | None = None

    @property
    def is_device_report(self) -> bool:
        """True for a fresh context with no cause: a late or unprompted device report."""
        return self.parent_id is None and self.user_id is None


@dataclass(frozen=True, slots=True)
class ServiceCall:
    """One action that the run asked for."""

    domain: str
    service: str
    data: Mapping[str, Any]
    entity_ids: tuple[str, ...]
    at: float


@dataclass(frozen=True, slots=True)
class StateChange:
    """One state change on a target entity."""

    entity_id: str
    state: str | None
    attributes: Mapping[str, Any]
    at: float
    matched_by: Literal["context", "window"]


@dataclass(slots=True)
class RunRecord:
    """Everything one run did, keyed by its context id."""

    context_id: str
    origin: Origin
    source: str | None
    started_at: float
    calls: list[ServiceCall] = field(default_factory=list)
    changes: list[StateChange] = field(default_factory=list)
    last_activity: float = 0.0

    @property
    def targets(self) -> set[str]:
        """Every entity that a call in this run targeted."""
        return {entity_id for call in self.calls for entity_id in call.entity_ids}

    def to_dict(self) -> dict[str, Any]:
        """Serialize for storage, keeping only attributes that a call set."""
        keys = {key for call in self.calls for key in call.data}
        return {
            "context_id": self.context_id,
            "origin": self.origin.value,
            "source": self.source,
            "started_at": self.started_at,
            "calls": [
                {
                    "domain": c.domain,
                    "service": c.service,
                    "data": dict(c.data),
                    "entity_ids": list(c.entity_ids),
                    "at": c.at,
                }
                for c in self.calls
            ],
            "changes": [
                {
                    "entity_id": s.entity_id,
                    "state": s.state,
                    "attributes": {k: v for k, v in s.attributes.items() if k in keys},
                    "at": s.at,
                    "matched_by": s.matched_by,
                }
                for s in self.changes
            ],
        }
