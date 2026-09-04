"""Launch Library 2 API client and pure data-shaping helpers.

Everything in this module is intentionally free of Home Assistant imports so
it can be unit tested with plain pytest (see tests/), without a running
Home Assistant core. HA-specific glue (the coordinator, entities, config
flow) lives in the other modules and consumes these functions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from .const import API_BASE_URL, LOCATIONS_PATH, UPCOMING_PATH

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 20


class LaunchLibraryError(Exception):
    """Raised for any Launch Library request failure."""


class LaunchLibraryRateLimited(LaunchLibraryError):
    """Raised specifically for HTTP 429 responses."""


class LaunchLibraryNoLocationMatch(LaunchLibraryError):
    """Raised when a typed site filter matches no known Launch Library location."""


@dataclass
class LaunchLibraryClient:
    """Thin async wrapper around the Launch Library 2 upcoming-launches endpoint.

    Uses Home Assistant's shared aiohttp session (passed in by the caller)
    rather than adding a new PyPI dependency.
    """

    session: Any
    api_key: str | None = None

    async def async_get_upcoming(self, location_ids: list[int] | None, limit: int) -> dict:
        """Fetch the next `limit` launches, optionally filtered to specific locations.

        Filtering by `location__ids` (exact numeric location ids, comma
        separated) rather than a text match: `location__name__contains` is a
        documented filter on the *pad* list endpoint, but wasn't confirmed
        against the launch/upcoming endpoint specifically, and unrecognized
        filter params on this API are silently ignored rather than
        rejected - which would make the "filter" a no-op with no error to
        show for it. `location__ids` is confirmed against the launch
        endpoint's own documented filters. Resolve site text to ids first
        with async_search_locations.
        """
        params: dict[str, Any] = {"limit": limit, "mode": "detailed"}
        if location_ids:
            params["location__ids"] = ",".join(str(i) for i in location_ids)

        return await self._get(UPCOMING_PATH, params)

    async def async_search_locations(self, name_contains: str) -> list[dict]:
        """Resolve free-text site input (e.g. "Vandenberg") to Launch Library location records."""
        payload = await self._get(LOCATIONS_PATH, {"name__contains": name_contains, "limit": 25})
        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            return []
        return [loc for loc in (parse_location(item) for item in results) if loc["id"] is not None]

    async def _get(self, path: str, params: dict[str, Any]) -> dict:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Token {self.api_key}"

        url = f"{API_BASE_URL}{path}"
        try:
            async with self.session.get(
                url, params=params, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS
            ) as response:
                if response.status == 429:
                    raise LaunchLibraryRateLimited(
                        "Launch Library 2 rate limit exceeded (free tier is "
                        "15 requests/hour; consider adding an API key)"
                    )
                if response.status >= 400:
                    body = await response.text()
                    raise LaunchLibraryError(
                        f"Launch Library 2 returned HTTP {response.status}: {body[:200]}"
                    )
                return await response.json()
        except LaunchLibraryError:
            raise
        except Exception as err:  # noqa: BLE001 - normalize every transport error
            raise LaunchLibraryError(f"Could not reach Launch Library 2: {err}") from err


def _as_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _nested(raw: dict, *path: str) -> Any:
    """Walk a chain of dict keys, returning None the moment anything's missing."""
    node: Any = raw
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def _image_url(raw: dict) -> str | None:
    image = raw.get("image")
    if isinstance(image, str):
        return image or None
    if isinstance(image, dict):
        return image.get("image_url") or image.get("url")
    return None


def _first_launcher_stage_landing(raw: dict) -> dict | None:
    """The first launcher stage's landing plan, if any.

    `rocket.launcher_stage` is a list (some vehicles have multiple stages),
    and only the first/booster stage's landing plan is relevant for a
    recovery-attempt badge. Defensive the same way the rest of this module
    is: a missing or malformed stage list just means "no landing data",
    never a crash.
    """
    stages = _nested(raw, "rocket", "launcher_stage")
    if not isinstance(stages, list) or not stages or not isinstance(stages[0], dict):
        return None
    landing = stages[0].get("landing")
    return landing if isinstance(landing, dict) else None


def parse_launch(raw: dict) -> dict:
    """Normalize one raw Launch Library 2 launch object.

    Deliberately defensive: every accessor falls back to None instead of
    raising, since the exact nesting of a couple of fields (image in
    particular) has changed across Launch Library API versions and isn't
    independently verified here against a live response.
    """
    landing = _first_launcher_stage_landing(raw)
    return {
        "id": raw.get("id"),
        "name": raw.get("name"),
        "status": _nested(raw, "status", "name"),
        "status_abbrev": _nested(raw, "status", "abbrev"),
        "net": _as_text(raw.get("net")),
        "window_start": _as_text(raw.get("window_start")),
        "window_end": _as_text(raw.get("window_end")),
        "net_precision": _nested(raw, "net_precision", "name"),
        "probability": raw.get("probability"),
        "provider": _nested(raw, "launch_service_provider", "name"),
        "rocket": _nested(raw, "rocket", "configuration", "name")
        or _nested(raw, "rocket", "configuration", "full_name"),
        "mission_name": _nested(raw, "mission", "name") or raw.get("name"),
        "mission_description": _nested(raw, "mission", "description"),
        "orbit": _nested(raw, "mission", "orbit", "name"),
        # Always a real bool (never None) once a landing object exists at
        # all, so the card can tell "no attempt" apart from "we don't know
        # yet" (older tracker versions never sent this key at all).
        "landing_attempt": bool(landing.get("attempt")) if landing is not None else None,
        # Launch Library renamed this field from `location` to
        # `landing_location` in API v2.3.0 (which API_BASE_URL now points
        # at) - fall back to the old key too in case an older/cached
        # response still uses it.
        "landing_location": (
            (_nested(landing, "landing_location", "name") or _nested(landing, "location", "name"))
            if landing is not None
            else None
        ),
        "pad_name": _nested(raw, "pad", "name"),
        "location_id": _nested(raw, "pad", "location", "id"),
        "location_name": _nested(raw, "pad", "location", "name"),
        "image": _image_url(raw),
        "webcast_live": bool(raw.get("webcast_live")),
        "hold_reason": _as_text(raw.get("holdreason")),
        "fail_reason": _as_text(raw.get("failreason")),
        "last_updated": _as_text(raw.get("last_updated")),
    }


def parse_launch_list(payload: dict) -> list[dict]:
    """Normalize a Launch Library 2 list response into our launch dicts.

    Launch Library returns results ordered soonest-first, and this preserves
    that order.
    """
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        return []
    return [parse_launch(item) for item in results if isinstance(item, dict)]


def parse_location(raw: dict) -> dict:
    """Normalize one raw Launch Library 2 location object."""
    return {"id": raw.get("id"), "name": raw.get("name")}


def filter_by_location_ids(launches: list[dict], location_ids: list[int] | None) -> list[dict]:
    """Drop any launch whose location id isn't one of the resolved ids.

    A safety net behind the server-side `location__ids` query filter, not a
    substitute for it: if the query filter ever misbehaves (a bad response,
    an API change), this still guarantees no other site's launches leak
    into the tracked list - it can only narrow results the server already
    returned, not recover ones it didn't. A launch with no location id at
    all is dropped when a filter is active, rather than assumed to match.
    """
    if not location_ids:
        return launches
    wanted = set(location_ids)
    return [launch for launch in launches if launch.get("location_id") in wanted]
