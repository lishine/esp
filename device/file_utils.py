import time
import settings_manager

# Minimum valid year for RTC
MIN_VALID_YEAR = 2023


def format_timestamp(t: tuple, include_ms: bool = False, ms: int = 0) -> str:
    """
    Formats a time tuple into a standardized string.
    Args:
        t: Time tuple (year, month, day, hour, minute, second, weekday, yearday)
        include_ms: Whether to include milliseconds
        ms: Milliseconds to include if include_ms is True
    Returns:
        Formatted string like "2023-05-19_15-30-00" or "2023-05-19_15-30-00_500"
    """
    base = f"{t[0]:04d}-{t[1]:02d}-{t[2]:02d}_{t[3]:02d}-{t[4]:02d}-{t[5]:02d}"
    return f"{base}_{ms:03d}" if include_ms else base


def format_date(t: tuple) -> str:
    """
    Formats a time tuple into a date string.
    Args:
        t: Time tuple (year, month, day, hour, minute, second, weekday, yearday)
    Returns:
        Formatted string like "2023-05-19"
    """
    return f"{t[0]:04d}-{t[1]:02d}-{t[2]:02d}"


def format_time(t: tuple, include_ms: bool = False, ms: int = 0) -> str:
    """
    Formats a time tuple into a time string.
    Args:
        t: Time tuple (year, month, day, hour, minute, second, weekday, yearday)
        include_ms: Whether to include milliseconds
        ms: Milliseconds to include if include_ms is True
    Returns:
        Formatted string like "15-30-00" or "15-30-00_500"
    """
    base_time = f"{t[3]:02d}-{t[4]:02d}-{t[5]:02d}"
    return f"{base_time}_{ms:03d}" if include_ms else base_time


def generate_filename(
    base_dir: str,
    extension: str,
    reset_count: int | None = None,
) -> str:
    """
    Generates a log filename based on reset count and RTC status.
    Args:
        base_dir: Base directory path
        extension: File extension without dot
        reset_count: Optional reset counter value, if None will get from settings_manager
    Returns:
        Full path like "/sd/data/0001_2023-10-26_10-30-00.jsonl" or "/sd/logs/0001.txt"
    """
    if reset_count is None:
        reset_count = settings_manager.get_reset_counter()

    rtc_valid, timestamp_tuple = is_rtc_year_valid()

    if rtc_valid:
        ts_str = format_timestamp(timestamp_tuple)
        filename_only = f"{reset_count:04d}_{ts_str}.{extension}"
    else:
        filename_only = f"{reset_count:04d}.{extension}"
    return f"{base_dir}/{filename_only}"


def is_rtc_year_valid() -> tuple[bool, tuple]:
    """
    Checks if the RTC year is valid (>= MIN_VALID_YEAR).
    Returns:
        Tuple of (is_valid_bool, time_tuple)
    """
    current_utc_tuple = time.gmtime()
    is_valid = current_utc_tuple[0] >= MIN_VALID_YEAR
    return is_valid, current_utc_tuple


def get_synced_timestamp(include_ms: bool = False) -> tuple[str, tuple]:
    """
    Gets current timestamp with optional milliseconds.
    Returns:
        Tuple of (formatted_timestamp_str, time_tuple)
    """
    now = time.gmtime()
    ms = time.ticks_ms() % 1000 if include_ms else 0
    return format_timestamp(now, include_ms, ms), now
