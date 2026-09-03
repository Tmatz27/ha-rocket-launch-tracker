"""The Rocket Launch Tracker integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

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
)
from .coordinator import RocketLaunchCoordinator

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Rocket Launch Tracker from a config entry."""
    config = {**entry.data, **entry.options}

    coordinator = RocketLaunchCoordinator(
        hass,
        site_filter=config.get(CONF_SITE_FILTER, DEFAULT_SITE_FILTER),
        location_ids=config.get(CONF_LOCATION_IDS),
        api_key=config.get(CONF_API_KEY) or None,
        upcoming_count=config.get(CONF_UPCOMING_COUNT, DEFAULT_UPCOMING_COUNT),
        near_window_hours=config.get(CONF_NEAR_WINDOW_HOURS, DEFAULT_NEAR_WINDOW_HOURS),
        near_interval_minutes=config.get(CONF_NEAR_INTERVAL_MINUTES, DEFAULT_NEAR_INTERVAL_MINUTES),
        far_interval_minutes=config.get(CONF_FAR_INTERVAL_MINUTES, DEFAULT_FAR_INTERVAL_MINUTES),
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change (site filter, intervals, ...)."""
    await hass.config_entries.async_reload(entry.entry_id)
