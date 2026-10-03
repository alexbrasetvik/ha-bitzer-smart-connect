"""Headless OIDC login for Bitzer Smart Connect.

Yields the mobile client's bearer access token plus the www app's cookie session, via a
headless authorization-code + PKCE flow (the SPA implicit flow is rejected by the server).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import html as html_lib
import json
import logging
import re
import secrets
import urllib.parse
from datetime import datetime, timedelta, timezone

import aiohttp

from ..const import (
    API_BASE,
    HTTP_TIMEOUT,
    LOGIN_BASE,
    OIDC_CLIENT_ID,
    OIDC_REDIRECT_URI,
    OIDC_SCOPE,
    OIDC_TOKEN_ENDPOINT,
    WWW_BASE,
)
from .models import Token

_LOGGER = logging.getLogger(__name__)

_REDIRECT_CODES = (301, 302, 303, 307, 308)
_TOKEN_RE = re.compile(
    r'name=["\']__RequestVerificationToken["\'][^>]*value=["\']([^"\']+)["\']'
)
# The scheme part of the (custom-scheme) OIDC redirect uri, e.g. "de.bitzer.balder:".
_REDIRECT_SCHEME = OIDC_REDIRECT_URI.split(":", 1)[0] + ":"


class BitzerAuthError(Exception):
    """Base error for the auth layer."""


class CannotConnect(BitzerAuthError):
    """Unable to reach the service."""


class InvalidAuth(BitzerAuthError):
    """Credentials were rejected."""


class BitzerAuth:
    """Owns the credentialed session and hands out valid access tokens."""

    def __init__(self, username: str, password: str) -> None:
        self._username = username
        self._password = password
        self._session = aiohttp.ClientSession(
            cookie_jar=aiohttp.CookieJar(),
            timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT),
            headers={"User-Agent": "ha-bitzer-smart-connect"},
        )
        self._token: Token | None = None
        self._www_ready = False

    @property
    def session(self) -> aiohttp.ClientSession:
        return self._session

    async def async_close(self) -> None:
        await self._session.close()

    # -- public -----------------------------------------------------------------

    async def async_login(self) -> Token:
        """Run the authorization-code + PKCE flow and store a fresh access token."""
        self._token = await self._code_login()
        self._www_ready = False  # a fresh token means the www session must be re-established
        return self._token

    async def async_access_token(self) -> str:
        """Return a valid Bearer token, refreshing or re-logging in as needed."""
        now = datetime.now(timezone.utc)
        if self._token is not None and self._token.is_valid(now):
            return self._token.access_token
        # Try a silent refresh_token grant before a full credentialed login.
        if self._token is not None and self._token.refresh_token:
            refreshed = await self._refresh()
            if refreshed is not None:
                self._token = refreshed
                return self._token.access_token
        await self.async_login()
        assert self._token is not None
        return self._token.access_token

    async def async_bearer_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {await self.async_access_token()}"}

    @property
    def user_id(self) -> str | None:
        """The OIDC subject (used for boundary lookups), from the id/access token claims."""
        if self._token is None:
            return None
        claims = _jwt_claims(self._token.id_token) or _jwt_claims(self._token.access_token)
        return claims.get("sub") or claims.get("userid") or claims.get("user_id")

    async def async_ensure_www_session(self) -> None:
        """Establish the ``www`` MVC cookie session (needed for Configurations/Save)."""
        await self.async_access_token()  # ensures IdP session cookie exists
        if self._www_ready:
            return
        await self._establish_www_session()
        self._www_ready = True

    async def async_csrf_token(self, device_id: int) -> str:
        """Fetch a fresh antiforgery token from the config page (www session must exist)."""
        await self.async_ensure_www_session()
        html = await self._text(
            "GET", f"{WWW_BASE}/Configurations?deviceId={device_id}"
        )
        m = _TOKEN_RE.search(html)
        if not m:
            # session may have lapsed; re-establish once and retry
            self._www_ready = False
            await self.async_ensure_www_session()
            html = await self._text("GET", f"{WWW_BASE}/Configurations?deviceId={device_id}")
            m = _TOKEN_RE.search(html)
        if not m:
            raise CannotConnect("could not obtain antiforgery token")
        return m.group(1)

    def invalidate_www_session(self) -> None:
        self._www_ready = False

    # -- authorization-code + PKCE login ----------------------------------------

    async def _code_login(self) -> Token:
        verifier, challenge = _pkce_pair()
        state, nonce = secrets.token_urlsafe(16), secrets.token_urlsafe(16)
        q = urllib.parse.urlencode(
            {
                "client_id": OIDC_CLIENT_ID,
                "redirect_uri": OIDC_REDIRECT_URI,
                "response_type": "code",
                "scope": OIDC_SCOPE,
                "state": state,
                "nonce": nonce,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        # 1) authorize -> the redirect uri carrying ?code=... when the SSO session is
        #    still valid, else the login page. IdentityServer may bounce through
        #    /connect/authorize/callback first, so follow http redirects along the way.
        url = f"{LOGIN_BASE}/connect/authorize?{q}"
        login_url = None
        code = None
        for _ in range(8):
            status, headers, _ = await self._raw("GET", url)
            loc = headers.get("Location", "")
            if status in _REDIRECT_CODES and _is_redirect_uri(loc):
                code = _code_from_redirect(loc)  # silent SSO, no credentials needed
                break
            if status not in _REDIRECT_CODES or not loc:
                raise CannotConnect(f"unexpected authorize response {status}")
            if "/account/login" in loc.lower():
                login_url = _abs(url, loc)
                break
            url = _abs(url, loc)

        # 2) credentialed login when there was no live SSO session
        if code is None:
            if login_url is None:
                raise CannotConnect("authorize did not resolve to a code or login page")
            code = await self._form_login(login_url)

        # 3) exchange the authorization code for tokens
        return await self._exchange_code(code, verifier)

    async def _form_login(self, login_url: str) -> str:
        """Submit the username/password form and return the authorization code."""
        html = await self._text("GET", login_url)
        loc = await self._submit_login(login_url, html)

        # Follow the post-login redirect chain until the custom-scheme redirect uri
        # (which carries ?code=...). The final hop is a non-http scheme, so inspect
        # each Location before dereferencing it.
        return await self._follow_to_code(login_url, loc)

    async def _submit_login(self, login_url: str, html: str) -> str:
        """POST credentials to the login page ``html`` and return the redirect Location."""
        form = _scrape_login_form(html)
        m = _TOKEN_RE.search(html)
        if not m:
            raise CannotConnect("login form has no antiforgery token")
        form["__RequestVerificationToken"] = form.get("__RequestVerificationToken") or m.group(1)
        form["Username"] = self._username
        form["Password"] = self._password
        form["RememberLogin"] = "true"
        off_min, off_enc = _tz_fields()
        form["ClientTimezoneOffsetMinutes"] = off_min
        form["ClientTimeZoneOffset"] = off_enc

        status, headers, body = await self._raw(
            "POST",
            login_url,
            data=form,
            headers={"Origin": LOGIN_BASE, "Referer": login_url},
        )
        if status not in _REDIRECT_CODES:
            low = body.lower()
            if "invalid username or password" in low or "invalid" in low or (
                "password" in low and "error" in low
            ):
                raise InvalidAuth("credentials rejected")
            raise CannotConnect(f"login POST returned {status}")
        return headers.get("Location", "")

    async def _follow_to_code(self, base: str, loc: str) -> str:
        for _ in range(10):
            if _is_redirect_uri(loc):
                return _code_from_redirect(loc)
            if not loc:
                raise CannotConnect("login did not reach the redirect uri")
            nxt = _abs(base, loc)
            status, headers, _ = await self._raw("GET", nxt)
            base = nxt
            loc = headers.get("Location", "")
            if status not in _REDIRECT_CODES:
                raise CannotConnect(f"login did not reach a code ({status})")
        raise CannotConnect("too many redirects chasing authorization code")

    async def _exchange_code(self, code: str, verifier: str) -> Token:
        status, _, body = await self._raw(
            "POST",
            OIDC_TOKEN_ENDPOINT,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": OIDC_REDIRECT_URI,
                "client_id": OIDC_CLIENT_ID,
                "code_verifier": verifier,
            },
            headers={"Accept": "application/json"},
        )
        if status != 200:
            raise CannotConnect(f"token exchange failed ({status}): {body[:200]}")
        return _token_from_json(body)

    async def _refresh(self) -> Token | None:
        """Attempt a refresh_token grant; return None on any failure (caller re-logs in)."""
        if self._token is None or not self._token.refresh_token:
            return None
        try:
            status, _, body = await self._raw(
                "POST",
                OIDC_TOKEN_ENDPOINT,
                data={
                    "grant_type": "refresh_token",
                    "client_id": OIDC_CLIENT_ID,
                    "refresh_token": self._token.refresh_token,
                },
                headers={"Accept": "application/json"},
            )
        except CannotConnect:
            return None
        if status != 200:
            return None
        try:
            return _token_from_json(body)
        except (KeyError, ValueError):
            return None

    # -- www code flow ----------------------------------------------------------

    async def _establish_www_session(self) -> None:
        cur = f"{WWW_BASE}/Configurations?deviceId=0"
        for _ in range(12):
            status, headers, body = await self._raw("GET", cur)
            loc = headers.get("Location", "")
            if status in _REDIRECT_CODES and loc:
                cur = _abs(cur, loc)
                continue
            if status == 200:
                fm = re.search(
                    r'<form\b[^>]*action=["\']([^"\']+)["\'][^>]*>(.*?)</form>',
                    body,
                    re.S | re.I,
                )
                if fm and "signin-oidc" in fm.group(1):
                    action = _abs(cur, fm.group(1))
                    status, headers, _ = await self._raw(
                        "POST", action, data=_form_inputs(fm.group(2))
                    )
                    loc = headers.get("Location", "")
                    if loc:
                        cur = _abs(action, loc)
                        continue
            return

    # -- low-level --------------------------------------------------------------

    async def _raw(
        self,
        method: str,
        url: str,
        *,
        data: dict | None = None,
        headers: dict | None = None,
    ) -> tuple[int, "aiohttp.typedefs.LooseHeaders", str]:
        try:
            async with self._session.request(
                method, url, data=data, headers=headers, allow_redirects=False
            ) as resp:
                text = await resp.text()
                return resp.status, resp.headers, text
        except aiohttp.ClientError as err:
            raise CannotConnect(str(err)) from err

    async def _text(self, method: str, url: str, **kw) -> str:
        _, _, text = await self._raw(method, url, **kw)
        return text


# -- module helpers -------------------------------------------------------------


def _abs(current: str, loc: str) -> str:
    return loc if loc.startswith("http") else urllib.parse.urljoin(current, loc)


def _scrape_login_form(html: str) -> dict[str, str]:
    """Return all inputs of the login form (the <form> containing Password), HTML-unescaped."""
    forms = re.findall(r"<form\b[^>]*>(.*?)</form>", html, re.S | re.I)
    form_html = next((f for f in forms if 'name="Password"' in f), html)
    return _form_inputs(form_html)


def _form_inputs(form_html: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for tag in re.findall(r"<input\b[^>]*>", form_html):
        nm = re.search(r'name=["\']([^"\']*)["\']', tag)
        vl = re.search(r'value=["\']([^"\']*)["\']', tag)
        if nm:
            out[nm.group(1)] = html_lib.unescape(vl.group(1)) if vl else ""
    return out


def _pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for PKCE with the S256 method."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _is_redirect_uri(loc: str) -> bool:
    """True when a Location is the client's (custom-scheme) redirect uri carrying a code."""
    return bool(loc) and loc.startswith(_REDIRECT_SCHEME) and "code=" in loc


def _code_from_redirect(loc: str) -> str:
    """Extract the authorization code from the redirect uri (query or fragment)."""
    if "?" in loc:
        part = loc.split("?", 1)[1]
    elif "#" in loc:
        part = loc.split("#", 1)[1]
    else:
        part = loc
    params = dict(urllib.parse.parse_qsl(part))
    code = params.get("code")
    if not code:
        raise CannotConnect("redirect uri carried no authorization code")
    return code


def _token_from_json(body: str) -> Token:
    """Parse a /connect/token JSON response into a Token."""
    d = json.loads(body)
    expires_in = int(d.get("expires_in", 3600))
    return Token(
        access_token=d["access_token"],
        id_token=d.get("id_token", ""),
        refresh_token=d.get("refresh_token", ""),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
    )


def _tz_fields() -> tuple[str, str]:
    """Reproduce the login page's JS: offset minutes + encodeURIComponent('+HH:MM')."""
    off = datetime.now().astimezone().utcoffset() or timedelta(0)
    utc_min = int(off.total_seconds() // 60)
    sign = "+" if utc_min >= 0 else "-"
    off_str = f"{sign}{abs(utc_min) // 60:02d}:{abs(utc_min) % 60:02d}"
    return str(-utc_min), urllib.parse.quote(off_str, safe="")


def _jwt_claims(token: str) -> dict:
    if not token or token.count(".") < 2:
        return {}
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except (ValueError, binascii.Error, json.JSONDecodeError):
        return {}
