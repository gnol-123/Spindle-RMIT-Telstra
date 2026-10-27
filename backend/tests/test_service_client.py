import pytest

from app.services import supabase as supabase_service


def test_service_client_requires_key(monkeypatch):
    monkeypatch.setattr(supabase_service.settings, "supabase_service_key", "")
    supabase_service.get_service_client.cache_clear()
    with pytest.raises(RuntimeError, match="SUPABASE_SERVICE_KEY"):
        supabase_service.get_service_client()


def test_clients_are_http1_with_a_bounded_pool():
    """HTTP/2 over one shared sync client interleaves frames across worker threads."""
    http = supabase_service._http()
    try:
        assert http._transport._pool._http2 is False
        assert http._transport._pool._max_connections == 10
    finally:
        http.close()
