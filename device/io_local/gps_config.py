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

    # Flush UART buffer before sending (Still useful even without reader running)
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

    log(f"GPS CFG TX: {full_message.hex()}")

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
    expect_payload: bool = False,
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
    header_bytes = bytearray()

    while time.ticks_diff(time.ticks_ms(), start_time) < timeout_ms:
        if uart.any():
            byte = uart.read(1)
            if not byte:
                continue

            # State Machine Logic
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
                    state = "PAYLOAD" if message_length > 0 else "CHECKSUM"
                    payload = bytearray()
                    checksum_bytes = bytearray()
            elif state == "PAYLOAD":
                payload.extend(byte)
                if len(payload) == message_length:
                    state = "CHECKSUM"
            elif state == "CHECKSUM":
                checksum_bytes.extend(byte)
                if len(checksum_bytes) == 2:
                    # Checksum Verification
                    calculated = _calculate_ubx_checksum(header_bytes + payload)
                    received_checksum = bytes(checksum_bytes)

                    if received_checksum == calculated:
                        # Message Handling
                        if (
                            expect_payload
                            and class_id == expected_class_id
                            and msg_id == expected_msg_id
                        ):
                            log(
                                f"GPS CFG RX: Received expected payload message {class_id:02X}/{msg_id:02X}"
                            )
                            return bytes(payload)
                        elif not expect_payload and class_id == UBX_CLASS_ACK:
                            if len(payload) == 2:
                                ack_class, ack_id = struct.unpack("<BB", payload)
                                if (
                                    ack_class == expected_class_id
                                    and ack_id == expected_msg_id
                                ):
                                    if msg_id == UBX_ACK_ACK:
                                        return True
                                    elif msg_id == UBX_ACK_NAK:
                                        log(
                                            f"GPS CFG RX: NAK received for {expected_class_id:02X}/{expected_msg_id:02X}"
                                        )
                                        return False
                        log(
                            f"GPS CFG RX: Ignoring valid but unexpected message {class_id:02X}/{msg_id:02X}"
                        )
                    else:
                        log(
                            f"GPS CFG RX: Checksum error for {class_id:02X}/{msg_id:02X}. Recv={received_checksum.hex()}, Calc={calculated.hex()}"
                        )

                    state = "SYNC1"  # Reset parser
        else:
            time.sleep_ms(5)  # Yield briefly

    log(
        f"GPS CFG RX: Timeout waiting for {expected_class_id:02X}/{expected_msg_id:02X} (expect_payload={expect_payload})"
    )
    return None


def _save_configuration(uart):  # Removed lock parameter
    """Helper function to save configuration to non-volatile memory."""
    # Assumes reader is stopped by user before calling
    log("GPS CFG: Attempting to save configuration to non-volatile memory")
    clear_mask = 0x0000
    save_mask = 0xFFFF
    load_mask = 0x0000
    device_mask = 0b00000111
    payload = struct.pack("<IIIB", clear_mask, save_mask, load_mask, device_mask)

    if not _send_ubx_command(uart, UBX_CLASS_CFG, UBX_CFG_CFG, payload):
        log("GPS CFG Error: Failed to send CFG-CFG save command")
        return False

    response = _read_ubx_response(
        uart, UBX_CLASS_CFG, UBX_CFG_CFG, timeout_ms=1500, expect_payload=False
    )
    if response is None:
        log("GPS CFG Error: Timeout waiting for CFG-CFG save ACK")
        return False
    elif not response:
        log("GPS CFG Error: No ACK received for CFG-CFG save command (NAK received)")
        return False

    log("GPS CFG: Configuration save command acknowledged")
    return True


def set_nav_rate(uart, rate_hz: int, max_retries: int = 3):  # Removed lock parameter
    """Sets the navigation measurement and solution rate with retry mechanism."""
    # Assumes reader is stopped by user before calling
    if not uart:
        log("GPS CFG Error: UART not available for set_nav_rate")
        return False

    result = False
    retry_count = 0

    while retry_count < max_retries:
        log(
            f"GPS CFG: Attempting to set nav rate to {rate_hz} Hz (try {retry_count+1}/{max_retries})"
        )

        if rate_hz <= 0:
            log("GPS CFG Error: Invalid rate_hz")
            break

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
            expect_payload=False,
        )
        if response is None:
            log("GPS CFG Error: Timeout waiting for CFG-RATE response")
            retry_count += 1
            time.sleep_ms(200 * (retry_count + 1))
            continue
        elif not response:
            log("GPS CFG Error: NAK received for CFG-RATE command")
            retry_count += 1
            time.sleep_ms(200 * (retry_count + 1))
            continue

        log("GPS CFG: CFG-RATE command acknowledged")

        # Try to save configuration
        save_success = _save_configuration(uart)  # Removed lock
        if not save_success:
            log(
                "GPS CFG Warning: Failed to save configuration. Rate change might be temporary."
            )

        result = True
        break  # Exit retry loop on success

    if not result:
        log(f"GPS CFG Error: Failed to set nav rate after {max_retries} attempts")

    return result


def handle_gps_settings_data(request: Request):
    """Handles getting and setting GPS configuration via UBX commands."""
    config = json.loads(request.body)
    action = config.get("action")
    uart = gps_reader.get_uart()
    # lock = gps_reader.get_uart_lock() # REMOVED

    # if not uart or not lock: # REMOVED lock check
    if not uart:
        log("GPS Settings API Error: UART not available")
        return Response(
            body=json.dumps(
                {
                    "success": False,
                    "message": "Internal Server Error: GPS UART unavailable",
                }
            ),
            status=500,
            headers={"Content-Type": "application/json"},
        )

    reader_enabled_event = gps_reader.get_reader_enabled_event()
    if not reader_enabled_event:
        log("GPS Settings API Error: Could not get reader enabled event.")
        return Response(
            body=json.dumps(
                {
                    "success": False,
                    "message": "Internal Server Error: Event unavailable",
                }
            ),
            status=500,
            headers={"Content-Type": "application/json"},
        )

    try:
        if action == "get_rate":
            log("GPS Settings API: Received get_rate request")
            # WARNING: User must manually disable reader first!
            if reader_enabled_event.is_set():
                log(
                    "GPS Settings API Warning: get_rate called while reader may be active!"
                )
            rate_data = get_nav_rate(uart)  # REMOVED lock
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
            log("GPS Settings API: Received set_rate request")
            # WARNING: User must manually disable reader first!
            if reader_enabled_event.is_set():
                log(
                    "GPS Settings API Warning: set_rate called while reader may be active!"
                )
            rate_hz = config.get("rate")
            if isinstance(rate_hz, int) and 1 <= rate_hz <= 10:
                success = set_nav_rate(uart, rate_hz)  # REMOVED lock
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

        elif action == "factory_reset":
            log("GPS Settings API: Received factory_reset request")
            # WARNING: User must manually disable reader first!
            if reader_enabled_event.is_set():
                log(
                    "GPS Settings API Warning: factory_reset called while reader may be active!"
                )
            success = factory_reset(uart)  # REMOVED lock
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

        # --- Add Reader Control Actions ---
        elif action == "start_reader":
            log("GPS Settings API: Received start_reader request")
            reader_enabled_event.set()
            # Optionally call start_gps_reader ensure task is running if stopped previously
            gps_reader.start_gps_reader()
            log("GPS Settings API: Reader enabled.")
            return Response(
                body=json.dumps({"success": True, "message": "GPS Reader enabled."}),
                headers={"Content-Type": "application/json"},
            )

        elif action == "stop_reader":
            log("GPS Settings API: Received stop_reader request")
            reader_enabled_event.clear()
            log("GPS Settings API: Reader disabled.")
            # We don't stop the task itself, just signal it to pause in its loop
            return Response(
                body=json.dumps({"success": True, "message": "GPS Reader disabled."}),
                headers={"Content-Type": "application/json"},
            )
        # --- End Reader Control Actions ---

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
        import sys

        sys.print_exception(e)
        # Ensure reader is re-enabled on error? Maybe not, user controls it.
        # reader_enabled_event.set()
        return Response(
            body=json.dumps(
                {"success": False, "message": f"Internal Server Error: {e}"}
            ),
            status=500,
            headers={"Content-Type": "application/json"},
        )


def get_nav_rate(uart: UART):  # Removed lock parameter
    """Polls and parses the current navigation measurement and solution rate (CFG-RATE)."""
    # Assumes reader is stopped by user before calling
    if not uart:
        log("GPS CFG Error: UART not available for get_nav_rate")
        return None

    result_data = None
    try:
        log("GPS CFG: Polling current nav rate (CFG-RATE)")
        send_ok = _send_ubx_command(uart, UBX_CLASS_CFG, UBX_CFG_RATE)
        if not send_ok:
            log("GPS CFG Error: Failed to send poll request for CFG-RATE")
        else:
            response_payload = _read_ubx_response(
                uart, UBX_CLASS_CFG, UBX_CFG_RATE, timeout_ms=1500, expect_payload=True
            )
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
                result_data = {
                    "rate_hz": round(rate_hz, 2),
                    "meas_rate_ms": meas_rate_ms,
                    "nav_rate_cycles": nav_rate_cycles,
                    "time_ref": time_ref,
                }
            else:
                log(
                    f"GPS CFG Error: Received unexpected response type or length for CFG-RATE poll. Type: {type(response_payload)}"
                )
    except Exception as e:
        log(f"Error during get_nav_rate: {e}")
        # Consider re-raising or specific handling

    return result_data


def factory_reset(uart):  # Removed lock parameter
    """Sends a factory reset command to the GPS module."""
    # Assumes reader is stopped by user before calling
    if not uart:
        log("GPS CFG Error: UART not available for factory_reset")
        return False

    result = False
    try:
        log("GPS CFG: Attempting factory reset")
        clear_mask = 0xFFFF
        save_mask = 0x0000
        load_mask = 0xFFFF
        device_mask = 0b00000111
        payload = struct.pack("<IIIB", clear_mask, save_mask, load_mask, device_mask)

        success = _send_ubx_command(uart, UBX_CLASS_CFG, UBX_CFG_CFG, payload)
        if success:
            log("GPS CFG: Factory reset command sent. Module may restart. Waiting...")
            time.sleep_ms(1500)
            result = True
        else:
            log("GPS CFG Error: Failed to send factory reset command")
            result = False
    except Exception as e:
        log(f"Error during factory_reset: {e}")
        result = False

    return result


# Optional: Verification function (from implementation plan)
def verify_nav_rate(
    uart, expected_rate_hz: int, timeout_ms: int = 5000
):  # Removed lock parameter
    """Verifies that the navigation rate has been set correctly by measuring the
    frequency of incoming NMEA sentences over a short time period."""
    # Assumes reader is stopped by user before calling
    if not uart:
        log("GPS CFG Error: UART not available for verify_nav_rate")
        return False

    result = False
    try:
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
                if line and line.startswith(b"$"):
                    sentence_count += 1
            time.sleep_ms(10)  # Yield control briefly

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
                f"GPS Verify Error: Navigation rate verification failed. Measured {measured_rate:.2f} Hz, expected {expected_rate_hz} Hz"
            )
            result = False

    except Exception as e:
        log(f"Error during verify_nav_rate: {e}")
        result = False

    return result
