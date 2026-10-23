"""Voice prompts: one recorded clip in, cleaned up dictation text out. Always Gemini."""

from functools import lru_cache

from pydantic_ai import Agent, BinaryContent
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from app.config import settings

_PROMPT = (
    "Transcribe this voice note as the text the speaker meant to type. "
    "Drop filler words (um, uh, you know), stutters and false starts. "
    "On a self-correction ('no wait', 'I mean'), keep only the corrected version. "
    "Add punctuation and casing. Keep their wording otherwise; do not summarise or answer it. "
    "Reply with the text only. No speech: reply with nothing."
)


@lru_cache(maxsize=1)
def _agent() -> Agent[None, str]:
    model = GoogleModel(
        settings.gemini_model, provider=GoogleProvider(api_key=settings.gemini_api_key)
    )
    return Agent(model, system_prompt=_PROMPT)


async def transcribe(audio: bytes, media_type: str) -> str:
    # "audio/webm;codecs=opus" -> "audio/webm"
    mime = media_type.split(";")[0].strip()
    result = await _agent().run([BinaryContent(data=audio, media_type=mime)])
    return result.output.strip()
