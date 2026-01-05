"""Cover platform for nRF Gate Controller."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, STATE_CLOSED, STATE_CLOSE, STATE_OPEN
from .coordinator import GateControllerCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the cover platform."""
    coordinator: GateControllerCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([GateCoverEntity(coordinator, entry)])


class GateCoverEntity(CoordinatorEntity, CoverEntity):
    """Representation of a gate cover."""

    _attr_device_class = CoverDeviceClass.GATE
    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.STOP
    )

    def __init__(
        self,
        coordinator: GateControllerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the cover entity."""
        super().__init__(coordinator)
        self._attr_name = entry.data.get("name", "Gate Controller")
        self._attr_unique_id = f"{entry.entry_id}_cover"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": self._attr_name,
            "manufacturer": "Nordic Semiconductor",
            "model": "nRF52840 Gate Controller",
        }

    @property
    def is_closed(self) -> bool | None:
        """Return if the cover is closed."""
        state = self.coordinator.data.get("state")
        if state is None:
            return None
        return state == STATE_CLOSED

    @property
    def is_opening(self) -> bool:
        """Return if the cover is opening."""
        state = self.coordinator.data.get("state")
        return state == STATE_OPEN

    @property
    def is_closing(self) -> bool:
        """Return if the cover is closing."""
        state = self.coordinator.data.get("state")
        return state == STATE_CLOSE

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        await self.coordinator.ble_client.open_gate()
        await self.coordinator.async_request_refresh()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        await self.coordinator.ble_client.close_gate()
        await self.coordinator.async_request_refresh()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        await self.coordinator.ble_client.stop_gate()
        await self.coordinator.async_request_refresh()

