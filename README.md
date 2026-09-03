# Rocket Launch Tracker

A Home Assistant integration that tracks upcoming rocket launches from
**[Launch Library 2](https://ll.thespacedevs.com)** (thespacedevs.com),
filtered server-side to a launch site you choose (Vandenberg, Cape
Canaveral, Starbase, wherever), with polling that speeds up automatically
as a launch gets close.

This is the backend half of a two-repo project:

- **This repo** — polls Launch Library 2 and exposes the result as Home
  Assistant sensors.
- **[Tmatz27/ha-rocket-launch-card](https://github.com/Tmatz27/ha-rocket-launch-card-)**
  — the Lovelace cards and automation blueprints that read those sensors.
  Install this repo first.

## Why this exists

[djtimca/harocketlaunchlive](https://github.com/djtimca/harocketlaunchlive)
(a different, older integration built on rocketlaunch.live) always exposes
exactly the next 5 launches worldwide, with no site filter of its own — if 5
launches from other sites are queued up before the next one from yours, it
simply isn't in the data yet, no matter what a card does with it
client-side. It also has no explicit Go/Hold/Scrub status field, only raw
target times.

Launch Library 2 supports filtering by location directly, and reports a real
status per launch, so this integration does the filtering **at the source**
instead: it only ever fetches and stores launches that match your site.

## How it works

- One config entry per site you want to track (add the integration again for
  a second site — Starbase alongside Vandenberg, for example).
- Polls Launch Library 2's `/launches/upcoming/` endpoint, filtered by
  `location__name__contains=<your site>`.
- **Adaptive polling**: far out, it polls infrequently (30 minutes by
  default); once the soonest tracked launch is inside a near-window (48
  hours by default), it switches to polling frequently (5 minutes by
  default). This is what keeps predicted-schedule data cheap while still
  getting live, up-to-date status once a launch actually matters.
- The unauthenticated Launch Library tier is rate-limited to **15
  requests/hour**. The defaults above use at most ~14/hour even with a
  launch imminent (2/hour baseline + up to 12/hour near a launch), so they
  fit inside the free tier without a key. A free registered API key raises
  that ceiling further — see [thespacedevs.com/llapi](https://thespacedevs.com/llapi).
  If you widen the intervals, the config flow won't let the near interval go
  below 3 minutes or the far interval below 15, as a guardrail against
  accidentally exceeding the free tier.
- On a 429 (rate limited), it backs off to at least double the far interval
  rather than retrying immediately.

## Requirements

1. Home Assistant 2024.10 or newer
2. HACS
3. Optionally, a free [Launch Library 2 API key](https://thespacedevs.com/llapi)
   for a higher rate limit — the free unauthenticated tier works fine for
   one or two tracked sites

## Install with HACS

1. Open **HACS**
2. Open the three-dot menu and choose **Custom repositories**
3. Add `https://github.com/Tmatz27/ha-rocket-launch-tracker`
4. Choose the **Integration** category
5. Install **Rocket Launch Tracker**
6. Restart Home Assistant

## Set up

**Settings → Devices & Services → + Add Integration → Rocket Launch
Tracker.**

| Field | Default | Description |
| --- | --- | --- |
| Launch site filter | `Vandenberg` | Case-insensitive text matched against the launch pad's location name. Leave blank to track every launch worldwide |
| API key | *(blank)* | Optional. Raises the rate limit above the free 15/hour tier |
| How many upcoming matching launches to track | `5` | Size of the "Upcoming Launches" list |
| Switch to live polling this many hours before launch | `48` | The near-window |
| Live polling interval (minutes) | `5` | How often to poll inside the near-window |
| Normal polling interval (minutes) | `30` | How often to poll otherwise |

Everything here can be changed later from the integration's **Configure**
button without removing and re-adding it.

## Entities

Each config entry creates a device (named after your site filter) with two
sensors:

- **`sensor.<site>_next_launch`** — a `timestamp`-class sensor. Its state
  *is* the next matching launch's target time (or `unknown` if none is
  tracked), which means it works directly in automations
  (`states('sensor.vandenberg_next_launch')`) and shows a relative
  countdown in Home Assistant's own UI, no template needed. Attributes:
  `name`, `mission_name`, `mission_description`, `status`, `status_abbrev`,
  `provider`, `rocket`, `pad_name`, `location_name`, `net_precision`,
  `window_start`, `window_end`, `probability`, `image`, `webcast_live`,
  `hold_reason`, `fail_reason`, `last_updated`.
- **`sensor.<site>_upcoming_launches`** — state is the count of currently
  tracked matching launches. Its `launches` attribute is the full list, each
  entry shaped the same as the next-launch sensor's attributes above, ordered
  soonest-first. This is what the Lovelace cards read.

## What's tested, and what isn't

The API client, launch-JSON parsing, and the adaptive-interval decision
logic (`api.py`, `interval.py`) are pure Python with no Home Assistant
dependency and have a real pytest suite (`tests/`) run in CI. They're the
parts most likely to have a bug and the easiest to get right in isolation.

The Home Assistant glue (`config_flow.py`, `coordinator.py`, `sensor.py`,
`__init__.py`) was written carefully against documented, stable Home
Assistant integration APIs and passes `hassfest` validation in CI, but
**wasn't exercised against a running Home Assistant instance** while being
built. After installing, check **Settings → Devices & Services → Rocket
Launch Tracker** and **Developer Tools → States** to confirm the entities
look right, and please open an issue if something doesn't.

A couple of Launch Library 2 response fields (`image` in particular) have
changed shape across API versions; parsing for those is defensive (falls
back to `None` rather than raising), so a launch missing an image just shows
no image rather than breaking the sensor.

## Development

```bash
pip install pytest
python -m pytest tests/ -v
```

## Credits

Data from [Launch Library 2](https://ll.thespacedevs.com) by
[The Space Devs](https://thespacedevs.com). Not affiliated with or endorsed
by them — please respect their [rate limits](https://thespacedevs.com/llapi).

## License

MIT
