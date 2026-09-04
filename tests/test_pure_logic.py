"""Unit tests for the Home-Assistant-free parts of the integration:
interval.py (adaptive polling decision) and api.py's parsing functions.

api.py has one relative import (`from .const import ...`), so it can't be
loaded as a bare standalone file the way interval.py can. Rather than
installing Home Assistant (heavy, and still wouldn't let us execute-test
against a real core here), this registers const.py and api.py under a
synthetic package name in sys.modules so the relative import resolves
without ever touching the real package's __init__.py (which does import
Home Assistant, and is intentionally not exercised by these tests - see
the "What's tested" note in the repo README).
"""

from __future__ import annotations

import importlib.util
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

COMPONENT_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "rocket_launch_tracker"


def _load(module_name: str, file_name: str, package: str | None = None):
    spec = importlib.util.spec_from_file_location(module_name, COMPONENT_DIR / file_name)
    module = importlib.util.module_from_spec(spec)
    if package is not None:
        module.__package__ = package
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_component_modules():
    pkg_name = "rocket_launch_tracker_under_test"
    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [str(COMPONENT_DIR)]
    sys.modules[pkg_name] = pkg
    const = _load(f"{pkg_name}.const", "const.py", package=pkg_name)
    api = _load(f"{pkg_name}.api", "api.py", package=pkg_name)
    return const, api


const, api = _load_component_modules()
interval = _load("rocket_launch_tracker_interval_under_test", "interval.py")


# --- interval.py ------------------------------------------------------


def _launch(net_iso: str | None) -> dict:
    return {"net": net_iso}


def test_far_interval_when_nothing_tracked():
    now = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)
    result = interval.next_poll_interval(
        [],
        now=now,
        near_window=timedelta(hours=48),
        near_interval=timedelta(minutes=5),
        far_interval=timedelta(minutes=30),
    )
    assert result == timedelta(minutes=30)


def test_far_interval_when_soonest_launch_outside_window():
    now = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)
    launches = [_launch("2026-09-10T12:00:00Z")]  # 7 days out
    result = interval.next_poll_interval(
        launches,
        now=now,
        near_window=timedelta(hours=48),
        near_interval=timedelta(minutes=5),
        far_interval=timedelta(minutes=30),
    )
    assert result == timedelta(minutes=30)


def test_near_interval_when_inside_window():
    now = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)
    launches = [_launch("2026-09-04T18:00:00Z")]  # 30 hours out
    result = interval.next_poll_interval(
        launches,
        now=now,
        near_window=timedelta(hours=48),
        near_interval=timedelta(minutes=5),
        far_interval=timedelta(minutes=30),
    )
    assert result == timedelta(minutes=5)


def test_near_interval_when_launch_is_overdue():
    # Past its predicted time with no update yet - exactly when we want to
    # be polling fast to catch the status change.
    now = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)
    launches = [_launch("2026-09-03T11:30:00Z")]
    result = interval.next_poll_interval(
        launches,
        now=now,
        near_window=timedelta(hours=48),
        near_interval=timedelta(minutes=5),
        far_interval=timedelta(minutes=30),
    )
    assert result == timedelta(minutes=5)


def test_picks_the_true_soonest_even_out_of_order():
    now = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)
    launches = [
        _launch("2026-09-20T00:00:00Z"),
        _launch(None),  # unparseable / TBD - must not crash or win the min()
        _launch("2026-09-04T00:00:00Z"),  # actually soonest
    ]
    result = interval.next_poll_interval(
        launches,
        now=now,
        near_window=timedelta(hours=48),
        near_interval=timedelta(minutes=5),
        far_interval=timedelta(minutes=30),
    )
    assert result == timedelta(minutes=5)


def test_parse_iso_handles_z_suffix_and_invalid_input():
    assert interval.parse_iso("2026-09-03T12:00:00Z") == datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)
    assert interval.parse_iso(None) is None
    assert interval.parse_iso("not a date") is None


# --- api.py parsing ------------------------------------------------------

RAW_LAUNCH_FULL = {
    "id": "abc-123",
    "name": "Falcon 9 Block 5 | Starlink Group 12-3",
    "status": {"id": 1, "name": "Go for Launch", "abbrev": "Go"},
    "net": "2026-09-14T13:05:00Z",
    "window_start": "2026-09-14T12:35:00Z",
    "window_end": "2026-09-14T14:35:00Z",
    "net_precision": {"id": 3, "name": "Hour"},
    "probability": 85,
    "holdreason": "",
    "failreason": "",
    "launch_service_provider": {"id": 121, "name": "SpaceX"},
    "rocket": {
        "configuration": {"name": "Falcon 9", "full_name": "Falcon 9 Block 5"},
        "launcher_stage": [
            {"landing": {"attempt": True, "location": {"name": "Landing Zone 1 (LZ-1)"}}}
        ],
    },
    "mission": {
        "name": "Starlink Group 12-3",
        "description": "A batch of Starlink satellites.",
        "orbit": {"name": "Low Earth Orbit"},
    },
    "pad": {"name": "Space Launch Complex 4E", "location": {"id": 11, "name": "Vandenberg SFB, CA, USA"}},
    "image": {"image_url": "https://example.com/image.jpg"},
    "webcast_live": True,
    "last_updated": "2026-09-03T10:00:00Z",
}

RAW_LAUNCH_SPARSE = {
    "id": "def-456",
    "name": "Minimal Mission",
    "net": None,
    "window_start": None,
    "window_end": None,
    "probability": None,
    "holdreason": "",
    "failreason": "",
    "image": "https://example.com/flat-image.jpg",
}


def test_parse_launch_full_record():
    launch = api.parse_launch(RAW_LAUNCH_FULL)
    assert launch["name"] == "Falcon 9 Block 5 | Starlink Group 12-3"
    assert launch["status"] == "Go for Launch"
    assert launch["status_abbrev"] == "Go"
    assert launch["net"] == "2026-09-14T13:05:00Z"
    assert launch["net_precision"] == "Hour"
    assert launch["probability"] == 85
    assert launch["provider"] == "SpaceX"
    assert launch["rocket"] == "Falcon 9"
    assert launch["mission_name"] == "Starlink Group 12-3"
    assert launch["pad_name"] == "Space Launch Complex 4E"
    assert launch["location_id"] == 11
    assert launch["location_name"] == "Vandenberg SFB, CA, USA"
    assert launch["image"] == "https://example.com/image.jpg"
    assert launch["webcast_live"] is True
    assert launch["hold_reason"] is None  # empty string normalized to None
    assert launch["fail_reason"] is None
    assert launch["orbit"] == "Low Earth Orbit"
    assert launch["landing_attempt"] is True
    assert launch["landing_location"] == "Landing Zone 1 (LZ-1)"


def test_parse_launch_handles_missing_nested_fields_without_raising():
    launch = api.parse_launch(RAW_LAUNCH_SPARSE)
    assert launch["name"] == "Minimal Mission"
    assert launch["status"] is None
    assert launch["net"] is None
    assert launch["provider"] is None
    assert launch["pad_name"] is None
    assert launch["location_name"] is None
    # Falls back to the flat-string image shape as well as the dict shape.
    assert launch["image"] == "https://example.com/flat-image.jpg"
    # No mission object at all - mission_name falls back to the launch name.
    assert launch["mission_name"] == "Minimal Mission"
    # No rocket/mission objects at all: unknown, not "confirmed no landing".
    assert launch["orbit"] is None
    assert launch["landing_attempt"] is None
    assert launch["landing_location"] is None


def test_parse_launch_landing_attempt_false_when_explicitly_not_attempted():
    # A real landing object is present, but this specific booster is expendable
    # (e.g. a high-energy GTO mission) - that's a confirmed False, not unknown.
    raw = {
        **RAW_LAUNCH_FULL,
        "rocket": {
            "configuration": {"name": "Falcon 9"},
            "launcher_stage": [{"landing": {"attempt": False, "location": None}}],
        },
    }
    launch = api.parse_launch(raw)
    assert launch["landing_attempt"] is False
    assert launch["landing_location"] is None


def test_parse_launch_landing_attempt_none_when_launcher_stage_missing():
    raw = {**RAW_LAUNCH_FULL, "rocket": {"configuration": {"name": "Atlas V"}}}
    launch = api.parse_launch(raw)
    assert launch["landing_attempt"] is None
    assert launch["landing_location"] is None


def test_parse_launch_landing_attempt_none_when_launcher_stage_is_empty():
    raw = {
        **RAW_LAUNCH_FULL,
        "rocket": {"configuration": {"name": "Falcon 9"}, "launcher_stage": []},
    }
    launch = api.parse_launch(raw)
    assert launch["landing_attempt"] is None


def test_parse_launch_landing_attempt_none_when_stage_has_no_landing_key():
    raw = {
        **RAW_LAUNCH_FULL,
        "rocket": {"configuration": {"name": "Falcon 9"}, "launcher_stage": [{}]},
    }
    launch = api.parse_launch(raw)
    assert launch["landing_attempt"] is None
    assert launch["landing_location"] is None


def test_parse_launch_orbit_missing_when_no_orbit_key():
    raw = {**RAW_LAUNCH_FULL, "mission": {"name": "No Orbit Listed"}}
    launch = api.parse_launch(raw)
    assert launch["orbit"] is None


def test_parse_launch_list_filters_non_dict_entries_and_preserves_order():
    payload = {"count": 2, "results": [RAW_LAUNCH_FULL, RAW_LAUNCH_SPARSE]}
    launches = api.parse_launch_list(payload)
    assert [launch["id"] for launch in launches] == ["abc-123", "def-456"]


def test_parse_launch_list_handles_missing_or_malformed_results():
    assert api.parse_launch_list({}) == []
    assert api.parse_launch_list({"results": None}) == []
    assert api.parse_launch_list({"results": "not-a-list"}) == []


# --- api.py location filtering --------------------------------------------
#
# location__name__contains (the original filter) was only ever confirmed
# against the Pad list endpoint's documented filters, not the launch/upcoming
# endpoint itself - and this API silently ignores filter params a given
# endpoint doesn't recognize rather than rejecting them, so a bad filter
# param looks identical to "no launches matched" instead of erroring. These
# tests cover the fix: exact numeric location__ids filtering plus a
# client-side safety net that can only narrow results, never miss ones the
# server already returned.


def test_parse_location():
    assert api.parse_location({"id": 11, "name": "Vandenberg SFB, CA, USA"}) == {
        "id": 11,
        "name": "Vandenberg SFB, CA, USA",
    }


def test_filter_by_location_ids_keeps_only_matching_launches():
    vandenberg = api.parse_launch(RAW_LAUNCH_FULL)  # location_id 11
    other = api.parse_launch({**RAW_LAUNCH_FULL, "id": "xyz-789", "pad": {"name": "SLC-40", "location": {"id": 27, "name": "Cape Canaveral SFS, FL, USA"}}})

    result = api.filter_by_location_ids([vandenberg, other], [11])
    assert [launch["id"] for launch in result] == ["abc-123"]


def test_filter_by_location_ids_accepts_multiple_ids():
    vandenberg = api.parse_launch(RAW_LAUNCH_FULL)
    other = api.parse_launch({**RAW_LAUNCH_FULL, "id": "xyz-789", "pad": {"name": "SLC-40", "location": {"id": 27, "name": "Cape Canaveral SFS, FL, USA"}}})

    result = api.filter_by_location_ids([vandenberg, other], [11, 27])
    assert {launch["id"] for launch in result} == {"abc-123", "xyz-789"}


def test_filter_by_location_ids_drops_launches_with_no_location_id_when_filtering():
    no_location = api.parse_launch(RAW_LAUNCH_SPARSE)  # no pad/location at all
    result = api.filter_by_location_ids([no_location], [11])
    assert result == []


def test_filter_by_location_ids_passthrough_when_no_filter_configured():
    launches = api.parse_launch_list({"results": [RAW_LAUNCH_FULL, RAW_LAUNCH_SPARSE]})
    assert api.filter_by_location_ids(launches, None) == launches
    assert api.filter_by_location_ids(launches, []) == launches
