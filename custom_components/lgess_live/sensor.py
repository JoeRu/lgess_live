"""Power, voltage, current, frequency and energy sensors."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (RestoreSensor, SensorDeviceClass, SensorEntity,
                                             SensorEntityDescription, SensorStateClass)
from homeassistant.const import (PERCENTAGE, UnitOfElectricCurrent, UnitOfElectricPotential,
                                 UnitOfEnergy, UnitOfFrequency, UnitOfPower)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .energy import EnergyIntegrator
from .entity import LgEssEntity


@dataclass(frozen=True, kw_only=True)
class LgEssSensorDescription(SensorEntityDescription):
    field: str


def _d(key, field, unit, dc, enabled=True, prec=None):
    return LgEssSensorDescription(key=key, field=field, native_unit_of_measurement=unit,
                                  device_class=dc, state_class=SensorStateClass.MEASUREMENT,
                                  entity_registry_enabled_default=enabled,
                                  suggested_display_precision=prec)


W, V, A, HZ = UnitOfPower.WATT, UnitOfElectricPotential.VOLT, UnitOfElectricCurrent.AMPERE, UnitOfFrequency.HERTZ
P, U, I, F = SensorDeviceClass.POWER, SensorDeviceClass.VOLTAGE, SensorDeviceClass.CURRENT, SensorDeviceClass.FREQUENCY

SENSORS: tuple[LgEssSensorDescription, ...] = (
    _d("pv_power", "ac_power_w", W, P),             # AC fed in by the inverter
    _d("pv_power_dc", "pv_power_w", W, P),
    _d("grid_power", "grid_power_w", W, P, prec=0),  # + import / - export
    _d("grid_import", "grid_import_w", W, P, prec=0),
    _d("grid_export", "grid_export_w", W, P, prec=0),
    _d("consumption", "load_power_w", W, P, prec=0),
    _d("grid_frequency", "meter_freq_hz", HZ, F, prec=2),
    _d("pv1_power", "pv1_power_w", W, P, False),
    _d("pv1_voltage", "pv1_voltage_v", V, U, False),
    _d("pv1_current", "pv1_current_a", A, I, False),
    _d("pv2_power", "pv2_power_w", W, P, False),
    _d("pv2_voltage", "pv2_voltage_v", V, U, False),
    _d("pv2_current", "pv2_current_a", A, I, False),
    _d("dc_link_voltage", "dc_link_v", V, U, False),
    _d("battery_power", "batt_power_w", W, P, False),
    _d("battery_voltage", "batt_voltage_v", V, U, False, 1),
    LgEssSensorDescription(key="battery_soc", field="batt_soc_pct", native_unit_of_measurement=PERCENTAGE,
                           device_class=SensorDeviceClass.BATTERY, state_class=SensorStateClass.MEASUREMENT,
                           entity_registry_enabled_default=False, suggested_display_precision=0),
)

# (key, power field) -> kWh counters for the energy dashboard
ENERGY = (
    ("grid_import_energy", "grid_import_w"),
    ("grid_export_energy", "grid_export_w"),
    ("pv_energy", "ac_power_w"),
    ("consumption_energy", "load_power_w"),
)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [LgEssSensor(coordinator, d) for d in SENSORS]
    entities += [LgEssEnergySensor(coordinator, key, field) for key, field in ENERGY]
    async_add_entities(entities)


class LgEssSensor(LgEssEntity, SensorEntity):
    entity_description: LgEssSensorDescription

    def __init__(self, coordinator, description: LgEssSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        return data.get(self.entity_description.field)


class LgEssEnergySensor(LgEssEntity, RestoreSensor):
    """kWh counter integrated from a power value; survives restarts."""

    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 3

    def __init__(self, coordinator, key: str, field: str) -> None:
        super().__init__(coordinator, key)
        self._field = field
        self._integrator = EnergyIntegrator()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_sensor_data()
        if last is not None and last.native_value is not None:
            try:
                self._integrator = EnergyIntegrator(float(last.native_value))
            except (TypeError, ValueError):
                pass
        self._handle_coordinator_update()

    @callback
    def _handle_coordinator_update(self) -> None:
        data = self.coordinator.data or {}
        if self.coordinator.last_update_success and self._field in data:
            self._integrator.add(data[self._field], dt_util.utcnow().timestamp())
        super()._handle_coordinator_update()

    @property
    def native_value(self) -> float:
        return round(self._integrator.total_kwh, 6)
