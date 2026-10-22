"""Preview thumbnails in the private ``project-previews`` bucket.

Sync, service client: call through ``to_thread.run_sync`` from async code.
"""

import threading
import time

from app.services.supabase import get_service_client

BUCKET = "project-previews"

# Signed for an hour, reused for 50 min so a served URL never expires mid-use.
_SIGN_S = 3600
_TTL_S = 3000
_MAX_CACHED = 5000
_lock = threading.Lock()
_cache: dict[tuple[str, str | None], tuple[float, str]] = {}


def _bucket():
    return get_service_client().storage.from_(BUCKET)


def upload_thumbnail(project_id: str, preview_id: str, data: bytes) -> str:
    path = f"{project_id}/{preview_id}.png"
    _bucket().upload(path, data, file_options={"content-type": "image/png", "upsert": "true"})
    return path


def upload_canvas_snapshot(project_id: str, data: bytes, content_type: str) -> str:
    path = f"{project_id}/canvas.webp"
    _bucket().upload(path, data, file_options={"content-type": content_type, "upsert": "true"})
    return path


def sign(paths: list[str], expires_s: int = 3600) -> dict[str, str]:
    """path -> signed url, one request. Paths that fail to sign are left out."""
    if not paths:
        return {}
    items = _bucket().create_signed_urls(paths, expires_s)
    return {i["path"]: i["signedURL"] for i in items if i.get("signedURL")}


def sign_cached(items: dict[str, str | None]) -> dict[str, str]:
    """path -> signed url, signing only the misses in one request.

    ``items`` maps path to a version (canvas_snapshot_at for the in-place
    canvas file, else None). A new version is a new key, so a re-upload gets
    a fresh URL and browsers refetch the image.
    """
    now = time.monotonic()
    out: dict[str, str] = {}
    with _lock:
        for path, ver in items.items():
            hit = _cache.get((path, ver))
            if hit is not None and now - hit[0] < _TTL_S:
                out[path] = hit[1]
    misses = [p for p in items if p not in out]
    if misses:
        fresh = sign(misses, _SIGN_S)
        with _lock:
            # ponytail: clear when full, an LRU if the churn ever shows up
            if len(_cache) + len(fresh) > _MAX_CACHED:
                _cache.clear()
            for path, url in fresh.items():
                _cache[(path, items[path])] = (now, url)
        out.update(fresh)
    return out


def remove_project(project_id: str) -> None:
    # ponytail: one page of 1000 files, loop on offset if a project exceeds it
    files = _bucket().list(project_id, {"limit": 1000})
    if files:
        _bucket().remove([f"{project_id}/{f['name']}" for f in files])
