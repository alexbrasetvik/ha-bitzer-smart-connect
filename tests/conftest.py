"""Test fixtures."""

from __future__ import annotations

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

# Sample Configurations/AsJSON payload, shaped like the real response
# (one group, one param of each kind we care about).
_SAMPLE_CONFIG: dict = {
    "deviceId": 1234,
    "deviceName": "HRV",
    "deviceOnline": True,
    "productId": "c51da380-ba51-45ca-8818-a4faf6179b77",
    "groups": [
        {
            "id": "PARAMGROUP_NAME_MAIN",
            "name": "PARAMGROUP_NAME_MAIN",
            "viewParameters": [
                {
                    "id": "_USER.Control.RunAct",
                    "name": "Control.RunAct",
                    "textId": "Control.RunAct",
                    "displayText": "Control.RunAct",
                    "actualValue": "1",
                    "minValue": "0",
                    "maxValue": "1",
                    "defaultValue": None,
                    "unit": "",
                    "readOnly": True,
                    "displayFormt": "FORM_BOOL",
                    "visible": True,
                },
                {
                    "id": "_USER.Control.VentSet",
                    "name": "Control.VentSet",
                    "textId": "Control.VentSet",
                    "displayText": "Control.VentSet",
                    "actualValue": "2",
                    "minValue": "0",
                    "maxValue": "4",
                    "defaultValue": "2",
                    "unit": "",
                    "readOnly": False,
                    "displayFormt": "FORM_1",
                    "visible": True,
                },
                {
                    "id": "_USER.Control.TempSet",
                    "name": "Control.TempSet",
                    "textId": "Control.TempSet",
                    "displayText": "Control.TempSet",
                    "actualValue": "21.00",
                    "minValue": "5",
                    "maxValue": "50",
                    "defaultValue": "20",
                    "unit": "",
                    "readOnly": False,
                    "displayFormt": "FORM_100",
                    "visible": True,
                },
            ],
        },
        {
            "id": "PARAMGROUP_NAME_INFORMATION",
            "name": "PARAMGROUP_NAME_INFORMATION",
            "viewParameters": [
                {
                    "id": "_USER.Input.T14_Supply",
                    "name": "Input.T14_Supply",
                    "textId": "Input.T14_Supply",
                    "displayText": "Input.T14_Supply",
                    "actualValue": "19.50",
                    "minValue": None,
                    "maxValue": None,
                    "defaultValue": None,
                    "unit": "",
                    "readOnly": True,
                    "displayFormt": "FORM_100",
                    "visible": True,
                },
                {
                    "id": "_USER.AirQual.RH",
                    "name": "AirQual.RH",
                    "textId": "AirQual.RH",
                    "displayText": "AirQual.RH",
                    "actualValue": "42",
                    "minValue": None,
                    "maxValue": None,
                    "defaultValue": None,
                    "unit": "%",
                    "readOnly": True,
                    "displayFormt": "FORM_1",
                    "visible": True,
                },
                {
                    "id": "_USER.AirQual.CO2",
                    "name": "AirQual.CO2",
                    "textId": "AirQual.CO2",
                    "displayText": "AirQual.CO2",
                    "actualValue": "612",
                    "minValue": None,
                    "maxValue": None,
                    "defaultValue": None,
                    "unit": "ppm",
                    "readOnly": True,
                    "displayFormt": "FORM_1",
                    "visible": True,
                },
            ],
        },
        {
            "id": "PARAMGROUP_NAME_ALARM",
            "name": "PARAMGROUP_NAME_ALARM",
            "viewParameters": [
                {
                    "id": "_USER.Alarm.FilterActive",
                    "name": "Alarm.FilterActive",
                    "textId": "Alarm.FilterActive",
                    "displayText": "Alarm.FilterActive",
                    "actualValue": "0",
                    "minValue": "0",
                    "maxValue": "1",
                    "defaultValue": "0",
                    "unit": "",
                    "readOnly": False,
                    "displayFormt": "FORM_BOOL",
                    "visible": True,
                },
            ],
        },
    ],
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def config_sample_json() -> dict:
    """A Configurations/AsJSON payload for tests."""
    return _SAMPLE_CONFIG
