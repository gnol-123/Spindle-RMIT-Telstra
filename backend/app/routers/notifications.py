"""Notification bell and Web Push subscription endpoints."""

from typing import Annotated
from uuid import UUID

from anyio import to_thread
from fastapi import APIRouter, Header, Query, Response, status
from pydantic import AfterValidator, BaseModel, HttpUrl

from app.config import push_enabled, settings
from app.repositories.notification_repo import NotificationRow
from app.routers.deps import NotificationRepo

router = APIRouter(tags=["notifications"])

_NO_CONTENT = status.HTTP_204_NO_CONTENT


class NotificationResponse(BaseModel):
    id: str
    project_id: str
    node_id: str
    message_id: str
    status: str
    node_name: str
    project_name: str
    nested: bool
    excerpt: str | None
    read_at: str | None
    created_at: str

    @classmethod
    def of(cls, n: NotificationRow) -> "NotificationResponse":
        return cls(**vars(n))


@router.get("/notifications", response_model=list[NotificationResponse])
async def list_notifications(
    repo: NotificationRepo, limit: Annotated[int, Query(ge=1, le=200)] = 100
) -> list[NotificationResponse]:
    rows = await to_thread.run_sync(repo.list_recent, limit)
    return [NotificationResponse.of(r) for r in rows]


class MarkReadRequest(BaseModel):
    project_id: UUID | None = None


class MarkReadResponse(BaseModel):
    updated: int


@router.post("/notifications/read", response_model=MarkReadResponse)
async def mark_read(req: MarkReadRequest, repo: NotificationRepo) -> MarkReadResponse:
    pid = str(req.project_id) if req.project_id else None
    return MarkReadResponse(updated=await to_thread.run_sync(repo.mark_read, pid))


class PushKeyResponse(BaseModel):
    public_key: str | None


@router.get("/push/key", response_model=PushKeyResponse)
async def push_key() -> PushKeyResponse:
    """Public by design: the browser needs it to subscribe."""
    return PushKeyResponse(public_key=settings.vapid_public_key if push_enabled() else None)


class PushKeys(BaseModel):
    p256dh: str
    auth: str


# Browser push services only. Mirrored in upsert_push_subscription.
_PUSH_HOSTS = {"web.push.apple.com", "fcm.googleapis.com", "updates.push.services.mozilla.com"}
_PUSH_SUFFIXES = (".push.services.mozilla.com", ".notify.windows.com")


def _push_endpoint(url: HttpUrl) -> HttpUrl:
    host = url.host or ""
    if (
        url.scheme != "https"
        or url.port != 443
        or url.username
        or url.password
        or not (host in _PUSH_HOSTS or host.endswith(_PUSH_SUFFIXES))
    ):
        raise ValueError("not a known push service endpoint")
    return url


class SubscribeRequest(BaseModel):
    endpoint: Annotated[HttpUrl, AfterValidator(_push_endpoint)]
    keys: PushKeys


class VisibleRequest(BaseModel):
    endpoint: HttpUrl
    visible: bool


class EndpointRequest(BaseModel):
    endpoint: HttpUrl


@router.post("/push/subscriptions", status_code=_NO_CONTENT)
async def subscribe(
    req: SubscribeRequest,
    repo: NotificationRepo,
    user_agent: Annotated[str, Header()] = "",
) -> Response:
    await to_thread.run_sync(
        repo.upsert_subscription,
        str(req.endpoint),
        req.keys.p256dh,
        req.keys.auth,
        user_agent[:300],
    )
    return Response(status_code=_NO_CONTENT)


@router.patch("/push/subscriptions", status_code=_NO_CONTENT)
async def set_visible(req: VisibleRequest, repo: NotificationRepo) -> Response:
    await to_thread.run_sync(repo.set_visible, str(req.endpoint), req.visible)
    return Response(status_code=_NO_CONTENT)


@router.delete("/push/subscriptions", status_code=_NO_CONTENT)
async def unsubscribe(req: EndpointRequest, repo: NotificationRepo) -> Response:
    await to_thread.run_sync(repo.delete_subscription, str(req.endpoint))
    return Response(status_code=_NO_CONTENT)
