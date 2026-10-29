"""Constants for the Warema WMS WebControl integration."""

DOMAIN = "warema_webcontrol"

CONF_SCAN_INTERVAL = "scan_interval"
CONF_TILT_OPEN_RAW = "tilt_open_raw"
CONF_TILT_CLOSED_RAW = "tilt_closed_raw"

DEFAULT_SCAN_INTERVAL = 60  # seconds, radio traffic should be kept low
FAST_SCAN_INTERVAL = 3  # seconds, while something is moving
FAST_SCAN_WINDOW = 120  # max seconds of fast polling after a command
MOVE_START_GRACE = 10  # seconds before "not moving" is trusted after a command
STALE_AFTER = 300  # seconds without answer before a channel becomes unavailable

# Raw <winkel> values of the WebControl, measured on real venetian blinds:
# the slats travel between 47 and 207, 127 is horizontal and 207 is the
# closed position used while driving down.
DEFAULT_TILT_OPEN_RAW = 127
DEFAULT_TILT_CLOSED_RAW = 207

ANGLE_UNSUPPORTED = 255

# <produkttyp> of the channel info response, as observed on real hardware
PRODUCT_VENETIAN_BLIND = "0"  # Raffstore
PRODUCT_AWNING = "3"  # Markise
PRODUCT_TYPES = (PRODUCT_VENETIAN_BLIND, PRODUCT_AWNING)
