# ha-rocket-launch-tracker

Home Assistant custom integration that polls Launch Library 2
(`ll.thespacedevs.com/2.3.0`) for one launch site (default Vandenberg) and
exposes it as two sensors. This is the backend half of a two-repo system;
the frontend is
**[Tmatz27/ha-rocket-launch-card](https://github.com/Tmatz27/ha-rocket-launch-card-)**,
which reads `sensor.<site>_next_launch` and `sensor.<site>_upcoming_launches`
and never calls Launch Library directly.

Current released version: **v0.2.10** (as of 2026-09-11). Check
`VERSION`/`CHANGELOG.md` for current truth.

## Architecture essentials

- `api.py` (`LaunchLibraryClient`) is pure Python, no HA imports - fully
  unit-testable offline. `coordinator.py`/`config_flow.py`/`sensor.py` are
  the HA glue and were written against documented HA APIs but were never
  exercised against a running HA instance during development - if
  something looks off in the entity/device setup, that's the first place
  to suspect, and worth confirming against Developer Tools → States.
- Site filtering uses exact numeric `location__ids` (resolved once at
  setup via `/locations/`), never a text filter server-side - LL2 silently
  ignores filter params an endpoint doesn't recognize rather than
  rejecting them, so a wrong filter would look identical to "no launches"
  instead of erroring. Results are also double-checked against those ids
  client-side as a safety net.
- **Shared request budget** (`request_budget.py`, added 0.2.9): a sliding
  15-req/hour window shared across all config entries via
  `hass.data["rocket_launch_tracker_request_budgets"]`, keyed by SHA-256 of
  the API key (or `"anonymous"`). `LaunchLibraryClient.budget` is a
  **required, keyword-only** constructor arg (0.2.10) - it used to default
  to `field(default_factory=RequestBudget)`, which meant a call site that
  forgot `budget=shared_budget(hass.data, api_key)` would silently get an
  unshared budget with no error, quietly defeating the whole point. If you
  add a new construction site, you must pass `budget=` or it won't compile.
- `backoff_seconds(far_seconds, current_seconds, retry_after)` is
  `max(3600, far*2, current, retry_after)` - deliberately a max, not a
  min, so a long configured far-interval is never shrunk by a 429.
- A `BudgetDeferred` (proactive local block, before any network call) is
  handled differently from a real server `LaunchLibraryRateLimited` (429):
  the former quietly serves cached data if available, the latter always
  raises `UpdateFailed` even with good cached data. This asymmetry is
  intentional but was flagged as a legitimate design question, not settled
  doctrine - reconsider it if it causes user-visible confusion.
- `landing_attempt` is a tri-state (`True`/`False`/`None`, not just
  bool) - `None` means the launch has no launcher-stage landing data at
  all, distinct from an explicit "no landing attempt planned." Landing
  location is `landing_location` (LL2 2.3.0 renamed this from the older
  `location` key - `parse_launch` falls back to the old key for
  compatibility).

## What's actually tested

- `tests/test_pure_logic.py` - parsing, interval/backoff decisions,
  location filtering. Stubs `homeassistant.*` in `sys.modules` via
  `patch.dict`, then does a REAL `importlib.import_module` of the actual
  module under test - not a hand-simulated reimplementation.
- `tests/test_request_budget.py` (added 0.2.9) - same stubbing pattern,
  extended to `coordinator.py`: `load_coordinator()` builds minimal fake
  HA base classes and imports the real coordinator against them, so
  `_async_update_data()`'s actual branching (`BudgetDeferred` vs.
  `LaunchLibraryRateLimited` vs. generic error) is genuinely exercised.
- Run with `python -m pytest tests/ -v` (35 tests as of 0.2.10).

## Release process

Push to `main` → `.github/workflows/validate.yml` (hassfest + HACS
validation + `scripts/check_version.py` + pytest) → on success,
`release.yml` fires via `workflow_run`, reads `VERSION`, pulls the
matching `## X.Y.Z` section from `CHANGELOG.md`, and publishes the GitHub
release. `check_version.py` requires `VERSION`, `manifest.json`'s
`version`, and a `## X.Y.Z` CHANGELOG heading to all agree - bump all
three together, no separate JS-style version constant here.

## What Launch Library 2 does NOT give you

No propellant/fuel mass field anywhere in the API - confirmed against
TheSpaceDevs' own 2.3.0 changelog. `LauncherConfiguration` (the rocket
*model*, e.g. "Falcon 9 Block 5" - not the individual launch) exposes
`launch_mass` (total liftoff mass), `to_thrust`, and payload capacities
(LEO/GTO/SSO), but nothing per-launch and nothing propellant-specific.
`parse_launch()` doesn't currently pull any of these fields into the
sensor payload at all - if a future feature wants vehicle-level specs
(mass, thrust) for a "how big/loud is this rocket" indicator, they'd need
to be added to `parse_launch()` from `rocket.configuration.*`, keeping in
mind they're constant per rocket type, not per launch.
