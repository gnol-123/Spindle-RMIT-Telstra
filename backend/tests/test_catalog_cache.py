from app.repositories import catalog_cache


def test_hit_within_ttl_miss_after(monkeypatch):
    calls = []
    load = lambda: calls.append(1) or ["row"]  # noqa: E731
    now = [100.0]
    monkeypatch.setattr(catalog_cache.time, "monotonic", lambda: now[0])

    assert catalog_cache.cached(("k",), load) == ["row"]
    assert catalog_cache.cached(("k",), load) == ["row"]
    assert len(calls) == 1
    now[0] += catalog_cache.TTL_S + 1
    catalog_cache.cached(("k",), load)
    assert len(calls) == 2


def test_none_is_not_stored():
    calls = []
    load = lambda: calls.append(1)  # noqa: E731  (returns None)
    catalog_cache.cached(("missing",), load)
    catalog_cache.cached(("missing",), load)
    assert len(calls) == 2
