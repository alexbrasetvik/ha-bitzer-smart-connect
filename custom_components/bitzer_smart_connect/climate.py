"""Primary control entity: one per device, owns Control.TempSet and Control.VentSet."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    FAN_OFF,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api.models import Parameter
from .const import (
    CONF_FAN_MAX,
    CONF_FAN_MIN,
    CONF_TEMP_MAX,
    CONF_TEMP_MIN,
    CONF_TEMP_STEP,
)
from .coordinator import BitzerConfigEntry, BitzerDeviceCoordinator
from .entity import BitzerEntity
from .entity_map import CURRENT_TEMP_KEYS
from .profiles import Limit, param_limit

PARALLEL_UPDATES = 0

TEMP_SET_KEY = "Control.TempSet"
VENT_SET_KEY = "Control.VentSet"

# Fallbacks only if the schema omits bounds.
DEFAULT_MIN_TEMP = 5.0
DEFAULT_MAX_TEMP = 50.0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BitzerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    if coordinator.data and _find(coordinator.data, TEMP_SET_KEY) is not None:
        async_add_entities([BscClimate(coordinator)])


def _find(data: dict[str, Parameter], key: str) -> Parameter | None:
    return data.get(f"_USER.{key}") or next((p for p in data.values() if p.key == key), None)


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    try:
        return float(value) != 0
    except ValueError:
        return value.strip().lower() not in ("", "false", "off", "no")


class BscClimate(BitzerEntity, ClimateEntity):
    """Primary HRV control surface: target temperature + ventilation speed."""

    _attr_name = None  # main feature of the device
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE
    )
    _attr_hvac_modes = [HVACMode.AUTO]
    _attr_hvac_mode = HVACMode.AUTO

    def __init__(self, coordinator: BitzerDeviceCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_id}_climate"

    @property
    def _temp_param(self) -> Parameter | None:
        if self.coordinator.data is None:
            return None
        return _find(self.coordinator.data, TEMP_SET_KEY)

    @property
    def _vent_param(self) -> Parameter | None:
        if self.coordinator.data is None:
            return None
        return _find(self.coordinator.data, VENT_SET_KEY)

    @property
    def _heat_param(self) -> Parameter | None:
        if self.coordinator.data is None:
            return None
        for param in self.coordinator.data.values():
            if "heat" not in param.key.lower():
                continue
            if param.is_combo or param.key.lower().endswith("runact"):
                return param
        return None

    @property
    def available(self) -> bool:
        return super().available and self._temp_param is not None

    def _limit(self, key: str) -> Limit | None:
        product_id = self.coordinator.config.product_id if self.coordinator.config else None
        return param_limit(product_id, key)

    def _override(self, option_key: str) -> float | None:
        value = self.coordinator.config_entry.options.get(option_key)
        try:
            return float(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None

    # -- temperature --------------------------------------------------------

    @property
    def current_temperature(self) -> float | None:
        if self.coordinator.data is None:
            return None
        for key in CURRENT_TEMP_KEYS:
            param = _find(self.coordinator.data, key)
            if param is None:
                continue
            value = param.float_value()
            if value is not None:
                return value
        return None

    @property
    def target_temperature(self) -> float | None:
        param = self._temp_param
        return param.float_value() if param else None

    @property
    def min_temp(self) -> float:
        override = self._override(CONF_TEMP_MIN)
        if override is not None:
            return override
        lim = self._limit(TEMP_SET_KEY)
        if lim and lim.min is not None:
            return lim.min
        param = self._temp_param
        value = param.float_min() if param else None
        return value if value is not None else DEFAULT_MIN_TEMP

    @property
    def max_temp(self) -> float:
        override = self._override(CONF_TEMP_MAX)
        if override is not None:
            return override
        lim = self._limit(TEMP_SET_KEY)
        if lim and lim.max is not None:
            return lim.max
        param = self._temp_param
        value = param.float_max() if param else None
        return value if value is not None else DEFAULT_MAX_TEMP

    @property
    def target_temperature_step(self) -> float:
        override = self._override(CONF_TEMP_STEP)
        if override is not None:
            return override
        lim = self._limit(TEMP_SET_KEY)
        if lim and lim.step is not None:
            return lim.step
        param = self._temp_param
        fmt = (param.display_format or "").upper() if param else ""
        return 0.5 if fmt in ("FORM_100", "FORM_10") else 1.0

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs.get(ATTR_TEMPERATURE)
        param = self._temp_param
        if temperature is None or param is None:
            return
        await self._async_write(param.id, str(temperature))

    # -- hvac action ----------------------------------------------------------

    @property
    def hvac_action(self) -> HVACAction | None:
        param = self._heat_param
        if param is None:
            return None
        return HVACAction.HEATING if _truthy(param.value) else HVACAction.IDLE

    # -- fan (ventilation speed) ----------------------------------------------

    def _vent_range(self) -> tuple[int, int]:
        lim = self._limit(VENT_SET_KEY)
        param = self._vent_param
        api_lo = int(param.float_min()) if param and param.float_min() is not None else 0
        api_hi = int(param.float_max()) if param and param.float_max() is not None else 4
        ov_lo, ov_hi = self._override(CONF_FAN_MIN), self._override(CONF_FAN_MAX)
        lo = int(ov_lo) if ov_lo is not None else (int(lim.min) if lim and lim.min is not None else api_lo)
        hi = int(ov_hi) if ov_hi is not None else (int(lim.max) if lim and lim.max is not None else api_hi)
        return lo, hi

    @property
    def fan_modes(self) -> list[str]:
        lo, hi = self._vent_range()
        return [_fan_label(i) for i in range(lo, hi + 1)]

    @property
    def fan_mode(self) -> str | None:
        param = self._vent_param
        if param is None:
            return None
        value = param.float_value()
        return _fan_label(int(value)) if value is not None else None

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        param = self._vent_param
        if param is None:
            return
        value = 0 if fan_mode == FAN_OFF else _as_int(fan_mode)
        if value is None:
            raise ServiceValidationError(f"unknown fan mode {fan_mode}")
        await self._async_write(param.id, str(value))

    # -- writes -----------------------------------------------------------------

    async def _async_write(self, param_id: str, value: str) -> None:
        await self.coordinator.client.async_set_parameters(
            self.coordinator.device_id, self.coordinator.config, {param_id: value}
        )
        await self.coordinator.async_request_refresh()


def _fan_label(value: int) -> str:
    return FAN_OFF if value == 0 else str(value)


def _as_int(value: str) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None
