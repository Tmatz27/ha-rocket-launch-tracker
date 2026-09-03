"""DataUpdateCoordinator for Rocket Launch Tracker.

Adaptive polling: a cheap far interval most of the time, stepping up to a
frequent near interval only once the soonest tracked launch is inside the
configured near-window - see interval.py for the (unit-tested) decision
logic itself.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    LaunchLibraryClient,
    LaunchLibraryError,
    LaunchLibraryRateLimited,
    filter_by_location_ids,
    parse_launch_list,
)
from .const import DOMAIN
from .interval import next_poll_interval

_LOGGER = logging.getLogger(__name__)


class RocketLaunchCoordinator(DataUpdateCoordinator[list[dict]]):
    """Fetches and holds the current list of matching upcoming launches."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        site_filter: str,
        location_ids: list[int] | None,
        api_key: str | None,
        upcoming_count: int,
        near_window_hours: float,
        near_interval_minutes: float,
        far_interval_minutes: float,
    ) -> None:
        self.site_filter = site_filter
        self.location_ids = location_ids or None
        self.upcoming_count = upcoming_count
        self._near_window = timedelta(hours=near_window_hours)
        self._near_interval = timedelta(minutes=near_interval_minutes)
        self._far_interval = timedelta(minutes=far_interval_minutes)
        self._client = LaunchLibraryClient(session=async_get_clientsession(hass), api_key=api_key)

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=self._far_interval,
        )

    async def _async_update_data(self) -> list[dict]:
        try:
            payload = await self._client.async_get_upcoming(self.location_ids, self.upcoming_count)
        except LaunchLibraryRateLimited as err:
            # Back off harder than the configured far interval rather than
            # hammering an endpoint that just told us to slow down.
            self.update_interval = min(self._far_interval * 2, timedelta(hours=1))
            raise UpdateFailed(str(err)) from err
        except LaunchLibraryError as err:
            raise UpdateFailed(str(err)) from err

        # filter_by_location_ids is a safety net behind the server-side
        # query filter above, not a replacement for it - see its docstring.
        launches = filter_by_location_ids(parse_launch_list(payload), self.location_ids)
        self.update_interval = next_poll_interval(
            launches,
            now=dt_util.utcnow(),
            near_window=self._near_window,
            near_interval=self._near_interval,
            far_interval=self._far_interval,
        )
        return launches
