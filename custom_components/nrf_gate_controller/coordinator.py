"""Data update coordinator for nRF Gate Controller."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .ble_client import GateControllerBLE
from .const import STATE_NAMES

_LOGGER = logging.getLogger(__name__)


class GateControllerCoordinator(DataUpdateCoordinator):
    """Coordinator for gate controller data updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        ble_client: GateControllerBLE,
        update_interval: float = 5.0,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Gate Controller",
            update_interval=update_interval,
        )
        self.ble_client = ble_client

    def _state_update_callback(self, state: int, mode: int) -> None:
        """Handle state updates from BLE notifications (automatic updates from device)."""
        state_name = STATE_NAMES.get(state, f"unknown_{state}")
        _LOGGER.info(
            "Получено обновление статуса: state=%d (%s), mode=%d",
            state,
            state_name,
            mode
        )
        self.async_set_updated_data({"state": state, "mode": mode})

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the device."""
        try:
            if not self.ble_client.is_connected:
                await self.ble_client.connect()
            
            # Always set callback for notifications (handles reconnections)
            # This ensures automatic state updates from device are received
            self.ble_client.set_state_callback(self._state_update_callback)

            # Request current state (polling fallback)
            await self.ble_client.get_state()
            
            # Wait a bit for response
            await asyncio.sleep(0.5)
            
            # Return current data (will be updated via callback for automatic updates)
            return self.data or {"state": None, "mode": None}

        except Exception as err:
            raise UpdateFailed(f"Error communicating with device: {err}") from err

