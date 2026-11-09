"""Report stored runs to Home Assistant: bus event, sensor data, Repairs issues."""

from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import DOMAIN, EVENT_RESULT, SIGNAL_UPDATED
from .logic.outputs import (
    DAY,
    RECENT,
    IssuePlan,
    failures_since,
    is_failure,
    plan_issues,
    summary,
)
from .store import GafferStore

# The failure count must fall as runs age out of 24 h, with no new run.
REFRESH_INTERVAL = timedelta(seconds=60)
ISSUE_KEY = "runtime_failure"


class Outputs:
    """Owns the reported state for one loaded config entry."""

    def __init__(self, hass: HomeAssistant, store: GafferStore) -> None:
        """Bind to Home Assistant and the store. Call async_start to report."""
        self._hass = hass
        self._store = store
        self._unsubs: list[CALLBACK_TYPE] = []
        self.failure_count = 0
        self.recent: list[dict[str, Any]] = []

    @callback
    def async_start(self) -> None:
        """Rebuild the reported state from the store, then refresh it on an interval."""
        self._unsubs.append(
            async_track_time_interval(self._hass, self._on_interval, REFRESH_INTERVAL)
        )
        self.refresh()

    @callback
    def async_stop(self) -> None:
        """Stop the refresh. Issues stay; the next load rebuilds them."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    @callback
    def on_stored(self, records: list[dict[str, Any]]) -> None:
        """Fire one gaffer_result event per failed run, then refresh."""
        for record in records:
            if is_failure(record):
                self._hass.bus.async_fire(EVENT_RESULT, summary(record))
        self.refresh()

    @callback
    def _on_interval(self, now: datetime) -> None:
        self.refresh()

    @callback
    def refresh(self) -> None:
        """Recompute the 24 h failures and the Repairs issues from the store."""
        runs = self._store.data["runs"]
        now = dt_util.utcnow().timestamp()
        failures = failures_since(runs, now - DAY)
        self.failure_count = len(failures)
        self.recent = [summary(run) for run in failures[:RECENT]]
        async_dispatcher_send(self._hass, SIGNAL_UPDATED)
        self._apply_issues(plan_issues(runs, now, _open_issue_ids(self._hass)))

    def _apply_issues(self, plan: IssuePlan) -> None:
        for issue in plan.upsert:
            ir.async_create_issue(
                self._hass,
                DOMAIN,
                issue.issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=ISSUE_KEY,
                translation_placeholders={
                    "name": issue.name,
                    "count": str(issue.count),
                    "failures": issue.failures,
                },
            )
        for issue_id in plan.delete:
            ir.async_delete_issue(self._hass, DOMAIN, issue_id)


def _open_issue_ids(hass: HomeAssistant) -> set[str]:
    registry = ir.async_get(hass)
    return {issue_id for domain, issue_id in registry.issues if domain == DOMAIN}


def remove_issues(hass: HomeAssistant) -> None:
    """Delete every Gaffer issue, for when the user removes the integration."""
    for issue_id in _open_issue_ids(hass):
        ir.async_delete_issue(hass, DOMAIN, issue_id)
