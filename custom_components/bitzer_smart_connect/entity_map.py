"""Map raw device parameters to Home Assistant entity platforms.

Free of HA imports so it's unit-testable in isolation. Only live-value sensors are enabled by
default (mirroring the vendor app); everything else is created hidden (``enabled_default=False``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .api.models import Parameter

# Parameters rendered by the dedicated climate entity (not duplicated as number/sensor).
CLIMATE_OWNED = frozenset({"Control.TempSet", "Control.VentSet"})

# Preferred source for climate.current_temperature (first present wins) — the setpoint regulates
# supply/inlet temperature, so prefer that.
CURRENT_TEMP_KEYS = (
    "Input.T7_Inlet",
    "Input.T14_Supply",
    "AirTemp.TempControl",
    "Input.T13_Return",
    "Input.T1_Intake",
)

# Bare live readings, matched by key: the controller reports these readOnly=false too, so readOnly
# can't distinguish sensor from setting. Threshold params (e.g. AirQual.RH_LimLo) must not match here.
_INPUT_TEMP_RE = re.compile(r"Input\.T\d+(_.*)?$")


@dataclass(frozen=True, slots=True)
class EntityHint:
    platform: str  # sensor | binary_sensor | number | select | switch
    device_class: str | None = None
    unit: str | None = None
    diagnostic: bool = False
    step: float | None = None
    enabled_default: bool = False


def _measurement(param: Parameter) -> tuple[str | None, str | None]:
    """(device_class, unit) for a bare live reading, else (None, None). Exact keys only."""
    key = param.key
    if key == "AirQual.RH":
        return "humidity", "%"
    if key == "AirQual.CO2":
        return "carbon_dioxide", "ppm"
    if key == "AirTemp.TempControl" or _INPUT_TEMP_RE.match(key):
        return "temperature", "°C"
    return None, None


def classify(param: Parameter) -> EntityHint | None:
    """Return the entity hint for a parameter, or None to skip it."""
    if not param.visible or param.key in CLIMATE_OWNED:
        return None
    has_value = param.value not in (None, "")

    device_class, unit = _measurement(param)
    if device_class is not None:
        # a physical sensor reading -> enabled sensor when it reports a value; otherwise the sensor
        # isn't wired on this unit, so skip it.
        if has_value:
            return EntityHint("sensor", device_class, unit, enabled_default=True)
        return None

    if param.is_combo:  # FORM_BOOL
        if param.read_only:
            return EntityHint("binary_sensor", diagnostic=True)
        return EntityHint("switch")

    if param.read_only:
        # genuine read-only status/enum (e.g. Control.ModeAct); hidden by default
        return EntityHint("sensor", None, param.unit, diagnostic=True) if has_value else None

    # writable config (thresholds, schedules, program) -> Number, hidden by default
    return EntityHint("number", None, param.unit, step=_step_for(param))


def _step_for(param: Parameter) -> float:
    fmt = (param.display_format or "").upper()
    return 0.5 if fmt in ("FORM_100", "FORM_10") else 1.0


def entities_for(parameters: dict[str, Parameter]) -> list[tuple[str, Parameter, EntityHint]]:
    """Return (platform, parameter, hint) for every mappable parameter."""
    out: list[tuple[str, Parameter, EntityHint]] = []
    for param in parameters.values():
        hint = classify(param)
        if hint is not None:
            out.append((hint.platform, param, hint))
    return out
