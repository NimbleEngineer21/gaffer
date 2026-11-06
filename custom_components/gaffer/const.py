"""Constants shared by the Home Assistant side of Gaffer."""

from typing import Final

DOMAIN: Final = "gaffer"
NAME: Final = "Gaffer"

STORAGE_VERSION: Final = 1
# Seconds to batch writes; run records arrive in bursts.
SAVE_DELAY: Final = 30

# Fired once per judged run whose verdict is a failure.
EVENT_RESULT: Final = "gaffer_result"
# Dispatcher signal: the reported failures changed.
SIGNAL_UPDATED: Final = "gaffer_updated"
