"""Personalisation layer.

The thesis of the product is that Relay should get measurably better at
predicting *this particular person's* words the longer they use it. A generic
model guesses what someone might say; Relay should learn that Maya says "Give me
a minute", never "Please hold on", and that "Tuesday" almost always means speech
therapy.

Every committed utterance is recorded and fed back into the next prediction's
system prompt — the most recent ones, plus the ones most relevant to what she
is saying right now. Backed by Amazon Bedrock AgentCore Memory when configured;
a local JSON file otherwise, with the same interface.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Protocol

from .config import settings

# Every choice lands in one long-lived AgentCore session so the phrasebook is
# continuous across app sessions, devices and restarts. Per-visit state is the
# client session id, which lives in the activity log, not here.
PHRASEBOOK_SESSION = "phrasebook"


def _tokens(text: str, min_len: int = 3) -> set[str]:
    return {t for t in re.findall(r"[a-z']+", text.lower()) if len(t) >= min_len}


def _sounds_like(heard: str, word: str) -> bool:
    """Loose match for a recogniser's mangling of impaired speech: "om" for
    "home", "chin" for "Chen", "tues" for "tuesday"."""
    if heard == word:
        return True
    if len(heard) == 2:
        # A dropped consonant or two ("om" for "home"). Only against words
        # long enough that the match is not a coincidence of two letters.
        return len(word) >= 4 and heard in word
    if heard in word or word in heard:
        return True
    return SequenceMatcher(None, heard, word).ratio() >= 0.75


def _overlap(query_tokens: set[str], text: str) -> int:
    words = _tokens(text)
    return sum(1 for q in query_tokens if any(_sounds_like(q, w) for w in words))


class Phrasebook(Protocol):
    backend: str

    def record_choice(self, text: str, channel: str) -> None: ...
    def recent_choices(self, limit: int = 12) -> list[str]: ...
    def relevant_choices(self, query: str, limit: int = 5) -> list[str]: ...
    def stats(self) -> dict[str, Any]: ...


class LocalPhrasebook:
    backend = "local-json"

    def __init__(self, path: str) -> None:
        self._path = Path(path)
        self._entries: list[dict[str, Any]] = []
        if self._path.exists():
            try:
                self._entries = json.loads(self._path.read_text("utf-8"))
            except (json.JSONDecodeError, OSError):
                self._entries = []

    def _save(self) -> None:
        try:
            self._path.write_text(
                json.dumps(self._entries[-400:], indent=2), encoding="utf-8"
            )
        except OSError:
            pass  # memory is an enhancement; never break speech over it

    def record_choice(self, text: str, channel: str) -> None:
        self._entries.append({"text": text, "channel": channel, "at": int(time.time())})
        self._save()

    def recent_choices(self, limit: int = 12) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for entry in reversed(self._entries):
            text = entry.get("text", "")
            if text and text not in seen:
                seen.add(text)
                out.append(text)
            if len(out) >= limit:
                break
        return out

    def relevant_choices(self, query: str, limit: int = 5) -> list[str]:
        needles = _tokens(query, min_len=2)
        if not needles:
            return []
        scored: dict[str, int] = {}
        for entry in self._entries:
            text = entry.get("text", "")
            overlap = _overlap(needles, text)
            if overlap:
                scored[text] = max(scored.get(text, 0), overlap)
        return [t for t, _ in sorted(scored.items(), key=lambda kv: -kv[1])[:limit]]

    def stats(self) -> dict[str, Any]:
        return {"backend": self.backend, "recorded": len(self._entries)}


class AgentCorePhrasebook:
    """AgentCore Memory: raw events are the short-term store (exact phrasing,
    newest first); a semantic strategy on the resource turns them into
    long-term records that can be retrieved by meaning."""

    backend = "agentcore"

    def __init__(self, memory_id: str, actor_id: str, region: str) -> None:
        from bedrock_agentcore.memory import MemoryClient

        self._client = MemoryClient(region_name=region)
        self._memory_id = memory_id
        self._actor_id = actor_id
        self._namespace = f"/relay/{actor_id}/phrasebook"
        self._recorded = 0
        # Newest first. Served from here so the prediction loop never waits on
        # a list call; the one network hit per prediction is semantic retrieval.
        self._recent: list[str] = self._load_recent()

    def _load_recent(self) -> list[str]:
        try:
            events = self._client.list_events(
                memory_id=self._memory_id,
                actor_id=self._actor_id,
                session_id=PHRASEBOOK_SESSION,
                max_results=100,
            )
        except Exception as exc:
            print(f"[relay] agentcore list_events failed: {exc}")
            return []
        out: list[str] = []
        for event in sorted(events, key=lambda e: e.get("eventTimestamp", 0), reverse=True):
            for item in event.get("payload", []):
                text = item.get("conversational", {}).get("content", {}).get("text", "")
                if text:
                    out.append(text)
        return out

    def record_choice(self, text: str, channel: str) -> None:
        self._recent.insert(0, text)
        try:
            self._client.create_event(
                memory_id=self._memory_id,
                actor_id=self._actor_id,
                session_id=PHRASEBOOK_SESSION,
                messages=[(text, "USER")],
                metadata={"channel": channel},
            )
            self._recorded += 1
        except Exception as exc:
            print(f"[relay] agentcore create_event failed: {exc}")

    def recent_choices(self, limit: int = 12) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for text in self._recent:
            if text not in seen:
                seen.add(text)
                out.append(text)
            if len(out) >= limit:
                break
        return out

    def relevant_choices(self, query: str, limit: int = 5) -> list[str]:
        if not query.strip():
            return []
        try:
            records = self._client.retrieve_memories(
                memory_id=self._memory_id,
                namespace=self._namespace,
                query=query,
                top_k=limit,
            )
        except Exception as exc:
            print(f"[relay] agentcore retrieve_memories failed: {exc}")
            return []
        return [
            r.get("content", {}).get("text", "")
            for r in records
            if r.get("content", {}).get("text")
        ]

    def stats(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "memory_id": self._memory_id,
            "recorded": self._recorded,
        }


def _open_phrasebook() -> Phrasebook:
    if settings.agentcore_memory_id:
        try:
            return AgentCorePhrasebook(
                settings.agentcore_memory_id, settings.agentcore_actor_id, settings.aws_region
            )
        except Exception as exc:  # package missing, no credentials, bad region
            print(f"[relay] AgentCore Memory unavailable, using local store: {exc}")
    return LocalPhrasebook(settings.memory_path)


memory: Phrasebook = _open_phrasebook()


async def learned_phrases(query: str) -> list[str]:
    """What to show the predictor: only past choices that relate to this
    moment. Unrelated recent choices are left out on purpose — a sentence she
    said in another conversation is a topic she is not raising now, and the
    model will happily raise it for her."""
    return await asyncio.to_thread(memory.relevant_choices, query, 8)
