"""HTTP surface."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .caller import partner_reply
from .config import settings
from .executor import activity_log, execute
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
    PredictRequest,
    PredictResponse,
    Scenario,
    UserProfile,
)

app = FastAPI(title="Relay", version="0.1.0")

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
    )


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
async def commit(req: CommitRequest) -> CommitResponse:
    """The user chose an utterance. Remember it, and run any action it implies."""
    memory.record_choice(req.text, req.channel)

    if req.action and req.action.type != "none":
        return await execute(req.text, req.action)

    return CommitResponse(spoken=req.text, receipt="", source=settings.provider)  # type: ignore[arg-type]


@app.get("/api/activity")
async def activity() -> dict[str, object]:
    return {"entries": list(reversed(activity_log[-30:])), "memory": memory.stats()}
