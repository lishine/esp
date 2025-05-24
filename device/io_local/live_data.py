from server_framework import Response, Request, error_response
import json
import uos
import time
from .data_log import get_latest_live_data
import settings_manager
from log import log

LIVE_DATA_HTML_PATH = "/io_local/live_data.html"


# Function to register routes with the main app instance
def register_live_data_routes(app_instance):
    @app_instance.route("/live-data", methods=["GET"])
    def get_live_data_page(request: Request):
        try:
            # uos.stat will raise OSError if path doesn't exist
            uos.stat(LIVE_DATA_HTML_PATH)
            with open(LIVE_DATA_HTML_PATH, "r") as f:
                content = f.read()
            return Response(
                body=content,
                status=200,
                headers={"Content-Type": "text/html; charset=utf-8"},
            )
        except OSError as e:
            if e.args[0] == 2:  # ENOENT - No such file or directory
                log(f"Live data HTML file not found: {LIVE_DATA_HTML_PATH} - {e}")
                return Response(body="Live Data page not found.", status=404)
            else:
                log(f"OSError accessing {LIVE_DATA_HTML_PATH}: {e}")
                return Response(
                    body=f"Error accessing Live Data page: {str(e)}", status=500
                )
        except Exception as e:
            log(f"Error reading {LIVE_DATA_HTML_PATH}: {e}")
            return Response(body=f"Error reading Live Data page: {str(e)}", status=500)

    @app_instance.route("/api/live-data", methods=["POST"])
    def post_read_live_data_api(request: Request):
        try:
            cached_data = get_latest_live_data()

            current_device_ticks_ms = time.ticks_ms()

            live_api_response = {}

            ds18b20_data_from_cache = cached_data.get("ds")
            processed_ds18_sensors = []
            if ds18b20_data_from_cache and isinstance(
                ds18b20_data_from_cache.get("value"), dict
            ):
                ds_value_dict = ds18b20_data_from_cache["value"]
                ds_timestamp_ms = ds18b20_data_from_cache.get("timestamp", 0)

                ds_associations = settings_manager.get_ds_associations()
                address_to_name_map = {
                    assoc["address"]: assoc["name"] for assoc in ds_associations
                }
                name_to_address_map = {
                    assoc["name"]: assoc["address"]
                    for assoc in ds_associations
                    if assoc.get("name")
                }

                for key, temp_c in ds_value_dict.items():
                    rom_address = None
                    sensor_name = ""

                    if key in address_to_name_map:
                        rom_address = key
                        sensor_name = address_to_name_map[key]
                    elif key in name_to_address_map:
                        rom_address = name_to_address_map[key]
                        sensor_name = key
                    elif len(key) == 16 and all(
                        c in "0123456789abcdefABCDEF" for c in key
                    ):
                        rom_address = key
                        sensor_name = ""
                    else:
                        log(
                            f"DS18B20: Could not determine ROM for key '{key}'. Skipping."
                        )
                        continue

                    if rom_address:
                        processed_ds18_sensors.append(
                            {
                                "rom": rom_address,
                                "name": sensor_name,
                                "temp_c": temp_c,
                            }
                        )

            live_api_response["ds18b20"] = {
                "count": len(processed_ds18_sensors),
                "sensors": processed_ds18_sensors,
                "timestamp_ms": (
                    ds18b20_data_from_cache.get("timestamp", 0)
                    if ds18b20_data_from_cache
                    else 0
                ),
            }

            for (
                sensor_name_key,
                sensor_info,
            ) in cached_data.items():
                if sensor_name_key == "ds":
                    continue

                value = sensor_info.get("value")
                timestamp_ms = sensor_info.get("timestamp", 0)

                live_api_response[sensor_name_key] = {
                    "value": value,
                    "timestamp_ms": timestamp_ms,
                }

            fan_is_on = settings_manager.is_fan_enabled()
            live_api_response["fan_status"] = {
                "value": {"enabled": fan_is_on},
                "timestamp_ms": current_device_ticks_ms,
            }

            return Response(
                body=json.dumps(live_api_response),
                status=200,
                headers={"Content-Type": "application/json"},
            )
        except Exception as e:
            log(f"Error in /api/live-data: {e}")
            body_err, status_err = error_response(
                f"Server error processing live data: {str(e)}",
                500,
            )
            return Response(
                body=body_err,
                status=status_err,
                headers={"Content-Type": "application/json"},
            )

    @app_instance.route("/api/settings/ds-names", methods=["POST"])
    def save_ds_names_api(request: Request):
        try:
            data = json.loads(request.body)
            if not isinstance(data, list):
                log(
                    f"/api/settings/ds-names: Invalid data format, expected a list. Got: {type(data)}"
                )
                raise ValueError(
                    "Invalid data format, expected a list of associations."
                )

            # Basic validation of list items
            for item in data:
                if (
                    not isinstance(item, dict)
                    or not item.get("address")
                    or not isinstance(item.get("address"), str)
                    or not isinstance(item.get("name"), str)
                ):  # Name can be empty string
                    log(
                        f"/api/settings/ds-names: Invalid item in associations list: {item}"
                    )
                    raise ValueError(
                        "Each association must be a dict with 'address' (str) and 'name' (str)."
                    )

            if settings_manager.set_ds_associations(data):
                log("/api/settings/ds-names: DS18B20 names saved successfully.")
                return Response(
                    body=json.dumps(
                        {"success": True, "message": "DS18B20 names saved."}
                    ),
                    status=200,
                    headers={"Content-Type": "application/json"},
                )
            else:
                log(
                    "/api/settings/ds-names: settings_manager.set_ds_associations returned False."
                )
                raise Exception("Failed to save DS18B20 names via settings_manager.")
        except ValueError as ve:  # Catch specific JSON or data format errors
            log(f"ValueError in /api/settings/ds-names: {ve}")
            body_err, status_err = error_response(
                f"Invalid data: {str(ve)}", 400
            )  # HTTP_BAD_REQUEST
            return Response(
                body=body_err,
                status=status_err,
                headers={"Content-Type": "application/json"},
            )
        except Exception as e:
            log(f"Unexpected error in /api/settings/ds-names: {e}")
            body_err, status_err = error_response(
                f"Error saving DS18B20 names: {str(e)}", 500
            )  # HTTP_INTERNAL_ERROR
            return Response(
                body=body_err,
                status=status_err,
                headers={"Content-Type": "application/json"},
            )
