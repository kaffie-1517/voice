"""HTTP surface."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from .caller import partner_reply
from .config import settings
from .executor import activity, execute
from .memory import memory
from .predictor import predict
from .profile import demo_profile
from .scenarios import SCENARIOS
from .schemas import (
    CallReplyRequest,
    CallReplyResponse,
    CommitRequest,
    CommitResponse,
    HealthResponse,
    InputSignal,
    PredictRequest,
    PredictResponse,
    Scenario,
    SpeakRequest,
    TranscribeResponse,
    UserProfile,
)
from .speech import stt_available, synthesize, transcribe, tts_available
from . import reminders, telegram


# Strands warns on every tool-loop turn that OpenAI-compatible endpoints drop
# reasoning blocks from history. Expected; not actionable.
logging.getLogger("strands.models.openai").setLevel(logging.ERROR)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # The first call to a provider pays for connection setup and a cold model
    # (~6s on Groq). Pay it here, not on the first thing the user says.
    if settings.provider != "scripted":
        asyncio.create_task(
            predict(PredictRequest(signals=[InputSignal(kind="speech", text="hello")]))
        )
    tasks = [asyncio.create_task(reminders.run())]
    if telegram.available():
        tasks.append(asyncio.create_task(telegram.run()))
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(title="Relay", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        provider=settings.provider,  # type: ignore[arg-type]
        fast_model=settings.fast_model,
        smart_model=settings.smart_model,
        memory_backend=memory.backend,
        scripted_fallback=settings.provider == "scripted",
        stt=stt_available(),
        tts=tts_available(),
        telegram=telegram.available(),
    )


@app.post("/api/transcribe", response_model=TranscribeResponse)
async def do_transcribe(audio: UploadFile) -> TranscribeResponse:
    data = await audio.read()
    text = await transcribe(data, audio.filename or "clip.webm")
    if text is None:
        raise HTTPException(status_code=503, detail="transcription unavailable")
    return TranscribeResponse(text=text)


@app.post("/api/speak")
async def do_speak(req: SpeakRequest) -> Response:
    audio = await synthesize(req.text, req.who)
    if audio is None:
        raise HTTPException(status_code=503, detail="synthesis unavailable")
    return Response(content=audio, media_type="audio/wav")


@app.get("/api/profile", response_model=UserProfile)
async def profile() -> UserProfile:
    return demo_profile


@app.get("/api/scenarios", response_model=list[Scenario])
async def list_scenarios() -> list[Scenario]:
    return SCENARIOS


@app.post("/api/predict", response_model=PredictResponse)
async def do_predict(req: PredictRequest) -> PredictResponse:
    return await predict(req)


@app.post("/api/call/reply", response_model=CallReplyResponse)
async def do_partner_reply(req: CallReplyRequest) -> CallReplyResponse:
    return await partner_reply(req)


@app.post("/api/commit", response_model=CommitResponse)
async def commit(
    req: CommitRequest, x_relay_session: str = Header(default="anonymous")
) -> CommitResponse:
    """The user chose an utterance. Remember it, and run any action it implies."""
    await asyncio.to_thread(memory.record_choice, req.text, req.channel)

    if req.action and req.action.type != "none":
        return await execute(req.text, req.action, x_relay_session)

    return CommitResponse(spoken=req.text, receipt="", source=settings.provider)  # type: ignore[arg-type]


@app.get("/api/activity")
async def activity_feed(x_relay_session: str = Header(default="anonymous")) -> dict[str, object]:
    return {"entries": activity.entries(x_relay_session), "memory": memory.stats()}
