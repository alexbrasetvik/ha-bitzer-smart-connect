"""Switch platform: writable boolean (FORM_BOOL) parameters."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_EXPOSE_ALL
from .coordinator import BitzerConfigEntry, BitzerDeviceCoordinator
from .entity import BitzerParameterEntity
from .entity_map import EntityHint, entities_for

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BitzerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    expose_all = entry.options.get(CONF_EXPOSE_ALL, False)
    entities = [
        BitzerSwitch(coordinator, param.id, hint)
        for (platform, param, hint) in entities_for(coordinator.data or {})
        if platform == "switch" and (hint.enabled_default or expose_all)
    ]
    async_add_entities(entities)


class BitzerSwitch(BitzerParameterEntity, SwitchEntity):
    """A writable boolean device parameter."""

    def __init__(
        self, coordinator: BitzerDeviceCoordinator, param_id: str, hint: EntityHint
    ) -> None:
        super().__init__(coordinator, param_id)
        self._attr_entity_registry_enabled_default = hint.enabled_default
        if hint.diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool | None:
        param = self.parameter
        if param is None:
            return None
        val = param.float_value()
        return None if val is None else val != 0

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_write("1")

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_write("0")

    async def _async_write(self, value: str) -> None:
        if param is None or self.coordinator.config is None:
            return
        await self.coordinator.client.async_set_parameters(
            self.coordinator.device_id, self.coordinator.config, {param.id: value}
        )
        await self.coordinator.async_request_refresh()
