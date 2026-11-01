import pytest

pytest_plugins = ["pytest_homeassistant_custom_component"]

SAMPLE = {
    "ac_freq_hz": 50.0, "ac_power_w": 1834, "batt_current_a": 0.0, "batt_power_w": 0,
    "batt_soc_pct": 0.0, "batt_status": 0, "batt_voltage_v": 76.2, "dc_link_v": 624,
    "grid_export_w": 1210.4, "grid_import_w": 0.0, "grid_power_w": -1210.4,
    "load_power_w": 623.6, "meter_freq_hz": 50.01, "meter_power_w": -1210.4,
    "pv1_current_a": 3, "pv1_power_w": 1012, "pv1_voltage_v": 342,
    "pv2_current_a": 2, "pv2_power_w": 905, "pv2_voltage_v": 318,
    "pv_power_w": 1917, "timestamp": 1793515177,
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield
