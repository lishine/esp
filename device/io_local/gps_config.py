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
                f"GPS CFG: Flushed {len(flushed_bytes)} bytes from UART RX buf yeah Manager lunchfer before sending"
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
    uart,
    expected_class_id: int,
    expected_msg_id: int,
    timeout_ms: int = 1000,
    expect_payload: bool = False,  # New parameter
):
    """Reads and validates a specific UBX response message with full protocol handling.
    Can return ACK/NAK status (True/False) or the message payload (bytes).
    Returns None on timeout or checksum error."""
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

            # --- State Machine Logic ---
            if state == "SYNC1":
                if byte[0] == UBX_SYNC_1:
                    state = "SYNC2"
            elif state == "SYNC2":
                if byte[0] == UBX_SYNC_2:
                    state = "HEADER"
                    header_bytes = bytearray()
                else:
                    state = "SYNC1"
            elif state == "HEADER":
                header_bytes.extend(byte)
                if len(header_bytes) == 4:
                    class_id, msg_id, message_length = struct.unpack(
                        "<BBH", header_bytes
                    )
                    # If expecting payload, check if this header matches
                    if (
                        expect_payload
                        and class_id == expected_class_id
                        and msg_id == expected_msg_id
                    ):
                        state = "PAYLOAD"
                        payload = bytearray()
                    # If expecting ACK/NAK, check if this is an ACK message
                    elif not expect_payload and class_id == UBX_CLASS_ACK:
                        state = "PAYLOAD"
                        payload = bytearray()
                    # Otherwise, it's not the message we're looking for right now
                    else:
                        # If message_length is 0, skip payload state
                        if message_length == 0:
                            state = "CHECKSUM"
                            checksum_bytes = bytearray()
                            payload = bytearray()  # Ensure payload is empty
                        else:
                            state = "PAYLOAD"  # Need to read payload to discard it
                            payload = bytearray()
            elif state == "PAYLOAD":
                payload.extend(byte)
                if len(payload) == message_length:
                    state = "CHECKSUM"
                    checksum_bytes = bytearray()
            elif state == "CHECKSUM":
                checksum_bytes.extend(byte)
                if len(checksum_bytes) == 2:
                    # --- Checksum Verification ---
                    calculated = _calculate_ubx_checksum(header_bytes + payload)
                    received_checksum = bytes(checksum_bytes)

                    if received_checksum == calculated:
                        # --- Message Handling ---
                        # Case 1: Expecting a specific payload message
                        if (
                            expect_payload
                            and class_id == expected_class_id
                            and msg_id == expected_msg_id
                        ):
                            log(
                                f"GPS CFG RX: Received expected payload message {class_id:02X}/{msg_id:02X}"
                            )
                            return bytes(payload)  # Return the payload

                        # Case 2: Expecting ACK/NAK for a sent command
                        elif not expect_payload and class_id == UBX_CLASS_ACK:
                            if len(payload) == 2:
                                ack_class, ack_id = struct.unpack("<BB", payload)
                                # Check if ACK/NAK corresponds to the command we *sent*
                                # Note: expected_class_id/msg_id here refer to the *sent* command
                                if (
                                    ack_class == expected_class_id
                                    and ack_id == expected_msg_id
                                ):
                                    if msg_id == UBX_ACK_ACK:
                                        return True  # ACK received for our command
                                    elif msg_id == UBX_ACK_NAK:
                                        log(
                                            f"GPS CFG RX: NAK received for {expected_class_id:02X}/{expected_msg_id:02X}"
                                        )
                                        return False  # NAK received for our command
                                # else: log ACK/NAK for unexpected command
                            # else: log incorrect ACK/NAK payload length

                        # Case 3: Received some other valid message - ignore it
                        # else:
                        #    log(f"GPS CFG RX: Ignoring valid message {class_id:02X}/{msg_id:02X}")

                    else:  # Checksum failed
                        log(
                            f"GPS CFG RX: Checksum error for {class_id:02X}/{msg_id:02X}. Recv={received_checksum.hex()}, Calc={calculated.hex()}"
                        )
                        # Do not return, just reset and keep listening

                    # Reset parser state machine after processing a complete message (good or bad checksum)
                    state = "SYNC1"
        else:
            # No data available, yield control briefly
            time.sleep_ms(5)

    # --- Timeout ---
    log(
        f"GPS CFG RX: Timeout waiting for {expected_class_id:02X}/{expected_msg_id:02X} (expect_payload={expect_payload})"
    )
    return None


def _save_configuration(uart, lock):  # Add lock parameter
    """Helper function to save configuration to non-volatile memory."""
    # Note: This function assumes the caller handles pausing/resuming the reader
    # and acquiring/releasing the lock. It only performs the UART operations.
    # It does NOT handle the pause/resume or lock itself.
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
        uart,
        UBX_CLASS_CFG,
        UBX_CFG_CFG,
        timeout_ms=1500,
        expect_payload=False,  # Expect ACK/NAK
    )  # Allow more time for save
    if response is None:
        log("GPS CFG Error: Timeout waiting for CFG-CFG save ACK")
        return False
    elif not response:  # False means NAK received
        log("GPS CFG Error: No ACK received for CFG-CFG save command (NAK received)")
        return False
    # True means ACK received

    log("GPS CFG: Configuration save command acknowledged")
    return True


def set_nav_rate(uart, lock, rate_hz: int, max_retries: int = 3):
    """Sets the navigation measurement and solution rate with retry mechanism."""
    if not uart or not lock:
        log("GPS CFG Error: UART or Lock not available for set_nav_rate")
        return False

    lock_acquired_by_config = False
    result = False  # Default result
    retry_count = 0
    config_request_event = gps_reader.get_config_request_event()
    config_done_event = gps_reader.get_config_done_event()

    if not config_request_event or not config_done_event:
        log("GPS CFG Error: Could not get sync events for set_nav_rate.")
        return False

    try:
        # --- Signal Reader ---
        log("GPS CFG: Signaling reader task for set_nav_rate...")
        config_request_event.set()

        # --- Acquire Lock (Wait for reader to see event and release lock) ---
        log(
            "GPS CFG: Acquiring UART lock for set_nav_rate (waiting for reader release)..."
        )
        lock_acquired_by_config = lock.acquire(True, 1.5)  # Wait up to 1.5 sec
        if not lock_acquired_by_config:
            log(
                "GPS CFG Error: Could not acquire UART lock for set_nav_rate (timeout waiting for reader release)."
            )
            config_request_event.clear()  # Clear request if we timed out
            return False
        log("GPS CFG: UART lock acquired.")

        # --- Perform UART Operations (Lock Held) ---
        while retry_count < max_retries:
            log(
                f"GPS CFG: Attempting to set nav rate to {rate_hz} Hz (try {retry_count+1}/{max_retries})"
            )

            if rate_hz <= 0:
                log("GPS CFG Error: Invalid rate_hz")
                break  # Exit retry loop

            meas_rate_ms = int(1000 / rate_hz)
            nav_rate_cycles = 1
            time_ref = 1
            payload = struct.pack("<HHH", meas_rate_ms, nav_rate_cycles, time_ref)

            if not _send_ubx_command(uart, UBX_CLASS_CFG, UBX_CFG_RATE, payload):
                log("GPS CFG Error: Failed to send CFG-RATE command")
                retry_count += 1
                time.sleep_ms(100 * (retry_count + 1))
                continue

            response = _read_ubx_response(
                uart,
                UBX_CLASS_CFG,
                UBX_CFG_RATE,
                timeout_ms=1000 * (retry_count + 1),
                expect_payload=False,  # Expect ACK/NAK
            )
            if response is None:
                log("GPS CFG Error: Timeout waiting for CFG-RATE response")
                retry_count += 1
                time.sleep_ms(200 * (retry_count + 1))
                continue
            elif not response:  # False means NAK
                log("GPS CFG Error: NAK received for CFG-RATE command")
                retry_count += 1
                time.sleep_ms(200 * (retry_count + 1))
                continue
            # True means ACK

            log("GPS CFG: CFG-RATE command acknowledged")

            # Try to save configuration
            # _save_configuration is called within the lock
            save_success = _save_configuration(uart, lock)
            if not save_success:
                log(
                    "GPS CFG Warning: Failed to save configuration. Rate change might be temporary."
                )
                # Continue anyway

            result = True
            break  # Exit retry loop on success

        if not result:
            log(f"GPS CFG Error: Failed to set nav rate after {max_retries} attempts")

    finally:
        # --- Signal Reader Done (BEFORE releasing lock) ---
        log("GPS CFG: Signaling reader task done.")
        config_done_event.set()

        # --- Release Lock ---
        if lock_acquired_by_config:
            log("GPS CFG: Releasing UART lock.")
            lock.release()
        # --- Ensure request event is clear (in case of errors before reader saw it) ---
        if config_request_event.is_set():
            config_request_event.clear()

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

        # --- Add Factory Reset Handling ---
        elif action == "factory_reset":
            log("GPS Settings API: Received factory_reset request")
            success = factory_reset(uart, lock)  # Call existing function
            if success:
                log("GPS Settings API: factory_reset successful")
                return Response(
                    body=json.dumps(
                        {
                            "success": True,
                            "message": "Factory reset command sent successfully.",
                        }
                    ),
                    headers={"Content-Type": "application/json"},
                )
            else:
                log("GPS Settings API Error: factory_reset failed")
                return Response(
                    body=json.dumps(
                        {
                            "success": False,
                            "message": "Failed to send factory reset command to GPS.",
                        }
                    ),
                    status=500,
                    headers={"Content-Type": "application/json"},
                )
        # --- End Factory Reset Handling ---

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


def get_nav_rate(uart: UART, lock):
    """Polls and parses the current navigation measurement and solution rate (CFG-RATE)."""
    if not uart or not lock:
        log("GPS CFG Error: UART or Lock not available for get_nav_rate")
        return None

    lock_acquired_by_config = False
    result_data = None
    config_request_event = gps_reader.get_config_request_event()
    config_done_event = gps_reader.get_config_done_event()

    if not config_request_event or not config_done_event:
        log("GPS CFG Error: Could not get sync events.")
        return None

    try:
        # --- Signal Reader ---
        log("GPS CFG: Signaling reader task for get_nav_rate...")
        config_request_event.set()

        # --- Acquire Lock (Wait for reader to see event and release lock) ---
        log(
            "GPS CFG: Acquiring UART lock for get_nav_rate (waiting for reader release)..."
        )
        lock_acquired_by_config = lock.acquire(True, 1.5)  # Wait up to 1.5 sec
        if not lock_acquired_by_config:
            log(
                "GPS CFG Error: Could not acquire UART lock for get_nav_rate (timeout waiting for reader release)."
            )
            config_request_event.clear()  # Clear request if we timed out
            return None
        log("GPS CFG: UART lock acquired.")

        # --- Perform UART Operations (Lock Held) ---
        log("GPS CFG: Polling current nav rate (CFG-RATE)")
        send_ok = _send_ubx_command(uart, UBX_CLASS_CFG, UBX_CFG_RATE)
        if not send_ok:
            log("GPS CFG Error: Failed to send poll request for CFG-RATE")
            # result_data remains None
        else:
            # Reader is waiting, now read response
            response_payload = _read_ubx_response(
                uart,
                expected_class_id=UBX_CLASS_CFG,
                expected_msg_id=UBX_CFG_RATE,
                timeout_ms=1500,
                expect_payload=True,
            )
            # ... (parsing logic) ...
            if response_payload is None:
                log("GPS CFG Error: Timeout or error reading CFG-RATE response")
            elif isinstance(response_payload, bytes) and len(response_payload) == 6:
                meas_rate_ms, nav_rate_cycles, time_ref = struct.unpack(
                    "<HHH", response_payload
                )
                rate_hz = 1000.0 / meas_rate_ms if meas_rate_ms > 0 else 0
                log(
                    f"GPS CFG RX: Parsed CFG-RATE - measRate={meas_rate_ms}ms ({rate_hz:.2f} Hz), navRate={nav_rate_cycles}, timeRef={time_ref}"
                )
                result_data = {  # Populate result
                    "rate_hz": round(rate_hz, 2),
                    "meas_rate_ms": meas_rate_ms,
                    "nav_rate_cycles": nav_rate_cycles,
                    "time_ref": time_ref,
                }
            else:
                log(
                    f"GPS CFG Error: Received unexpected response type or length for CFG-RATE poll. Type: {type(response_payload)}"
                )

    finally:
        # --- Signal Reader Done (BEFORE releasing lock) ---
        log("GPS CFG: Signaling reader task done.")
        config_done_event.set()

        # --- Release Lock ---
        if lock_acquired_by_config:
            log("GPS CFG: Releasing UART lock.")
            lock.release()
        # --- Ensure request event is clear (in case of errors before reader saw it) ---
        if config_request_event.is_set():
            config_request_event.clear()
    return result_data  # Return the dictionary or None


def factory_reset(uart, lock):  # No longer async, lock type hint removed
    """Sends a factory reset command to the GPS module."""
    if not uart or not lock:
        log("GPS CFG Error: UART or Lock not available for factory_reset")
        return False

    lock_acquired_by_config = False
    result = False  # Default result
    config_request_event = gps_reader.get_config_request_event()
    config_done_event = gps_reader.get_config_done_event()

    if not config_request_event or not config_done_event:
        log("GPS CFG Error: Could not get sync events for factory_reset.")
        return False

    try:
        # --- Signal Reader ---
        log("GPS CFG: Signaling reader task for factory_reset...")
        config_request_event.set()

        # --- Acquire Lock (Wait for reader to see event and release lock) ---
        log(
            "GPS CFG: Acquiring UART lock for factory_reset (waiting for reader release)..."
        )
        lock_acquired_by_config = lock.acquire(True, 1.5)  # Wait up to 1.5 sec
        if not lock_acquired_by_config:
            log(
                "GPS CFG Error: Could not acquire UART lock for factory_reset (timeout waiting for reader release)."
            )
            config_request_event.clear()  # Clear request if we timed out
            return False
        log("GPS CFG: UART lock acquired.")

        # --- Perform UART Operations (Lock Held) ---
        log("GPS CFG: Attempting factory reset")
        clear_mask = 0xFFFF
        save_mask = 0x0000
        load_mask = 0xFFFF
        device_mask = 0b00000111
        payload = struct.pack("<IIIB", clear_mask, save_mask, load_mask, device_mask)

        success = _send_ubx_command(uart, UBX_CLASS_CFG, UBX_CFG_CFG, payload)
        if success:
            log("GPS CFG: Factory reset command sent. Module may restart. Waiting...")
            # Wait for module to potentially reset and start up
            # Note: No ACK check here as reset behavior varies.
            time.sleep_ms(1500)
            result = True
        else:
            log("GPS CFG Error: Failed to send factory reset command")
            result = False

    finally:
        # --- Signal Reader Done (BEFORE releasing lock) ---
        log("GPS CFG: Signaling reader task done.")
        config_done_event.set()

        # --- Release Lock ---
        if lock_acquired_by_config:
            log("GPS CFG: Releasing UART lock.")
            lock.release()
        # --- Ensure request event is clear (in case of errors before reader saw it) ---
        if config_request_event.is_set():
            config_request_event.clear()
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
    # This function might also need the event/lock logic if the reader is running
    # For simplicity, assuming it's called when reader is already stopped or
    # doesn't interfere significantly over the measurement period.
    # If issues arise, apply the same pattern here.

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
