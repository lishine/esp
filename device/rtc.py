import time
import machine
import log
from file_utils import MIN_VALID_YEAR
import settings_manager


def set_rtc_from_gmtime_tuple(gmtime_tuple: tuple) -> bool:
    """Set the RTC from a standard time.gmtime() tuple (year, month, mday, hour, minute, second, weekday, yearday).
    Returns True if successful, False otherwise."""
    try:
        rtc = machine.RTC()
        # Convert gmtime tuple to RTC tuple format (year, month, day, weekday, hour, minute, second, subseconds)
        rtc_tuple = (
            gmtime_tuple[0],  # year
            gmtime_tuple[1],  # month
            gmtime_tuple[2],  # day
            gmtime_tuple[6],  # weekday (0-6 for Mon-Sun)
            gmtime_tuple[3],  # hour
            gmtime_tuple[4],  # minute
            gmtime_tuple[5],  # second
            0,  # subseconds
        )
        rtc.datetime(rtc_tuple)
        return True
    except Exception as e:
        log.log(f"RTC: Error setting from gmtime tuple: {e}")
        return False


rtc_set_with_time = False


def get_rtc_set_with_time() -> bool:
    """Returns the status of whether RTC was set with time."""
    return rtc_set_with_time


def update_rtc_if_needed(
    gmtime_tuple_from_gps: tuple | None = None, from_settings: bool = False
) -> bool:
    global rtc_set_with_time
    """
    Checks if RTC needs update and performs it.
    Can be called with GPS time or to set time from stored settings.
    """
    if from_settings:
        log.log("RTC: Attempting to set time from stored settings.")
        last_date_from_settings = settings_manager.get_last_date()
        if (
            last_date_from_settings
        ):  # settings_manager.get_last_date() should return a valid 8-int tuple or None
            # The tuple from get_last_date should already be suitable for set_rtc_from_gmtime_tuple
            # Convert the gmtime tuple to epoch seconds
            try:
                epoch_seconds = time.mktime(last_date_from_settings)  # type: ignore
                # Increment by 1 second
                new_epoch_seconds = epoch_seconds + 1
                # Convert back to gmtime tuple
                incremented_date_tuple = time.gmtime(new_epoch_seconds)
            except (OverflowError, ValueError, TypeError) as e:
                log.log(f"RTC: Error incrementing date from settings: {e}")
                return False

            # Use the incremented tuple to set the RTC
            if set_rtc_from_gmtime_tuple(incremented_date_tuple):
                log.log(
                    f"RTC: Successfully set from settings (incremented): {incremented_date_tuple}"
                )
                return True
            else:
                # set_rtc_from_gmtime_tuple would have logged its own error
                log.log(
                    f"RTC: Failed to set RTC from settings using incremented date: {incremented_date_tuple}"
                )
                return False
        else:
            log.log(
                "RTC: No 'last_date' found in settings or it was invalid. Cannot set RTC from settings."
            )
            return False
    elif gmtime_tuple_from_gps is not None:
        # Existing logic for updating from GPS
        if (
            not isinstance(gmtime_tuple_from_gps, tuple)
            or len(gmtime_tuple_from_gps) < 8
        ):
            log.log("RTC: Invalid gmtime_tuple_from_gps format or length.")
            return False

        if gmtime_tuple_from_gps[0] < MIN_VALID_YEAR:  # Use constant from file_utils
            log.log("RTC: GPS year invalid.")
            return False

        try:
            gps_epoch_seconds = time.mktime(gmtime_tuple_from_gps)  # type: ignore
        except OverflowError:
            year, month, day = (
                gmtime_tuple_from_gps[0],
                gmtime_tuple_from_gps[1],
                gmtime_tuple_from_gps[2],
            )
            log.log(
                f"RTC: GPS date {year:04d}-{month:02d}-{day:02d} out of range for mktime."
            )
            return False
        except Exception as e:
            log.log(f"RTC: Error converting GPS time to epoch: {e}")
            return False

        current_rtc_epoch_seconds = time.time()

        if gps_epoch_seconds > current_rtc_epoch_seconds:
            if set_rtc_from_gmtime_tuple(gmtime_tuple_from_gps):
                year, month, day, hour, minute, second = (
                    gmtime_tuple_from_gps[0],
                    gmtime_tuple_from_gps[1],
                    gmtime_tuple_from_gps[2],
                    gmtime_tuple_from_gps[3],
                    gmtime_tuple_from_gps[4],
                    gmtime_tuple_from_gps[5],
                )
                log.log(
                    f"RTC: Updated by GPS time: {year}-{month:02d}-{day:02d} "
                    f"{hour:02d}:{minute:02d}:{second:02d} UTC"
                )
                # Try to rename data log file after successful RTC update from GPS
                rtc_set_with_time = True
                try:
                    date_to_save: tuple = tuple(
                        int(gmtime_tuple_from_gps[i]) for i in range(8)
                    )
                    # Only save if it's different from what might have been set from settings
                    stored_last_date = settings_manager.get_last_date()
                    if stored_last_date is None or date_to_save != stored_last_date:
                        if settings_manager.set_last_date(date_to_save):
                            log.log(
                                "RTC: Last sensible date (from GPS) saved to settings."
                            )
                        else:
                            log.log(
                                "RTC: Failed to save last sensible date (from GPS) to settings."
                            )
                    else:
                        log.log(
                            "RTC: GPS date is same as stored date. Not re-saving to settings."
                        )
                except (IndexError, ValueError, TypeError) as e_conv:
                    log.log(
                        f"RTC: Could not convert GPS time tuple for saving: {e_conv}"
                    )
                return True
            else:
                log.log(
                    "RTC: Update attempt with GPS time failed (set_rtc_from_gmtime_tuple returned False)."
                )
                return False
        else:
            log.log(
                f"RTC: GPS time {gps_epoch_seconds} not newer than current RTC {current_rtc_epoch_seconds}. No update."
            )
            return False
    else:
        # from_settings is False and gmtime_tuple_from_gps is None
        log.log(
            "RTC: update_rtc_if_needed called without GPS data and not in from_settings mode."
        )
        return False


log.log(
    "RTC: Synced timestamp utilities loaded. Call set_time_baseline() after RTC/NTP sync."
)
