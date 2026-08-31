"""Climate: fan modes mapped to Home Assistant's standard low/medium/high via the profile."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from custom_components.bitzer_smart_connect.api.models import DeviceConfig
from custom_components.bitzer_smart_connect.climate import BscClimate


def _climate(config_sample_json) -> BscClimate:
    config = DeviceConfig.from_json(config_sample_json)
    coordinator = MagicMock()
    coordinator.device_id = 1234
    coordinator.device_name = "HRV"
    coordinator.config = config
    coordinator.data = config.parameters
    coordinator.config_entry = MagicMock()
    coordinator.config_entry.options = {}
    coordinator.client.async_set_parameters = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()
    return BscClimate(coordinator)


def test_fan_modes_are_named(config_sample_json):
    climate = _climate(config_sample_json)
    assert climate.fan_modes == ["low", "medium", "high"]


def test_fan_mode_reflects_value(config_sample_json):
    # sample Control.VentSet actualValue is "2"
    assert _climate(config_sample_json).fan_mode == "medium"


async def test_set_fan_mode_writes_raw_value(config_sample_json):
    climate = _climate(config_sample_json)
    await climate.async_set_fan_mode("high")
    _, _, changes = climate.coordinator.client.async_set_parameters.call_args.args
    assert changes == {"_USER.Control.VentSet": "3"}
