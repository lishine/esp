import uasyncio as asyncio
import struct
import time
import json
from log import log
from machine import UART
from . import gps_reader  # Relative import for reader module
from server_framework import Response, Request

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


def _calculate_ubx_checksum(data: bytes) -> bytes:
    """Calculates the 2-byte Fletcher checksum for UBX messages.
    Data should contain Class ID + Message ID + Length + Payload data."""
    ck_a = 0
    ck_b = 0
    for byte in data:
        ck_a = (ck_a + byte) & 0xFF
        ck_b = (ck_b + ck_a) & 0xFF
    return bytes([ck_a, ck_b])


def _send_ubx_command(uart: UART, class_id: int, msg_id: int, payload: bytes = b""):
    """Constructs and sends a UBX command message."""
    msg_len = len(payload)

    # Flush UART buffer before sending
    if uart and uart.any():
        flushed_bytes = uart.read(uart.any())
        if flushed_bytes:
            log(
                f"GPS CFG: Flushed {len(flushed_bytes)} bytes from UART RX buffer before sending"
            )

    # Build message header: Class + ID + Length
    header = struct.pack("<BBH", class_id, msg_id, msg_len)

    # Calculate checksum over: Class + ID + Length + Payload
    checksum = _calculate_ubx_checksum(header + payload)

    # Construct full message: Sync chars + Header + Payload + Checksum
    sync = struct.pack("<BB", UBX_SYNC_1, UBX_SYNC_2)
    full_message = sync + header + payload + checksum

    log(f"GPS CFG TX: {full_message.hex()}")  # Log hex representation

    # Send message
    if uart:
        written = uart.write(full_message)
        if written != len(full_message):
            log(f"GPS CFG TX Error: Wrote {written}/{len(full_message)} bytes")
            return False
        return True
    else:
        log("GPS CFG TX Error: UART not available")
        return False


def _read_ubx_response(
    uart, expected_class_id: int, expected_msg_id: int, timeout_ms: int = 1000
):
    """Reads and validates a specific UBX response message (ACK/NAK) with full protocol handling.
    Increased default timeout to 1000ms."""
    start_time = time.ticks_ms()
    state = "SYNC1"
    message_length = 0
    checksum_bytes = bytearray()
    class_id = 0
    msg_id = 0
    payload = bytearray()
    header_bytes = bytearray()  # Stores Class, ID, Length

    while time.ticks_diff(time.ticks_ms(), start_time) < timeout_ms:
        if uart.any():
            byte = uart.read(1)
            if not byte:
                continue

            # log(f"State: {state}, Byte: {byte.hex()}") # Debugging

            if state == "SYNC1":
                if byte[0] == UBX_SYNC_1:
                    state = "SYNC2"
            elif state == "SYNC2":
                if byte[0] == UBX_SYNC_2:
                    state = "HEADER"
                    header_bytes = bytearray()  # Reassign instead of clear()
                else:
                    state = "SYNC1"  # Reset if second sync byte is wrong
            elif state == "HEADER":
                header_bytes.extend(byte)
                if len(header_bytes) == 4:  # Class(1) + ID(1) + Length(2)
                    class_id, msg_id, message_length = struct.unpack(
                        "<BBH", header_bytes
                    )
                    # log(f"Header parsed: Class={class_id:02X}, ID={msg_id:02X}, Len={message_length}") # Debugging
                    if message_length == 0:  # ACK/NAK has 2 byte payload, not 0
                        if class_id == UBX_CLASS_ACK:
                            state = "PAYLOAD"
                            payload = bytearray()  # Reassign instead of clear()
                        else:  # Unexpected message type with 0 payload length
                            log(
                                f"GPS CFG RX: Unexpected message {class_id:02X}/{msg_id:02X} with 0 length"
                            )
                            state = "SYNC1"  # Reset parser
                    else:
                        state = "PAYLOAD"
                        payload = bytearray()  # Reassign instead of clear()
            elif state == "PAYLOAD":
                payload.extend(byte)
                if len(payload) == message_length:
                    state = "CHECKSUM"
                    checksum_bytes = bytearray()  # Reassign instead of clear()
            elif state == "CHECKSUM":
                checksum_bytes.extend(byte)
                if len(checksum_bytes) == 2:
                    # Checksum is calculated over: Class + ID + Length + Payload
                    calculated = _calculate_ubx_checksum(header_bytes + payload)
                    received_checksum = bytes(checksum_bytes)

                    # log(f"Checksum: Recv={received_checksum.hex()}, Calc={calculated.hex()}") # Debugging

                    if received_checksum == calculated:
                        # log(f"GPS CFG RX: Valid message received: Class={class_id:02X}, ID={msg_id:02X}") # Debugging
                        # Check if it's the ACK/NAK we are expecting
                        if class_id == UBX_CLASS_ACK:
                            if (
                                len(payload) == 2
                            ):  # ACK/NAK payload is Class/ID of ack'd msg
                                ack_class, ack_id = struct.unpack("<BB", payload)
                                if (
                                    ack_class == expected_class_id
                                    and ack_id == expected_msg_id
                                ):
                                    if msg_id == UBX_ACK_ACK:
                                        # log(f"GPS CFG RX: ACK received for {expected_class_id:02X}/{expected_msg_id:02X}")
                                        return True  # Correct ACK received
                                    elif msg_id == UBX_ACK_NAK:
                                        log(
                                            f"GPS CFG RX: NAK received for {expected_class_id:02X}/{expected_msg_id:02X}"
                                        )
                                        return False  # NAK received
                                else:
                                    log(
                                        f"GPS CFG RX: ACK/NAK received for unexpected msg {ack_class:02X}/{ack_id:02X}"
                                    )
                            else:
                                log(
                                    f"GPS CFG RX: ACK/NAK received with incorrect payload length {len(payload)}"
                                )
                        # else: # Ignore other valid messages while waiting for ACK/NAK
                        #    log(f"GPS CFG RX: Ignoring valid message {class_id:02X}/{msg_id:02X} while waiting for ACK")
                        #    pass
                    else:
                        log(
                            f"GPS CFG RX: Checksum error for {class_id:02X}/{msg_id:02X}. Recv={received_checksum.hex()}, Calc={calculated.hex()}"
                        )

                    # Reset parser state machine whether checksum was good or bad
                    state = "SYNC1"
        else:
            # No data available, yield control briefly
            time.sleep_ms(5)  # Short sleep when buffer is empty

    log(
        f"GPS CFG RX: Timeout waiting for ACK/NAK for {expected_class_id:02X}/{expected_msg_id:02X}"
    )
    return None  # Timeout


def _save_configuration(uart):
    """Helper function to save configuration to non-volatile memory."""
    log("GPS CFG: Attempting to save configuration to non-volatile memory")
    # Send CFG-CFG command to save configuration
    clear_mask = 0x0000  # Clear nothing
    save_mask = 0xFFFF  # Save all sections (IO, MSG, INF, NAV, RXM, etc.)
    load_mask = 0x0000  # Load nothing
    # deviceMask: bit 0=devBBR, bit 1=devFlash, bit 2=devEEPROM, bit 4=devSpiFlash
    # Save to BBR, Flash, EEPROM (if available)
    device_mask = 0b00000111

    payload = struct.pack("<IIIB", clear_mask, save_mask, load_mask, device_mask)

    if not _send_ubx_command(uart, UBX_CLASS_CFG, UBX_CFG_CFG, payload):
        log("GPS CFG Error: Failed to send CFG-CFG save command")
        return False

    # Wait for ACK
    response = _read_ubx_response(
        uart, UBX_CLASS_CFG, UBX_CFG_CFG, timeout_ms=1500
    )  # Allow more time for save
    if response is None:
        log("GPS CFG Error: Timeout waiting for CFG-CFG save ACK")
        return False
    elif not response:
        log("GPS CFG Error: No ACK received for CFG-CFG save command (NAK received)")
        return False

    log("GPS CFG: Configuration save command acknowledged")
    return True


def set_nav_rate(uart, lock, rate_hz: int, max_retries: int = 3):
    """Sets the navigation measurement and solution rate with retry mechanism."""
    if not uart or not lock:
        log("GPS CFG Error: UART or Lock not available for set_nav_rate")
        return False

    lock_acquired = False
    result = False  # Default result
    retry_count = 0

    try:
        lock_acquired = lock.acquire(True, 1.0)  # Blocking acquire with timeout
        if not lock_acquired:
            log("GPS CFG Error: Could not acquire UART lock for set_nav_rate")
            return False  # Exit if lock not acquired

        while retry_count < max_retries:
            log(
                f"GPS CFG: Attempting to set nav rate to {rate_hz} Hz (try {retry_count+1}/{max_retries})"
            )

            if rate_hz <= 0:
                log("GPS CFG Error: Invalid rate_hz")
                break  # Exit loop if rate is invalid

            # Calculate parameters
            meas_rate_ms = int(1000 / rate_hz)
            nav_rate_cycles = 1  # Output a solution for every measurement
            time_ref = 1  # 0=UTC, 1=GPS time (use GPS time for NAV-RATE)

            # Payload: measRate (ms, u2), navRate (cycles, u2), timeRef (0=UTC, 1=GPS, u2)
            payload = struct.pack("<HHH", meas_rate_ms, nav_rate_cycles, time_ref)

            # Send CFG-RATE command
            if not _send_ubx_command(uart, UBX_CLASS_CFG, UBX_CFG_RATE, payload):
                log("GPS CFG Error: Failed to send CFG-RATE command")
                retry_count += 1
                time.sleep_ms(100 * (retry_count + 1))  # Incremental backoff
                continue

            # Wait for ACK with longer timeout on retries
            response = _read_ubx_response(
                uart, UBX_CLASS_CFG, UBX_CFG_RATE, timeout_ms=1000 * (retry_count + 1)
            )
            if response is None:
                log("GPS CFG Error: Timeout waiting for CFG-RATE response")
                retry_count += 1
                time.sleep_ms(200 * (retry_count + 1))  # Incremental backoff
                continue
            elif not response:
                log(
                    "GPS CFG Error: No ACK received for CFG-RATE command (NAK received)"
                )
                retry_count += 1
                time.sleep_ms(200 * (retry_count + 1))  # Incremental backoff
                continue

            log("GPS CFG: CFG-RATE command acknowledged")

            # Try to save configuration to non-volatile memory
            save_success = _save_configuration(uart)
            if not save_success:
                log(
                    "GPS CFG Warning: Failed to save configuration to non-volatile memory. Rate change might be temporary."
                )
                # Continue anyway, rate change might still work until power cycle

            # Configuration successfully changed (and hopefully saved)
            result = True
            break  # Exit retry loop on success

        if not result:
            log(f"GPS CFG Error: Failed to set nav rate after {max_retries} attempts")

    finally:
        if lock_acquired:
            lock.release()  # Release only if acquired

    return result


def handle_gps_settings_data(request: Request):
    """Handles getting and setting GPS configuration via UBX commands."""
    config = json.loads(request.body)

    action = config.get("action")
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
            status=500,
            headers={"Content-Type": "application/json"},
        )

    try:
        if action == "get_rate":
            log("GPS Settings API: Received get_rate request")
            # Call local function directly
            rate_data = get_nav_rate(uart, lock)
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
                    status=500,
                    headers={"Content-Type": "application/json"},
                )

        elif action == "set_rate":
            rate_hz = config.get("rate")
            log(f"GPS Settings API: Received set_rate request for {rate_hz} Hz")
            if isinstance(rate_hz, int) and 1 <= rate_hz <= 10:  # Basic validation
                # Call local function directly with retry mechanism
                success = set_nav_rate(uart, lock, rate_hz)  # Uses default retries=3
                if success:
                    log(f"GPS Settings API: set_nav_rate for {rate_hz} Hz successful")
                    # Optional: Add verification step here if needed
                    # verified = verify_nav_rate(uart, lock, rate_hz)
                    # log(f"GPS Settings API: Rate verification result: {verified}")
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
                                "message": "Failed to send set rate command to GPS after retries",
                            }
                        ),
                        status=500,
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
                    status=400,
                    headers={"Content-Type": "application/json"},
                )

        else:
            log(f"GPS Settings API Error: Unknown action received: {action}")
            return Response(
                body=json.dumps(
                    {"success": False, "message": f"Unknown action: {action}"}
                ),
                status=400,
                headers={"Content-Type": "application/json"},
            )

    except Exception as e:
        log(f"GPS Settings API Error: Exception during action '{action}': {e}")
        # Consider logging traceback if available/needed
        import sys

        sys.print_exception(e)  # Print traceback for debugging
        return Response(
            body=json.dumps(
                {"success": False, "message": f"Internal Server Error: {e}"}
            ),
            status=500,
            headers={"Content-Type": "application/json"},
        )


def get_nav_rate(uart: UART, lock):  # Lock type hint removed
    """Polls the current navigation measurement and solution rate."""
    if not uart or not lock:
        log("GPS CFG Error: UART or Lock not available for get_nav_rate")
        return None

    lock_acquired = False
    result = None  # Default result
    try:
        lock_acquired = lock.acquire(True, 1.0)  # Blocking acquire with timeout
        if not lock_acquired:
            log("GPS CFG Error: Could not acquire UART lock for get_nav_rate")
            return None  # Exit if lock not acquired
        log("GPS CFG: Attempting to poll nav rate")
        # Send poll request (empty payload)
        success = _send_ubx_command(uart, UBX_CLASS_CFG, UBX_CFG_RATE)
        if success:
            # Read the CFG-RATE response (Implementation needed in _read_ubx_response)
            # For now, return placeholder as response reading isn't implemented
            # TODO: Implement reading the actual CFG-RATE response payload
            log("GPS CFG: get_nav_rate poll sent (response reading not implemented)")
            result = {
                "rate_hz": 1.0,  # Placeholder - Needs actual implementation
                "meas_rate_ms": 1000,  # Placeholder
                "nav_rate_cycles": 1,  # Placeholder
                "time_ref": 1,  # Placeholder
            }
        else:
            log("GPS CFG Error: Failed to send poll request for CFG-RATE")
            result = None
    finally:
        if lock_acquired:
            lock.release()  # Release only if acquired
    return result


def factory_reset(uart, lock):  # No longer async, lock type hint removed
    """Sends a factory reset command to the GPS module."""
    if not uart or not lock:
        log("GPS CFG Error: UART or Lock not available for factory_reset")
        return False

    lock_acquired = False
    result = False  # Default result
    try:
        lock_acquired = lock.acquire(True, 1.0)  # Blocking acquire with timeout
        if not lock_acquired:
            log("GPS CFG Error: Could not acquire UART lock for factory_reset")
            return False  # Exit if lock not acquired
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

        success = _send_ubx_command(uart, UBX_CLASS_CFG, UBX_CFG_CFG, payload)
        if success:
            # Factory reset takes time, module might restart. No ACK expected.
            # Some modules might send an ACK, but it's not guaranteed after a reset.
            log("GPS CFG: Factory reset command sent. Module may restart. Waiting...")
            # Wait a bit for module to potentially reset and start up
            time.sleep_ms(1500)  # Increased wait time
            result = True
        else:
            log("GPS CFG Error: Failed to send factory reset command")
            result = False
    finally:
        if lock_acquired:
            lock.release()  # Release only if acquired
    return result


# Optional: Verification function (from implementation plan)
def verify_nav_rate(uart, lock, expected_rate_hz: int, timeout_ms: int = 5000):
    """Verifies that the navigation rate has been set correctly by measuring the
    frequency of incoming NMEA sentences over a short time period."""
    if not uart or not lock:
        log("GPS CFG Error: UART or Lock not available for verify_nav_rate")
        return False

    lock_acquired = False
    result = False

    try:
        lock_acquired = lock.acquire(True, 1.0)
        if not lock_acquired:
            log("GPS CFG Error: Could not acquire UART lock for verify_nav_rate")
            return False

        log(f"GPS CFG: Verifying navigation rate is {expected_rate_hz} Hz")

        # Clear any pending data
        if uart.any():
            flushed_bytes = uart.read(uart.any())
            log(f"GPS Verify: Flushed {len(flushed_bytes)} bytes from UART buffer")

        # Count NMEA sentences over a period
        start_time = time.ticks_ms()
        sentence_count = 0

        while time.ticks_diff(time.ticks_ms(), start_time) < timeout_ms:
            if uart.any():
                line = uart.readline()
                if line and line.startswith(
                    b"$"
                ):  # Basic check for NMEA sentence start
                    sentence_count += 1

            # Yield control briefly
            time.sleep_ms(10)

        # Calculate measured rate
        elapsed_sec = time.ticks_diff(time.ticks_ms(), start_time) / 1000.0
        measured_rate = sentence_count / elapsed_sec if elapsed_sec > 0 else 0

        log(
            f"GPS Verify: Measured rate: {measured_rate:.2f} Hz over {elapsed_sec:.1f}s (expected: {expected_rate_hz} Hz)"
        )

        # Allow for some variation (e.g., ±20%)
        min_acceptable = expected_rate_hz * 0.8
        max_acceptable = expected_rate_hz * 1.2

        if min_acceptable <= measured_rate <= max_acceptable:
            log(
                f"GPS Verify: Navigation rate successfully verified at ~{measured_rate:.2f} Hz"
            )
            result = True
        else:
            log(
                f"GPS Verify Error: Navigation rate verification failed. "
                + f"Measured {measured_rate:.2f} Hz, expected {expected_rate_hz} Hz"
            )
            result = False

    finally:
        if lock_acquired:
            lock.release()

    return result
