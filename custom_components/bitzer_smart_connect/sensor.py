"""Sensor platform: read-only measurement/status parameters."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfRatio,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_EXPOSE_ALL
from .coordinator import BitzerConfigEntry, BitzerDeviceCoordinator
from .entity import BitzerParameterEntity
from .entity_map import EntityHint, entities_for

PARALLEL_UPDATES = 0

_DEVICE_CLASS = {
    "temperature": SensorDeviceClass.TEMPERATURE,
    "humidity": SensorDeviceClass.HUMIDITY,
    "carbon_dioxide": SensorDeviceClass.CO2,
}
_MEASUREMENT_CLASSES = frozenset(_DEVICE_CLASS.values())

_UNIT = {
    "°C": UnitOfTemperature.CELSIUS,
    "%": PERCENTAGE,
    "ppm": UnitOfRatio.PARTS_PER_MILLION,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BitzerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    expose_all = entry.options.get(CONF_EXPOSE_ALL, False)
    entities = [
        BitzerSensor(coordinator, param.id, hint)
        for (plat, param, hint) in entities_for(coordinator.data or {})
        if plat == "sensor" and (hint.enabled_default or expose_all)
    ]
    async_add_entities(entities)


class BitzerSensor(BitzerParameterEntity, SensorEntity):
    """Generic read-only parameter sensor."""

    def __init__(
        self, coordinator: BitzerDeviceCoordinator, param_id: str, hint: EntityHint
    ) -> None:
        super().__init__(coordinator, param_id)
        self._attr_entity_registry_enabled_default = hint.enabled_default
        self._attr_device_class = _DEVICE_CLASS.get(hint.device_class or "")
        self._attr_native_unit_of_measurement = _UNIT.get(hint.unit or "", hint.unit)
        if hint.diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        if self._attr_device_class in _MEASUREMENT_CLASSES:
            self._attr_state_class = SensorStateClass.MEASUREMENT
        if self._attr_device_class == SensorDeviceClass.TEMPERATURE:
            self._attr_suggested_display_precision = 1

    @property
    def native_value(self) -> float | str | None:
        param = self.parameter
        if param is None:
            return None
        value = param.float_value()
        return value if value is not None else param.value
