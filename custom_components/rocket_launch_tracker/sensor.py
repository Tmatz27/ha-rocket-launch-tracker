"""Sensor entities for Rocket Launch Tracker."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN
from .coordinator import RocketLaunchCoordinator
from .interval import parse_iso


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the two sensor entities for a config entry."""
    coordinator: RocketLaunchCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            NextLaunchSensor(coordinator, entry),
            UpcomingLaunchesSensor(coordinator, entry),
        ]
    )


class _BaseLaunchEntity(CoordinatorEntity[RocketLaunchCoordinator], SensorEntity):
    """Shared device grouping for both sensors."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(self, coordinator: RocketLaunchCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Launch Library 2 (thespacedevs.com)",
            model="Rocket Launch Tracker",
        )

    @property
    def _launches(self) -> list[dict]:
        return self.coordinator.data or []


class NextLaunchSensor(_BaseLaunchEntity):
    """The soonest matching launch, exposed as a timestamp entity.

    A timestamp state means it works directly in automations and the
    history graph (`states('sensor...')` is already an ISO datetime), not
    just as a display attribute.
    """

    _attr_translation_key = "next_launch"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:rocket-launch"

    def __init__(self, coordinator: RocketLaunchCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_next_launch"

    @property
    def _next(self) -> dict | None:
        return self._launches[0] if self._launches else None

    @property
    def native_value(self):
        launch = self._next
        if not launch:
            return None
        return parse_iso(launch.get("net")) or parse_iso(launch.get("window_start"))

    @property
    def extra_state_attributes(self) -> dict:
        launch = self._next
        if not launch:
            return {"site_filter": self.coordinator.site_filter}
        return {
            "site_filter": self.coordinator.site_filter,
            "launch_id": launch.get("id"),
            "name": launch.get("name"),
            "mission_name": launch.get("mission_name"),
            "mission_description": launch.get("mission_description"),
            "status": launch.get("status"),
            "status_abbrev": launch.get("status_abbrev"),
            "provider": launch.get("provider"),
            "rocket": launch.get("rocket"),
            "pad_name": launch.get("pad_name"),
            "location_id": launch.get("location_id"),
            "location_name": launch.get("location_name"),
            "net_precision": launch.get("net_precision"),
            "window_start": launch.get("window_start"),
            "window_end": launch.get("window_end"),
            "probability": launch.get("probability"),
            "image": launch.get("image"),
            "webcast_live": launch.get("webcast_live"),
            "hold_reason": launch.get("hold_reason"),
            "fail_reason": launch.get("fail_reason"),
            "last_updated": launch.get("last_updated"),
        }


class UpcomingLaunchesSensor(_BaseLaunchEntity):
    """Count of currently-tracked matching launches, with the full list as an attribute."""

    _attr_translation_key = "upcoming_launches"
    _attr_icon = "mdi:rocket-launch-outline"
    _attr_native_unit_of_measurement = "launches"

    def __init__(self, coordinator: RocketLaunchCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_upcoming_launches"

    @property
    def native_value(self) -> int:
        return len(self._launches)

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "site_filter": self.coordinator.site_filter,
            "launches": self._launches,
        }
