"""Button: install or update the lgess_live service on the ESS."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import CONF_HOST, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_SSH_PASSWORD, CONF_SSH_USER, DEFAULT_SSH_USER
from .deploy import DeployError, deploy
from .entity import LgEssEntity


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([LgEssDeployButton(entry.runtime_data)])


class LgEssDeployButton(LgEssEntity, ButtonEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "install_service")

    @property
    def available(self) -> bool:
        return True  # needed exactly when the service is down

    async def async_press(self) -> None:
        data = self.coordinator.config_entry.data
        try:
            await deploy(data[CONF_HOST], data.get(CONF_SSH_USER, DEFAULT_SSH_USER),
                         data.get(CONF_SSH_PASSWORD) or None)
        except DeployError as err:
            raise HomeAssistantError(f"Installing the service on the ESS failed: {err}") from err
        await self.coordinator.async_request_refresh()
