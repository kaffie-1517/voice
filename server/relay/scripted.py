"""The offline engine.

Two jobs. First, it lets the whole app be run and judged with no API key and no
AWS account. Second — and this is why it is worth the code — conference wifi
fails, and a communication aid that goes silent when the network does is not a
communication aid. Relay falls back to this on any live-model error rather than
showing an empty screen.

These are pattern-matched, not generated. They are deliberately narrow: better to
offer three honest guesses than to fake intelligence badly.
"""

from __future__ import annotations

import re

from .scenarios import SCRIPTED_PARTNER_LINES
from .schemas import PredictedUtterance, PredictionSet, PredictRequest, Turn

# fragment patterns -> candidate utterances, most likely first
_RULES: list[tuple[str, list[tuple[str, str, float]]]] = [
    # Safety first: these must never be answered with "Give me a minute".
    (
        r"\b(fire|smoke|burn)",
        [
            ("There's a fire. I need help now.", "Fire", 0.95),
            ("Call the fire brigade.", "Fire brigade", 0.80),
        ],
    ),
    (
        r"\b(help|emergenc|ambulance|police|hurt|fall|fell|chest|breath)",
        [
            ("I need help right now.", "Need help", 0.93),
            ("Please call an ambulance.", "Ambulance", 0.78),
            ("I've had a fall.", "Fallen", 0.55),
        ],
    ),
    (
        r"\b(doc|dr|chen|appoint|clinic|book)",
        [
            ("I need to book an appointment with Dr. Chen.", "Book Dr. Chen", 0.86),
            ("I need to change my appointment with Dr. Chen.", "Change it", 0.62),
            ("When is my next appointment with Dr. Chen?", "When is it?", 0.48),
        ],
    ),
    (
        r"\b(tues|tue)\b|\btuesday",
        [
            ("Tuesday works for me.", "Tuesday works", 0.84),
            ("Not Tuesday — I have speech therapy.", "Not Tuesday", 0.66),
            ("Tuesday morning, if you have it.", "Tuesday a.m.", 0.58),
        ],
    ),
    (
        r"\b(thurs|thu)\b|\bthursday",
        [
            ("Thursday is better for me.", "Thursday", 0.82),
            ("Thursday afternoon, please.", "Thursday p.m.", 0.64),
        ],
    ),
    (
        r"\b(morn|morning|am)\b",
        [
            ("The morning is better for me.", "Morning", 0.80),
            ("Anything before eleven, please.", "Before 11", 0.52),
        ],
    ),
    (
        r"\b(after|afternoon|pm)\b",
        [
            ("The afternoon suits me better.", "Afternoon", 0.80),
            ("Any time after two.", "After 2", 0.52),
        ],
    ),
    (
        r"\b(pill|med|presc|refill|pharm|tablet)",
        [
            ("I need a refill on my prescription.", "Refill", 0.85),
            ("I need my clopidogrel refilled.", "Clopidogrel", 0.70),
            ("Is my prescription ready to collect?", "Is it ready?", 0.55),
        ],
    ),
    (
        r"\b(sam|son)\b",
        [
            ("Can you drive me on Tuesday?", "Lift Tuesday", 0.78),
            ("Sam, can you call me back when you get a minute?", "Call me back", 0.60),
            ("I wanted to hear your voice.", "Just calling", 0.44),
        ],
    ),
    (
        r"\b(theo|grand|foot|ball|match)",
        [
            ("Are you taking Theo to football on Saturday?", "Theo football", 0.79),
            ("I'd like to come and watch Theo play.", "Come watch", 0.63),
        ],
    ),
    (
        r"\b(nad|speech|therap)",
        [
            ("I have speech therapy with Nadia on Tuesday.", "Therapy Tuesday", 0.81),
            ("I need to move my session with Nadia.", "Move session", 0.57),
        ],
    ),
    (
        r"\b(yes|yeah|yep|ok|okay|good|that)",
        [
            ("Yes — that's it.", "Yes", 0.88),
            ("Yes, that works.", "That works", 0.74),
        ],
    ),
    (
        r"\b(no|not|nope|wrong)\b",
        [
            ("No, not that one.", "No", 0.87),
            ("No, sorry — let me start again.", "Start again", 0.58),
        ],
    ),
    (
        r"\b(thank|thanks|cheers)",
        [
            ("Thank you, that's very kind.", "Thanks", 0.86),
            ("Thanks for your help.", "Thanks", 0.70),
        ],
    ),
    (
        r"\b(wait|minute|slow|again|repeat)",
        [
            ("Give me a minute.", "One minute", 0.85),
            ("Can you say that again?", "Say again", 0.72),
        ],
    ),
]

# Used when nothing matches. Kept genuinely useful rather than filler — these are
# the things a person most often needs when the words will not come at all.
_FALLBACK: dict[str, list[tuple[str, str, float]]] = {
    "call": [
        ("Give me a minute.", "One minute", 0.42),
        ("Can you say that again?", "Say again", 0.38),
        ("Yes, that's right.", "Yes", 0.34),
        ("Can I call you back?", "Call back", 0.28),
    ],
    "default": [
        ("Give me a minute.", "One minute", 0.40),
        ("Yes — that's it.", "Yes", 0.36),
        ("No, not that one.", "No", 0.32),
        ("I need some help with this.", "Need help", 0.26),
    ],
}


def _question_bias(transcript: list[Turn]) -> list[tuple[str, str, float]]:
    """If the other party just asked something, answer THAT."""
    if not transcript or transcript[-1].speaker != "partner":
        return []
    asked = transcript[-1].text.lower()

    if re.search(r"\bwhen\b|\bwhat day\b|\btime\b|\bsuit|\bcome in\b", asked):
        return [
            ("Tuesday morning, if you have it.", "Tuesday a.m.", 0.82),
            ("Thursday afternoon works too.", "Thursday p.m.", 0.68),
            ("Whatever you have soonest.", "Soonest", 0.55),
        ]
    if re.search(r"\bwhich\b|\bwhat.*(prescription|medic)", asked):
        return [
            ("The clopidogrel, please.", "Clopidogrel", 0.80),
            ("All three of my repeat prescriptions.", "All three", 0.60),
        ]
    if re.search(r"\banything else\b|\bthat everything\b", asked):
        return [
            ("No, that's everything. Thank you.", "That's all", 0.78),
            ("Actually, one more thing.", "One more", 0.52),
        ]
    if re.search(r"\balright\b|\bok\b|\byou\b.*\bgood\b|\beverything\b", asked):
        return [
            ("I'm alright, thanks.", "I'm alright", 0.70),
            ("I need a bit of help with something.", "Need help", 0.58),
        ]
    return []


def scripted_predict(req: PredictRequest) -> PredictionSet:
    blob = " ".join(s.text for s in req.signals).lower()

    scored: list[tuple[str, str, float]] = []
    seen: set[str] = set()

    def add(items: list[tuple[str, str, float]], weight: float = 1.0) -> None:
        for text, gist, conf in items:
            if text not in seen:
                seen.add(text)
                scored.append((text, gist, conf * weight))

    # A question on the line outranks loose fragments — it constrains the answer.
    add(_question_bias(req.transcript), weight=1.1)

    for pattern, items in _RULES:
        if re.search(pattern, blob):
            add(items)

    if not scored:
        add(_FALLBACK.get(req.channel, _FALLBACK["default"]))

    scored.sort(key=lambda row: row[2], reverse=True)

    return PredictionSet(
        utterances=[
            PredictedUtterance(text=text, gist=gist, confidence=min(conf, 0.95))
            for text, gist, conf in scored[: req.count]
        ]
    )


def scripted_partner_reply(scenario_id: str, transcript: list[Turn]) -> tuple[str, bool]:
    lines = SCRIPTED_PARTNER_LINES.get(scenario_id, [])
    turns_taken = sum(1 for t in transcript if t.speaker == "user")

    if not lines:
        return ("Mm-hm, go on.", False)
    index = min(turns_taken, len(lines)) - 1
    if index < 0:
        return (lines[0], False)
    return (lines[index], index >= len(lines) - 1)
