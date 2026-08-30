"""Auth helpers: silent-refresh token fragment detection and parsing."""

from __future__ import annotations

from custom_components.bitzer_smart_connect.api.auth import (
    _has_token_fragment,
    _token_from_fragment,
)

# response_type "id_token token" -> the fragment leads with id_token, access_token follows.
SILENT_REFRESH = (
    "https://www.bitzersmartconnect.com/auth/callback/"
    "#id_token=aaa.bbb.ccc&access_token=xxx.yyy.zzz&token_type=Bearer&expires_in=3600&scope=openid"
)


def test_detects_token_fragment_when_id_token_leads():
    assert _has_token_fragment(SILENT_REFRESH) is True


def test_ignores_login_redirect():
    assert _has_token_fragment(
        "https://login.bitzersmartconnect.com/Account/Login?ReturnUrl=%2Fconnect%2Fauthorize"
    ) is False


def test_ignores_intermediate_callback_without_fragment():
    assert _has_token_fragment(
        "https://login.bitzersmartconnect.com/connect/authorize/callback?client_id=BitzerIoC.SPA"
    ) is False


def test_parses_token_regardless_of_fragment_order():
    tok = _token_from_fragment(SILENT_REFRESH)
    assert tok.access_token == "xxx.yyy.zzz"
    assert tok.id_token == "aaa.bbb.ccc"
