"""Parameter / DeviceConfig parsing."""

from __future__ import annotations

from custom_components.bitzer_smart_connect.api.models import DeviceConfig, Parameter


def _param(**overrides) -> Parameter:
    base = dict(
        id="_USER.Control.TempSet",
        name="Control.TempSet",
        group_id="PARAMGROUP_NAME_MAIN",
        group_name="PARAMGROUP_NAME_MAIN",
        display_text="Control.TempSet",
        text_id="Control.TempSet",
        value="21.00",
        min_value="5",
        max_value="50",
        default_value="20",
        unit=None,
        read_only=False,
        display_format="FORM_100",
        visible=True,
    )
    base.update(overrides)
    return Parameter(**base)


def test_key_strips_user_prefix():
    assert _param(id="_USER.Control.TempSet").key == "Control.TempSet"


def test_key_passthrough_without_prefix():
    assert _param(id="Control.TempSet").key == "Control.TempSet"


def test_save_field_text_value():
    p = _param(id="_USER.Control.TempSet", display_format="FORM_100")
    assert p.save_field() == "_USER_Control_TempSet_T"


def test_save_field_combo_form_bool():
    p = _param(id="_USER.Alarm.FilterActive", display_format="FORM_BOOL")
    assert p.is_combo is True
    assert p.save_field() == "_USER_Alarm_FilterActive_C"


def test_save_field_non_bool_dropdown_still_text_field():
    # Program.Select is a dropdown but its displayFormt is FORM_1, not FORM_BOOL: the model
    # only treats FORM_BOOL as a combo, so this is a _T field like any numeric.
    p = _param(id="_USER.Program.Select", display_format="FORM_1")
    assert p.is_combo is False
    assert p.save_field() == "_USER_Program_Select_T"


def test_float_value_min_max():
    p = _param(value="21.00", min_value="5", max_value="50")
    assert p.float_value() == 21.0
    assert p.float_min() == 5.0
    assert p.float_max() == 50.0


def test_float_value_none_when_missing():
    p = _param(value=None, min_value=None, max_value="")
    assert p.float_value() is None
    assert p.float_min() is None
    assert p.float_max() is None


def test_float_value_non_numeric_returns_none():
    p = _param(value="not-a-number")
    assert p.float_value() is None


def test_device_config_from_json_groups_params_and_flags():
    sample = {
        "deviceId": 1234,
        "productId": "c51da380-ba51-45ca-8818-a4faf6179b77",
        "deviceOnline": True,
        "groups": [
            {
                "id": "PARAMGROUP_NAME_MAIN",
                "name": "PARAMGROUP_NAME_MAIN",
                "viewParameters": [
                    {
                        "id": "_USER.Control.VentSet",
                        "name": "Control.VentSet",
                        "actualValue": "2",
                        "minValue": "0",
                        "maxValue": "4",
                        "readOnly": False,
                        "displayFormt": "FORM_1",
                    }
                ],
            },
            {
                "id": "PARAMGROUP_NAME_INFORMATION",
                "name": "PARAMGROUP_NAME_INFORMATION",
                "viewParameters": [
                    {
                        "id": "_USER.Input.T14_Supply",
                        "name": "Input.T14_Supply",
                        "actualValue": "19.50",
                        "readOnly": True,
                        "displayFormt": "FORM_100",
                    }
                ],
            },
        ],
    }

    config = DeviceConfig.from_json(sample)

    assert config.device_id == 1234
    assert config.product_id == "c51da380-ba51-45ca-8818-a4faf6179b77"
    assert config.online is True
    assert set(config.parameters) == {"_USER.Control.VentSet", "_USER.Input.T14_Supply"}

    vent = config.parameters["_USER.Control.VentSet"]
    assert vent.key == "Control.VentSet"
    assert vent.group_name == "PARAMGROUP_NAME_MAIN"
    assert vent.read_only is False
    assert vent.float_value() == 2.0

    supply = config.parameters["_USER.Input.T14_Supply"]
    assert supply.group_name == "PARAMGROUP_NAME_INFORMATION"
    assert supply.read_only is True
    assert supply.float_value() == 19.5


def test_device_config_from_json_defaults_when_fields_absent():
    config = DeviceConfig.from_json({})
    assert config.device_id is None
    assert config.product_id is None
    assert config.online is False
    assert config.parameters == {}


def test_device_config_from_sample(config_sample_json):
    config = DeviceConfig.from_json(config_sample_json)

    assert config.device_id == 1234
    assert config.online is True
    assert config.parameters
    assert all(isinstance(p, Parameter) for p in config.parameters.values())
    # every parameter round-trips through key/save_field without raising
    for param in config.parameters.values():
        assert param.save_field().startswith(param.id.replace(".", "_"))
