"""Pure adaptive-polling decision logic, kept separate from the coordinator
so it can be unit tested without Home Assistant installed.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def parse_iso(value: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp as Launch Library returns it (UTC, 'Z' suffix)."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def soonest_launch_time(launches: list[dict]) -> datetime | None:
    """Return the earliest parseable `net` time among the given launches.

    Launch Library orders results soonest-first, but this doesn't assume
    that - it takes the actual minimum, so a launch with a missing/invalid
    `net` earlier in the list can't hide a valid one behind it.
    """
    times = [parse_iso(launch.get("net")) for launch in launches]
    valid = [t for t in times if t is not None]
    return min(valid) if valid else None


def next_poll_interval(
    launches: list[dict],
    *,
    now: datetime,
    near_window: timedelta,
    near_interval: timedelta,
    far_interval: timedelta,
) -> timedelta:
    """Decide how soon to poll again.

    Near-window, frequent polling only kicks in once the soonest known
    matching launch is inside `near_window` of now - everything else
    (nothing tracked yet, or the nearest launch still far out) uses the
    cheap far interval, which is what keeps this comfortably inside the
    free-tier rate limit when nothing is imminent. A launch already at or
    past its predicted time also gets fast polling (no lower bound on
    `time_until`) since that's exactly when a status update - a scrub, a
    new target time, an actual liftoff - is most likely to land.
    """
    soonest = soonest_launch_time(launches)
    if soonest is None:
        return far_interval
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    time_until = soonest - now
    if time_until <= near_window:
        return near_interval
    return far_interval
