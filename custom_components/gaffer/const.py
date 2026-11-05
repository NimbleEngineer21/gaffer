"""Constants shared by the Home Assistant side of Gaffer."""

from typing import Final

DOMAIN: Final = "gaffer"
NAME: Final = "Gaffer"

STORAGE_VERSION: Final = 1
# Seconds to batch writes; run records arrive in bursts.
SAVE_DELAY: Final = 30
