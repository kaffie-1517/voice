"""Intent detection that does not depend on a model.

Two jobs. First, emergencies: if what she chose to say signals one, the
executor runs no matter what the predictor attached. Second, plain requests
— "tell Sam…", "call Dr. Chen", "remind me…" — must reliably reach the agent;
a model that forgets to attach an action must not turn a request into mere
speech. Judged on the sentence she committed to, which is unambiguous.
"""

from __future__ import annotations

import re

from .schemas import ActionSpec, ActionType

_EMERGENCY = re.compile(
    r"\b(fire|smoke|emergenc\w*|ambulance|paramedic|police|"
    r"can'?t breathe|chest pain|stroke|heart attack|"
    r"(i'?ve |i )?(fallen|fell|had a fall)|bleeding|unconscious|"
    r"help( me)?( now| right now| please)?[.!]?$|need help (now|right now))",
    re.IGNORECASE,
)

# (pattern, action type, summary). First match wins.
_REQUESTS: list[tuple[re.Pattern[str], ActionType, str]] = [
    (re.compile(r"\b(share|send)\s+(them\s+|him\s+|her\s+)?my\s+location\b", re.I), "share_location", "Share her location"),
    (re.compile(r"\bremind\s+me\b", re.I), "set_reminder", "Set a reminder"),
    (re.compile(r"\b(call|ring|phone)\s+(?!me\b|you\b|back\b|it\b)", re.I), "place_call", "Place a call"),
    (re.compile(r"\bsend\b(?!\s+(me|us)\b).*\b(scan|report|document|letter|file|results?|prescription|photo|form)\b", re.I), "send_document", "Send a document"),
    (re.compile(r"^(please\s+)?(tell|text|message|let)\s+(?!me\b|you\b)\w+", re.I), "send_message", "Send a message"),
    (re.compile(r"\b(text|message)\s+(?!me\b|you\b)\w+", re.I), "send_message", "Send a message"),
    (re.compile(r"\b(order|reorder)\b", re.I), "order", "Place an order"),
]


def is_emergency(text: str) -> bool:
    return bool(_EMERGENCY.search(text.strip()))


def emergency_action(text: str) -> ActionSpec | None:
    if not is_emergency(text):
        return None
    return ActionSpec(type="alert_emergency", summary="Alert her emergency contacts and get help")


def implied_action(text: str) -> ActionSpec | None:
    """The action a sentence plainly asks for, emergencies first."""
    emergency = emergency_action(text)
    if emergency:
        return emergency
    stripped = text.strip()
    for pattern, kind, summary in _REQUESTS:
        if pattern.search(stripped):
            return ActionSpec(type=kind, summary=summary)
    return None
