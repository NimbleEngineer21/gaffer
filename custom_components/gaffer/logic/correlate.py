"""Group service calls and state changes into runs.

Rules (confirmed in the M0 spike on Home Assistant 2026.11):
- Every call and state change in a run carries the run's context id. Scripts
  called by an automation and scene member calls reuse it.
- An entity keeps that context for 5 s only. A later state write has a fresh
  context with no parent and no user. Such a change is matched to the newest open
  run that targeted the entity, if it falls inside that entity's settle window.
"""

from collections.abc import Callable
from dataclasses import replace

from .models import Ctx, Origin, RunRecord, ServiceCall, StateChange

WindowFor = Callable[[str], float]


class RunTracker:
    """Open runs, fed by events, closed when their settle windows pass."""

    def __init__(self, window_for: WindowFor, *, track_user: bool = False) -> None:
        """Set the per-entity settle window and whether UI calls start runs."""
        self._window_for = window_for
        self._track_user = track_user
        self._open: dict[str, RunRecord] = {}

    @property
    def open_runs(self) -> list[RunRecord]:
        """Runs that are not closed yet, oldest first."""
        return list(self._open.values())

    def start(self, ctx: Ctx, origin: Origin, source: str | None, at: float) -> None:
        """Open a run. The first start wins; UI-made runs need track_user."""
        if ctx.user_id is not None and not self._track_user:
            return
        if ctx.id not in self._open:
            self._open[ctx.id] = RunRecord(ctx.id, origin, source, at, last_activity=at)

    def on_call(self, ctx: Ctx, call: ServiceCall) -> None:
        """Add a call to its run, or start a run for a root scene or UI call."""
        run = self._open.get(ctx.id)
        if run is None:
            origin = self._root_origin(ctx, call)
            if origin is None:
                return
            self.start(ctx, origin, None, call.at)
            run = self._open[ctx.id]
        run.calls.append(call)
        run.last_activity = call.at

    def on_state(self, ctx: Ctx, change: StateChange) -> None:
        """Add a state change by context, or by window for a device report."""
        if not self._open:
            return
        run = self._open.get(ctx.id)
        if run is not None:
            if change.entity_id in run.targets:
                run.changes.append(change)
                run.last_activity = max(run.last_activity, change.at)
            return
        if not ctx.is_device_report:
            return
        window = self._window_for(change.entity_id)
        for run in reversed(self._open.values()):
            last_call = max(
                (c.at for c in run.calls if change.entity_id in c.entity_ids), default=None
            )
            if last_call is not None and change.at - last_call <= window:
                run.changes.append(replace(change, matched_by="window"))
                run.last_activity = max(run.last_activity, change.at)
                return

    def close_expired(self, now: float) -> list[RunRecord]:
        """Remove and return runs whose longest target window has passed."""
        closed = [run for run in self._open.values() if now - run.last_activity > self._span(run)]
        for run in closed:
            del self._open[run.context_id]
        return closed

    def _span(self, run: RunRecord) -> float:
        return max((self._window_for(e) for e in run.targets), default=0.0)

    def _root_origin(self, ctx: Ctx, call: ServiceCall) -> Origin | None:
        if ctx.parent_id is not None:
            return None
        if ctx.user_id is not None:
            return Origin.USER if self._track_user else None
        if (call.domain, call.service) == ("scene", "turn_on"):
            return Origin.SCENE
        return None
