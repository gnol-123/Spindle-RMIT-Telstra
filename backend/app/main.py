import asyncio
import logging
import re

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import auth, chat, environments, health, oauth, projects
from app.services.runs import hand_off, join_detached
from app.tools.mcp.base import close_pool

log = logging.getLogger(__name__)

_TOKEN = re.compile(r"(token=)[^&\s\"']+")


class RedactToken(logging.Filter):
    """Blanks ?token= values (terminal websocket bearer) in uvicorn log lines."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _TOKEN.sub(r"\1[redacted]", record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(
                _TOKEN.sub(r"\1[redacted]", a) if isinstance(a, str) else a for a in record.args
            )
        return True


for _name in ("uvicorn.error", "uvicorn.access"):
    logging.getLogger(_name).addFilter(RedactToken())

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Downloads from the code preview name their file here; without this the
    # browser hides the header from a cross-origin fetch.
    expose_headers=["Content-Disposition"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(environments.router)
app.include_router(chat.router)
app.include_router(oauth.router)


_recovery_task: asyncio.Task | None = None


async def _join_detached_turns() -> None:
    if _recovery_task is not None:
        _recovery_task.cancel()
    if settings.supabase_service_key:
        # The next instance's recovery loop resumes them; waiting would only delay that.
        await hand_off(settings.detached_join_timeout_s)
    await join_detached(settings.detached_join_timeout_s)


app.add_event_handler("shutdown", _join_detached_turns)
# After turns join, so no run loses its session mid-call.
app.add_event_handler("shutdown", close_pool)


async def _sweep_stale_turns() -> None:
    """Repair tool_calls and nodes a previous process left `running` on a hard restart."""
    if not settings.supabase_service_key:
        return
    from anyio import to_thread

    from app.services.runs import sweep_stale
    from app.services.supabase import get_service_client

    try:
        counts = await to_thread.run_sync(
            lambda: sweep_stale(
                get_service_client(), min_age_s=settings.detached_join_timeout_s + 30
            )
        )
        if any(counts.values()):
            log.info("swept stale turn rows: %s", counts)
    except Exception:
        log.exception("stale turn sweep failed")


app.add_event_handler("startup", _sweep_stale_turns)


async def _start_recovery() -> None:
    """Resume turns a previous or departing instance left running. A loop, not a
    startup check: Railway starts this instance before the old one stops."""
    global _recovery_task
    if not settings.supabase_service_key:
        return
    from app.services.recovery import recovery_loop

    _recovery_task = asyncio.ensure_future(recovery_loop())


app.add_event_handler("startup", _start_recovery)


@app.get("/")
def root():
    return {"app": settings.app_name, "environment": settings.environment}
