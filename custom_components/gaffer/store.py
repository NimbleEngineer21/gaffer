"""Persistence for run records and user-declared expectations."""

from typing import Any, TypedDict

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN, SAVE_DELAY, STORAGE_VERSION


class StoredData(TypedDict):
    """Shape of the storage file, version 1."""

    runs: list[dict[str, Any]]
    expectations: dict[str, list[dict[str, Any]]]


def empty_data() -> StoredData:
    """Return the data for a new install."""
    return {"runs": [], "expectations": {}}


class GafferStore:
    """Thin wrapper around Home Assistant's storage helper."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Bind to the `.storage/gaffer` file."""
        self._store: Store[StoredData] = Store(hass, STORAGE_VERSION, DOMAIN, private=True)
        self.data: StoredData = empty_data()

    async def async_load(self) -> None:
        """Read the file, or start empty when there is none."""
        loaded = await self._store.async_load()
        self.data = empty_data() if loaded is None else loaded

    def async_schedule_save(self) -> None:
        """Write after SAVE_DELAY seconds; later calls in the window merge."""
        self._store.async_delay_save(lambda: self.data, SAVE_DELAY)

    async def async_save_now(self) -> None:
        """Write at once."""
        await self._store.async_save(self.data)

    async def async_remove(self) -> None:
        """Delete the file."""
        await self._store.async_remove()
