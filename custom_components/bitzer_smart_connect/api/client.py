"""REST client for Bitzer Smart Connect (reads via Bearer, writes via the www MVC form)."""

from __future__ import annotations

import logging
import urllib.parse

import aiohttp

from ..const import API_BASE, WWW_BASE
from .auth import BitzerAuth, CannotConnect
from .models import Boundary, Device, DeviceConfig

_LOGGER = logging.getLogger(__name__)


class BitzerClient:
    """High-level cloud operations on top of :class:`BitzerAuth`."""

    def __init__(self, auth: BitzerAuth) -> None:
        self._auth = auth

    @property
    def auth(self) -> BitzerAuth:
        return self._auth

    # -- reads (Bearer) ---------------------------------------------------------

    async def async_get_boundaries(self) -> list[Boundary]:
        uid = self._auth.user_id
        await self._auth.async_access_token()
        uid = uid or self._auth.user_id
        if not uid:
            raise CannotConnect("no user id in token")
        data = await self._get_json(f"{API_BASE}/Boundary/GetUserBoundaries/{uid}")
        return [Boundary.from_json(b) for b in (data or [])]

    async def async_get_user_devices(self) -> list[Device]:
        """List the account's devices via UserDevice/GetUserDevicesWithClaimTypes/<userId>.

        That payload carries device ids but not names (``device`` is null), so names are filled in
        best-effort from each device's config snapshot; callers may still allow a manual device id.
        """
        await self._auth.async_access_token()
        uid = self._auth.user_id
        if not uid:
            return []
        try:
            data = await self._get_json(
                f"{API_BASE}/UserDevice/GetUserDevicesWithClaimTypes/{uid}"
            )
        except CannotConnect:
            return []
        by_id: dict[int, Device] = {}
        for entry in data or []:
            did = entry.get("deviceId") if isinstance(entry, dict) else None
            if did is None or did in by_id:
                continue
            by_id[did] = Device(id=did, name=f"Device {did}")
        return list(by_id.values())

    async def async_get_config(self, device_id: int) -> DeviceConfig:
        """One configuration snapshot: parameter schema + current values (www, Bearer-authed)."""
        url = f"{WWW_BASE}/Configurations/AsJSON/?deviceId={device_id}&_=0"
        headers = await self._auth.async_bearer_headers()
        headers["X-Requested-With"] = "XMLHttpRequest"
        data = await self._get_json(url, headers=headers)
        return DeviceConfig.from_json(data or {})

    async def async_get_status(self, device_id: int) -> bool:
        data = await self._get_json(f"{API_BASE}/devicedata/{device_id}/status")
        return bool(data)

    async def async_get_localization(self, product_id: str) -> dict[str, str]:
        try:
            data = await self._get_json(f"{API_BASE}/Localization/ProductStrings/{product_id}")
        except CannotConnect:
            return {}
        return data if isinstance(data, dict) else {}

    # -- write (www MVC form: cookie session + antiforgery) ---------------------

    async def async_set_parameters(
        self, device_id: int, config: DeviceConfig, changes: dict[str, str]
    ) -> None:
        """Write one or more parameters via Configurations/Save (read-modify-write).

        ``changes`` maps Parameter.id -> new string value. Every form field is sent blank
        (``_T``) / ``-1`` (``_C``) meaning "no change", except the targeted parameters.
        """
        token = await self._auth.async_csrf_token(device_id)
        body: dict[str, str] = {"btnSubmit": "", "hdnDeviceId": str(device_id)}
        for param in config.parameters.values():
            body[param.save_field()] = "-1" if param.is_combo else ""
        for pid, value in changes.items():
            param = config.parameters.get(pid)
            if param is None:
                raise ValueError(f"unknown parameter {pid}")
            body[param.save_field()] = str(value)
        body["__RequestVerificationToken"] = token

        headers = await self._auth.async_bearer_headers()
        headers["Origin"] = WWW_BASE
        headers["Referer"] = f"{WWW_BASE}/main/configurations/{device_id}"
        status, resp_headers, text = await self._auth._raw(  # noqa: SLF001 - shared session
            "POST",
            f"{WWW_BASE}/Configurations/Save",
            data=body,
            headers=headers,
        )
        if status not in (200, 302):
            # a lapsed www session yields a redirect to login; retry once fresh
            self._auth.invalidate_www_session()
            token = await self._auth.async_csrf_token(device_id)
            body["__RequestVerificationToken"] = token
            status, resp_headers, text = await self._auth._raw(  # noqa: SLF001
                "POST", f"{WWW_BASE}/Configurations/Save", data=body, headers=headers
            )
        if status not in (200, 302):
            raise CannotConnect(f"Save returned {status}")

    # -- low level --------------------------------------------------------------

    async def _get_json(self, url: str, headers: dict | None = None):
        if headers is None:
            headers = await self._auth.async_bearer_headers()
        headers.setdefault("Accept", "application/json")
        try:
            async with self._auth.session.get(
                url, headers=headers, allow_redirects=False
            ) as resp:
                if resp.status in (301, 302, 303, 307, 308):
                    raise CannotConnect(f"{url} -> {resp.status} (auth?)")
                if resp.status == 401:
                    raise CannotConnect(f"{url} -> 401")
                resp.raise_for_status()
                text = await resp.text()
                if not text:
                    return None
                try:
                    return _loads(text)
                except ValueError as err:
                    raise CannotConnect(f"{url}: bad JSON") from err
        except aiohttp.ClientError as err:
            raise CannotConnect(str(err)) from err


def _loads(text: str):
    import json

    return json.loads(text)
