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
        timeout: float = 10.0, name_filter: str | None = None
    ) -> list[BLEDevice]:
        """Scan for gate controller devices."""
        devices = []
        _LOGGER.info("Scanning for devices...")

        def detection_callback(device: BLEDevice, advertisement_data: AdvertisementData):
            if NUS_SERVICE_UUID in advertisement_data.service_uuids:
                if name_filter is None or (
                    device.name and name_filter.lower() in device.name.lower()
                ):
                    devices.append(device)
                    _LOGGER.info("Found device: %s (%s)", device.name, device.address)

        async with BleakScanner(detection_callback=detection_callback):
            await asyncio.sleep(timeout)

        return devices

