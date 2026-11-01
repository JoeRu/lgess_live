"""Config flow: find the service, or install it on the ESS first."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import LgEssApi, LgEssError
from .const import (CONF_SCAN_INTERVAL, CONF_SSH_PASSWORD, CONF_SSH_USER, DEFAULT_PORT,
                    DEFAULT_SCAN_INTERVAL, DEFAULT_SSH_USER, DOMAIN)
from .deploy import DeployError, deploy

CONF_INSTALL = "install_service"


class LgEssConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()
            if user_input.get(CONF_INSTALL):
                try:
                    await deploy(host, user_input[CONF_SSH_USER],
                                 user_input.get(CONF_SSH_PASSWORD))
                except DeployError:
                    errors["base"] = "deploy_failed"
            if not errors:
                api = LgEssApi(async_get_clientsession(self.hass), host, user_input[CONF_PORT])
                try:
                    await api.fetch(timeout=10)
                except LgEssError:
                    errors["base"] = "cannot_connect"
            if not errors:
                return self.async_create_entry(
                    title=f"LG ESS ({host})",
                    data={CONF_HOST: host, CONF_PORT: user_input[CONF_PORT],
                          CONF_SSH_USER: user_input[CONF_SSH_USER],
                          CONF_SSH_PASSWORD: user_input.get(CONF_SSH_PASSWORD, "")})
        schema = vol.Schema({
            vol.Required(CONF_HOST): str,
            vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
            vol.Required(CONF_INSTALL, default=False): bool,
            vol.Required(CONF_SSH_USER, default=DEFAULT_SSH_USER): str,
            vol.Optional(CONF_SSH_PASSWORD, default=""): str,
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return LgEssOptionsFlow()


class LgEssOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        schema = vol.Schema({
            vol.Required(CONF_SCAN_INTERVAL,
                         default=self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)):
                vol.All(int, vol.Range(min=1, max=300)),
        })
        return self.async_show_form(step_id="init", data_schema=schema)
