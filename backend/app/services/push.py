"""Web Push for finished turns.

claim_push_batch inserts the delivery rows it returns, so a row is sent at most
once across instances. _finalise kicks a send; push_loop catches the rest.
"""

import asyncio
import json
import logging

from anyio import CapacityLimiter, to_thread
from pywebpush import WebPushException, webpush

from app.config import push_enabled, settings
from app.services import runs
from app.services.supabase import get_service_client

log = logging.getLogger(__name__)

POLL_S = 10
_BATCH = 50
_TTL_S = 3600
_TIMEOUT_S = 10
# Own threads: a slow push service must not starve the shared pool DB writes use.
_LIMITER = CapacityLimiter(8)
# Push service says the subscription is gone.
_DEAD = (404, 410)

_VERBS = {"complete": "finished", "failed": "failed", "awaiting_approval": "needs your approval"}


def payload_for(row: dict) -> dict:
    title = row["node_name"] + (" · via orchestrator" if row.get("nested") else "")
    body = f"{row['project_name']} · {_VERBS.get(row['status'], row['status'])}"
    if row.get("excerpt"):
        body += "\n" + row["excerpt"]
    return {
        "title": title,
        "body": body,
        "url": f"/?project={row['project_id']}",
        # Per turn: "finished" replaces that turn's "needs your approval".
        "tag": row["message_id"],
    }


async def _send(client, row: dict) -> bool:
    try:
        await to_thread.run_sync(
            lambda: webpush(
                subscription_info={
                    "endpoint": row["endpoint"],
                    "keys": {"p256dh": row["p256dh"], "auth": row["auth"]},
                },
                data=json.dumps(payload_for(row)),
                vapid_private_key=settings.vapid_private_key,
                # Fresh per call: webpush writes aud and exp into it.
                vapid_claims={"sub": settings.vapid_subject},
                ttl=_TTL_S,
                timeout=_TIMEOUT_S,
            ),
            limiter=_LIMITER,
        )
        return True
    except WebPushException as e:
        if e.status_code in _DEAD:
            try:
                await to_thread.run_sync(
                    lambda: client.table("push_subscriptions")
                    .delete()
                    .eq("id", row["subscription_id"])
                    .execute()
                )
            except Exception:
                log.exception("dead subscription delete failed for %s", row["subscription_id"])
        else:
            log.warning("push to %s failed: %s", row["subscription_id"], e)
    except Exception:
        log.exception("push to %s failed", row["subscription_id"])
    return False


async def send_batch(client) -> int:
    """One claim, one push per row. Returns rows sent."""
    rows = await to_thread.run_sync(
        lambda: client.rpc("claim_push_batch", {"p_limit": _BATCH}).execute().data
    )
    if not rows:
        return 0
    sent = await asyncio.gather(*(_send(client, r) for r in rows))
    return sum(sent)


async def _kicked(client) -> None:
    try:
        await send_batch(client)
    except Exception:
        log.exception("push send failed")


def kick() -> None:
    """Send now, in the background. Never raises."""
    if not push_enabled():
        return
    try:
        runs.track_finaliser(asyncio.ensure_future(_kicked(get_service_client())))
    except Exception:
        log.exception("push kick failed")


async def push_loop() -> None:
    """Poll forever. Cancelled at shutdown."""
    while True:
        try:
            await send_batch(get_service_client())
        except Exception:
            log.exception("push poll failed")
        await asyncio.sleep(POLL_S)
