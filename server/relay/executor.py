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

import re
import time
from collections import defaultdict
from datetime import datetime
from types import SimpleNamespace
from typing import Any

from strands import Agent, tool
from strands.event_loop._retry import ModelRetryStrategy
from strands.types.tools import ToolContext

from .config import settings
from .profile import demo_profile
from .prompts import EXECUTOR_SYSTEM_PROMPT
from .providers import load_model
from .safety import is_throttled
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
    """Start an assisted phone call to a contact, or ask them to call back.

    The user does not speak unaided on a call — Relay suggests each reply and
    speaks the one they choose. Contacts reachable on Telegram are told she is
    calling and asked to ring her now.

    Args:
        contact: Who to call — a name, a relationship, or a service such as
            "the fire brigade" or "an ambulance".
        purpose: Why they are calling, so replies can be predicted in context.

    Returns:
        A confirmation that the call is being placed.
    """
    from .telegram import deliver_message

    who = _resolve_contact(contact)
    reached = deliver_message(
        who,
        f"📞 {demo_profile.name.split()[0]} is calling you through Relay — {purpose}. "
        "She may not be able to say much. Please call her now.",
    )
    via = " — reached on Telegram, asked to call her back" if reached else ""
    return activity.add(
        _session_of(tool_context), "call",
        f"Calling {who} — {purpose}{via}. Open the Call tab in Relay to talk with replies ready.",
    )


@tool(context=True)
def alert_emergency(situation: str, service: str, tool_context: ToolContext) -> str:
    """Raise the alarm: tell every one of the user's emergency contacts what is
    happening and call the right emergency service. Use for fire, a fall,
    chest pain, breathing trouble, or any plain call for help.

    Args:
        situation: What is wrong, in one plain sentence, in her words.
        service: Which service to call — "fire brigade", "ambulance", "police",
            or "none" if it is clearly not that kind of emergency.

    Returns:
        Who was reached and what was called.
    """
    from .telegram import deliver_location, deliver_message, maps_link, state

    session = _session_of(tool_context)
    first = demo_profile.name.split()[0]
    where = maps_link()
    reached: list[str] = []
    for contact in demo_profile.contacts:
        # Adults who can act: not the pharmacy, not her nine-year-old grandson,
        # and services get their own call below.
        if contact.relationship in ("pharmacy", "grandson", "emergency service"):
            continue
        if deliver_message(
            contact.name,
            f"🚨 EMERGENCY from {first}: {situation}\n"
            f"She has aphasia and may not be able to speak. "
            f"Please call her right now, and call emergency services if you cannot reach her."
            + (f"\nWhere she is: {where}" if where else ""),
        ):
            parts = contact.name.split()
            reached.append(" ".join(parts[:2]) if parts[0].endswith(".") else parts[0])
            if where:
                deliver_location(contact.name)
    activity.add(
        session, "emergency",
        f"Alerted emergency contacts: {', '.join(reached) if reached else 'none reachable on Telegram'}.",
    )
    called = ""
    if service and service.lower() != "none":
        # The service's own channel, when one is linked (a real dispatcher
        # integration would go here); otherwise the call is logged only.
        answered = deliver_message(
            service,
            f"🚒 EMERGENCY CALL via Relay for {demo_profile.name}: {situation}\n"
            f"Caller has aphasia and cannot speak clearly. Phone: {demo_profile.contacts[1].phone}."
            + (f"\nLocation: {where}" if where else ""),
        )
        if answered and where:
            deliver_location(service)
        activity.add(session, "call", f"Calling the {service} — {situation}" + (" (reached)" if answered else ""))
        called = f" and calling the {service}"
    who = ", ".join(reached) if reached else "no one on Telegram"
    if not state.links:
        who += " (no contacts linked yet — use /link in Telegram)"
    return f"Alerted {who}{called}."


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


@tool(context=True)
def share_location(recipient: str, tool_context: ToolContext) -> str:
    """Send the user's current location to one of her contacts as a map pin.

    Args:
        recipient: Who should receive it — a name or a relationship.

    Returns:
        A confirmation, or a note that her location is not known yet.
    """
    from .telegram import deliver_location, state

    who = _resolve_contact(recipient)
    if not state.location:
        return activity.add(
            _session_of(tool_context), "location",
            f"Could not share location with {who}: she has not shared it yet (/where in Telegram).",
        )
    sent = deliver_location(who)
    return activity.add(
        _session_of(tool_context), "location",
        f"Shared her location with {who}." if sent else f"Could not reach {who} on Telegram to share her location.",
    )


TOOLS = [send_document, set_reminder, send_message, place_call, order_item, alert_emergency, share_location]


def _mentioned_contact(text: str) -> str | None:
    """The first of her people named in the sentence, by name or relationship."""
    low = text.lower()
    for c in demo_profile.contacts:
        first = c.name.split()[-1].lower()  # surname or single name
        if c.name.lower() in low or first in low or c.relationship.lower() in low:
            return c.name
        if c.name.lower().startswith("dr.") and "doctor" in low:
            return c.name
    return None


def _emergency_service(text: str) -> str:
    low = text.lower()
    if re.search(r"fire|smoke|burn", low):
        return "fire brigade"
    if re.search(r"ambulance|chest|breath|fall|fell|bleed|stroke|heart|unconscious|hurt|pain", low):
        return "ambulance"
    if re.search(r"police|intruder|break", low):
        return "police"
    return "ambulance" if re.search(r"help|emergenc", low) else "none"


def offline_execute(text: str, action: ActionSpec, session_id: str) -> str:
    """No model, or the model failed. The detected intent still runs the tools
    directly. Cruder than the agent — no clever argument extraction — but an
    emergency alert must never depend on a provider being up."""
    ctx = SimpleNamespace(invocation_state={"session_id": session_id})
    who = _mentioned_contact(text)
    kind = action.type
    if kind == "alert_emergency":
        return alert_emergency(situation=text, service=_emergency_service(text), tool_context=ctx)
    if kind == "place_call":
        return place_call(contact=who or "Sam", purpose=text, tool_context=ctx)
    if kind == "send_message":
        # "Tell Sam I'll be late." -> body after the name, else the whole sentence.
        body = text
        if who:
            m = re.search(rf"\b(tell|text|message|let)\s+\w+\s+(know\s+)?(that\s+)?(.+)$", text, re.I)
            body = (m.group(4) if m else text).strip().rstrip(".") + "."
        return send_message(recipient=who or "Sam", body=body, tool_context=ctx)
    if kind == "share_location":
        return share_location(recipient=who or "Sam", tool_context=ctx)
    if kind == "set_reminder":
        what = re.sub(r"^\s*remind me\s*(to\s+)?", "", text, flags=re.I).strip()
        return set_reminder(what=what or text, when=text, when_iso="", tool_context=ctx)
    if kind == "send_document":
        return send_document(recipient=who or "Dr. Chen", document="her latest scan", tool_context=ctx)
    if kind == "order":
        return order_item(item=re.sub(r"^\s*(re)?order\s*", "", text, flags=re.I) or text, tool_context=ctx)
    return activity.add(session_id, "noted", f'Noted: "{text}"')


async def execute(text: str, action: ActionSpec | None, session_id: str) -> CommitResponse:
    """Run the committed utterance through the action agent."""
    model = load_model("smart")
    if model is None:
        if action and action.type != "none":
            return CommitResponse(spoken=text, receipt=offline_execute(text, action, session_id), source="scripted")
        detail = activity.add(session_id, "noted", f'Noted: "{text}"')
        return CommitResponse(spoken=text, receipt=detail, source="scripted")

    now = datetime.now()
    intent = f'The person said: "{text}"'
    if action and action.type == "alert_emergency":
        intent += (
            "\nTHIS IS AN EMERGENCY. Call alert_emergency first with what is wrong "
            "and the right service. Do not ask questions. Do not do anything else "
            "unless she asked for it."
        )
    elif action and action.type != "none":
        intent += f"\nThey expect this to result in: {action.summary or action.type}"
    intent += f"\nCurrent local time: {now.strftime('%A %Y-%m-%dT%H:%M')}"
    intent += "\n\nCarry out what they asked for, then confirm it in one short sentence."

    async def live(m: Any) -> str:
        agent = Agent(
            model=m,
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
        return receipt

    try:
        try:
            receipt = await live(model)
        except Exception as exc:
            backup = load_model("smart", backup=True)
            if backup is None or not is_throttled(exc):
                raise
            print("[relay] primary key throttled, retrying executor on backup key")
            receipt = await live(backup)
        return CommitResponse(
            spoken=text,
            receipt=receipt or "Done.",
            source=settings.provider,  # type: ignore[arg-type]
        )
    except Exception as exc:
        print(f"[relay] executor failed, running the intent offline: {exc}")
        if action and action.type != "none":
            return CommitResponse(spoken=text, receipt=offline_execute(text, action, session_id), source="scripted")
        detail = activity.add(session_id, "noted", f'Noted: "{text}"')
        return CommitResponse(spoken=text, receipt=detail, source="scripted")
