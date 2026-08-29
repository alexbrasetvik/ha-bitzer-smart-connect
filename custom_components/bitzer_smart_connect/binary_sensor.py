"""Binary sensor platform."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_EXPOSE_ALL
from .coordinator import BitzerConfigEntry
from .entity import BitzerParameterEntity
from .entity_map import EntityHint, entities_for

PARALLEL_UPDATES = 0

_TRUE_VALUES = frozenset({"1", "true", "on", "yes"})
_FALSE_VALUES = frozenset({"0", "false", "off", "no", ""})


def _device_class(param_key: str) -> BinarySensorDeviceClass | None:
    key = param_key.lower()
    if any(word in key for word in ("alarm", "fault", "filter")):
        return BinarySensorDeviceClass.PROBLEM
    if any(word in key for word in ("run", "status")):
        return BinarySensorDeviceClass.RUNNING
    return None


def _bool_value(value: str | None) -> bool | None:
    if value is None:
        return None
    v = value.strip().lower()
    if v in _TRUE_VALUES:
        return True
    if v in _FALSE_VALUES:
        return False
    try:
        return float(v) != 0
    except ValueError:
        return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BitzerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    expose_all = entry.options.get(CONF_EXPOSE_ALL, False)
    entities = [
        BitzerBinarySensor(coordinator, param.id, param.key, hint)
        for (platform, param, hint) in entities_for(coordinator.data or {})
        if platform == "binary_sensor" and (hint.enabled_default or expose_all)
    ]
    async_add_entities(entities)


class BitzerBinarySensor(BitzerParameterEntity, BinarySensorEntity):
    def __init__(self, coordinator, param_id: str, param_key: str, hint: EntityHint) -> None:
        super().__init__(coordinator, param_id)
        self._attr_entity_registry_enabled_default = hint.enabled_default
        self._attr_device_class = _device_class(param_key)
        if hint.diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool | None:
        param = self.parameter
        if param is None:
            return None
        return _bool_value(param.value)
