"""Constants for the LG ESS Live integration."""

DOMAIN = "lgess_live"

CONF_SSH_USER = "ssh_user"
CONF_SSH_PASSWORD = "ssh_password"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_PORT = 8085
DEFAULT_SSH_USER = "root"
DEFAULT_SCAN_INTERVAL = 5  # seconds

# Do not integrate power across gaps longer than this (outage, HA restart):
# the energy of an unknown period is not invented.
MAX_INTEGRATION_GAP = 60.0  # seconds
