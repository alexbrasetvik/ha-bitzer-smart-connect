"""Auth helpers: PKCE pair, authorization-code extraction, and www session setup."""

from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timedelta, timezone

from multidict import CIMultiDict

from custom_components.bitzer_smart_connect.api.auth import (
    BitzerAuth,
    _code_from_redirect,
    _is_redirect_uri,
    _pkce_pair,
    _token_from_json,
)
from custom_components.bitzer_smart_connect.api.models import Token
from custom_components.bitzer_smart_connect.const import LOGIN_BASE, WWW_BASE

# The mobile client's custom-scheme redirect uri, as IdentityServer returns it.
CODE_REDIRECT = "de.bitzer.balder:/oauth2redirect?code=abc123&scope=openid&state=xyz"


def test_pkce_challenge_is_s256_of_verifier():
    verifier, challenge = _pkce_pair()
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    assert challenge == expected
    assert "=" not in verifier and "=" not in challenge  # base64url, unpadded


def test_detects_redirect_uri_with_code():
    assert _is_redirect_uri(CODE_REDIRECT) is True


def test_ignores_login_redirect():
    assert (
        _is_redirect_uri(
            "https://login.bitzersmartconnect.com/Account/Login?ReturnUrl=%2Fconnect%2Fauthorize"
        )
        is False
    )


def test_ignores_intermediate_callback_without_code():
    assert (
        _is_redirect_uri(
            "https://login.bitzersmartconnect.com/connect/authorize/callback?client_id=Bitzer.Balder.Code"
        )
        is False
    )


def test_extracts_code_from_query():
    assert _code_from_redirect(CODE_REDIRECT) == "abc123"


def test_extracts_code_from_fragment():
    assert _code_from_redirect("de.bitzer.balder:/oauth2redirect#code=frag99&state=z") == "frag99"


def test_parses_token_response():
    body = (
        '{"access_token":"xxx.yyy.zzz","refresh_token":"r-123",'
        '"id_token":"aaa.bbb.ccc","token_type":"Bearer","expires_in":3600}'
    )
    tok = _token_from_json(body)
    assert tok.access_token == "xxx.yyy.zzz"
    assert tok.refresh_token == "r-123"
    assert tok.id_token == "aaa.bbb.ccc"


async def test_www_session_logs_in_again_when_idp_session_lapsed():
    """A refreshed bearer token doesn't renew the IdP cookie; writes must still work."""
    login_url = f"{LOGIN_BASE}/Account/Login?ReturnUrl=%2Fconnect%2Fauthorize%2Fcallback"
    callback = f"{LOGIN_BASE}/connect/authorize/callback?client_id=www"
    login_html = (
        '<form method="post"><input name="Username"><input name="Password" type="password">'
        '<input name="__RequestVerificationToken" type="hidden" value="login-csrf"></form>'
    )
    form_post_html = (
        f'<form method="post" action="{WWW_BASE}/signin-oidc">'
        '<input type="hidden" name="code" value="www-code"></form>'
    )
    config_html = '<input name="__RequestVerificationToken" type="hidden" value="save-csrf">'

    def redirect(loc):
        return 302, CIMultiDict(Location=loc), ""

    responses = {
        ("GET", f"{WWW_BASE}/Configurations?deviceId=0"): [
            redirect(f"{LOGIN_BASE}/connect/authorize?client_id=www"),
            (200, CIMultiDict(), config_html),
        ],
        ("GET", f"{LOGIN_BASE}/connect/authorize?client_id=www"): [redirect(login_url)],
        ("GET", login_url): [(200, CIMultiDict(), login_html)],
        ("POST", login_url): [redirect("/connect/authorize/callback?client_id=www")],
        ("GET", callback): [(200, CIMultiDict(), form_post_html)],
        ("POST", f"{WWW_BASE}/signin-oidc"): [redirect("/Configurations?deviceId=0")],
        ("GET", f"{WWW_BASE}/Configurations?deviceId=4670"): [(200, CIMultiDict(), config_html)],
    }
    posted = {}

    async def fake_raw(method, url, *, data=None, headers=None):
        if data is not None:
            posted[url] = data
        return responses[(method, url)].pop(0)

    auth = BitzerAuth("user@example.com", "hunter2")
    try:
        auth._token = Token(  # a live bearer token, as after a refresh_token grant
            access_token="a.b.c",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        auth._raw = fake_raw
        assert await auth.async_csrf_token(4670) == "save-csrf"
    finally:
        await auth.async_close()

    assert posted[login_url]["Username"] == "user@example.com"
    assert posted[login_url]["Password"] == "hunter2"
    assert posted[f"{WWW_BASE}/signin-oidc"] == {"code": "www-code"}
