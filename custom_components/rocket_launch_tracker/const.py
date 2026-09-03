"""Constants for the Rocket Launch Tracker integration."""

DOMAIN = "rocket_launch_tracker"

API_BASE_URL = "https://ll.thespacedevs.com/2.3.0"
UPCOMING_PATH = "/launches/upcoming/"

CONF_SITE_FILTER = "site_filter"
CONF_API_KEY = "api_key"
CONF_UPCOMING_COUNT = "upcoming_count"
CONF_NEAR_WINDOW_HOURS = "near_window_hours"
CONF_NEAR_INTERVAL_MINUTES = "near_interval_minutes"
CONF_FAR_INTERVAL_MINUTES = "far_interval_minutes"

DEFAULT_SITE_FILTER = "Vandenberg"
DEFAULT_UPCOMING_COUNT = 5
DEFAULT_NEAR_WINDOW_HOURS = 48
DEFAULT_NEAR_INTERVAL_MINUTES = 5
DEFAULT_FAR_INTERVAL_MINUTES = 30

# Free, unauthenticated Launch Library 2 access is rate-limited to 15
# requests/hour (https://thespacedevs.com/llapi). A registered API key raises
# that ceiling. These floors keep a misconfigured instance from ever being
# able to exceed the free tier on its own, regardless of the configured
# intervals; async_get_stub_config and the options flow clamp to them.
MIN_NEAR_INTERVAL_MINUTES = 3
MIN_FAR_INTERVAL_MINUTES = 15

ATTRIBUTION = "Data provided by Launch Library 2 (thespacedevs.com)"
