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
    # Whisper's prompt is best used as a bare glossary, not instructions — long
    # prose gets echoed back verbatim on near-silent clips.
    terms = [c.name for c in demo_profile.contacts] + demo_profile.medications
    return ", ".join(terms) + "."


_HINT_WORDS = {w.strip(".,").lower() for w in _vocabulary_hint().split()}

# Whisper's per-segment signals for "I made this up". Groq reports
# no_speech_prob as 0 even on pure noise, so avg_logprob does the work:
# measured -0.18 on real fragments, -0.59 on a noise-only clip.
NO_SPEECH_MAX = 0.5
LOGPROB_MIN = -0.6
LOGPROB_WEAK = -0.35
COMPRESSION_MAX = 2.4


def _clean(segments: list[Any], text: str) -> str:
    kept: list[str] = []
    worst_logprob = 0.0
    for seg in segments:
        get = seg.get if isinstance(seg, dict) else lambda k, d=None: getattr(seg, k, d)
        logprob = float(get("avg_logprob", 0) or 0)
        if float(get("no_speech_prob", 0) or 0) > NO_SPEECH_MAX:
            continue
        if logprob < LOGPROB_MIN:
            continue
        if float(get("compression_ratio", 0) or 0) > COMPRESSION_MAX:
            continue
        worst_logprob = min(worst_logprob, logprob)
        kept.append(str(get("text", "") or "").strip())
    out = " ".join(t for t in kept if t).strip() if segments else text.strip()

    words = [w.strip(".,!?").lower() for w in out.split()]
    if not words or all(not any(ch.isalpha() for ch in w) for w in words):
        return ""  # digits and punctuation only — silence hallucination
    glossary_share = sum(w in _HINT_WORDS for w in words) / len(words)
    if len(words) >= 3 and glossary_share > 0.6:
        return ""  # echoing the glossary back
    if glossary_share == 1.0 and worst_logprob < LOGPROB_WEAK:
        return ""  # a lone glossary word, weakly held — noise wearing a name
    return out


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
            response_format="verbose_json",
            temperature=0,
        )
        return _clean(list(getattr(result, "segments", None) or []), str(result.text or ""))

    try:
        return await asyncio.to_thread(call)
    except Exception as exc:
        print(f"[relay] transcription failed: {exc}")
        return None


async def synthesize(text: str, who: str, fmt: str = "wav") -> bytes | None:
    global _tts_retry_at
    client = _groq_client()
    if client is None or not tts_available() or not text.strip():
        return None

    def call() -> bytes:
        response = client.audio.speech.create(
            model=TTS_MODEL,
            voice=TTS_VOICES.get(who, TTS_VOICES["self"]),
            input=text,
            response_format=fmt,
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


