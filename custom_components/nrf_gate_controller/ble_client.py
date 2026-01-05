"""BLE client for NRF Gate Controller."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Callable

from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

try:
    from homeassistant.core import HomeAssistant
except ImportError:
    HomeAssistant = None  # type: ignore[assignment, misc]

from .const import (
    NUS_RX_CHAR_UUID,
    NUS_TX_CHAR_UUID,
    NUS_SERVICE_UUID,
    CMD_WORKING_MODE_1,
    CMD_WORKING_MODE_2,
    CMD_WORKING_MODE_3,
    CMD_WORKING_MODE_4,
    CMD_WORKING_MODE_5,
    CMD_WORKING_MODE_6,
)

_LOGGER = logging.getLogger(__name__)


class GateControllerBLE:
    """BLE client for NRF Gate Controller."""

    def __init__(self, address: str, name: str | None = None) -> None:
        """Initialize the BLE client."""
        self.address = address
        self.name = name
        self.client: BleakClient | None = None
        self._state_callback: Callable[[int, int], None] | None = None
        self._connected = False

    async def connect(self) -> bool:
        """Connect to the device."""
        try:
            self.client = BleakClient(self.address)
            await self.client.connect()
            self._connected = True
            _LOGGER.info("Connected to %s", self.address)

            # Subscribe to notifications
            await self.client.start_notify(NUS_TX_CHAR_UUID, self._notification_handler)

            return True
        except Exception as e:
            _LOGGER.error("Failed to connect: %s", e)
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """Disconnect from the device."""
        if self.client and self._connected:
            try:
                await self.client.stop_notify(NUS_TX_CHAR_UUID)
                await self.client.disconnect()
            except Exception as e:
                _LOGGER.error("Error disconnecting: %s", e)
            finally:
                self._connected = False
                self.client = None

    def _notification_handler(
        self, sender: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        """Handle notifications from the device."""
        try:
            # Convert bytes to string
            message = data.decode("utf-8")
            _LOGGER.debug("Received: %s", message)

            # Parse JSON response
            if "*" in message:
                message = message.split("*")[0]  # Remove terminator

            try:
                response = json.loads(message)
                if "state" in response and "mode" in response:
                    state = response["state"]
                    mode = response["mode"]
                    if self._state_callback:
                        self._state_callback(state, mode)
            except json.JSONDecodeError:
                _LOGGER.warning("Failed to parse JSON: %s", message)

        except Exception as e:
            _LOGGER.error("Error handling notification: %s", e)

    async def send_command(self, command: int) -> dict | None:
        """Send a command to the device."""
        if not self.client or not self._connected:
            _LOGGER.error("Not connected")
            return None

        try:
            # Create JSON command
            cmd_json = json.dumps({"cmd": command}) + "*\n"
            cmd_bytes = cmd_json.encode("utf-8")

            # Send command
            await self.client.write_gatt_char(NUS_RX_CHAR_UUID, cmd_bytes)
            _LOGGER.debug("Sent command: %s", cmd_json.strip())

            # Wait a bit for response
            await asyncio.sleep(0.5)

            return {"status": "sent"}

        except Exception as e:
            _LOGGER.error("Error sending command: %s", e)
            return None

    async def get_state(self) -> dict | None:
        """Get current state from the device."""
        return await self.send_command(17)  # SERVER_COMMAND_SEND

    async def open_gate(self) -> dict | None:
        """Open the gate."""
        return await self.send_command(1)  # SERVER_COMMAND_OPEN

    async def close_gate(self) -> dict | None:
        """Close the gate."""
        return await self.send_command(3)  # SERVER_COMMAND_CLOSE

    async def stop_gate(self) -> dict | None:
        """Stop the gate."""
        return await self.send_command(2)  # SERVER_COMMAND_STOP_MIDDLE

    async def set_working_mode(self, working_mode: int) -> dict | None:
        """Set working mode on the device."""
        mode_commands = {
            1: CMD_WORKING_MODE_1,  # PP
            2: CMD_WORKING_MODE_2,  # Open/Close
            3: CMD_WORKING_MODE_3,  # Door
            4: CMD_WORKING_MODE_4,  # SCA
            5: CMD_WORKING_MODE_5,  # SCA Open
            6: CMD_WORKING_MODE_6,  # SCA Motion
        }
        
        if working_mode not in mode_commands:
            _LOGGER.error("Invalid working mode: %s", working_mode)
            return None
        
        return await self.send_command(mode_commands[working_mode])

    def set_state_callback(self, callback: Callable[[int, int], None]) -> None:
        """Set callback for state updates."""
        self._state_callback = callback

    @property
    def is_connected(self) -> bool:
        """Check if connected."""
        return self._connected

    @staticmethod
    async def scan_for_devices(
        hass: HomeAssistant | None = None,
        timeout: float = 10.0, 
        name_filter: str | None = None
    ) -> list[BLEDevice]:
        """Scan for gate controller devices using Home Assistant Bluetooth API."""
        from homeassistant.components import bluetooth as ha_bluetooth
        
        devices = []
        _LOGGER.info(
            "[SCAN] Starting BLE device scan with timeout %s seconds (no service filter for testing)",
            timeout
        )

        if hass is None:
            # Fallback to direct BleakScanner if no hass context
            _LOGGER.warning("No Home Assistant context, using direct BleakScanner")
            try:
                def detection_callback(device: BLEDevice, advertisement_data: AdvertisementData):
                    try:
                        service_uuids = advertisement_data.service_uuids or []
                        if NUS_SERVICE_UUID in service_uuids:
                            if name_filter is None or (
                                device.name and name_filter.lower() in device.name.lower()
                            ):
                                if not any(d.address == device.address for d in devices):
                                    devices.append(device)
                                    _LOGGER.info(
                                        "Found device: %s (%s)", 
                                        device.name or "Unknown", 
                                        device.address
                                    )
                    except Exception as e:
                        _LOGGER.debug("Error in detection callback: %s", e)

                scanner = BleakScanner(detection_callback=detection_callback)
                await scanner.start()
                await asyncio.sleep(timeout)
                await scanner.stop()
                _LOGGER.info("Scan completed, found %d device(s)", len(devices))
            except Exception as e:
                _LOGGER.error("BLE scan error: %s (type: %s)", e, type(e).__name__)
                raise
            return devices

        # Use Home Assistant Bluetooth API
        try:
            discovered_addresses: set[str] = set()
            all_discovered_count = 0
            
            def match_callback(
                service_info: ha_bluetooth.BluetoothServiceInfo,
                change: ha_bluetooth.BluetoothChange,
            ) -> None:
                """Callback for device discovery - logs all devices for testing."""
                nonlocal all_discovered_count
                try:
                    all_discovered_count += 1
                    address = service_info.address
                    name = getattr(service_info, "name", None) or "Unknown"
                    service_uuids = getattr(service_info, "service_uuids", [])
                    rssi = getattr(service_info, "rssi", None)
                    
                    # Log all discovered devices for debugging
                    _LOGGER.info(
                        "[SCAN DEBUG] Device #%d: Name='%s', Address=%s, RSSI=%s, Services=%s, Change=%s",
                        all_discovered_count,
                        name,
                        address,
                        rssi,
                        service_uuids,
                        change
                    )
                    
                    # Check if device advertises NUS service (for reference, but don't filter)
                    has_nus_service = NUS_SERVICE_UUID.lower() in [
                        uuid.lower() for uuid in service_uuids
                    ]
                    if has_nus_service:
                        _LOGGER.info(
                            "[SCAN DEBUG] Device %s has NUS service UUID!", address
                        )
                    
                    # Apply name filter if provided
                    if name_filter:
                        if name_filter.lower() not in name.lower():
                            _LOGGER.debug(
                                "[SCAN DEBUG] Device %s filtered out by name filter", address
                            )
                            return
                    
                    # Avoid duplicates
                    if address in discovered_addresses:
                        _LOGGER.debug(
                            "[SCAN DEBUG] Device %s already in list, skipping", address
                        )
                        return
                    
                    discovered_addresses.add(address)
                    
                    # Create BLEDevice from service_info
                    device = BLEDevice(
                        address=address,
                        name=name or address,
                        details=getattr(service_info, "device", None),
                    )
                    
                    devices.append(device)
                    _LOGGER.info(
                        "[SCAN] Added device to results: %s (%s) - Services: %s", 
                        name, 
                        address,
                        service_uuids
                    )
                except Exception as e:
                    _LOGGER.error(
                        "[SCAN ERROR] Error in match callback: %s (type: %s)", 
                        e, 
                        type(e).__name__,
                        exc_info=True
                    )
            
            # Register callback for device discovery - NO FILTER for testing
            _LOGGER.info(
                "[SCAN] Registering callback for ALL BLE devices (no service filter)"
            )
            callback = ha_bluetooth.async_register_callback(
                hass,
                match_callback,
                ha_bluetooth.BluetoothCallbackMatcher(),  # No filter - match all devices
                ha_bluetooth.BluetoothScanningMode.ACTIVE,
            )
            
            try:
                # Wait for discoveries
                _LOGGER.info(
                    "[SCAN] Starting scan, waiting %s seconds for device discoveries...", 
                    timeout
                )
                await asyncio.sleep(timeout)
                _LOGGER.info(
                    "[SCAN] Scan period ended. Total devices discovered: %d, Added to results: %d",
                    all_discovered_count,
                    len(devices)
                )
            finally:
                # Unregister callback
                _LOGGER.debug("[SCAN] Unregistering callback")
                callback()
            
            _LOGGER.info(
                "[SCAN] Scan completed. Found %d device(s) in results", len(devices)
            )
            
        except Exception as e:
            _LOGGER.error(
                "[SCAN ERROR] BLE scan error: %s (type: %s)", 
                e, 
                type(e).__name__,
                exc_info=True
            )
            # If callback registration fails, try simpler approach
            _LOGGER.warning(
                "[SCAN] Falling back to checking already discovered devices"
            )
            try:
                # Try to get scanner and check discovered devices
                scanner = ha_bluetooth.async_get_scanner(hass)
                if scanner:
                    _LOGGER.info(
                        "[SCAN] Scanner available, waiting %s seconds...", timeout
                    )
                    # Wait a bit for devices to be discovered
                    await asyncio.sleep(timeout)
                    _LOGGER.info(
                        "[SCAN] Using already discovered devices from scanner cache"
                    )
                else:
                    _LOGGER.warning("[SCAN] Scanner not available")
            except Exception as fallback_error:
                _LOGGER.error(
                    "[SCAN ERROR] Fallback also failed: %s (type: %s)",
                    fallback_error,
                    type(fallback_error).__name__,
                    exc_info=True
                )
                raise e

        return devices

