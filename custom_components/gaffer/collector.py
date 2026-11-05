"""Feed Home Assistant events into the run tracker, and store closed runs."""

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from homeassistant.const import ENTITY_MATCH_ALL, EVENT_CALL_SERVICE, EVENT_STATE_CHANGED
from homeassistant.core import CALLBACK_TYPE, Context, Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.target import TargetSelection, async_extract_referenced_entity_ids
from homeassistant.util import dt as dt_util

from .logic.correlate import RunTracker
from .logic.models import Ctx, Origin, RunRecord, ServiceCall, StateChange
from .logic.retention import retain
from .logic.windows import settle_window
from .store import GafferStore

# Event names confirmed in the M0 spike. Literals avoid importing the
# automation, script, and homekit integrations.
EVENT_AUTOMATION_TRIGGERED = "automation_triggered"
EVENT_SCRIPT_STARTED = "script_started"
EVENT_HOMEKIT_CHANGED = "homekit_state_change"
CLOSE_INTERVAL = timedelta(seconds=5)


def _ctx(context: Context) -> Ctx:
    return Ctx(context.id, context.parent_id, context.user_id)


class Collector:
    """Owns the run tracker for one loaded config entry."""

    def __init__(self, hass: HomeAssistant, store: GafferStore) -> None:
        """Bind to Home Assistant and the store. Call async_start to listen."""
        self._hass = hass
        self._store = store
        self.tracker = RunTracker(settle_window)
        self._unsubs: list[CALLBACK_TYPE] = []

    @callback
    def async_start(self) -> None:
        """Subscribe to the events that make up runs."""
        listen = self._hass.bus.async_listen
        self._unsubs = [
            listen(EVENT_AUTOMATION_TRIGGERED, self._starter(Origin.AUTOMATION)),
            listen(EVENT_SCRIPT_STARTED, self._starter(Origin.SCRIPT)),
            listen(EVENT_HOMEKIT_CHANGED, self._starter(Origin.HOMEKIT)),
            listen(EVENT_CALL_SERVICE, self._on_call),
            listen(EVENT_STATE_CHANGED, self._on_state),
            async_track_time_interval(self._hass, self._on_tick, CLOSE_INTERVAL),
        ]

    @callback
    def async_stop(self) -> None:
        """Unsubscribe, and store every open run as it is."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        self._keep(self.tracker.close_expired(float("inf")))

    def _starter(self, origin: Origin) -> Callable[[Event[Any]], None]:
        @callback
        def _on_start(event: Event[Any]) -> None:
            self.tracker.start(
                _ctx(event.context), origin, event.data.get("entity_id"), event.time_fired_timestamp
            )

        return _on_start

    @callback
    def _on_call(self, event: Event[Any]) -> None:
        domain: str = event.data["domain"]
        data: dict[str, Any] = dict(event.data.get("service_data") or {})
        call = ServiceCall(
            domain,
            event.data["service"],
            data,
            self._resolve(domain, data),
            event.time_fired_timestamp,
        )
        self.tracker.on_call(_ctx(event.context), call)

    @callback
    def _on_state(self, event: Event[Any]) -> None:
        new = event.data["new_state"]
        change = StateChange(
            event.data["entity_id"],
            None if new is None else new.state,
            {} if new is None else dict(new.attributes),
            event.time_fired_timestamp,
            "context",
        )
        self.tracker.on_state(_ctx(event.context), change)

    @callback
    def _on_tick(self, now: datetime) -> None:
        self._keep(self.tracker.close_expired(now.timestamp()))

    def _keep(self, closed: list[RunRecord]) -> None:
        if not closed:
            return
        runs = self._store.data["runs"] + [run.to_dict() for run in closed]
        self._store.data["runs"] = retain(runs, dt_util.utcnow().timestamp())
        self._store.async_schedule_save()

    def _resolve(self, domain: str, data: dict[str, Any]) -> tuple[str, ...]:
        """Expand entity, device, area, floor, and label targets to entity ids."""
        if data.get("entity_id") == ENTITY_MATCH_ALL:
            return tuple(sorted(self._hass.states.async_entity_ids(domain)))
        selection = TargetSelection(data)
        if not selection.has_any_target:
            return ()
        selected = async_extract_referenced_entity_ids(self._hass, selection)
        return tuple(sorted(selected.referenced | selected.indirectly_referenced))
