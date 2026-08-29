"""Per-product limits the raw API range doesn't capture, keyed by ``productId``.

The API reports the controller's raw capabilities (e.g. ``Control.VentSet`` 0-4); the
tighter real limits live on the device's on-device HMI panel, not a web UI.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Limit:
    """Override for a parameter's bounds/step; None fields defer to the API value."""

    min: float | None = None
    max: float | None = None
    step: float | None = None


@dataclass(frozen=True, slots=True)
class ProductProfile:
    model: str
    limits: dict[str, Limit]


PRODUCT_PROFILES: dict[str, ProductProfile] = {
    # Ensy InoVent HRV (LMC311 controller)
    "c51da380-ba51-45ca-8818-a4faf6179b77": ProductProfile(
        model="Ensy InoVent",
        limits={
            "Control.VentSet": Limit(min=1, max=3),  # 1..3 ventilation steps; no off, no step 4
            "Control.TempSet": Limit(min=10, max=26, step=0.5),
        },
    ),
}


def product_model(product_id: str | None) -> str | None:
    profile = PRODUCT_PROFILES.get(product_id or "")
    return profile.model if profile else None


def param_limit(product_id: str | None, key: str) -> Limit | None:
    profile = PRODUCT_PROFILES.get(product_id or "")
    return profile.limits.get(key) if profile else None
