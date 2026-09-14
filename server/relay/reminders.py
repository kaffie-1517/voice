"""Reminders that actually fire.

The executor's set_reminder tool schedules here; a background loop delivers
due reminders to the user's Telegram chat and into the activity feed. Stored
on disk so a restart in the middle of a demo does not lose them.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

STORE = Path(".relay-reminders.json")
POLL_S = 5

_reminders: list[dict[str, Any]] = []


def _load() -> None:
    global _reminders
    if STORE.exists():
        try:
            _reminders = json.loads(STORE.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            _reminders = []


def _save() -> None:
    try:
        STORE.write_text(json.dumps(_reminders, indent=2), "utf-8")
    except OSError:
        pass


_load()


def _parse_when(when_iso: str, when_text: str) -> datetime | None:
    """The model gives an ISO time; fall back to "in N minutes/hours" from the
    human text if it did not."""
    try:
        return datetime.fromisoformat(when_iso.strip())
    except (ValueError, AttributeError):
        pass
    m = re.search(r"in\s+(\d+)\s*(min|minute|hour|hr|sec|second)", when_text.lower())
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        delta = timedelta(hours=n) if unit.startswith("h") else timedelta(seconds=n) if unit.startswith("s") else timedelta(minutes=n)
        return datetime.now() + delta
    return None


def _clock(at: datetime) -> str:
    return at.strftime("%I:%M %p").lstrip("0").lower()


def describe(at: datetime) -> str:
    """How a person would say when: "in 2 minutes", "today at 4:00 pm"."""
    now = datetime.now()
    delta = at - now
    if delta < timedelta(hours=1):
        mins = max(1, round(delta.total_seconds() / 60))
        return f"in {mins} minute{'s' if mins != 1 else ''}"
    if at.date() == now.date():
        return f"today at {_clock(at)}"
    if at.date() == (now + timedelta(days=1)).date():
        return f"tomorrow at {_clock(at)}"
    return f"{at.strftime('%A')} at {_clock(at)}"


def schedule(session_id: str, what: str, when_text: str, when_iso: str) -> tuple[str, datetime | None]:
    """Returns (receipt, fire time). No fire time means it could not be placed."""
    at = _parse_when(when_iso, when_text)
    if at is None:
        return f"Reminder noted: {what} — {when_text}. (Could not work out the exact time.)", None
    if at < datetime.now():
        at = datetime.now() + timedelta(minutes=1)
    _reminders.append({
        "id": f"{int(time.time() * 1000)}",
        "session": session_id,
        "what": what,
        "when_text": when_text,
        "at": at.isoformat(timespec="seconds"),
        "fired": False,
    })
    _save()
    return f"Reminder set: {what} — {describe(at)}.", at


def pending() -> list[dict[str, Any]]:
    return [r for r in _reminders if not r["fired"]]


async def run() -> None:
    """Fire due reminders. Imports inside to avoid a cycle with the executor."""
    from .executor import activity
    from .telegram import notify_me

    while True:
        now = datetime.now()
        for r in _reminders:
            if r["fired"]:
                continue
            try:
                due = datetime.fromisoformat(r["at"]) <= now
            except ValueError:
                r["fired"] = True
                continue
            if not due:
                continue
            r["fired"] = True
            _save()
            text = f"🔔 Reminder: {r['what']}"
            activity.add(r["session"], "reminder", f"Reminder fired: {r['what']}")
            try:
                await notify_me(text)
            except Exception as exc:
                print(f"[relay] reminder delivery failed: {exc}")
        await asyncio.sleep(POLL_S)
