"""New-project prompt: is it a title or an app idea, and what to call the idea."""

import logging
import re
import string
from functools import lru_cache
from typing import Literal

import httpx
from pydantic import BaseModel, Field
from pydantic_ai import Agent

from app.config import settings
from app.services.agent import _model

log = logging.getLogger(__name__)

# Tests swap in httpx.MockTransport.
_transport: httpx.AsyncBaseTransport | None = None

_MIN_CONFIDENCE = 0.6
_TITLE_PROMPT = (
    "Name this app idea in at most 4 words, title case, no punctuation. "
    "Reply with the name only: no code, markdown, quotes or explanation."
)
_INTENT = {
    "type": "choice",
    "instructions": "Is this text only a project title, or a request to make something?",
    "criteria": {
        "name": "Only a short project title, no request to build or make anything",
        "build": "Asks for something to be built, made or created, or describes an app idea",
    },
}


async def classify(text: str) -> Literal["name", "build"]:
    """'build' only on a confident Jev answer; anything else is a plain name."""
    if not settings.jev_api_key:
        return "name"
    body = {"model": settings.jev_model, "state": text, "questions": {"intent": _INTENT}}
    try:
        async with httpx.AsyncClient(transport=_transport, timeout=8) as client:
            res = await client.post(
                f"{settings.jev_api_base}/v1/systemone",
                json=body,
                headers={"Authorization": f"Bearer {settings.jev_api_key}"},
            )
        res.raise_for_status()
        intent = res.json()["answers"]["intent"]
        choice, confidence = intent["choice"], float(intent["confidence"])
    except Exception as exc:
        # No traceback: keeps request headers (the key) out of logs.
        log.warning("jev classify failed: %r", exc)
        return "name"
    return "build" if choice == "build" and confidence >= _MIN_CONFIDENCE else "name"


class ProjectTitle(BaseModel):
    name: str = Field(description="The app's name, at most 4 words")


def _make_title_agent(model) -> Agent[None, ProjectTitle]:
    # Typed output: the model fills a name field instead of free text it can turn into code.
    return Agent(model, output_type=ProjectTitle, system_prompt=_TITLE_PROMPT)


@lru_cache(maxsize=1)
def _title_agent() -> Agent[None, ProjectTitle]:
    return _make_title_agent(_model(settings.summary_model))


# Lead-ins of a model answering the idea instead of naming it.
_CHATTY = re.compile(r"^(here(?:'s| is)|sure|certainly|okay|ok|i |i'|this |below )", re.I)


def _clean_title(raw: str) -> str:
    """First line, no markdown, labels or code, at most 4 words. Empty when unusable."""
    line = next((ln for ln in raw.splitlines() if ln.strip()), "")
    if line.lstrip().startswith(("```", "<")) or _CHATTY.match(line.strip()):
        return ""
    line = re.sub(r"^\W*(title|name)\W*:", "", line.strip(), flags=re.I)
    words = re.sub(r"[^\w\s&'-]", " ", line).split()
    return " ".join(words[:4])[:60].strip()


async def title_for(idea: str) -> str:
    """Short project name for an idea. Falls back to its first 5 words, never empty."""
    try:
        result = await _title_agent().run(idea)
        title = _clean_title(result.output.name)
        if title:
            return title
    except Exception:
        log.warning("title model failed", exc_info=True)
    return string.capwords(" ".join(idea.split()[:5])) or "New Project"
