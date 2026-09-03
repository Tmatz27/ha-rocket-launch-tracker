# Changelog

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
