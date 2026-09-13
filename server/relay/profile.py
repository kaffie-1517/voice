"""The demo persona.

In a real deployment this is filled in during onboarding by the user's family or
speech therapist. It is not decoration: this vocabulary is what lets the
predictor resolve the fragment "chuh" to "Dr. Chen" instead of guessing.
"""

from __future__ import annotations

from .schemas import Contact, UserProfile

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
