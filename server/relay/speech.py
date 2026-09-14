"""Speech in and out, when a provider offers it.

The browser's own recogniser autocorrects impaired speech into fluent wrong
words — "doc… tues" becomes "Testing how". Whisper, given a vocabulary hint,
keeps fragments as fragments, which is what the predictor needs. Both functions
return None when unavailable so the client can fall back to the browser.
"""

from __future__ import annotations

import asyncio
import functools
import os
import time
from typing import Any

from .profile import demo_profile

STT_MODEL = "whisper-large-v3-turbo"
TTS_MODEL = "canopylabs/orpheus-v1-english"
TTS_VOICES = {"self": "hannah", "partner": "troy"}


@functools.lru_cache(maxsize=1)
def _groq_client() -> Any | None:
    if not os.environ.get("GROQ_API_KEY"):
        return None
    import openai

    return openai.OpenAI(
        api_key=os.environ["GROQ_API_KEY"], base_url="https://api.groq.com/openai/v1"
    )


def stt_available() -> bool:
    return _groq_client() is not None


# Orpheus needs a one-time terms acceptance in the Groq console. After a refusal
# we stop asking for a while, then quietly try again in case it has been done.
_tts_retry_at = 0.0
TTS_BACKOFF_S = 60


def tts_available() -> bool:
    return _groq_client() is not None and time.time() >= _tts_retry_at


def _vocabulary_hint() -> str:
    names = ", ".join(c.name for c in demo_profile.contacts)
    meds = ", ".join(demo_profile.medications)
    return (
        f"Broken fragments of speech from {demo_profile.name}, who has aphasia. "
        f"Transcribe exactly what is said, even single syllables. Names: {names}. "
        f"Medications: {meds}."
    )


async def transcribe(audio: bytes, filename: str) -> str | None:
    client = _groq_client()
    if client is None or not audio:
        return None

    def call() -> str:
        result = client.audio.transcriptions.create(
            model=STT_MODEL,
            file=(filename, audio),
            language="en",
            prompt=_vocabulary_hint(),
            response_format="json",
            temperature=0,
        )
        return str(result.text or "").strip()

    try:
        return await asyncio.to_thread(call)
    except Exception as exc:
        print(f"[relay] transcription failed: {exc}")
        return None


async def synthesize(text: str, who: str) -> bytes | None:
    global _tts_retry_at
    client = _groq_client()
    if client is None or not tts_available() or not text.strip():
        return None

    def call() -> bytes:
        response = client.audio.speech.create(
            model=TTS_MODEL,
            voice=TTS_VOICES.get(who, TTS_VOICES["self"]),
            input=text,
            response_format="wav",
        )
        return response.read()

    try:
        return await asyncio.to_thread(call)
    except Exception as exc:
        message = str(exc)
        if "terms acceptance" in message:
            _tts_retry_at = time.time() + TTS_BACKOFF_S
            print(
                "[relay] Groq TTS needs terms acceptance: "
                f"https://console.groq.com/playground?model={TTS_MODEL} — using browser voices"
            )
        else:
            print(f"[relay] synthesis failed: {exc}")
        return None


