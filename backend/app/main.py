import logging
import re

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import auth, chat, environments, health, oauth, projects
from app.services.dbos_app import setup_dbos
from app.services.runs import join_detached

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

# Must come after routers are registered so DBOS can instrument them.
setup_dbos(app)


async def _join_detached_turns() -> None:
    await join_detached(settings.detached_join_timeout_s)


app.add_event_handler("shutdown", _join_detached_turns)


async def _sweep_stale_turns() -> None:
    """Repair rows a previous process left `running` on a hard restart."""
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


@app.get("/")
def root():
    return {"app": settings.app_name, "environment": settings.environment}
