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

from .const import (
    DOMAIN,
    STATE_CLOSED,
    STATE_CLOSE,
    STATE_OPEN,
    STATE_OPENED,
    STATE_STOP_MIDDLE,
    STATE_NAMES,
)
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
    def current_cover_position(self) -> int | None:
        """Return current position of cover (0-100)."""
        state = self.coordinator.data.get("state")
        if state is None:
            return None
        
        # Map states to positions
        if state == STATE_CLOSED:
            return 0
        elif state == STATE_OPENED:
            return 100
        elif state == STATE_STOP_MIDDLE:
            return 50  # Stopped in middle
        elif state == STATE_OPEN:
            return None  # Opening - position unknown
        elif state == STATE_CLOSE:
            return None  # Closing - position unknown
        return None

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
        if state is None:
            return False
        return state == STATE_OPEN

    @property
    def is_closing(self) -> bool:
        """Return if the cover is closing."""
        state = self.coordinator.data.get("state")
        if state is None:
            return False
        return state == STATE_CLOSE

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        state = self.coordinator.data.get("state")
        if state is not None:
            state_name = STATE_NAMES.get(state, f"unknown_{state}")
            _LOGGER.debug(
                "Обновление статуса в cover entity: state=%d (%s)",
                state,
                state_name
            )
        super()._handle_coordinator_update()

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

