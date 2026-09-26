"""Constants for the Rocket Launch Tracker integration."""

DOMAIN = "rocket_launch_tracker"

API_BASE_URL = "https://ll.thespacedevs.com/2.3.0"
UPCOMING_PATH = "/launches/upcoming/"
LOCATIONS_PATH = "/locations/"

CONF_SITE_FILTER = "site_filter"
CONF_LOCATION_IDS = "location_ids"
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
# requests/hour (https://thespacedevs.com/llapi). The shared request budget
# enforces this across entries and setup requests; interval floors alone
# cannot enforce a combined ceiling. Clamp legacy values at runtime too.
MIN_NEAR_INTERVAL_MINUTES = 5
MIN_FAR_INTERVAL_MINUTES = 15

# A single failed poll (timeout, 5xx, rate limit) keeps serving the last good
# data; the sensors only go unavailable once this many polls in a row fail.
# Counting polls rather than minutes scales with cadence: ~15 minutes near a
# launch, ~90 minutes otherwise.
FAILED_POLLS_BEFORE_UNAVAILABLE = 3

ATTRIBUTION = "Data provided by Launch Library 2 (thespacedevs.com)"
