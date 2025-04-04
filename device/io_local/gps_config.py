import uasyncio as asyncio
import struct
import time
import json
from lib.microdot import Response  # Needed for the handler
from log import log
from machine import UART
from . import gps_reader  # Relative import for reader module

# UBX Protocol constants
UBX_SYNC_1 = 0xB5
UBX_SYNC_2 = 0x62

# UBX Class IDs
UBX_CLASS_NAV = 0x01  # Navigation Results
UBX_CLASS_RXM = 0x02  # Receiver Manager Messages
UBX_CLASS_INF = 0x04  # Information Messages
UBX_CLASS_ACK = 0x05  # Ack/Nack Messages
UBX_CLASS_CFG = 0x06  # Configuration Input Messages
UBX_CLASS_UPD = 0x09  # Firmware Update Messages
UBX_CLASS_MON = 0x0A  # Monitoring Messages
UBX_CLASS_AID = 0x0B  # AssistNow Aiding Messages
UBX_CLASS_TIM = 0x0D  # Timing Messages
UBX_CLASS_ESF = 0x10  # External Sensor Fusion Messages
UBX_CLASS_MGA = 0x13  # Multiple GNSS Assistance Messages
UBX_CLASS_LOG = 0x21  # Logging Messages
UBX_CLASS_SEC = 0x27  # Security Feature Messages
UBX_CLASS_HNR = 0x28  # High Rate Navigation Results Messages
UBX_CLASS_NMEA = 0xF0  # NMEA Standard Messages (for configuring NMEA output)
UBX_CLASS_PUBX = 0xF1  # u-blox Proprietary Messages

# UBX CFG Message IDs
UBX_CFG_RATE = 0x08  # Navigation/Measurement Rate Settings
UBX_CFG_CFG = 0x09  # Clear, Save, and Load configurations

# UBX ACK Message IDs
UBX_ACK_NAK = 0x00  # Message Not-Acknowledged
UBX_ACK_ACK = 0x01  # Message Acknowledged


def _calculate_ubx_checksum(payload: bytes) -> bytes:
    """Calculates the 2-byte Fletcher checksum for UBX messages."""
    ck_a = 0
    ck_b = 0
    for byte in payload:
        ck_a = (ck_a + byte) & 0xFF
        ck_b = (ck_b + ck_a) & 0xFF
    return bytes([ck_a, ck_b])


async def _send_ubx_command(
    uart: UART, class_id: int, msg_id: int, payload: bytes = b""
):
    """Constructs and sends a UBX command message."""
    msg_len = len(payload)
    # <H is unsigned short (2 bytes), little-endian
    header = struct.pack("<BBBBH", UBX_SYNC_1, UBX_SYNC_2, class_id, msg_id, msg_len)
    message = header + payload
    checksum_payload = struct.pack("<BBH", class_id, msg_id, msg_len) + payload
    checksum = _calculate_ubx_checksum(checksum_payload)
    full_message = message + checksum
    log(f"GPS CFG TX: {full_message.hex()}")  # Log hex representation
    if uart:
        written = uart.write(full_message)
        if written != len(full_message):
            log(f"GPS CFG TX Error: Wrote {written}/{len(full_message)} bytes")
            return False
        return True
    else:
        log("GPS CFG TX Error: UART not available")
        return False


async def _read_ubx_response(
    uart, expected_class_id: int, expected_msg_id: int, timeout_ms: int = 500
):
    """Reads and validates a specific UBX response message."""
    # TODO: Implement UBX response reading and parsing logic
    # This needs to handle reading bytes, finding sync chars, checking class/id,
    # reading payload based on length, and verifying checksum.
    log("GPS CFG RX: _read_ubx_response not implemented yet")
    await asyncio.sleep_ms(10)  # Placeholder
    return None  # Placeholder


async def set_nav_rate(uart, lock: asyncio.Lock, rate_hz: int):
    """Sets the navigation measurement and solution rate."""
    if not uart or not lock:
        log("GPS CFG Error: UART or Lock not available for set_nav_rate")
        return False

    await lock.acquire()
    result = False  # Default result
    try:
        log(f"GPS CFG: Attempting to set nav rate to {rate_hz} Hz")
        if rate_hz <= 0:
            log("GPS CFG Error: Invalid rate_hz")
            # No need to return here, finally will release lock
        else:
            meas_rate_ms = int(1000 / rate_hz)
            nav_rate_cycles = 1  # Output a solution for every measurement
            time_ref = 1  # 0=UTC, 1=GPS time (use GPS time for NAV-RATE)

            # Payload: measRate (ms, u2), navRate (cycles, u2), timeRef (0=UTC, 1=GPS, u2)
            # <HHH is 3x unsigned short (2 bytes each), little-endian
            payload = struct.pack("<HHH", meas_rate_ms, nav_rate_cycles, time_ref)

            success = await _send_ubx_command(
                uart, UBX_CLASS_CFG, UBX_CFG_RATE, payload
            )
            if success:
                # Optional: Wait for ACK/NAK (Implementation needed in _read_ubx_response)
                # ... ACK/NAK logic would go here ...
                # For now, assume success if command sent without ACK check
                log("GPS CFG: set_nav_rate command sent (ACK check skipped)")
                result = True
            # else: result remains False
    finally:
        lock.release()
    return result


async def handle_gps_settings_data(request):
    """Handles getting and setting GPS configuration via UBX commands."""
    if not request.json:
        return Response(
            body=json.dumps({"success": False, "message": "Bad Request: No JSON body"}),
            status_code=400,
            headers={"Content-Type": "application/json"},
        )

    action = request.json.get("action")
    # Use the relative import for gps_reader
    uart = gps_reader.get_uart()
    lock = gps_reader.get_uart_lock()

    if not uart or not lock:
        log("GPS Settings API Error: UART or Lock not available")
        return Response(
            body=json.dumps(
                {
                    "success": False,
                    "message": "Internal Server Error: GPS UART/Lock unavailable",
                }
            ),
            status_code=500,
            headers={"Content-Type": "application/json"},
        )

    try:
        if action == "get_rate":
            log("GPS Settings API: Received get_rate request")
            # Call local function directly
            rate_data = await get_nav_rate(uart, lock)
            if rate_data:
                log(f"GPS Settings API: get_rate successful - {rate_data}")
                return Response(
                    body=json.dumps({"success": True, "rate": rate_data}),
                    headers={"Content-Type": "application/json"},
                )
            else:
                log("GPS Settings API Error: get_nav_rate returned None")
                return Response(
                    body=json.dumps(
                        {
                            "success": False,
                            "message": "Failed to retrieve rate from GPS",
                        }
                    ),
                    status_code=500,
                    headers={"Content-Type": "application/json"},
                )

        elif action == "set_rate":
            rate_hz = request.json.get("rate")
            log(f"GPS Settings API: Received set_rate request for {rate_hz} Hz")
            if isinstance(rate_hz, int) and 1 <= rate_hz <= 10:  # Basic validation
                # Call local function directly
                success = await set_nav_rate(uart, lock, rate_hz)
                if success:
                    log(f"GPS Settings API: set_nav_rate for {rate_hz} Hz successful")
                    return Response(
                        body=json.dumps(
                            {
                                "success": True,
                                "message": f"Set rate command sent for {rate_hz} Hz",
                            }
                        ),
                        headers={"Content-Type": "application/json"},
                    )
                else:
                    log(f"GPS Settings API Error: set_nav_rate for {rate_hz} Hz failed")
                    return Response(
                        body=json.dumps(
                            {
                                "success": False,
                                "message": "Failed to send set rate command to GPS",
                            }
                        ),
                        status_code=500,
                        headers={"Content-Type": "application/json"},
                    )
            else:
                log(f"GPS Settings API Error: Invalid rate value received: {rate_hz}")
                return Response(
                    body=json.dumps(
                        {
                            "success": False,
                            "message": "Invalid rate value (must be integer 1-10)",
                        }
                    ),
                    status_code=400,
                    headers={"Content-Type": "application/json"},
                )

        else:
            log(f"GPS Settings API Error: Unknown action received: {action}")
            return Response(
                body=json.dumps(
                    {"success": False, "message": f"Unknown action: {action}"}
                ),
                status_code=400,
                headers={"Content-Type": "application/json"},
            )

    except Exception as e:
        log(f"GPS Settings API Error: Exception during action '{action}': {e}")
        # Consider logging traceback if available/needed
        return Response(
            body=json.dumps(
                {"success": False, "message": f"Internal Server Error: {e}"}
            ),
            status_code=500,
            headers={"Content-Type": "application/json"},
        )


async def get_nav_rate(uart: UART, lock: asyncio.Lock):
    """Polls the current navigation measurement and solution rate."""
    if not uart or not lock:
        log("GPS CFG Error: UART or Lock not available for get_nav_rate")
        return None

    await lock.acquire()
    result = None  # Default result
    try:
        log("GPS CFG: Attempting to poll nav rate")
        # Send poll request (empty payload)
        success = await _send_ubx_command(uart, UBX_CLASS_CFG, UBX_CFG_RATE)
        if success:
            # Read the CFG-RATE response (Implementation needed in _read_ubx_response)
            # response_payload = await _read_ubx_response(uart, UBX_CLASS_CFG, UBX_CFG_RATE, timeout_ms=1000)
            # if response_payload and len(response_payload) == 6:
            #     meas_rate_ms, nav_rate_cycles, time_ref = struct.unpack('<HHH', response_payload)
            #     rate_hz = 1000 / meas_rate_ms if meas_rate_ms > 0 else 0
            #     log(f"GPS CFG RX: Current Rate={rate_hz:.2f} Hz (measRate={meas_rate_ms}ms, navRate={nav_rate_cycles}, timeRef={time_ref})")
            #     result = {"rate_hz": rate_hz, "meas_rate_ms": meas_rate_ms, "nav_rate_cycles": nav_rate_cycles, "time_ref": time_ref}
            # else:
            #     log("GPS CFG Error: Did not receive valid CFG-RATE response")
            #     # result remains None

            # For now, return placeholder as response reading isn't implemented
            log("GPS CFG: get_nav_rate poll sent (response reading not implemented)")
            result = {
                "rate_hz": 1.0,  # Placeholder
                "meas_rate_ms": 1000,  # Placeholder
                "nav_rate_cycles": 1,  # Placeholder
                "time_ref": 1,  # Placeholder
            }
        # else: result remains None
    finally:
        lock.release()
    return result


async def factory_reset(uart, lock: asyncio.Lock):
    """Sends a factory reset command to the GPS module."""
    if not uart or not lock:
        log("GPS CFG Error: UART or Lock not available for factory_reset")
        return False

    await lock.acquire()
    result = False  # Default result
    try:
        log("GPS CFG: Attempting factory reset")
        # Payload for CFG-CFG: clearMask (u4), saveMask (u4), loadMask (u4), deviceMask (u1)
        # Masks specify which memory sections to affect (IO, MSG, INF, NAV, RXM, etc.)
        # To reset everything to defaults: clear BBR+Flash, save nothing, load defaults.
        # See u-blox protocol spec for CFG-CFG mask details.
        # Example: Clear all, save nothing, load defaults for BBR and Flash
        clear_mask = 0xFFFF  # Clear everything possible
        save_mask = 0x0000  # Save nothing
        load_mask = 0xFFFF  # Load defaults for everything possible
        device_mask = 0b00000111  # Affects BBR, Flash, EEPROM (if present)

        # <IIIB = 3x unsigned int (4 bytes), 1x unsigned char (1 byte), little-endian
        payload = struct.pack("<IIIB", clear_mask, save_mask, load_mask, device_mask)

        success = await _send_ubx_command(uart, UBX_CLASS_CFG, UBX_CFG_CFG, payload)
        if success:
            # Factory reset takes time, module might restart. No ACK expected.
            log("GPS CFG: Factory reset command sent. Module may restart.")
            # Wait a bit for module to potentially reset
            await asyncio.sleep_ms(1000)
            result = True
        # else: result remains False
    finally:
        lock.release()
    return result
