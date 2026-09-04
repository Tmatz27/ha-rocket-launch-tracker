# Changelog

## 0.1.3

- `parse_launch()` now also forwards `orbit` (from `mission.orbit.name`),
  `landing_attempt`, and `landing_location` (from the first entry of
  `rocket.launcher_stage[].landing`), so the companion card can show target
  orbit and booster recovery status without any client-side guessing. The
  upcoming-launches request already used `mode=detailed`, so this data was
  already coming back from Launch Library - it just wasn't being forwarded
- `landing_attempt` is `None` (not `False`) when a launch has no launcher
  stage/landing data at all, so consumers can tell "confirmed expendable"
  apart from "we don't know yet" instead of assuming the latter is a no

## 0.1.2

- **Fixed launch-site filtering**: switched from `location__name__contains`
  to `location__ids`. The text filter was only ever confirmed against the
  Pad list endpoint's documented filters, not the launch/upcoming endpoint
  itself, and unrecognized filter params are silently ignored rather than
  rejected on this API - so it was at real risk of quietly matching
  nothing (returning every launch worldwide, unfiltered) instead of
  actually restricting to your site
- The site filter you type is now resolved to Launch Library location id(s)
  once at setup (via the `/locations/` search endpoint) rather than passed
  through as text on every poll; setup now fails with a clear error if
  nothing matches, instead of silently creating a tracker that never finds
  anything
- Added a client-side safety-net filter (by exact location id) behind the
  server-side query filter, so a launch from the wrong site can't leak
  into the tracked list even if the upstream filter ever misbehaves
- `sensor.<site>_next_launch` and the `launches` list both now include a
  `location_id` attribute

## 0.1.1

- Fixed `manifest.json` key ordering (hassfest requires `domain`, `name`,
  then the rest alphabetical) - this was failing CI outright
- Added brand assets (`custom_components/rocket_launch_tracker/brand/icon.png`
  and `logo.png`), required for HACS's integration-category validation since
  this integration isn't (yet) listed in the community brands repository
- `sensor.<site>_next_launch` now also exposes a `launch_id` attribute, so
  automations can tell "the same launch's time changed" apart from "a
  different launch is now next" - used by the reschedule-alert blueprint in
  the companion ha-rocket-launch-card repo

## 0.1.0

- Initial release
- Polls Launch Library 2, filtered server-side by launch site
- Adaptive polling: cheap far interval normally, frequent near interval once
  the soonest tracked launch is inside a configurable window, with backoff
  on rate-limit (429) responses
- `sensor.<site>_next_launch` (timestamp entity) and
  `sensor.<site>_upcoming_launches` (count + full list attribute)
- Config flow with site filter, optional API key, and adjustable intervals;
  editable later via Options without removing the integration
- Multiple config entries supported, for tracking more than one site
