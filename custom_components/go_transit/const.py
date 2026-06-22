"""Constants for GO Transit integration."""

DOMAIN = "go_transit"
CONF_API_KEY = "api_key"
CONF_FROM_STOP = "from_stop"
CONF_FROM_STOP_CODE = "from_stop_code"
CONF_TO_STOP = "to_stop"
CONF_TO_STOP_CODE = "to_stop_code"
CONF_LINE_CODE = "line_code"
CONF_LINE_NAME = "line_name"
CONF_MAX_DEPARTURES = "max_departures"
CONF_COMMUTE_START = "commute_start"
CONF_COMMUTE_END = "commute_end"
CONF_TRAVEL_TIME_SENSOR = "travel_time_sensor"
CONF_TRAVEL_TIME_FIXED = "travel_time_fixed"
CONF_SERVICE_START = "service_start"
CONF_SERVICE_END = "service_end"

BASE_URL = "https://api.openmetrolinx.com/OpenDataAPI/api/V1"

# Platforms this integration sets up
PLATFORMS = ["sensor", "binary_sensor", "device_tracker"]

# Poll intervals (seconds)
INTERVAL_DEPARTURES = 120        # next departure + schedule
INTERVAL_VEHICLES_ACTIVE = 30    # vehicle positions during commute window
INTERVAL_VEHICLES_IDLE = 300     # vehicle positions outside commute window
INTERVAL_ALERTS = 900            # service alerts
INTERVAL_CONSIST = 300           # consist
INTERVAL_GUARANTEE = 300         # service guarantee

# Backoff: when a coordinator hits consecutive failures, multiply its interval
BACKOFF_MULTIPLIER = 2.0
BACKOFF_MAX_INTERVAL = 1800      # cap backoff at 30 min
BACKOFF_THRESHOLD = 3            # start backing off after N consecutive failures

# Sensor unique ID suffixes
SENSOR_NEXT_DEPARTURE = "next_departure"
SENSOR_DEPARTURES = "departures"
SENSOR_ALERTS = "alerts"
SENSOR_VEHICLE_POSITION = "vehicle_position"
SENSOR_DELAY = "delay"
SENSOR_CONSIST = "consist"
SENSOR_GUARANTEE = "guarantee"
SENSOR_PLATFORM = "platform"
SENSOR_STATUS = "status"
BINARY_CATCHABLE = "catchable"
TRACKER_TRAIN = "train"

# Defaults
DEFAULT_COMMUTE_START = "05:00"
DEFAULT_COMMUTE_END = "10:00"
DEFAULT_TRAVEL_TIME_FIXED = 10   # minutes — fallback if no sensor / sensor unavailable
DEFAULT_SERVICE_START = "05:00"  # no trains poll before this
DEFAULT_SERVICE_END = "01:30"    # service runs late; overnight window (05:00–01:30 next day)
