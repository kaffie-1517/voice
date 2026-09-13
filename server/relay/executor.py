"""The action executor — a real Strands agent loop.

This is the half of Relay that genuinely needs an agent. Once the user has
committed to an utterance like "Send my last scan to Dr. Chen and remind me
Tuesday", something has to decide which tools to call, in what order, with what
arguments. That is a model-driven tool loop, which is exactly what Strands is for.

The tools here simulate their effects and return receipts. Swapping any one of
them for a real integration is a change inside a single function — the agent,
the prompt, and the UI are untouched.
"""

from __future__ import annotations

import time
from typing import Any

from strands import Agent, tool

from .config import settings
from .profile import demo_profile
from .prompts import EXECUTOR_SYSTEM_PROMPT
from .providers import load_model
from .schemas import ActionSpec, CommitResponse

# Everything the agent did this session, surfaced in the UI so the user can see
# that saying the sentence actually caused something to happen.
activity_log: list[dict[str, Any]] = []


def _log(kind: str, detail: str) -> str:
    entry = {"kind": kind, "detail": detail, "at": int(time.time())}
    activity_log.append(entry)
    return detail


def _resolve_contact(name: str) -> str:
    """Match a loosely-spoken name against the profile's contacts."""
    needle = name.lower().strip()
    for contact in demo_profile.contacts:
        if needle in contact.name.lower() or contact.name.lower().startswith(needle):
            return contact.name
        if needle and needle in contact.relationship.lower():
            return contact.name
    return name


@tool
def send_document(recipient: str, document: str) -> str:
    """Send a document or medical record to one of the user's contacts.

    Args:
        recipient: Who it goes to. A name or a relationship such as "my neurologist".
        document: Which document to send, e.g. "the MRI scan from March".

    Returns:
        A confirmation describing what was sent and to whom.
    """
    who = _resolve_contact(recipient)
    return _log("document", f"Sent {document} to {who}.")


@tool
def set_reminder(what: str, when: str) -> str:
    """Set a reminder for the user.

    Args:
        what: What they are being reminded about, in their own words.
        when: When to remind them, e.g. "Tuesday at 9am" or "tomorrow morning".

    Returns:
        A confirmation of the reminder that was set.
    """
    return _log("reminder", f"Reminder set: {what} — {when}.")


@tool
def send_message(recipient: str, body: str) -> str:
    """Send a text message to one of the user's contacts.

    Args:
        recipient: Who the message goes to.
        body: The message text, written in the user's own voice.

    Returns:
        A confirmation of the message that was sent.
    """
    who = _resolve_contact(recipient)
    return _log("message", f'Message to {who}: "{body}"')


@tool
def place_call(contact: str, purpose: str) -> str:
    """Start an assisted phone call to a contact.

    The user does not speak unaided on this call — Relay suggests each reply and
    speaks the one they choose.

    Args:
        contact: Who to call.
        purpose: Why they are calling, so replies can be predicted in context.

    Returns:
        A confirmation that the call is being placed.
    """
    who = _resolve_contact(contact)
    return _log("call", f"Calling {who} — {purpose}.")


@tool
def order_item(item: str, vendor: str = "") -> str:
    """Order or reorder something on the user's behalf.

    Args:
        item: What to order, e.g. "my repeat prescription".
        vendor: Where from, if the user named somewhere. Optional.

    Returns:
        A confirmation of the order that was placed.
    """
    where = f" from {_resolve_contact(vendor)}" if vendor else ""
    return _log("order", f"Ordered {item}{where}.")


TOOLS = [send_document, set_reminder, send_message, place_call, order_item]


async def execute(text: str, action: ActionSpec | None) -> CommitResponse:
    """Run the committed utterance through the action agent."""
    model = load_model("smart")
    if model is None:
        detail = _log("noted", f'Noted: "{text}"')
        return CommitResponse(spoken=text, receipt=detail, source="scripted")

    intent = f'The person said: "{text}"'
    if action and action.type != "none":
        intent += f"\nThey expect this to result in: {action.summary or action.type}"
    intent += "\n\nCarry out what they asked for, then confirm it in one short sentence."

    try:
        agent = Agent(
            model=model,
            system_prompt=EXECUTOR_SYSTEM_PROMPT,
            tools=TOOLS,
            callback_handler=None,
        )
        result = await agent.invoke_async(intent)
        receipt = str(result.message).strip()
        # Strands returns the message as a content-block structure; pull the text.
        if isinstance(result.message, dict):
            blocks = result.message.get("content", [])
            receipt = " ".join(
                b.get("text", "") for b in blocks if isinstance(b, dict)
            ).strip()
        return CommitResponse(
            spoken=text,
            receipt=receipt or "Done.",
            source=settings.provider,  # type: ignore[arg-type]
        )
    except Exception as exc:
        print(f"[relay] executor failed: {exc}")
        detail = _log("noted", f'Noted: "{text}"')
        return CommitResponse(spoken=text, receipt=detail, source="scripted")
