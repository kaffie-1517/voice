"""Wire formats shared with the web client, plus the structured-output models
the Strands agents are constrained to."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

InputKind = Literal["speech", "keyword", "typed"]
Channel = Literal["call", "voicenote", "message", "inperson"]
ActionType = Literal[
    "send_document", "set_reminder", "send_message", "place_call", "order", "none"
]
EngineSource = Literal["bedrock", "anthropic", "openai", "groq", "scripted"]


class InputSignal(BaseModel):
    kind: InputKind
    text: str
    at: int = 0


class Turn(BaseModel):
    speaker: Literal["user", "partner"]
    text: str
    at: int = 0


class Partner(BaseModel):
    name: str
    role: str
    relationship: str = ""


class Contact(BaseModel):
    name: str
    relationship: str
    phone: str = ""
    notes: str = ""


class UserProfile(BaseModel):
    name: str
    pronouns: str
    aphasia_type: str
    onset: str
    contacts: list[Contact]
    medications: list[str]
    routines: list[str]
    frequent_phrases: list[str]
    notes: str


# --- What the fast model is constrained to return -------------------------
#
# Deliberately lean: no ids, no timestamps. Anything the server can compute,
# the server computes — every field here is one the model has to think about,
# and tokens spent on bookkeeping are latency the user feels mid-sentence.


class PredictedUtterance(BaseModel):
    """One complete thing Maya might be trying to say."""

    text: str = Field(
        description=(
            "The complete utterance in first person, exactly as she would say it "
            "out loud. No quotation marks, no preamble."
        )
    )
    gist: str = Field(
        description=(
            "Two or three words capturing the intent, so it can be scanned at a "
            "glance without reading the full sentence. Example: 'Tuesday works'."
        )
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="0-1. How likely this is what she actually meant."
    )
    # Both nullable: Strands advertises defaulted fields as nullable in the tool
    # schema, and models send null. Rejecting that costs a whole retry round trip.
    action_type: ActionType | None = Field(
        default="none",
        description=(
            "Set only when saying this should also DO something in the world. "
            "Use 'none' for ordinary speech, which is the common case."
        ),
    )
    action_summary: str | None = Field(
        default="",
        description="If action_type is not 'none', one plain line describing the action.",
    )


class PredictionSet(BaseModel):
    """The candidate set returned for a single moment of speech."""

    utterances: list[PredictedUtterance] = Field(
        description="Ordered most-likely first. Each must be a DIFFERENT intent."
    )


class PartnerReply(BaseModel):
    """One turn from the simulated person on the other end of the line."""

    text: str = Field(description="What they say next. One or two sentences, natural.")
    ended: bool | None = Field(
        default=False, description="True only if the call has reached a natural goodbye."
    )


# --- HTTP request / response shapes ---------------------------------------


class ActionSpec(BaseModel):
    type: ActionType = "none"
    summary: str = ""
    params: dict[str, str] = Field(default_factory=dict)


class Candidate(BaseModel):
    id: str
    text: str
    gist: str
    confidence: float
    action: ActionSpec | None = None


class PredictRequest(BaseModel):
    signals: list[InputSignal] = Field(default_factory=list)
    channel: Channel = "inperson"
    partner: Partner | None = None
    transcript: list[Turn] = Field(default_factory=list)
    count: int = 4


class PredictResponse(BaseModel):
    candidates: list[Candidate]
    latency_ms: int
    source: EngineSource
    degraded: bool = False


class CallReplyRequest(BaseModel):
    scenario_id: str
    transcript: list[Turn] = Field(default_factory=list)


class CallReplyResponse(BaseModel):
    text: str
    ended: bool
    source: EngineSource


class CommitRequest(BaseModel):
    """The user picked a candidate and committed to it."""

    text: str
    channel: Channel = "inperson"
    action: ActionSpec | None = None


class CommitResponse(BaseModel):
    spoken: str
    receipt: str = ""
    source: EngineSource


class Scenario(BaseModel):
    id: str
    title: str
    blurb: str
    partner: Partner
    goal: str
    opening: str


class HealthResponse(BaseModel):
    provider: EngineSource
    fast_model: str
    smart_model: str
    memory_backend: str
    scripted_fallback: bool
