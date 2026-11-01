from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.lgess_live.api import LgEssError
from custom_components.lgess_live.const import DOMAIN
from custom_components.lgess_live.deploy import DeployError

from .conftest import SAMPLE

USER = {"host": "10.0.0.17", "port": 8085, "install_service": False, "ssh_user": "root", "ssh_password": ""}
API = "custom_components.lgess_live.config_flow.LgEssApi.fetch"
DEPLOY = "custom_components.lgess_live.config_flow.deploy"


async def test_service_found(hass):
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert r["type"] is FlowResultType.FORM
    with patch(API, AsyncMock(return_value=SAMPLE)), \
         patch("custom_components.lgess_live.async_setup_entry", AsyncMock(return_value=True)):
        r = await hass.config_entries.flow.async_configure(r["flow_id"], USER)
    assert r["type"] is FlowResultType.CREATE_ENTRY
    assert r["data"]["host"] == "10.0.0.17"


async def test_service_missing_shows_error(hass):
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    with patch(API, AsyncMock(side_effect=LgEssError("down"))):
        r = await hass.config_entries.flow.async_configure(r["flow_id"], USER)
    assert r["errors"] == {"base": "cannot_connect"}


async def test_install_then_connect(hass):
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    dep = AsyncMock(return_value="")
    with patch(DEPLOY, dep), patch(API, AsyncMock(return_value=SAMPLE)), \
         patch("custom_components.lgess_live.async_setup_entry", AsyncMock(return_value=True)):
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {**USER, "install_service": True})
    assert r["type"] is FlowResultType.CREATE_ENTRY
    dep.assert_awaited_once_with("10.0.0.17", "root", "")


async def test_install_failure(hass):
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    with patch(DEPLOY, AsyncMock(side_effect=DeployError("auth"))):
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {**USER, "install_service": True})
    assert r["errors"] == {"base": "deploy_failed"}
