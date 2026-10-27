import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _fresh_catalog_cache():
    # Catalog cache is process-wide; one test's fake rows mustn't leak into the next.
    from app.repositories import catalog_cache

    catalog_cache.clear()
    yield
    catalog_cache.clear()


@pytest.fixture(autouse=True)
def _fresh_signed_urls():
    from app.services import previews_storage

    previews_storage._cache.clear()
    yield
    previews_storage._cache.clear()


@pytest.fixture(autouse=True)
def _fresh_token_cache():
    # Verified-token cache is process-wide; tests reuse tokens like "t".
    from app.routers.auth import _clear_token_cache

    _clear_token_cache()
    yield
    _clear_token_cache()


@pytest.fixture(autouse=True)
def _no_push(monkeypatch):
    # _finalise kicks a send and startup polls; neither may reach a real push service.
    monkeypatch.setattr("app.services.push.push_enabled", lambda: False)
    monkeypatch.setattr("app.main.push_enabled", lambda: False)


@pytest.fixture(autouse=True)
def _fresh_held_connections():
    # Held sandbox connections are process-wide; fakes share ids like "sbx_1".
    from app.environments import workspace

    workspace._HELD.clear()
    yield
    workspace._HELD.clear()
