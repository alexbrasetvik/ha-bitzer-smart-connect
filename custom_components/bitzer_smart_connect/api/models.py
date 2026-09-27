"""Typed models for the Bitzer Smart Connect API."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class Token:
    """An OIDC access token with its expiry."""

    access_token: str
    expires_at: datetime
    id_token: str = ""
    refresh_token: str = ""

    def is_valid(self, now: datetime, margin_seconds: float = 300) -> bool:
        return (self.expires_at - now).total_seconds() > margin_seconds


@dataclass(slots=True)
class Boundary:
    """A site/boundary the user has access to."""

    id: int
    name: str
    customer_id: str | None = None

    @classmethod
    def from_json(cls, d: dict) -> Boundary:
        return cls(
            id=d["boundaryId"],
            name=d.get("boundaryName", str(d["boundaryId"])),
            customer_id=d.get("customerId"),
        )


@dataclass(slots=True)
class Device:
    """A device (e.g. an HRV) under a boundary."""

    id: int
    name: str
    product_id: str | None = None
    boundary_id: int | None = None
    online: bool | None = None

    @classmethod
    def from_json(cls, d: dict) -> Device:
        return cls(
            id=d.get("deviceId") or d.get("id"),
            name=d.get("deviceName") or d.get("name") or f"Device {d.get('deviceId')}",
            product_id=d.get("productId"),
            boundary_id=d.get("boundaryId"),
            online=d.get("online"),
        )


@dataclass(slots=True)
class Parameter:
    """A single device parameter from Configurations/AsJSON.

    ``id`` looks like ``_USER.Control.VentSet``. The write form field for it is the id with dots
    replaced by underscores plus a ``_T`` (value) or ``_C`` (combo/select, "-1" == unchanged)
    suffix — see :meth:`save_field`.
    """

    id: str
    name: str
    group_id: str
    group_name: str
    display_text: str
    text_id: str
    value: str | None  # current actual value (device-reported), as a string
    min_value: str | None
    max_value: str | None
    default_value: str | None
    unit: str | None
    read_only: bool
    display_format: str | None
    visible: bool = True

    # display formats that represent an enumerated/boolean control (write via _C, "-1" == no change)
    _COMBO_FORMATS = frozenset({"FORM_BOOL"})

    @classmethod
    def from_json(cls, d: dict, group_id: str, group_name: str) -> Parameter:
        return cls(
            id=d["id"],
            name=d.get("name", d["id"]),
            group_id=group_id,
            group_name=group_name,
            display_text=d.get("displayText") or d.get("textId") or d.get("name", d["id"]),
            text_id=d.get("textId", ""),
            value=_as_str(d.get("actualValue")),
            min_value=_as_str(d.get("minValue")),
            max_value=_as_str(d.get("maxValue")),
            default_value=_as_str(d.get("defaultValue")),
            unit=(d.get("unit") or None),
            read_only=bool(d.get("readOnly", True)),
            display_format=d.get("displayFormt"),
            visible=bool(d.get("visible", True)),
        )

    @property
    def key(self) -> str:
        """Stable short key, e.g. ``Control.VentSet`` (id without the ``_USER.`` prefix)."""
        return self.id[6:] if self.id.startswith("_USER.") else self.id

    @property
    def is_combo(self) -> bool:
        return (self.display_format or "") in self._COMBO_FORMATS

    def save_field(self) -> str:
        """The Configurations/Save form field name for this parameter."""
        base = self.id.replace(".", "_")
        return f"{base}_C" if self.is_combo else f"{base}_T"

    def float_value(self) -> float | None:
        return _as_float(self.value)

    def float_min(self) -> float | None:
        return _as_float(self.min_value)

    def float_max(self) -> float | None:
        return _as_float(self.max_value)


@dataclass(slots=True)
class DeviceConfig:
    """A full device configuration snapshot (Configurations/AsJSON)."""

    device_id: int
    product_id: str | None
    online: bool
    parameters: dict[str, Parameter] = field(default_factory=dict)  # keyed by Parameter.id

    @classmethod
    def from_json(cls, d: dict) -> DeviceConfig:
        params: dict[str, Parameter] = {}
        for group in d.get("groups", []):
            gid = group.get("id", "")
            gname = group.get("name", gid)
            for p in group.get("viewParameters") or []:
                param = Parameter.from_json(p, gid, gname)
                params[param.id] = param
        return cls(
            device_id=d.get("deviceId"),
            product_id=d.get("productId"),
            online=bool(d.get("deviceOnline", False)),
            parameters=params,
        )


def _as_str(v: object) -> str | None:
    return None if v is None else str(v)


def _as_float(v: object) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
