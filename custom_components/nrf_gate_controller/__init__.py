"""The nRF Gate Controller integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .ble_client import GateControllerBLE
from .coordinator import GateControllerCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.COVER]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up nRF Gate Controller from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    
    # Initialize BLE client with Home Assistant context
    ble_client = GateControllerBLE(
        address=entry.data["address"],
        name=entry.data.get("name"),
        hass=hass,
    )
    
    try:
        connected = await ble_client.connect()
        if not connected:
            _LOGGER.error("Failed to connect to device")
            return False
    except Exception as e:
        _LOGGER.error("Failed to connect to device: %s", e)
        return False
    
    # Create coordinator
    coordinator = GateControllerCoordinator(hass, ble_client)
    
    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()
    
    hass.data[DOMAIN][entry.entry_id] = {
        "ble_client": ble_client,
        "coordinator": coordinator,
    }
    
    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        await data["ble_client"].disconnect()
    
    return unload_ok

