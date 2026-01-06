"""BLE client for NRF Gate Controller."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice

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
    """BLE client for NRF Gate Controller using Home Assistant Bluetooth API."""

    def __init__(
        self, 
        address: str, 
        name: str | None = None,
        hass: HomeAssistant | None = None
    ) -> None:
        """Initialize the BLE client."""
        self.address = address
        self.name = name
        self.hass = hass
        # BleakClient instance (using BLEDevice from Home Assistant)
        self.client: BleakClient | None = None
        self._state_callback: Callable[[int, int], None] | None = None
        self._connected = False

    def _is_connected(self) -> bool:
        """Check if client is connected and connection is still active."""
        if not self.client or not self._connected:
            return False
        try:
            # Check if client reports as connected
            return self.client.is_connected
        except Exception:
            return False

    async def _wait_for_security_ready(self, max_attempts: int = 10, delay: float = 0.5) -> bool:
        """Wait for security/pairing to complete before accessing characteristics.
        
        The device starts pairing after connection with a delay (SECURITY_REQUEST_DELAY ≈ 400ms).
        This function waits for pairing to complete by attempting to access characteristics
        with retries.
        
        Note: If pairing fails (e.g., rejected by Home Assistant), the device may disconnect.
        This function will detect disconnection and return False.
        
        Args:
            max_attempts: Maximum number of attempts to access characteristics
            delay: Delay between attempts in seconds
            
        Returns:
            True if security is ready, False if not ready or connection lost
        """
        if not self._is_connected():
            _LOGGER.warning("Connection lost while waiting for security")
            return False
        
        # Initial delay to allow pairing process to start
        # SECURITY_REQUEST_DELAY is ~400ms, add some buffer
        await asyncio.sleep(0.6)
        
        for attempt in range(max_attempts):
            # Check connection status before each attempt
            if not self._is_connected():
                _LOGGER.warning(
                    "Connection lost during security wait (attempt %d/%d)",
                    attempt + 1,
                    max_attempts
                )
                self._connected = False
                return False
            
            try:
                # Try to get services and access the NUS characteristics
                # If pairing is not complete, characteristics may not be accessible
                services = await self.client.get_services()
                if services:
                    # Try to access the NUS service and its characteristics
                    nus_service = services.get_service(NUS_SERVICE_UUID)
                    if nus_service:
                        # Verify that we can access the characteristics we need
                        tx_char = nus_service.get_characteristic(NUS_TX_CHAR_UUID)
                        rx_char = nus_service.get_characteristic(NUS_RX_CHAR_UUID)
                        if tx_char and rx_char:
                            _LOGGER.debug(
                                "Security ready (attempt %d/%d) - characteristics accessible",
                                attempt + 1,
                                max_attempts
                            )
                            return True
                        else:
                            _LOGGER.debug(
                                "NUS service found but characteristics not accessible yet (attempt %d/%d)",
                                attempt + 1,
                                max_attempts
                            )
            except Exception as e:
                # Check if error is due to disconnection
                error_str = str(e).lower()
                if "not connected" in error_str or "disconnected" in error_str:
                    _LOGGER.warning(
                        "Connection lost during security wait (attempt %d/%d): %s",
                        attempt + 1,
                        max_attempts,
                        e
                    )
                    self._connected = False
                    return False
                
                _LOGGER.debug(
                    "Security not ready yet (attempt %d/%d): %s",
                    attempt + 1,
                    max_attempts,
                    e,
                )
            
            if attempt < max_attempts - 1:
                await asyncio.sleep(delay)
        
        # Final connection check
        if not self._is_connected():
            _LOGGER.warning(
                "Connection lost after security wait (pairing may have failed)"
            )
            self._connected = False
            return False
        
        _LOGGER.warning(
            "Security may not be ready after %d attempts, proceeding anyway",
            max_attempts
        )
        return False

    async def connect(self) -> bool:
        """Connect to the device using Home Assistant Bluetooth API.
        
        Note: The device requires BLE pairing (Just Works) before characteristics
        are accessible. If pairing fails (error 0x85), Home Assistant may have
        rejected the pairing request. Ensure pairing mode is enabled on the device
        (single button click) before connecting.
        
        Returns:
            True if connection and pairing succeeded, False otherwise
        """
        if self.hass is None:
            _LOGGER.error("Home Assistant context required for connection")
            return False
        
        from homeassistant.components import bluetooth as ha_bluetooth
        
        try:
            # Get BLE device from Home Assistant
            _LOGGER.debug("Getting BLE device for address: %s", self.address)
            ble_device = ha_bluetooth.async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )
            
            if ble_device is None:
                _LOGGER.error("Device %s not found in Bluetooth cache", self.address)
                return False
            
            # Create BleakClient using BLEDevice from Home Assistant
            # According to HA docs: use BLEDevice from async_ble_device_from_address
            # and create BleakClient directly
            _LOGGER.debug("Creating BleakClient for device: %s", self.address)
            self.client = BleakClient(ble_device)
            
            _LOGGER.info("Connecting to %s...", self.address)
            await self.client.connect()
            self._connected = True
            _LOGGER.info("Connected to %s", self.address)

            # Wait for security/pairing to complete before accessing characteristics
            # The device requires pairing before characteristics are accessible
            # Note: If pairing fails (e.g., rejected by Home Assistant), 
            # the device will disconnect and _wait_for_security_ready will return False
            _LOGGER.debug("Waiting for security/pairing to complete...")
            security_ready = await self._wait_for_security_ready()
            
            # Check if connection is still active after security wait
            if not self._is_connected():
                _LOGGER.error(
                    "Connection lost during pairing. "
                    "Pairing may have been rejected by Home Assistant. "
                    "Check if device requires pairing mode to be enabled."
                )
                self._connected = False
                return False
            
            if not security_ready:
                _LOGGER.warning(
                    "Security may not be ready, but connection is active. "
                    "Attempting to access characteristics anyway."
                )
            
            _LOGGER.debug("Security ready, accessing characteristics")

            # Subscribe to notifications (now that security is ready)
            try:
                # Double-check connection before subscribing
                if not self._is_connected():
                    _LOGGER.error("Connection lost before subscribing to notifications")
                    self._connected = False
                    return False
                
                await self.client.start_notify(NUS_TX_CHAR_UUID, self._notification_handler)
                _LOGGER.debug("Subscribed to notifications on %s", NUS_TX_CHAR_UUID)
            except Exception as e:
                error_str = str(e).lower()
                if "not connected" in error_str or "disconnected" in error_str:
                    _LOGGER.error(
                        "Connection lost before subscribing to notifications. "
                        "Pairing may have failed: %s",
                        e
                    )
                else:
                    _LOGGER.error(
                        "Failed to subscribe to notifications: %s",
                        e
                    )
                # Connection is lost, clean up
                self._connected = False
                try:
                    await self.disconnect()
                except Exception:
                    pass  # Ignore errors during cleanup
                return False

            return True
        except Exception as e:
            _LOGGER.error("Failed to connect to %s: %s", self.address, e, exc_info=True)
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """Disconnect from the device."""
        if self.client and self._connected:
            try:
                # Try to stop notifications if they were started
                # This may fail if service discovery wasn't performed yet
                try:
                    if self.client.is_connected:
                        await self.client.stop_notify(NUS_TX_CHAR_UUID)
                except Exception as notify_error:
                    error_str = str(notify_error).lower()
                    if "service discovery" in error_str or "not been performed" in error_str:
                        _LOGGER.debug(
                            "Cannot stop notifications: service discovery not performed yet"
                        )
                    else:
                        _LOGGER.debug("Error stopping notifications: %s", notify_error)
                
                # Disconnect from device
                if self.client.is_connected:
                    await self.client.disconnect()
            except Exception as e:
                error_str = str(e).lower()
                if "not connected" in error_str or "disconnected" in error_str:
                    _LOGGER.debug("Already disconnected: %s", e)
                else:
                    _LOGGER.error("Error disconnecting: %s", e)
            finally:
                self._connected = False
                self.client = None

    def _notification_handler(
        self, sender: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        """Handle notifications from the device (including automatic state updates)."""
        try:
            # Convert bytes to string
            message = data.decode("utf-8")
            _LOGGER.debug("Received notification: %s", message)

            # Parse JSON response
            # Handle messages that may be split across multiple notifications
            if "*" in message:
                message = message.split("*")[0]  # Remove terminator

            try:
                response = json.loads(message)
                if "state" in response and "mode" in response:
                    state = response["state"]
                    mode = response["mode"]
                    _LOGGER.debug("Parsed state update: state=%d, mode=%d", state, mode)
                    if self._state_callback:
                        # Callback will update coordinator with automatic state change
                        self._state_callback(state, mode)
                else:
                    _LOGGER.debug("Notification does not contain state/mode: %s", response)
            except json.JSONDecodeError:
                _LOGGER.warning("Failed to parse JSON from notification: %s", message)

        except Exception as e:
            _LOGGER.error("Error handling notification: %s", e, exc_info=True)

    async def send_command(self, command: int) -> dict | None:
        """Send a command to the device."""
        if not self._is_connected():
            _LOGGER.error("Not connected")
            self._connected = False
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
            error_str = str(e).lower()
            if "not connected" in error_str or "disconnected" in error_str:
                _LOGGER.error("Connection lost while sending command: %s", e)
                self._connected = False
            else:
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
        return self._is_connected()

    @staticmethod
    async def scan_for_devices(
        hass: HomeAssistant,
        timeout: float = 10.0, 
        name_filter: str | None = None
    ) -> list[BLEDevice]:
        """Scan for gate controller devices using Home Assistant Bluetooth API.
        
        Args:
            hass: Home Assistant instance (required)
            timeout: Scan timeout in seconds
            name_filter: Optional name filter
            
        Returns:
            List of discovered BLEDevice objects
        """
        from homeassistant.components import bluetooth as ha_bluetooth
        
        if hass is None:
            raise ValueError("Home Assistant context is required for BLE scanning")
        
        devices = []
        _LOGGER.info(
            "[SCAN] Starting BLE device scan with timeout %s seconds (no service filter for testing)",
            timeout
        )

        # Use Home Assistant Bluetooth API
        try:
            discovered_addresses: set[str] = set()
            all_discovered_count = 0
            
            def match_callback(
                service_info: ha_bluetooth.BluetoothServiceInfoBleak,
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
                    
                    # Use BLEDevice from service_info (according to HA docs)
                    # service_info has a 'device' attribute that is a BLEDevice
                    ble_device = getattr(service_info, "device", None)
                    if ble_device is None:
                        # Fallback: create BLEDevice if not available
                        ble_device = BLEDevice(
                            address=address,
                            name=name or address,
                            details=None,
                        )
                    
                    devices.append(ble_device)
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
            # According to HA docs: matcher is a dict, not BluetoothCallbackMatcher object
            _LOGGER.info(
                "[SCAN] Registering callback for ALL BLE devices (no service filter)"
            )
            callback = ha_bluetooth.async_register_callback(
                hass,
                match_callback,
                {},  # Empty dict = match all devices (no filter)
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

