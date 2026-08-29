"""HA select platform: enumerated/combo device parameters."""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api.models import Parameter
from .const import CONF_EXPOSE_ALL
from .coordinator import BitzerConfigEntry, BitzerDeviceCoordinator
from .entity import BitzerParameterEntity
from .entity_map import EntityHint, entities_for

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


def _as_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _int_range(param: Parameter) -> tuple[int, int] | None:
    lo, hi = param.float_min(), param.float_max()
    if lo is None or hi is None:
        return None
    lo_i, hi_i = int(lo), int(hi)
    return (lo_i, hi_i) if lo_i <= hi_i else None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BitzerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    expose_all = entry.options.get(CONF_EXPOSE_ALL, False)
    entities = [
        BitzerSelect(coordinator, param.id, hint)
        for (platform, param, hint) in entities_for(coordinator.data or {})
        if platform == "select" and (hint.enabled_default or expose_all)
    ]
    async_add_entities(entities)


class BitzerSelect(BitzerParameterEntity, SelectEntity):
    """A writable enumerated device parameter (combo/range with labeled values)."""

    def __init__(
        self, coordinator: BitzerDeviceCoordinator, param_id: str, hint: EntityHint
    ) -> None:
        super().__init__(coordinator, param_id)
        self._attr_entity_registry_enabled_default = hint.enabled_default
        if hint.diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._label_to_value: dict[str, str] = {}
        self._value_to_label: dict[str, str] = {}
        param = self.parameter
        if param is None:
            self._attr_options = []
            return
        self._build_options(param)

    def _build_options(self, param: Parameter) -> None:
        # Options are the device's static schema (min/max); safe to build once at setup.
        tail = param.key.rsplit(".", 1)[-1].upper()
        lo, hi = _int_range(param) or (0, 1)
        current = _as_int(param.value)
        if current is not None:
            lo, hi = min(lo, current), max(hi, current)
        localization = self.coordinator.localization
        for n in range(lo, hi + 1):
            value = str(n)
            label = localization.get(f"TOGGLE_VALUE_{tail}_{n}", value)
            self._label_to_value[label] = value
            self._value_to_label[value] = label
        self._attr_options = list(self._label_to_value)

    @property
    def current_option(self) -> str | None:
        param = self.parameter
        if param is None:
            return None
        current = _as_int(param.value)
        if current is None:
            return None
        return self._value_to_label.get(str(current))

    async def async_select_option(self, option: str) -> None:
        param = self.parameter
        coordinator = self.coordinator
        if param is None or coordinator.config is None:
            _LOGGER.warning("Cannot set %s: device config unavailable", self._param_id)
            return
        value = self._label_to_value.get(option, option)
        await coordinator.client.async_set_parameters(
            coordinator.device_id, coordinator.config, {param.id: value}
        )
        await coordinator.async_request_refresh()
