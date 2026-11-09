"""Diagnostics download for a bug report.

It holds entity ids and states from recent runs, because a bug report needs them.
The README asks the user to read it before posting it in public.
"""

from typing import Any

from homeassistant.core import HomeAssistant

from . import GafferConfigEntry
from .logic.outputs import counts, newest_first, summary

RECENT_RUNS = 20


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: GafferConfigEntry
) -> dict[str, Any]:
    """Return store sizes, verdict counts, open runs, and the newest run summaries."""
    data = entry.runtime_data
    runs = data.store.data["runs"]
    return {
        "options": dict(entry.options),
        "stored_runs": len(runs),
        "declared_expectations": len(data.store.data["expectations"]),
        "open_runs": len(data.collector.tracker.open_runs),
        "failures_24h": data.outputs.failure_count,
        **counts(runs),
        "recent": [summary(run) for run in newest_first(runs)[:RECENT_RUNS]],
    }
