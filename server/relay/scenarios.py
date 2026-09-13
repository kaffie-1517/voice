"""Simulated call partners.

Phone calls are the hardest case for aphasia — no gestures, no face, no patience
from the other end, and a stranger who will hang up. These scenarios let the
call-assist surface be built and demoed without telephony; the same interface
takes a real audio bridge later.
"""

from __future__ import annotations

from .schemas import Partner, Scenario

SCENARIOS: list[Scenario] = [
    Scenario(
        id="clinic",
        title="Book an appointment",
        blurb="Wells Park Clinic reception — the call most people with aphasia give up on.",
        partner=Partner(
            name="Dani at Wells Park Clinic",
            role="clinic receptionist booking appointments",
            relationship="Maya's neurology clinic",
        ),
        goal="Book Maya a follow-up with Dr. Chen and confirm the day and time.",
        opening="Good morning, Wells Park Clinic, Dani speaking. How can I help?",
    ),
    Scenario(
        id="pharmacy",
        title="Refill a prescription",
        blurb="Corner Pharmacy — a short call, but dense with words that are hard to retrieve.",
        partner=Partner(
            name="Corner Pharmacy",
            role="pharmacy counter assistant",
            relationship="Maya's regular pharmacy",
        ),
        goal="Take a repeat prescription request and say when it will be ready.",
        opening="Corner Pharmacy, good morning.",
    ),
    Scenario(
        id="son",
        title="Call Sam",
        blurb="A family call — warm and patient, with no script to hide behind.",
        partner=Partner(
            name="Sam",
            role="Maya's son",
            relationship="son, lives nearby, drives her to appointments",
        ),
        goal="Catch up with your mum and find out if she needs anything.",
        opening="Hey Mum. Everything alright?",
    ),
]


def find_scenario(scenario_id: str) -> Scenario | None:
    return next((s for s in SCENARIOS if s.id == scenario_id), None)


# Offline partner lines, used when no model is configured or a live call fails
# mid-demo. Indexed by how many turns the user has taken.
SCRIPTED_PARTNER_LINES: dict[str, list[str]] = {
    "clinic": [
        "Of course. Do you know roughly when you'd like to come in?",
        "Let me look. I have Tuesday the 4th at 10:30, or Thursday the 6th in the afternoon.",
        "Lovely, I've got you down for that. You'll get a text confirmation shortly.",
        "You're very welcome, Maya. Take care now.",
    ],
    "pharmacy": [
        "Sure — which prescription was it you were after?",
        "Got it. That'll be ready for collection after four o'clock today.",
        "No problem at all. See you later.",
    ],
    "son": [
        "Course I can. What day is it?",
        "Alright, putting it in my calendar now. Anything else you need picking up?",
        "Done. Love you, Mum. See you Tuesday.",
    ],
}
