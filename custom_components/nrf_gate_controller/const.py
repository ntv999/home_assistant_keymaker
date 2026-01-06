"""Constants for the nRF Gate Controller integration."""
from typing import Final

DOMAIN: Final = "nrf_gate_controller"

# Nordic UART Service UUIDs
# NOTE: Firmware uses NUS UUIDs with +5 offset (see secure_nus.c: uuid = BLE_UUID_xxx + 5)
# Standard NUS:
#   Service: 6e400001-b5a3-f393-e0a9-e50e24dcca9e
#   RX:      6e400002-b5a3-f393-e0a9-e50e24dcca9e
#   TX:      6e400003-b5a3-f393-e0a9-e50e24dcca9e
# Firmware (offset +5):
#   Service: 6e400006-b5a3-f393-e0a9-e50e24dcca9e
#   RX:      6e400007-b5a3-f393-e0a9-e50e24dcca9e
#   TX:      6e400008-b5a3-f393-e0a9-e50e24dcca9e
NUS_SERVICE_UUID: Final = "6e400006-b5a3-f393-e0a9-e50e24dcca9e"
NUS_RX_CHAR_UUID: Final = "6e400007-b5a3-f393-e0a9-e50e24dcca9e"  # Write
NUS_TX_CHAR_UUID: Final = "6e400008-b5a3-f393-e0a9-e50e24dcca9e"  # Notify

# Gate States (from main_message_handler.h)
STATE_OPENED: Final = 0
STATE_OPEN: Final = 1
STATE_STOP_MIDDLE: Final = 2
STATE_CLOSE: Final = 3
STATE_CLOSED: Final = 4

# Gate Commands (from main_message_handler.h)
CMD_OPEN: Final = 1
CMD_STOP_MIDDLE: Final = 2
CMD_CLOSE: Final = 3
CMD_SEND: Final = 17  # Get current state

# Working Modes (from main_flash.h)
WORKING_MODE_PP: Final = 1  # pp
WORKING_MODE_OPEN_CLOSE: Final = 2  # start/stop
WORKING_MODE_DOOR: Final = 3  # door
WORKING_MODE_SCA: Final = 4  # sca
WORKING_MODE_SCA_OPEN: Final = 5
WORKING_MODE_SCA_MOTION: Final = 6  # sca_motion

# Working mode commands (from main_message_handler.h)
CMD_WORKING_MODE_1: Final = 11  # pp
CMD_WORKING_MODE_2: Final = 12  # start/stop
CMD_WORKING_MODE_3: Final = 13  # door
CMD_WORKING_MODE_4: Final = 14  # sca
CMD_WORKING_MODE_5: Final = 15
CMD_WORKING_MODE_6: Final = 16  # sca_motion

# Working mode names for UI
WORKING_MODE_NAMES = {
    WORKING_MODE_PP: "PP (Импульсный)",
    WORKING_MODE_OPEN_CLOSE: "Open/Close (Старт/Стоп)",
    WORKING_MODE_DOOR: "Door (Дверь)",
    WORKING_MODE_SCA: "SCA",
    WORKING_MODE_SCA_OPEN: "SCA Open",
    WORKING_MODE_SCA_MOTION: "SCA Motion",
}

# State names for logging
STATE_NAMES = {
    STATE_OPENED: "opened",
    STATE_OPEN: "opening",
    STATE_STOP_MIDDLE: "stopped",
    STATE_CLOSE: "closing",
    STATE_CLOSED: "closed",
}

