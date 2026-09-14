"""The action executor — a real Strands agent loop.

This is the half of Relay that genuinely needs an agent. Once the user has
committed to an utterance like "Send my last scan to Dr. Chen and remind me
Tuesday", something has to decide which tools to call, in what order, with what
arguments. That is a model-driven tool loop, which is exactly what Strands is for.

send_message and send_document deliver for real when the recipient is linked
on Telegram, and set_reminder really fires (to Telegram and the activity
feed); place_call and order_item simulate their effect and return a receipt.
Swapping a tool for a real integration is a change inside that one function —
the agent, the prompt, and the UI are untouched.
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime
from typing import Any

from strands import Agent, tool
from strands.event_loop._retry import ModelRetryStrategy
from strands.types.tools import ToolContext

from .config import settings
from .profile import demo_profile
from .prompts import EXECUTOR_SYSTEM_PROMPT
from .providers import load_model
from .schemas import ActionSpec, CommitResponse


class ActivityLog:
    """What the agent did, per client session, so the user can see that saying
    the sentence actually caused something to happen — and only their own."""

    def __init__(self, keep: int = 200) -> None:
        self._keep = keep
        self._by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def add(self, session_id: str, kind: str, detail: str) -> str:
        entries = self._by_session[session_id]
        entries.append({"kind": kind, "detail": detail, "at": int(time.time())})
        del entries[: -self._keep]
        return detail

    def entries(self, session_id: str, limit: int = 30) -> list[dict[str, Any]]:
        return list(reversed(self._by_session.get(session_id, [])[-limit:]))


activity = ActivityLog()


def _session_of(ctx: ToolContext) -> str:
    return str(ctx.invocation_state.get("session_id", "anonymous"))


def _resolve_contact(name: str) -> str:
    """Match a loosely-spoken name against the profile's contacts."""
    needle = name.lower().strip()
    for contact in demo_profile.contacts:
        if needle in contact.name.lower() or contact.name.lower().startswith(needle):
            return contact.name
        if needle and needle in contact.relationship.lower():
            return contact.name
    return name


@tool(context=True)
def send_document(recipient: str, document: str, tool_context: ToolContext) -> str:
    """Send a document or medical record to one of the user's contacts.

    Args:
        recipient: Who it goes to. A name or a relationship such as "my neurologist".
        document: Which document to send, e.g. "the MRI scan from March".

    Returns:
        A confirmation describing what was sent and to whom.
    """
    from .telegram import deliver_document

    who = _resolve_contact(recipient)
    via = " on Telegram" if deliver_document(who, document) else ""
    return activity.add(_session_of(tool_context), "document", f"Sent {document} to {who}{via}.")


@tool(context=True)
def set_reminder(what: str, when: str, when_iso: str, tool_context: ToolContext) -> str:
    """Set a reminder for the user. It will be delivered to them at that time.

    Args:
        what: What they are being reminded about, in their own words.
        when: When to remind them, as they said it, e.g. "Tuesday at 9am",
            "in two minutes", "tomorrow morning".
        when_iso: The same moment as an ISO 8601 local datetime, computed from
            the current time given in the request, e.g. "2026-09-15T09:00".
            If they gave a day but no time, use 09:00.

    Returns:
        A confirmation of the reminder that was set.
    """
    from .reminders import schedule

    receipt, _ = schedule(_session_of(tool_context), what, when, when_iso)
    return activity.add(_session_of(tool_context), "reminder", receipt)


@tool(context=True)
def send_message(recipient: str, body: str, tool_context: ToolContext) -> str:
    """Send a text message to one of the user's contacts.

    Args:
        recipient: Who the message goes to.
        body: The message text, written in the user's own voice.

    Returns:
        A confirmation of the message that was sent.
    """
    from .telegram import deliver_message

    who = _resolve_contact(recipient)
    via = " on Telegram" if deliver_message(who, body) else ""
    return activity.add(_session_of(tool_context), "message", f'Message to {who}{via}: "{body}"')


@tool(context=True)
def place_call(contact: str, purpose: str, tool_context: ToolContext) -> str:
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
    return activity.add(_session_of(tool_context), "call", f"Calling {who} — {purpose}.")


@tool(context=True)
def order_item(item: str, tool_context: ToolContext, vendor: str = "") -> str:
    """Order or reorder something on the user's behalf.

    Args:
        item: What to order, e.g. "my repeat prescription".
        vendor: Where from, if the user named somewhere. Optional.

    Returns:
        A confirmation of the order that was placed.
    """
    where = f" from {_resolve_contact(vendor)}" if vendor else ""
    return activity.add(_session_of(tool_context), "order", f"Ordered {item}{where}.")


TOOLS = [send_document, set_reminder, send_message, place_call, order_item]


async def execute(text: str, action: ActionSpec | None, session_id: str) -> CommitResponse:
    """Run the committed utterance through the action agent."""
    model = load_model("smart")
    if model is None:
        detail = activity.add(session_id, "noted", f'Noted: "{text}"')
        return CommitResponse(spoken=text, receipt=detail, source="scripted")

    now = datetime.now()
    intent = f'The person said: "{text}"'
    if action and action.type != "none":
        intent += f"\nThey expect this to result in: {action.summary or action.type}"
    intent += f"\nCurrent local time: {now.strftime('%A %Y-%m-%dT%H:%M')}"
    intent += "\n\nCarry out what they asked for, then confirm it in one short sentence."

    try:
        agent = Agent(
            model=model,
            system_prompt=EXECUTOR_SYSTEM_PROMPT,
            tools=TOOLS,
            callback_handler=None,
            # One quick retry, not Strands' default six with minutes of backoff.
            retry_strategy=ModelRetryStrategy(max_attempts=2, initial_delay=2, max_delay=2),
        )
        result = await agent.invoke_async(
            intent, invocation_state={"session_id": session_id}
        )
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
        detail = activity.add(session_id, "noted", f'Noted: "{text}"')
        return CommitResponse(spoken=text, receipt=detail, source="scripted")
