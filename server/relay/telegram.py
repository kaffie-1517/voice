"""Relay inside Telegram.

Three things happen here, all through one bot:

  1. Inline mode. In ANY chat she types "@RelayBot om tues" and Telegram pops
     up her three or four candidate sentences; tapping one sends it as her own
     message. No one else needs the bot.

  2. The relay. Family and services message the bot; the bot forwards each
     message to her with reply candidates as buttons; she taps one and the bot
     delivers it to them. Voice notes are transcribed on the way in — a judge
     can speak into their phone and watch her answer.

  3. Real actions. The executor's send_message / send_document tools deliver
     to linked Telegram chats instead of logging a receipt.

Long-polling, so it runs from the same process with no public URL.
"""

from __future__ import annotations

import asyncio
import json
import secrets
import time
from pathlib import Path
from typing import Any

import httpx

from .config import settings
from .executor import execute
from .memory import memory
from .predictor import predict
from .profile import demo_profile
from .schemas import Candidate, InputSignal, Partner, PredictRequest, Turn
from .speech import transcribe

ASSETS = Path(__file__).resolve().parent.parent / "assets"
STATE_PATH = Path(".relay-telegram.json")

HELP = (
    "Relay — your words, on time.\n\n"
    "• In any chat, type @{bot} and a few words or sounds. Pick the sentence you meant.\n"
    "• /me — this is Maya's chat. Messages from linked people arrive here with replies to tap.\n"
    "• /link Sam — link this chat as Sam (or Dr. Chen, Nadia, pharmacy…).\n"
    "• Send a voice note. It works on broken speech."
)


def _api_url(method: str) -> str:
    return f"https://api.telegram.org/bot{settings.telegram_bot_token}/{method}"


def _file_url(path: str) -> str:
    return f"https://api.telegram.org/file/bot{settings.telegram_bot_token}/{path}"


class TelegramState:
    """Who is who. Persisted so links survive a restart mid-demo."""

    def __init__(self) -> None:
        self.me: int | None = None
        self.links: dict[str, int] = {}  # profile contact name -> chat id
        self.transcripts: dict[str, list[Turn]] = {}
        self._load()

    def _load(self) -> None:
        if STATE_PATH.exists():
            try:
                data = json.loads(STATE_PATH.read_text("utf-8"))
                self.me = data.get("me")
                self.links = {k: int(v) for k, v in data.get("links", {}).items()}
            except (json.JSONDecodeError, OSError, ValueError):
                pass

    def save(self) -> None:
        try:
            STATE_PATH.write_text(json.dumps({"me": self.me, "links": self.links}, indent=2), "utf-8")
        except OSError:
            pass

    def name_for(self, chat_id: int) -> str | None:
        return next((n for n, c in self.links.items() if c == chat_id), None)

    def chat_for(self, name: str) -> int | None:
        needle = name.lower().strip()
        for contact_name, chat_id in self.links.items():
            if needle in contact_name.lower() or contact_name.lower().startswith(needle):
                return chat_id
        return None

    def turns(self, name: str) -> list[Turn]:
        return self.transcripts.setdefault(name, [])


state = TelegramState()

# Candidates waiting for a tap, by short token. Callback data is capped at 64
# bytes by Telegram, so the sentence itself cannot travel in the button.
_pending: dict[str, dict[str, Any]] = {}


def _contact_display(name: str) -> str:
    for c in demo_profile.contacts:
        if c.name == name:
            return c.name.split()[0] if c.relationship in ("son", "grandson") else c.name
    return name


# --- outbound, usable from sync tool functions ---------------------------------


def deliver_message(recipient: str, body: str) -> bool:
    chat_id = state.chat_for(recipient)
    if chat_id is None or not settings.telegram_bot_token:
        return False
    with httpx.Client(timeout=15) as client:
        r = client.post(_api_url("sendMessage"), json={"chat_id": chat_id, "text": body})
    return r.is_success


def deliver_document(recipient: str, document: str) -> bool:
    chat_id = state.chat_for(recipient)
    if chat_id is None or not settings.telegram_bot_token:
        return False
    path = ASSETS / "mri-scan-march.pdf"
    if not path.exists():
        return False
    with httpx.Client(timeout=30) as client:
        r = client.post(
            _api_url("sendDocument"),
            data={"chat_id": chat_id, "caption": f"From {demo_profile.name}: {document}"},
            files={"document": (path.name, path.read_bytes(), "application/pdf")},
        )
    return r.is_success


# --- inbound -------------------------------------------------------------------


class Bot:
    def __init__(self) -> None:
        self.client = httpx.AsyncClient(timeout=40)
        self.username = ""

    async def call(self, method: str, **params: Any) -> Any:
        r = await self.client.post(_api_url(method), json=params)
        data = r.json()
        if not data.get("ok"):
            print(f"[relay] telegram {method} failed: {data.get('description')}")
        return data.get("result")

    async def send(self, chat_id: int, text: str, buttons: list[list[dict[str, str]]] | None = None) -> None:
        params: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if buttons:
            params["reply_markup"] = {"inline_keyboard": buttons}
        await self.call("sendMessage", **params)

    async def download(self, file_id: str) -> bytes:
        info = await self.call("getFile", file_id=file_id)
        r = await self.client.get(_file_url(info["file_path"]))
        return r.content

    # -- message handling --

    async def fragments_from(self, msg: dict[str, Any]) -> tuple[list[InputSignal], str]:
        """What was said, as prediction signals, plus a readable form."""
        if "voice" in msg or "audio" in msg:
            media = msg.get("voice") or msg.get("audio")
            audio = await self.download(media["file_id"])
            text = await transcribe(audio, "voice.ogg") or ""
            if not text:
                return [], ""
            return [InputSignal(kind="speech", text=text)], f"🎤 {text}"
        text = (msg.get("text") or "").strip()
        return ([InputSignal(kind="typed", text=text)] if text else []), text

    async def offer(self, chat_id: int, header: str, req: PredictRequest, deliver_to: str | None) -> None:
        """Show candidates as buttons in Maya's chat."""
        res = await predict(req)
        token = secrets.token_urlsafe(6)
        _pending[token] = {
            "candidates": res.candidates,
            "deliver_to": deliver_to,
            "channel": req.channel,
            "at": time.time(),
        }
        buttons = [
            [{"text": f"{i + 1}. {c.text}", "callback_data": f"{token}:{i}"}]
            for i, c in enumerate(res.candidates)
        ]
        note = "" if not res.degraded else "\n(offline engine)"
        await self.send(chat_id, f"{header}{note}", buttons)
        # Drop stale offers so the table does not grow all demo long.
        for k in [k for k, v in _pending.items() if time.time() - v["at"] > 1800]:
            _pending.pop(k, None)

    async def on_message(self, msg: dict[str, Any]) -> None:
        chat_id = int(msg["chat"]["id"])
        text = (msg.get("text") or "").strip()
        sender = msg.get("from", {}).get("first_name", "someone")

        if text.startswith("/start") or text.startswith("/help"):
            await self.send(chat_id, HELP.format(bot=self.username or "RelayBot"))
            return
        if text.startswith("/me"):
            state.me = chat_id
            state.save()
            await self.send(chat_id, f"This is {demo_profile.name}'s chat now. Send a voice note or a few words.")
            return
        if text.startswith("/link"):
            name = text[5:].strip()
            resolved = next(
                (c.name for c in demo_profile.contacts
                 if name and (name.lower() in c.name.lower() or name.lower() in c.relationship.lower())),
                None,
            )
            if not resolved:
                await self.send(chat_id, "Link as who? Try: " + ", ".join(c.name for c in demo_profile.contacts))
                return
            state.links[resolved] = chat_id
            state.save()
            await self.send(chat_id, f"Linked. You are {resolved}. Message here and {demo_profile.name.split()[0]} will answer.")
            return

        signals, shown = await self.fragments_from(msg)
        if not signals:
            return

        if chat_id == state.me:
            # Her own chat: "Say" mode. Pick a sentence; actions run.
            await self.offer(chat_id, f"You: {shown}", PredictRequest(signals=signals, channel="message"), None)
            return

        name = state.name_for(chat_id)
        if name is None:
            await self.send(chat_id, f"Hi {sender}. Use /link <name> so {demo_profile.name.split()[0]} knows who you are.")
            return
        if state.me is None:
            await self.send(chat_id, f"{demo_profile.name.split()[0]}'s chat is not set up yet (/me).")
            return

        turns = state.turns(name)
        turns.append(Turn(speaker="partner", text=shown.replace("🎤 ", ""), at=int(time.time())))
        contact = next((c for c in demo_profile.contacts if c.name == name), None)
        await self.offer(
            state.me,
            f"{_contact_display(name)}: {shown}",
            PredictRequest(
                signals=[],
                channel="message",
                partner=Partner(name=name, role=contact.relationship if contact else "", relationship=contact.notes if contact else ""),
                transcript=turns[-8:],
            ),
            deliver_to=name,
        )

    async def on_callback(self, cq: dict[str, Any]) -> None:
        await self.call("answerCallbackQuery", callback_query_id=cq["id"])
        token, _, idx = (cq.get("data") or "").partition(":")
        offer = _pending.pop(token, None)
        if offer is None:
            return
        try:
            chosen: Candidate = offer["candidates"][int(idx)]
        except (ValueError, IndexError):
            return

        chat_id = int(cq["message"]["chat"]["id"])
        await self.call(
            "editMessageText",
            chat_id=chat_id,
            message_id=cq["message"]["message_id"],
            text=f"{cq['message']['text']}\n\n✔ {chosen.text}",
        )

        await asyncio.to_thread(memory.record_choice, chosen.text, offer["channel"])
        receipt = ""
        if chosen.action and chosen.action.type != "none":
            result = await execute(chosen.text, chosen.action, f"tg-{chat_id}")
            receipt = result.receipt

        if offer["deliver_to"]:
            name = offer["deliver_to"]
            state.turns(name).append(Turn(speaker="user", text=chosen.text, at=int(time.time())))
            if not deliver_message(name, chosen.text):
                receipt = receipt or f"Could not reach {name} on Telegram."
        if receipt:
            await self.send(chat_id, receipt)

    async def on_inline(self, iq: dict[str, Any]) -> None:
        query = (iq.get("query") or "").strip()
        results: list[dict[str, Any]] = []
        if query:
            res = await predict(PredictRequest(signals=[InputSignal(kind="typed", text=query)], channel="message"))
            for c in res.candidates:
                results.append({
                    "type": "article",
                    "id": c.id,
                    "title": c.text,
                    "description": c.gist,
                    "input_message_content": {"message_text": c.text},
                })
        await self.call("answerInlineQuery", inline_query_id=iq["id"], results=results, cache_time=0, is_personal=True)

    async def on_chosen_inline(self, ch: dict[str, Any]) -> None:
        # Needs /setinlinefeedback in BotFather; harmless if it never arrives.
        text = (ch.get("query") or "").strip()
        if text:
            await asyncio.to_thread(memory.record_choice, text, "message")

    # -- loop --

    async def run(self) -> None:
        me = await self.call("getMe")
        if not me:
            print("[relay] telegram: bad token, bot not started")
            return
        self.username = me.get("username", "")
        print(f"[relay] telegram bot @{self.username} polling")
        offset = 0
        while True:
            try:
                updates = await self.call("getUpdates", offset=offset, timeout=30,
                                          allowed_updates=["message", "callback_query", "inline_query", "chosen_inline_result"])
                for u in updates or []:
                    offset = u["update_id"] + 1
                    try:
                        if "message" in u:
                            await self.on_message(u["message"])
                        elif "callback_query" in u:
                            await self.on_callback(u["callback_query"])
                        elif "inline_query" in u:
                            await self.on_inline(u["inline_query"])
                        elif "chosen_inline_result" in u:
                            await self.on_chosen_inline(u["chosen_inline_result"])
                    except Exception as exc:
                        print(f"[relay] telegram update failed: {exc}")
            except (httpx.HTTPError, asyncio.TimeoutError) as exc:
                print(f"[relay] telegram poll error: {exc}")
                await asyncio.sleep(3)


def available() -> bool:
    return bool(settings.telegram_bot_token)


async def run() -> None:
    if available():
        await Bot().run()
