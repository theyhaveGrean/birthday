"""Shared display timezone for the clock and memo timestamps."""

import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

TIMEZONE_ENV = "VIDEO_ARCHIVE_TIMEZONE"
DEFAULT_CLOCK_TIMEZONE = "America/Los_Angeles"
MIN_SANE_YEAR = 2020


def display_timezone():
    name = os.environ.get(TIMEZONE_ENV, DEFAULT_CLOCK_TIMEZONE).strip()
    try:
        return ZoneInfo(name or DEFAULT_CLOCK_TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError):
        return timezone.utc


def current_clock_time():
    return datetime.now(display_timezone())


def parse_timestamp(value):
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return parsed


def format_timestamp(value):
    if value is None or value.year < MIN_SANE_YEAR:
        return "TIME UNSYNCED"
    # Legacy display dates have no offset. Preserve their wall time rather
    # than pretending we know the OS timezone used when they were created.
    if value.tzinfo is not None:
        value = value.astimezone(display_timezone())
    return value.strftime("%Y-%m-%d %H:%M")


def format_stored_timestamp(value):
    parsed = parse_timestamp(value)
    return format_timestamp(parsed) if parsed else str(value or "TIME UNSYNCED")
