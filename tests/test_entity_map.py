"""classify() / entities_for() parameter -> platform mapping."""

from __future__ import annotations

from custom_components.bitzer_smart_connect.api.models import Parameter
from custom_components.bitzer_smart_connect.entity_map import classify, entities_for


def _param(key: str, **overrides) -> Parameter:
    base = dict(
        id=f"_USER.{key}",
        name=key,
        group_id="PARAMGROUP_NAME_MAIN",
        group_name="PARAMGROUP_NAME_MAIN",
        display_text=key,
        text_id=key,
        value="1",
        min_value=None,
        max_value=None,
        default_value=None,
        unit=None,
        read_only=True,
        display_format="FORM_1",
        visible=True,
    )
    base.update(overrides)
    base["id"] = f"_USER.{key}"
    return Parameter(**base)


def test_temperature_read_only_with_value_is_enabled_measurement():
    p = _param("Input.T14_Supply", read_only=True, display_format="FORM_100")
    hint = classify(p)
    assert hint is not None
    assert hint.platform == "sensor"
    assert hint.device_class == "temperature"
    assert hint.unit == "°C"
    assert hint.diagnostic is False
    assert hint.enabled_default is True


def test_read_only_without_value_is_skipped():
    p = _param("Input.T99_Unused", read_only=True, value=None, display_format="FORM_1")
    assert classify(p) is None


def test_writable_numeric_is_hidden_by_default():
    p = _param("AirQual.CO2_LimHi", read_only=False, value=None, display_format="FORM_1")
    hint = classify(p)
    assert hint is not None
    assert hint.platform == "number"
    assert hint.enabled_default is False


def test_humidity_detected_by_rh_suffix():
    p = _param("AirQual.RH", read_only=True)
    hint = classify(p)
    assert hint is not None
    assert hint.platform == "sensor"
    assert hint.device_class == "humidity"
    assert hint.unit == "%"


def test_co2_detected_by_key_substring():
    p = _param("AirQual.CO2", read_only=True)
    hint = classify(p)
    assert hint is not None
    assert hint.device_class == "carbon_dioxide"
    assert hint.unit == "ppm"


def test_plain_read_only_numeric_falls_back_to_generic_sensor():
    p = _param("Program.Active", read_only=True, unit="kWh", display_format="FORM_1")
    hint = classify(p)
    assert hint is not None
    assert hint.platform == "sensor"
    assert hint.device_class is None
    assert hint.unit == "kWh"


def test_writable_numeric_is_number_with_bounds_step():
    p = _param(
        "CentralHeat.SupplyMin",
        read_only=False,
        display_format="FORM_100",
        min_value="5",
        max_value="60",
    )
    hint = classify(p)
    assert hint is not None
    assert hint.platform == "number"
    assert hint.diagnostic is False
    assert hint.step == 0.5  # FORM_100 -> decimals in the display mask


def test_writable_numeric_whole_step_defaults_to_one():
    p = _param("Program.Select", read_only=False, display_format="FORM_1")
    hint = classify(p)
    assert hint is not None
    assert hint.platform == "number"
    assert hint.step == 1.0


def test_form_bool_read_only_is_binary_sensor():
    p = _param("Control.RunAct", read_only=True, display_format="FORM_BOOL")
    hint = classify(p)
    assert hint is not None
    assert hint.platform == "binary_sensor"
    assert hint.diagnostic is True


def test_form_bool_writable_is_switch():
    p = _param("Alarm.FilterActive", read_only=False, display_format="FORM_BOOL")
    hint = classify(p)
    assert hint is not None
    assert hint.platform == "switch"
    assert hint.diagnostic is False


def test_climate_owned_params_are_skipped():
    for key in ("Control.TempSet", "Control.VentSet"):
        p = _param(key, read_only=False, display_format="FORM_100")
        assert classify(p) is None


def test_invisible_param_is_skipped():
    p = _param("Input.T14_Supply", visible=False)
    assert classify(p) is None


def test_information_group_forces_diagnostic_even_if_writable():
    p = _param(
        "AirFlow.Balance",
        group_name="PARAMGROUP_NAME_INFORMATION",
        read_only=False,
        display_format="FORM_BOOL",
    )
    hint = classify(p)
    assert hint is not None
    # writable combo -> switch, which doesn't carry the diagnostic flag
    assert hint.platform == "switch"


def test_entities_for_filters_and_tags_platform():
    params = {
        "_USER.Control.TempSet": _param("Control.TempSet", read_only=False, display_format="FORM_100"),
        "_USER.Control.VentSet": _param("Control.VentSet", read_only=False, display_format="FORM_1"),
        "_USER.Input.T14_Supply": _param("Input.T14_Supply", read_only=True, display_format="FORM_100"),
        "_USER.AirQual.RH": _param("AirQual.RH", read_only=True),
        "_USER.Alarm.FilterActive": _param(
            "Alarm.FilterActive", read_only=False, display_format="FORM_BOOL"
        ),
        "_USER.Control.RunAct": _param("Control.RunAct", read_only=True, display_format="FORM_BOOL"),
        "_USER.Hidden.Thing": _param("Hidden.Thing", visible=False),
    }

    out = entities_for(params)
    platforms_by_key = {p.key: platform for platform, p, _hint in out}

    # CLIMATE_OWNED + invisible are excluded entirely
    assert "Control.TempSet" not in platforms_by_key
    assert "Control.VentSet" not in platforms_by_key
    assert "Hidden.Thing" not in platforms_by_key

    assert platforms_by_key["Input.T14_Supply"] == "sensor"
    assert platforms_by_key["AirQual.RH"] == "sensor"
    assert platforms_by_key["Alarm.FilterActive"] == "switch"
    assert platforms_by_key["Control.RunAct"] == "binary_sensor"
    assert len(out) == 4
