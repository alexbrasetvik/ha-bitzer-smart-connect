"""Shared base entity for Bitzer Smart Connect."""

from __future__ import annotations

import re

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .api.models import Parameter
from .coordinator import BitzerDeviceCoordinator
from .profiles import product_model


def friendly_name(localization: dict[str, str], key: str) -> str:
    """Best human name for a parameter key, from the device's own localization.

    Prefers the concise ``SIMPLE_PARM_*`` label, then the descriptive ``RDB_HELPTEXT_*`` help text.
    Localization keying is inconsistent for the temperature inputs: some carry the full suffix
    (``Input.T3_Exhaust`` -> ``RDB_HELPTEXT_INPUT_T3_EXHAUST``), others only the base T-number
    (``Input.T18_Rotor`` -> ``RDB_HELPTEXT_INPUT_T18`` -> "Rotor temperature"), so both are tried.
    Falls back to a humanized key.
    """
    upper = key.upper().replace(".", "_")
    forms = [upper]
    base = re.match(r"(INPUT_T\d+)_", upper)
    if base:
        forms.append(base.group(1))
    for form in forms:
        for prefix in ("SIMPLE_PARM_", "RDB_HELPTEXT_"):
            name = localization.get(prefix + form)
            if name:
                return name
    return _humanize(key)


def _humanize(key: str) -> str:
    tail = key.rsplit(".", 1)[-1]
    words = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", tail).replace("_", " ").strip()
    return words[:1].upper() + words[1:] if words else key


class BitzerEntity(CoordinatorEntity[BitzerDeviceCoordinator]):
    """Base class wiring device info + availability once."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: BitzerDeviceCoordinator) -> None:
        super().__init__(coordinator)
        product_id = coordinator.config.product_id if coordinator.config else None
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(coordinator.device_id))},
            manufacturer=MANUFACTURER,
            model=product_model(product_id) or "LMC311",
            name=coordinator.device_name,
        )

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.device_online


class BitzerParameterEntity(BitzerEntity):
    """Base for an entity bound to a single device parameter."""

    def __init__(self, coordinator: BitzerDeviceCoordinator, param_id: str) -> None:
        super().__init__(coordinator)
        self._param_id = param_id
        self._attr_unique_id = f"{coordinator.device_id}_{param_id}"
        key = param_id[6:] if param_id.startswith("_USER.") else param_id
        self._attr_name = friendly_name(coordinator.localization, key)

    @property
    def parameter(self) -> Parameter | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._param_id)

    @property
    def available(self) -> bool:
        return super().available and self.parameter is not None
