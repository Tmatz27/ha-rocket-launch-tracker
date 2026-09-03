"""Config flow for Rocket Launch Tracker."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import LaunchLibraryClient, LaunchLibraryError, LaunchLibraryNoLocationMatch
from .const import (
    CONF_API_KEY,
    CONF_FAR_INTERVAL_MINUTES,
    CONF_LOCATION_IDS,
    CONF_NEAR_INTERVAL_MINUTES,
    CONF_NEAR_WINDOW_HOURS,
    CONF_SITE_FILTER,
    CONF_UPCOMING_COUNT,
    DEFAULT_FAR_INTERVAL_MINUTES,
    DEFAULT_NEAR_INTERVAL_MINUTES,
    DEFAULT_NEAR_WINDOW_HOURS,
    DEFAULT_SITE_FILTER,
    DEFAULT_UPCOMING_COUNT,
    DOMAIN,
    MIN_FAR_INTERVAL_MINUTES,
    MIN_NEAR_INTERVAL_MINUTES,
)


def _schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_SITE_FILTER, default=defaults.get(CONF_SITE_FILTER, DEFAULT_SITE_FILTER)
            ): str,
            vol.Optional(CONF_API_KEY, default=defaults.get(CONF_API_KEY, "")): str,
            vol.Optional(
                CONF_UPCOMING_COUNT, default=defaults.get(CONF_UPCOMING_COUNT, DEFAULT_UPCOMING_COUNT)
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=20)),
            vol.Optional(
                CONF_NEAR_WINDOW_HOURS,
                default=defaults.get(CONF_NEAR_WINDOW_HOURS, DEFAULT_NEAR_WINDOW_HOURS),
            ): vol.All(vol.Coerce(float), vol.Range(min=1, max=240)),
            vol.Optional(
                CONF_NEAR_INTERVAL_MINUTES,
                default=defaults.get(CONF_NEAR_INTERVAL_MINUTES, DEFAULT_NEAR_INTERVAL_MINUTES),
            ): vol.All(vol.Coerce(float), vol.Range(min=MIN_NEAR_INTERVAL_MINUTES, max=120)),
            vol.Optional(
                CONF_FAR_INTERVAL_MINUTES,
                default=defaults.get(CONF_FAR_INTERVAL_MINUTES, DEFAULT_FAR_INTERVAL_MINUTES),
            ): vol.All(vol.Coerce(float), vol.Range(min=MIN_FAR_INTERVAL_MINUTES, max=720)),
        }
    )


async def _resolve_location_ids(client: LaunchLibraryClient, site_filter: str) -> list[int]:
    """Resolve free-text site input to Launch Library location ids.

    Filtering the launch endpoint itself only works reliably by numeric
    `location__ids` (see api.py's async_get_upcoming), so a typed site name
    has to be turned into id(s) once here rather than passed through as
    text on every poll. Raises LaunchLibraryError (including a dedicated
    "no match" case) rather than returning silently - a site filter that
    quietly matches nothing would otherwise show up only as an
    empty-forever integration with no explanation.
    """
    matches = await client.async_search_locations(site_filter)
    if not matches:
        raise LaunchLibraryNoLocationMatch(f'No Launch Library location matches "{site_filter}".')
    return [loc["id"] for loc in matches]


class RocketLaunchTrackerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle initial setup. Multiple entries are allowed (e.g. one per site)."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            site_filter = user_input[CONF_SITE_FILTER].strip()
            user_input[CONF_SITE_FILTER] = site_filter
            await self.async_set_unique_id((site_filter or "all").lower())
            self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass)
            client = LaunchLibraryClient(session=session, api_key=user_input.get(CONF_API_KEY) or None)
            try:
                location_ids = await _resolve_location_ids(client, site_filter) if site_filter else []
                user_input[CONF_LOCATION_IDS] = location_ids
                await client.async_get_upcoming(location_ids or None, limit=1)
            except LaunchLibraryNoLocationMatch:
                errors["base"] = "no_location_match"
            except LaunchLibraryError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(title=site_filter or "All launch sites", data=user_input)

        return self.async_show_form(step_id="user", data_schema=_schema({}), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> RocketLaunchTrackerOptionsFlow:
        return RocketLaunchTrackerOptionsFlow(config_entry)


class RocketLaunchTrackerOptionsFlow(config_entries.OptionsFlow):
    """Let the site filter and polling intervals be adjusted after setup."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            site_filter = user_input[CONF_SITE_FILTER].strip()
            user_input[CONF_SITE_FILTER] = site_filter

            session = async_get_clientsession(self.hass)
            client = LaunchLibraryClient(session=session, api_key=user_input.get(CONF_API_KEY) or None)
            try:
                user_input[CONF_LOCATION_IDS] = await _resolve_location_ids(client, site_filter) if site_filter else []
            except LaunchLibraryNoLocationMatch:
                errors["base"] = "no_location_match"
            except LaunchLibraryError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(title="", data=user_input)

        current = {**self._config_entry.data, **self._config_entry.options, **(user_input or {})}
        return self.async_show_form(step_id="init", data_schema=_schema(current), errors=errors)
