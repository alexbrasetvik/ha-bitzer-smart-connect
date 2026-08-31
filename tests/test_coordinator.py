"""Coordinator: device-online debounce (brief dropouts must not flap availability)."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.bitzer_smart_connect.const import (
    DEVICE_OFFLINE_GRACE,
    DOMAIN,
)
from custom_components.bitzer_smart_connect.coordinator import BitzerDeviceCoordinator


def _coordinator(hass) -> BitzerDeviceCoordinator:
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    coord = BitzerDeviceCoordinator(hass, entry, MagicMock(), 1234, "HRV", 120)
    coord.device_online = True
    return coord


async def _advance(hass, seconds: int) -> None:
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=seconds))
    await hass.async_block_till_done()


async def test_brief_offline_does_not_flap(hass):
    coord = _coordinator(hass)
    coord._apply_online_signal(False)  # dropout
    assert coord.device_online is True  # still online during grace
    coord._apply_online_signal(True)  # recovered quickly
    await _advance(hass, DEVICE_OFFLINE_GRACE + 5)
    assert coord.device_online is True  # cancelled timer never fired


async def test_sustained_offline_marks_unavailable(hass):
    coord = _coordinator(hass)
    coord._apply_online_signal(False)
    assert coord.device_online is True
    await _advance(hass, DEVICE_OFFLINE_GRACE + 5)
    assert coord.device_online is False


async def test_recovery_after_offline_is_immediate(hass):
    coord = _coordinator(hass)
    coord._apply_online_signal(False)
    await _advance(hass, DEVICE_OFFLINE_GRACE + 5)
    assert coord.device_online is False
    coord._apply_online_signal(True)
    assert coord.device_online is True
