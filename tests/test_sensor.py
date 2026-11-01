from datetime import timedelta
from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from homeassistant.util import dt as dt_util

from custom_components.lgess_live.const import DOMAIN

from .conftest import SAMPLE

API = "custom_components.lgess_live.LgEssApi.fetch"


def entry():
    return MockConfigEntry(domain=DOMAIN, unique_id="10.0.0.17", title="LG ESS",
                           data={"host": "10.0.0.17", "port": 8085, "ssh_user": "root", "ssh_password": ""})


async def test_sensors_and_energy(hass, freezer):
    e = entry(); e.add_to_hass(hass)
    with patch(API, AsyncMock(return_value=SAMPLE)):
        assert await hass.config_entries.async_setup(e.entry_id)
        await hass.async_block_till_done()
        assert hass.states.get("sensor.lg_ess_grid_power").state == "-1210.4"
        assert hass.states.get("sensor.lg_ess_pv_power").state == "1834"
        assert hass.states.get("sensor.lg_ess_grid_export").attributes["unit_of_measurement"] == "W"
        assert hass.states.get("sensor.lg_ess_grid_export_energy").state == "0.0"
        freezer.tick(timedelta(seconds=5))
        async_fire_time_changed(hass, dt_util.utcnow())
        await hass.async_block_till_done()
    exp = float(hass.states.get("sensor.lg_ess_grid_export_energy").state)
    assert abs(exp - 1210.4 * 5 / 3_600_000) < 1e-6
    imp = float(hass.states.get("sensor.lg_ess_grid_import_energy").state)
    assert imp == 0.0
    st = hass.states.get("sensor.lg_ess_pv_energy")
    assert st.attributes["state_class"] == "total_increasing"
    assert st.attributes["device_class"] == "energy"


async def test_unavailable_when_service_down(hass, freezer):
    e = entry(); e.add_to_hass(hass)
    from custom_components.lgess_live.api import LgEssError
    m = AsyncMock(return_value=SAMPLE)
    with patch(API, m):
        assert await hass.config_entries.async_setup(e.entry_id)
        await hass.async_block_till_done()
        m.side_effect = LgEssError("down")
        freezer.tick(timedelta(seconds=5))
        async_fire_time_changed(hass, dt_util.utcnow())
        await hass.async_block_till_done()
    assert hass.states.get("sensor.lg_ess_grid_power").state == "unavailable"
    # the install button stays usable exactly then
    assert hass.states.get("button.lg_ess_install_or_update_service").state != "unavailable"
