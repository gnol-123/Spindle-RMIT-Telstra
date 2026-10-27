"""get_current_user caches verified tokens, capped by the JWT exp."""

import base64
import json
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.routers.auth import get_current_user


def _jwt(exp):
    b = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()  # noqa: E731
    return f"{b({'alg': 'none'})}.{b({'exp': exp})}.sig"


def _creds(token):
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def _client(uid="u1"):
    c = MagicMock()
    c.auth.get_user.return_value = SimpleNamespace(
        user=SimpleNamespace(id=uid, email="a@b.c", user_metadata={})
    )
    return c


async def test_second_call_hits_cache():
    c = _client()
    tok = _jwt(time.time() + 3600)
    with patch("app.routers.auth.get_client", return_value=c):
        a = await get_current_user(_creds(tok))
        b = await get_current_user(_creds(tok))
    assert a == b
    assert c.auth.get_user.call_count == 1


async def test_failure_not_cached():
    c = MagicMock()
    c.auth.get_user.side_effect = Exception("bad")
    with patch("app.routers.auth.get_client", return_value=c):
        for _ in range(2):
            with pytest.raises(HTTPException) as e:
                await get_current_user(_creds("bad"))
            assert e.value.status_code == 401
    assert c.auth.get_user.call_count == 2


async def test_expired_exp_not_cached():
    c = _client()
    tok = _jwt(time.time() - 10)
    with patch("app.routers.auth.get_client", return_value=c):
        await get_current_user(_creds(tok))
        await get_current_user(_creds(tok))
    assert c.auth.get_user.call_count == 2


async def test_different_tokens_separate():
    c = _client()
    with patch("app.routers.auth.get_client", return_value=c):
        await get_current_user(_creds(_jwt(time.time() + 3600)))
        await get_current_user(_creds(_jwt(time.time() + 7200)))
    assert c.auth.get_user.call_count == 2
