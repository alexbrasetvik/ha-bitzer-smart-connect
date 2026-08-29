"""Number platform: writable numeric parameters without a dedicated home."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfRatio, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api.models import Parameter
from .const import CONF_EXPOSE_ALL
from .coordinator import BitzerConfigEntry, BitzerDeviceCoordinator
from .entity import BitzerParameterEntity
from .entity_map import EntityHint, entities_for

PARALLEL_UPDATES = 0

_DEVICE_CLASSES: dict[str, NumberDeviceClass] = {
    "temperature": NumberDeviceClass.TEMPERATURE,
    "humidity": NumberDeviceClass.HUMIDITY,
    "carbon_dioxide": NumberDeviceClass.CO2,
}
_UNITS: dict[str, str] = {
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
        BitzerNumber(coordinator, param, hint)
        for (platform, param, hint) in entities_for(coordinator.data or {})
        if platform == "number" and (hint.enabled_default or expose_all)
    ]
    async_add_entities(entities)


class BitzerNumber(BitzerParameterEntity, NumberEntity):
    """A writable numeric device parameter (setpoint/threshold)."""

    def __init__(
        self, coordinator: BitzerDeviceCoordinator, param: Parameter, hint: EntityHint
    ) -> None:
        super().__init__(coordinator, param.id)
        self._attr_entity_registry_enabled_default = hint.enabled_default
        self._attr_native_step = hint.step or 1.0
        min_value = param.float_min()
        max_value = param.float_max()
        self._attr_native_min_value = 0.0 if min_value is None else min_value
        self._attr_native_max_value = 100.0 if max_value is None else max_value
        if hint.device_class:
            self._attr_device_class = _DEVICE_CLASSES.get(hint.device_class)
        if hint.unit:
            self._attr_native_unit_of_measurement = _UNITS.get(hint.unit, hint.unit)
        self._attr_entity_category = (
            EntityCategory.DIAGNOSTIC if hint.diagnostic else EntityCategory.CONFIG
        )

    @property
    def native_value(self) -> float | None:
        param = self.parameter
        return None if param is None else param.float_value()

    async def async_set_native_value(self, value: float) -> None:
        param = self.parameter
        if param is None:
            return
        await self.coordinator.client.async_set_parameters(
            self.coordinator.device_id, self.coordinator.config, {param.id: str(value)}
        )
        await self.coordinator.async_request_refresh()
