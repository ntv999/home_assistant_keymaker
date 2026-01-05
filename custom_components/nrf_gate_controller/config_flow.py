"""Config flow for nRF Gate Controller integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .ble_client import GateControllerBLE
from .const import (
    DOMAIN,
    WORKING_MODE_PP,
    WORKING_MODE_OPEN_CLOSE,
    WORKING_MODE_DOOR,
    WORKING_MODE_SCA,
    WORKING_MODE_SCA_OPEN,
    WORKING_MODE_SCA_MOTION,
    WORKING_MODE_NAMES,
)

_LOGGER = logging.getLogger(__name__)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    address = data["address"].upper()
    
    # Basic MAC address validation
    if len(address) != 17 or address.count(":") != 5:
        raise InvalidAddress
    
    # Validate working mode
    working_mode = data.get("working_mode", WORKING_MODE_PP)
    if working_mode not in [
        WORKING_MODE_PP,
        WORKING_MODE_OPEN_CLOSE,
        WORKING_MODE_DOOR,
        WORKING_MODE_SCA,
        WORKING_MODE_SCA_OPEN,
        WORKING_MODE_SCA_MOTION,
    ]:
        raise InvalidWorkingMode
    
    # Try to connect
    ble_client = GateControllerBLE(address=address, name=data.get("name"))
    try:
        connected = await ble_client.connect()
        if not connected:
            raise CannotConnect
        
        # Set working mode if provided
        if working_mode:
            await ble_client.set_working_mode(working_mode)
            await asyncio.sleep(0.5)  # Wait for mode to be set
        
        await ble_client.disconnect()
    except Exception as e:
        _LOGGER.exception("Connection test failed: %s", e)
        raise CannotConnect from e
    
    return {
        "address": address,
        "name": data.get("name", "Gate Controller"),
        "working_mode": working_mode,
    }


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for nRF Gate Controller."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize config flow."""
        self._discovered_devices: dict[str, str] = {}
        self._address: str | None = None
        self._name: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if not bluetooth.async_scanner_count(self.hass, connectable=True):
            return self.async_abort(reason="bluetooth_not_available")

        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required("method", default="scan"): vol.In(
                            {
                                "scan": "Автоматическое сканирование",
                                "manual": "Ввести MAC-адрес вручную",
                            }
                        ),
                    }
                ),
            )

        if user_input["method"] == "scan":
            return await self.async_step_scan()
        return await self.async_step_manual()

    async def async_step_scan(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle scanning step."""
        errors = {}

        if user_input is None:
            # Perform actual scan
            _LOGGER.info("Starting BLE scan for NUS devices...")
            try:
                devices = await GateControllerBLE.scan_for_devices(timeout=10.0)
                self._discovered_devices = {
                    device.address: device.name or device.address
                    for device in devices
                }

                if not self._discovered_devices:
                    # Allow retry by resubmitting the form
                    return self.async_show_form(
                        step_id="scan",
                        data_schema=vol.Schema({}),
                        errors={"base": "no_devices_found"},
                        description_placeholders={"count": "0"},
                    )

            except Exception as e:
                _LOGGER.exception("Scan failed: %s", e)
                # Allow retry by resubmitting the form
                return self.async_show_form(
                    step_id="scan",
                    data_schema=vol.Schema({}),
                    errors={"base": "scan_failed"},
                )

            # Show device selection form
            return self.async_show_form(
                step_id="scan",
                data_schema=vol.Schema(
                    {
                        vol.Required("address"): vol.In(
                            {
                                addr: f"{name} ({addr})"
                                for addr, name in self._discovered_devices.items()
                            }
                        ),
                        vol.Optional("name", default="Gate Controller"): str,
                    }
                ),
                description_placeholders={
                    "count": str(len(self._discovered_devices)),
                },
            )

        # If no address in input, user wants to retry scanning
        if "address" not in user_input:
            # Retry scanning
            return await self.async_step_scan()

        address = user_input["address"].upper()
        name = user_input.get("name", self._discovered_devices.get(address, "Gate Controller"))

        # Store address and name for working mode step
        self._address = address
        self._name = name
        return await self.async_step_working_mode()

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle manual entry step."""
        if user_input is None:
            return self.async_show_form(
                step_id="manual",
                data_schema=vol.Schema(
                    {
                        vol.Required("address"): str,
                        vol.Optional("name", default="Gate Controller"): str,
                    }
                ),
            )

        errors = {}

        # Store address and name for working mode step
        self._address = user_input["address"].upper()
        self._name = user_input.get("name", "Gate Controller")
        return await self.async_step_working_mode()

    async def async_step_working_mode(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle working mode selection step."""
        errors = {}

        if user_input is None:
            return self.async_show_form(
                step_id="working_mode",
                data_schema=vol.Schema(
                    {
                        vol.Required(
                            "working_mode",
                            default=str(WORKING_MODE_PP),
                        ): vol.In(
                            {
                                str(WORKING_MODE_PP): WORKING_MODE_NAMES[WORKING_MODE_PP],
                                str(WORKING_MODE_OPEN_CLOSE): WORKING_MODE_NAMES[WORKING_MODE_OPEN_CLOSE],
                                str(WORKING_MODE_DOOR): WORKING_MODE_NAMES[WORKING_MODE_DOOR],
                                str(WORKING_MODE_SCA): WORKING_MODE_NAMES[WORKING_MODE_SCA],
                                str(WORKING_MODE_SCA_OPEN): WORKING_MODE_NAMES[WORKING_MODE_SCA_OPEN],
                                str(WORKING_MODE_SCA_MOTION): WORKING_MODE_NAMES[WORKING_MODE_SCA_MOTION],
                            }
                        ),
                    }
                ),
                description_placeholders={
                    "name": self._name or "Gate Controller",
                },
            )

        working_mode = int(user_input["working_mode"])

        try:
            info = await validate_input(
                self.hass,
                {
                    "address": self._address,
                    "name": self._name,
                    "working_mode": working_mode,
                },
            )
        except InvalidAddress:
            errors["base"] = "invalid_address"
        except InvalidWorkingMode:
            errors["base"] = "invalid_working_mode"
        except CannotConnect:
            errors["base"] = "cannot_connect"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            await self.async_set_unique_id(info["address"])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=info["name"], data=info)

        return self.async_show_form(
            step_id="working_mode",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "working_mode",
                        default=str(working_mode),
                    ): vol.In(
                        {
                            str(WORKING_MODE_PP): WORKING_MODE_NAMES[WORKING_MODE_PP],
                            str(WORKING_MODE_OPEN_CLOSE): WORKING_MODE_NAMES[WORKING_MODE_OPEN_CLOSE],
                            str(WORKING_MODE_DOOR): WORKING_MODE_NAMES[WORKING_MODE_DOOR],
                            str(WORKING_MODE_SCA): WORKING_MODE_NAMES[WORKING_MODE_SCA],
                            str(WORKING_MODE_SCA_OPEN): WORKING_MODE_NAMES[WORKING_MODE_SCA_OPEN],
                            str(WORKING_MODE_SCA_MOTION): WORKING_MODE_NAMES[WORKING_MODE_SCA_MOTION],
                        }
                    ),
                }
            ),
            errors=errors,
            description_placeholders={
                "name": self._name or "Gate Controller",
            },
        )


class InvalidAddress(HomeAssistantError):
    """Error to indicate the address is invalid."""


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidWorkingMode(HomeAssistantError):
    """Error to indicate the working mode is invalid."""

