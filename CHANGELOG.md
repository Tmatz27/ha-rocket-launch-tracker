# Changelog

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
