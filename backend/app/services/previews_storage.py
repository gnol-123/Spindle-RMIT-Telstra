"""Preview thumbnails in the private ``project-previews`` bucket.

Sync, service client: call through ``to_thread.run_sync`` from async code.
"""

from app.services.supabase import get_service_client

BUCKET = "project-previews"


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


def remove_project(project_id: str) -> None:
    # ponytail: one page of 1000 files, loop on offset if a project exceeds it
    files = _bucket().list(project_id, {"limit": 1000})
    if files:
        _bucket().remove([f"{project_id}/{f['name']}" for f in files])
