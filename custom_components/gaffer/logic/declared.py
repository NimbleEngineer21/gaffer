"""User-declared expectations (plan section 4.4, source 2).

A user declares expectations for an automation when inference is wrong or
missing. The store and the gaffer.set_expectation action come in M4; this module
holds the shape, its validation, and how it overrides inferred expectations.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from .models import Check, Comparator, Expectation


@dataclass(frozen=True, slots=True)
class DeclaredExpectation:
    """Checks that a user expects on one entity at the end of a run."""

    entity_id: str
    checks: tuple[Check, ...]
    window: float | None = None


def _positive_number(value: Any, name: str, *, allow_zero: bool) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{name} must be a number")
    if value < 0 or (value == 0 and not allow_zero):
        raise ValueError(f"{name} must be {'zero or more' if allow_zero else 'more than zero'}")
    return float(value)


def _parse_check(raw: Any) -> Check:
    if not isinstance(raw, Mapping):
        raise ValueError("each check must be a mapping")
    key = raw.get("key")
    if not isinstance(key, str) or not key:
        raise ValueError("check key must be a non-empty string")
    try:
        comparator = Comparator(raw.get("comparator", Comparator.EQ))
    except ValueError:
        raise ValueError(f"unknown comparator {raw.get('comparator')!r}") from None
    if "value" not in raw:
        raise ValueError(f"check {key!r} has no value")
    value = raw["value"]
    if comparator in (Comparator.IN, Comparator.NOT_IN):
        if not isinstance(value, list | tuple) or not value:
            raise ValueError(f"check {key!r} needs a non-empty list for {comparator.value}")
        value = tuple(value)
    elif isinstance(value, list):
        value = tuple(value)
    tolerance = _positive_number(raw.get("tolerance", 0), "tolerance", allow_zero=True)
    if comparator is Comparator.APPROX:
        _positive_number(value, f"check {key!r} value", allow_zero=True)
    return Check(key, comparator, value, tolerance)


def parse(raw: Any) -> DeclaredExpectation:
    """Validate one declared expectation from stored or user data.

    Raises ValueError with a message for the user when the shape is wrong.
    """
    if not isinstance(raw, Mapping):
        raise ValueError("a declared expectation must be a mapping")
    entity_id = raw.get("entity_id")
    if not isinstance(entity_id, str) or "." not in entity_id:
        raise ValueError("entity_id must be an entity id such as light.kitchen")
    checks = raw.get("checks")
    if not isinstance(checks, list | tuple) or not checks:
        raise ValueError("checks must be a non-empty list")
    window = raw.get("window")
    return DeclaredExpectation(
        entity_id,
        tuple(_parse_check(check) for check in checks),
        None if window is None else _positive_number(window, "window", allow_zero=False),
    )


def merge(
    inferred: Sequence[Expectation], declared: Sequence[DeclaredExpectation]
) -> list[Expectation]:
    """Apply declared checks to the last expectation on each declared entity.

    A declared check replaces an inferred check on the same key and adds a check
    on a new key. A declared window replaces the inferred one. A declaration for
    an entity that no call in the run targets is ignored.
    """
    result = list(inferred)
    for item in declared:
        index = next(
            (i for i in reversed(range(len(result))) if result[i].entity_id == item.entity_id),
            None,
        )
        if index is None:
            continue
        exp = result[index]
        keys = {check.key for check in item.checks}
        checks = tuple(c for c in exp.checks if c.key not in keys) + item.checks
        result[index] = replace(
            exp, checks=checks, window=exp.window if item.window is None else item.window
        )
    return result
