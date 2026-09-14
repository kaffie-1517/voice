"""The prediction loop.

Deliberately NOT an agent loop. This runs while someone is mid-sentence with a
receptionist waiting on the line, so it is a single constrained model call with
no tools and no conversation state. Strands gives us the structured-output
guarantee here without the round trips an agentic loop would add.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from .config import settings
from .memory import learned_phrases
from .profile import demo_profile
from .prompts import anchor_counts, build_predict_system_prompt, build_predict_user_prompt
from .safety import implied_action, is_throttled
from .providers import load_model
from .schemas import (
    ActionSpec,
    Candidate,
    PredictionSet,
    PredictRequest,
    PredictResponse,
)
from .scripted import scripted_predict

# Someone is on the line. Past this, an offline guess beats a perfect one, and
# a provider that is throttling us must not be retried into a two-minute wait.
PREDICT_DEADLINE_S = 8.0


def _to_candidates(prediction: PredictionSet, count: int) -> list[Candidate]:
    candidates: list[Candidate] = []
    for utterance in prediction.utterances[:count]:
        text = utterance.text.strip().strip('"')
        if not text:
            continue
        action = implied_action(text)
        if action is None and utterance.action_type and utterance.action_type != "none":
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


def _honour_her_words(candidates: list[Candidate], req: PredictRequest) -> list[Candidate]:
    """A word she clearly said must be on screen. Models drift towards what a
    caller in her situation usually wants; this keeps what she actually said
    at the top, and puts it there verbatim if the model dropped it entirely."""
    counts = anchor_counts(req)
    anchors = sorted(counts, key=lambda w: -counts[w])
    if not anchors or not candidates:
        return candidates

    # Words she said more than once (or tapped) are beyond doubt. Every one of
    # them must appear somewhere on screen; a single spoken word only needs to
    # be present if nothing else of hers is.
    strong = [a for a in anchors if counts[a] >= 2] or anchors[:1]

    def uses_anchor(c: Candidate) -> bool:
        text = c.text.lower()
        return any(a in text for a in anchors)

    hits = [c for c in candidates if uses_anchor(c)]
    ordered = hits + [c for c in candidates if not uses_anchor(c)]
    if hits:
        top = max(c.confidence for c in candidates)
        hits[0].confidence = max(hits[0].confidence, top)

    covered = all(any(a in c.text.lower() for c in candidates) for a in strong)
    if covered:
        return ordered

    # Something she clearly said is missing from every candidate. Say her
    # words back plainly, in her order of emphasis — for "fire… house… help"
    # that is the right thing to have on screen. First if nothing else of
    # hers made it; last if the model got the gist and just dropped a word.
    literal = Candidate(
        id=uuid.uuid4().hex[:8],
        text=" ".join(a.capitalize() + "." for a in (strong + [a for a in anchors if a not in strong])[:4]),
        gist="As said",
        confidence=0.5,
        action=None,
    )
    if hits:
        return [*ordered[: max(0, req.count - 1)], literal]
    return [literal, *ordered[: max(0, req.count - 1)]]


async def predict(req: PredictRequest) -> PredictResponse:
    started = time.perf_counter()

    def elapsed() -> int:
        return int((time.perf_counter() - started) * 1000)

    model = load_model("fast", PredictionSet)
    if model is None:
        return PredictResponse(
            candidates=_honour_her_words(
                _to_candidates(scripted_predict(req), req.count), req
            ),
            latency_ms=elapsed(),
            source="scripted",
            degraded=False,
        )

    async def live(m: Any) -> list[Candidate]:
        from strands import Agent

        query = " ".join(s.text for s in req.signals)
        if req.transcript and req.transcript[-1].speaker == "partner":
            query += " " + req.transcript[-1].text
        agent = Agent(
            model=m,
            system_prompt=build_predict_system_prompt(
                demo_profile, await learned_phrases(query)
            ),
            tools=[],
            # Strands prints streamed tokens to stdout by default; silence it,
            # this is a server.
            callback_handler=None,
            retry_strategy=None,
        )
        result = await asyncio.wait_for(
            agent.invoke_async(
                build_predict_user_prompt(req),
                structured_output_model=PredictionSet,
            ),
            timeout=PREDICT_DEADLINE_S,
        )
        prediction = result.structured_output
        if prediction is None or not prediction.utterances:
            raise ValueError("model returned no utterances")
        candidates = _to_candidates(prediction, req.count)
        if not candidates:
            raise ValueError("no usable candidates after cleaning")
        return candidates

    try:
        try:
            candidates = await live(model)
        except Exception as exc:
            backup = load_model("fast", PredictionSet, backup=True)
            if backup is None or not is_throttled(exc):
                raise
            print("[relay] primary key throttled, retrying prediction on backup key")
            candidates = await live(backup)

        return PredictResponse(
            candidates=_honour_her_words(candidates, req),
            latency_ms=elapsed(),
            source=settings.provider,  # type: ignore[arg-type]
            degraded=False,
        )

    except Exception as exc:
        # Never leave the screen empty. Someone is mid-sentence.
        print(f"[relay] prediction fell back to scripted: {exc}")
        return PredictResponse(
            candidates=_honour_her_words(
                _to_candidates(scripted_predict(req), req.count), req
            ),
            latency_ms=elapsed(),
            source="scripted",
            degraded=True,
        )
