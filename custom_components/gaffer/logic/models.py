"""Plain records of what happened during a run."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal

# Service data keys that set an attribute of a different name.
_ATTRIBUTE_FOR_KEY = {"brightness_pct": "brightness"}


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
class Snapshot:
    """The state and attributes of one entity at one time."""

    state: str | None
    attributes: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ServiceCall:
    """One action that the run asked for, with each target's state before it ran."""

    domain: str
    service: str
    data: Mapping[str, Any]
    entity_ids: tuple[str, ...]
    at: float
    prior: Mapping[str, Snapshot] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StateChange:
    """One state change on a target entity.

    matched_by is "context" or "window" for a change that this run caused, and
    "foreign" for a change that another run or a user made on the same entity.
    """

    entity_id: str
    state: str | None
    attributes: Mapping[str, Any]
    at: float
    matched_by: Literal["context", "window", "foreign"]


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
        keys = {_ATTRIBUTE_FOR_KEY.get(k, k) for call in self.calls for k in call.data}

        def kept(attributes: Mapping[str, Any]) -> dict[str, Any]:
            return {k: v for k, v in attributes.items() if k in keys}

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
                    "prior": {
                        entity_id: {"state": snap.state, "attributes": kept(snap.attributes)}
                        for entity_id, snap in c.prior.items()
                    },
                }
                for c in self.calls
            ],
            "changes": [
                {
                    "entity_id": s.entity_id,
                    "state": s.state,
                    "attributes": kept(s.attributes),
                    "at": s.at,
                    "matched_by": s.matched_by,
                }
                for s in self.changes
            ],
        }


class Verdict(StrEnum):
    """The result of one expectation, plan section 4.5."""

    CONFIRMED = "confirmed"
    LATE = "late"
    NO_EFFECT = "no_effect"
    REVERTED = "reverted"
    PARTIAL = "partial"
    TARGET_UNAVAILABLE = "target_unavailable"
    UNCHECKED = "unchecked"
    SUPERSEDED = "superseded"


FAILURES = frozenset(
    {Verdict.NO_EFFECT, Verdict.REVERTED, Verdict.PARTIAL, Verdict.TARGET_UNAVAILABLE}
)


class Comparator(StrEnum):
    """How an observed value is compared with the expected value."""

    EQ = "eq"
    APPROX = "approx"
    IN = "in"
    NOT_IN = "not_in"


STATE = "state"


@dataclass(frozen=True, slots=True)
class Check:
    """One expected value: the state (key "state") or one attribute."""

    key: str
    comparator: Comparator
    value: Any
    tolerance: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize for storage."""
        value = list(self.value) if isinstance(self.value, tuple) else self.value
        return {
            "key": self.key,
            "comparator": self.comparator.value,
            "value": value,
            "tolerance": self.tolerance,
        }


@dataclass(frozen=True, slots=True)
class Expectation:
    """What one call should do to one entity.

    No checks means the call is unchecked. entity_id is None only for an
    unchecked call that has no target, such as notify.
    """

    entity_id: str | None
    call_index: int
    checks: tuple[Check, ...]
    window: float

    @property
    def keys(self) -> set[str]:
        """The state and attribute names that this expectation sets."""
        return {check.key for check in self.checks}


@dataclass(frozen=True, slots=True)
class ActionResult:
    """The verdict on one expectation, with the values seen at each check."""

    expectation: Expectation
    verdict: Verdict
    at_action: Mapping[str, Any] = field(default_factory=dict)
    at_run: Mapping[str, Any] = field(default_factory=dict)
    failed: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Serialize for storage."""
        exp = self.expectation
        return {
            "entity_id": exp.entity_id,
            "call_index": exp.call_index,
            "window": exp.window,
            "checks": [check.to_dict() for check in exp.checks],
            "verdict": self.verdict.value,
            "at_action": dict(self.at_action),
            "at_run": dict(self.at_run),
            "failed": list(self.failed),
        }
