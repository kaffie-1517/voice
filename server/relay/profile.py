"""The demo persona.

In a real deployment this is filled in during onboarding by the user's family or
speech therapist. It is not decoration: this vocabulary is what lets the
predictor resolve the fragment "chuh" to "Dr. Chen" instead of guessing.
"""

from __future__ import annotations

import json
from pathlib import Path

from .schemas import Contact, UserProfile

# What she (or her family) has told Relay since setup: contacts shared from a
# phone book, notes typed or spoken. Merged into the profile on load.
LEARNED_PATH = Path(".relay-profile.json")

demo_profile = UserProfile(
    name="Maya Ellis",
    pronouns="she/her",
    aphasia_type="Broca's (expressive) aphasia",
    onset="a left-hemisphere stroke 14 months ago",
    contacts=[
        Contact(
            name="Dr. Priya Chen",
            relationship="neurologist",
            phone="+1 555 0148",
            notes="Wells Park Clinic. Maya sees her every 8 weeks.",
        ),
        Contact(
            name="Sam",
            relationship="son",
            phone="+1 555 0102",
            notes="Lives 20 minutes away. Drives Maya to appointments.",
        ),
        Contact(
            name="Nadia Okonkwo",
            relationship="speech therapist",
            phone="+1 555 0177",
            notes="Sessions Tuesday mornings.",
        ),
        Contact(
            name="Corner Pharmacy",
            relationship="pharmacy",
            phone="+1 555 0190",
            notes="Handles Maya's repeat prescriptions.",
        ),
        Contact(
            name="Theo",
            relationship="grandson",
            notes="Nine years old. Football on Saturdays.",
        ),
    ],
    medications=["clopidogrel", "atorvastatin", "levetiracetam"],
    routines=[
        "Speech therapy with Nadia, Tuesday mornings at 10",
        "A walk around the park most mornings",
        "Theo's football match on Saturday afternoons",
    ],
    frequent_phrases=[
        "Give me a minute.",
        "No, not that one.",
        "Yes — that's it.",
        "I'm still here.",
        "Can you say that again?",
    ],
    notes=(
        "Maya's comprehension is fully intact and she reads well. What is damaged "
        "is word retrieval and sentence assembly. She was a school principal for "
        "22 years and finds being spoken to slowly, or in a childish register, "
        "humiliating. She would rather say one short accurate sentence than a "
        "long approximate one."
    ),
)


def _load_learned() -> dict:
    if LEARNED_PATH.exists():
        try:
            return json.loads(LEARNED_PATH.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"contacts": [], "notes": []}


_learned = _load_learned()


def _save_learned() -> None:
    try:
        LEARNED_PATH.write_text(json.dumps(_learned, indent=2), "utf-8")
    except OSError:
        pass


def _apply(contact: dict) -> None:
    if any(c.name.lower() == contact["name"].lower() for c in demo_profile.contacts):
        return
    demo_profile.contacts.append(Contact(**contact))


for _c in _learned["contacts"]:
    _apply(_c)
if _learned["notes"]:
    demo_profile.notes += " " + " ".join(_learned["notes"])


def add_contact(name: str, relationship: str = "contact", phone: str = "", notes: str = "") -> Contact:
    """Someone she shared from her phone book, or named. Known from now on."""
    entry = {"name": name.strip(), "relationship": relationship.strip() or "contact",
             "phone": phone.strip(), "notes": notes.strip()}
    _apply(entry)
    _learned["contacts"].append(entry)
    _save_learned()
    return Contact(**entry)


def add_note(text: str) -> None:
    """A fact about her life, in her or her family's words."""
    text = text.strip()
    if not text:
        return
    _learned["notes"].append(text)
    demo_profile.notes += " " + text
    _save_learned()
