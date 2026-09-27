"""Auth helpers: PKCE pair generation and authorization-code extraction."""

from __future__ import annotations

import base64
import hashlib

from custom_components.bitzer_smart_connect.api.auth import (
    _code_from_redirect,
    _is_redirect_uri,
    _pkce_pair,
    _token_from_json,
)

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
