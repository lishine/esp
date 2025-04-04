# Get Navigation Rate Implementation Plan

This plan details the modifications needed for `_read_ubx_response` and `get_nav_rate` in `device/io_local/gps_config.py` to correctly poll and parse the current navigation rate from the GPS module.

## 1. Modify `_read_ubx_response`

The function needs to be enhanced to return the message payload when expecting a specific message type, instead of just handling ACK/NAK for sent commands.

**Current `_read_ubx_response` (Relevant Logic):**

```python
# ... inside the checksum valid block ...
if received_checksum == calculated:
    # Check if it's the ACK/NAK we are expecting
    if class_id == UBX_CLASS_ACK:
        if len(payload) == 2: # ACK/NAK payload is Class/ID of ack'd msg
            ack_class, ack_id = struct.unpack("<BB", payload)
            if ack_class == expected_class_id and ack_id == expected_msg_id:
                if msg_id == UBX_ACK_ACK:
                    return True # Correct ACK received
                elif msg_id == UBX_ACK_NAK:
                    log(...)
                    return False # NAK received
            # ... handle unexpected ACK/NAK ...
        # ... handle incorrect ACK/NAK payload length ...
    # else: # Ignore other valid messages
    #    pass
# ... handle checksum error ...
# ... handle timeout ...
return None
```

**Proposed Changes for `_read_ubx_response`:**

```python
def _read_ubx_response(
    uart,
    expected_class_id: int,
    expected_msg_id: int,
    timeout_ms: int = 1000,
    expect_payload: bool = False, # New parameter
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

            # --- State Machine Logic (largely unchanged) ---
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
                    class_id, msg_id, message_length = struct.unpack("<BBH", header_bytes)
                    # If expecting payload, check if this header matches
                    if expect_payload and class_id == expected_class_id and msg_id == expected_msg_id:
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
                             payload = bytearray() # Ensure payload is empty
                         else:
                             state = "PAYLOAD" # Need to read payload to discard it
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
                        if expect_payload and class_id == expected_class_id and msg_id == expected_msg_id:
                            log(f"GPS CFG RX: Received expected payload message {class_id:02X}/{msg_id:02X}")
                            return bytes(payload) # Return the payload

                        # Case 2: Expecting ACK/NAK for a sent command
                        elif not expect_payload and class_id == UBX_CLASS_ACK:
                            if len(payload) == 2:
                                ack_class, ack_id = struct.unpack("<BB", payload)
                                # Check if ACK/NAK corresponds to the command we *sent*
                                # Note: expected_class_id/msg_id here refer to the *sent* command
                                if ack_class == expected_class_id and ack_id == expected_msg_id:
                                    if msg_id == UBX_ACK_ACK:
                                        return True # ACK received for our command
                                    elif msg_id == UBX_ACK_NAK:
                                        log(f"GPS CFG RX: NAK received for {expected_class_id:02X}/{expected_msg_id:02X}")
                                        return False # NAK received for our command
                                # else: log ACK/NAK for unexpected command
                            # else: log incorrect ACK/NAK payload length

                        # Case 3: Received some other valid message - ignore it
                        # else:
                        #    log(f"GPS CFG RX: Ignoring valid message {class_id:02X}/{msg_id:02X}")

                    else: # Checksum failed
                        log(f"GPS CFG RX: Checksum error for {class_id:02X}/{msg_id:02X}. Recv={received_checksum.hex()}, Calc={calculated.hex()}")
                        # Do not return, just reset and keep listening

                    # Reset parser state machine after processing a complete message (good or bad checksum)
                    state = "SYNC1"
        else:
            # No data available, yield control briefly
            time.sleep_ms(5)

    # --- Timeout ---
    log(f"GPS CFG RX: Timeout waiting for {expected_class_id:02X}/{expected_msg_id:02X} (expect_payload={expect_payload})")
    return None
```

**Key Changes in `_read_ubx_response`:**

1.  Added `expect_payload: bool = False` parameter.
2.  Modified the state machine logic in the `HEADER` state to check if the incoming message header matches the expectation based on `expect_payload`.
3.  Modified the message handling logic after checksum validation:
    - If `expect_payload` is `True` and the message matches, return `bytes(payload)`.
    - If `expect_payload` is `False` and an ACK/NAK matching the _sent_ command is received, return `True` or `False`.
    - Ignore other valid messages.
4.  Improved logging for timeouts and errors.

## 2. Update `get_nav_rate`

Use the modified `_read_ubx_response` to poll and parse the CFG-RATE message.

**Current `get_nav_rate`:**

```python
def get_nav_rate(uart: UART, lock):
    # ... lock acquisition ...
    success = _send_ubx_command(uart, UBX_CLASS_CFG, UBX_CFG_RATE) # Poll request
    if success:
        # TODO: Implement reading the actual CFG-RATE response payload
        log("GPS CFG: get_nav_rate poll sent (response reading not implemented)")
        result = { # Placeholder data
            "rate_hz": 1.0,
            "meas_rate_ms": 1000,
            "nav_rate_cycles": 1,
            "time_ref": 1,
        }
    # ... error handling & lock release ...
    return result
```

**Proposed `get_nav_rate`:**

```python
def get_nav_rate(uart: UART, lock):
    """Polls and parses the current navigation measurement and solution rate (CFG-RATE)."""
    if not uart or not lock:
        log("GPS CFG Error: UART or Lock not available for get_nav_rate")
        return None

    lock_acquired = False
    result_data = None
    try:
        lock_acquired = lock.acquire(True, 1.0)
        if not lock_acquired:
            log("GPS CFG Error: Could not acquire UART lock for get_nav_rate")
            return None

        log("GPS CFG: Polling current nav rate (CFG-RATE)")
        # Send poll request (empty payload)
        if not _send_ubx_command(uart, UBX_CLASS_CFG, UBX_CFG_RATE):
             log("GPS CFG Error: Failed to send poll request for CFG-RATE")
             return None # Exit if send fails

        # Expect the CFG-RATE message itself as the response (with payload)
        response_payload = _read_ubx_response(
            uart,
            expected_class_id=UBX_CLASS_CFG,
            expected_msg_id=UBX_CFG_RATE,
            timeout_ms=1500, # Allow reasonable time for response
            expect_payload=True
        )

        if response_payload is None:
            log("GPS CFG Error: Timeout or error reading CFG-RATE response")
            # result_data remains None
        elif isinstance(response_payload, bytes) and len(response_payload) == 6:
            # Payload: measRate (ms, u2), navRate (cycles, u2), timeRef (u2)
            meas_rate_ms, nav_rate_cycles, time_ref = struct.unpack('<HHH', response_payload)
            rate_hz = 1000.0 / meas_rate_ms if meas_rate_ms > 0 else 0

            log(f"GPS CFG RX: Parsed CFG-RATE - measRate={meas_rate_ms}ms ({rate_hz:.2f} Hz), navRate={nav_rate_cycles}, timeRef={time_ref}")
            result_data = {
                "rate_hz": round(rate_hz, 2),
                "meas_rate_ms": meas_rate_ms,
                "nav_rate_cycles": nav_rate_cycles,
                "time_ref": time_ref,
            }
        else:
            # Received something unexpected (e.g., ACK/NAK bool, or wrong payload)
            log(f"GPS CFG Error: Received unexpected response type or length for CFG-RATE poll. Type: {type(response_payload)}")
            # result_data remains None

    finally:
        if lock_acquired:
            lock.release()
    return result_data # Return the dictionary or None
```

**Key Changes in `get_nav_rate`:**

1.  Calls `_send_ubx_command` with only Class and ID to poll CFG-RATE.
2.  Calls the modified `_read_ubx_response` with `expect_payload=True` and the specific Class/ID `UBX_CLASS_CFG`/`UBX_CFG_RATE`.
3.  Checks if the returned `response_payload` is valid `bytes` of length 6.
4.  Unpacks the payload using `struct.unpack('<HHH', ...)`.
5.  Calculates `rate_hz`.
6.  Populates the `result_data` dictionary with the actual values.
7.  Returns the dictionary on success, `None` on failure (send error, timeout, invalid response).

## 3. Update Calls in `set_nav_rate` and `_save_configuration`

Ensure that the calls to `_read_ubx_response` within `set_nav_rate` and `_save_configuration` still correctly expect only ACK/NAK status. Since the default for `expect_payload` is `False`, no explicit change is needed unless you want to be verbose:

```python
# Inside set_nav_rate, after sending CFG-RATE command:
response = _read_ubx_response(
    uart, UBX_CLASS_CFG, UBX_CFG_RATE,
    timeout_ms=1000 * (retry_count + 1),
    expect_payload=False # Default, but explicit here
)
# ... check if response is True ...

# Inside _save_configuration, after sending CFG-CFG command:
response = _read_ubx_response(
    uart, UBX_CLASS_CFG, UBX_CFG_CFG,
    timeout_ms=1500,
    expect_payload=False # Default, but explicit here
)
# ... check if response is True ...
```

## Next Steps

1.  Switch to Code mode.
2.  Apply these changes to `device/io_local/gps_config.py`.
3.  Upload the modified code.
4.  Test by calling the `/api/gps-settings/data` endpoint with `{"action": "get_rate"}`.
