import logging

import anyio

from app.config import settings
from app.main import RedactToken
from app.tools.mcp import base


def test_redacts_token_in_args():
    rec = logging.LogRecord(
        "uvicorn.error", 20, "", 0, '"WebSocket %s" [accepted]', ("/t?token=abc.def&x=1",), None
    )
    RedactToken().filter(rec)
    assert "abc" not in rec.getMessage()
    assert "token=[redacted]&x=1" in rec.getMessage()


def test_mcp_blocks_private_and_bad_scheme_in_prod(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    assert not base._allowed("http://127.0.0.1:8080/mcp")
    assert not base._allowed("ftp://example.com")
    res = anyio.run(base.verify_toolset, "http://169.254.169.254/", lambda: None)
    assert not res.ok and res.detail == base._BLOCKED


def test_mcp_dev_allows_loopback(monkeypatch):
    monkeypatch.setattr(settings, "environment", "development")
    assert base._allowed("http://127.0.0.1:27123/mcp")
