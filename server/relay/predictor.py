"""The prediction loop.

Deliberately NOT an agent loop. This runs while someone is mid-sentence with a
receptionist waiting on the line, so it is a single constrained model call with
no tools and no conversation state. Strands gives us the structured-output
guarantee here without the round trips an agentic loop would add.
"""

from __future__ import annotations

import time
import uuid

from .config import settings
from .memory import learned_phrases
from .profile import demo_profile
from .prompts import build_predict_system_prompt, build_predict_user_prompt
from .providers import load_model
from .schemas import (
    ActionSpec,
    Candidate,
    PredictionSet,
    PredictRequest,
    PredictResponse,
)
from .scripted import scripted_predict


def _to_candidates(prediction: PredictionSet, count: int) -> list[Candidate]:
    candidates: list[Candidate] = []
    for utterance in prediction.utterances[:count]:
        text = utterance.text.strip().strip('"')
        if not text:
            continue
        action = None
        if utterance.action_type and utterance.action_type != "none":
            action = ActionSpec(
                type=utterance.action_type,
                summary=utterance.action_summary or text,
            )
        candidates.append(
            Candidate(
                id=uuid.uuid4().hex[:8],
                text=text,
                gist=utterance.gist.strip() or text[:24],
                confidence=utterance.confidence,
                action=action,
            )
        )
    return candidates


async def predict(req: PredictRequest) -> PredictResponse:
    started = time.perf_counter()

    def elapsed() -> int:
        return int((time.perf_counter() - started) * 1000)

    model = load_model("fast", PredictionSet)
    if model is None:
        return PredictResponse(
            candidates=_to_candidates(scripted_predict(req), req.count),
            latency_ms=elapsed(),
            source="scripted",
            degraded=False,
        )

    try:
        from strands import Agent

        query = " ".join(s.text for s in req.signals)
        if req.transcript and req.transcript[-1].speaker == "partner":
            query += " " + req.transcript[-1].text
        agent = Agent(
            model=model,
            system_prompt=build_predict_system_prompt(
                demo_profile, await learned_phrases(query)
            ),
            tools=[],
            # Strands prints streamed tokens to stdout by default; silence it,
            # this is a server.
            callback_handler=None,
        )
        result = await agent.invoke_async(
            build_predict_user_prompt(req),
            structured_output_model=PredictionSet,
        )
        prediction = result.structured_output
        if prediction is None or not prediction.utterances:
            raise ValueError("model returned no utterances")

        candidates = _to_candidates(prediction, req.count)
        if not candidates:
            raise ValueError("no usable candidates after cleaning")

        return PredictResponse(
            candidates=candidates,
            latency_ms=elapsed(),
            source=settings.provider,  # type: ignore[arg-type]
            degraded=False,
        )

    except Exception as exc:
        # Never leave the screen empty. Someone is mid-sentence.
        print(f"[relay] prediction fell back to scripted: {exc}")
        return PredictResponse(
            candidates=_to_candidates(scripted_predict(req), req.count),
            latency_ms=elapsed(),
            source="scripted",
            degraded=True,
        )
