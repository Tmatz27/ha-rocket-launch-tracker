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

from .const import API_BASE_URL, UPCOMING_PATH

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 20


class LaunchLibraryError(Exception):
    """Raised for any Launch Library request failure."""


class LaunchLibraryRateLimited(LaunchLibraryError):
    """Raised specifically for HTTP 429 responses."""


@dataclass
class LaunchLibraryClient:
    """Thin async wrapper around the Launch Library 2 upcoming-launches endpoint.

    Uses Home Assistant's shared aiohttp session (passed in by the caller)
    rather than adding a new PyPI dependency.
    """

    session: Any
    api_key: str | None = None

    async def async_get_upcoming(self, site_filter: str, limit: int) -> dict:
        """Fetch the next `limit` launches, optionally filtered to a site."""
        params: dict[str, Any] = {"limit": limit, "mode": "detailed"}
        if site_filter:
            # location__name__contains matches against the pad's location
            # name (e.g. "Vandenberg SFB, CA, USA"), so a short substring
            # like "Vandenberg" is enough - confirmed against the Pad list
            # endpoint's documented filter parameters.
            params["location__name__contains"] = site_filter

        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Token {self.api_key}"

        url = f"{API_BASE_URL}{UPCOMING_PATH}"
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


def parse_launch(raw: dict) -> dict:
    """Normalize one raw Launch Library 2 launch object.

    Deliberately defensive: every accessor falls back to None instead of
    raising, since the exact nesting of a couple of fields (image in
    particular) has changed across Launch Library API versions and isn't
    independently verified here against a live response.
    """
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
        "pad_name": _nested(raw, "pad", "name"),
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
