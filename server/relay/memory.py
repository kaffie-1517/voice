"""Personalisation layer.

The thesis of the product is that Relay should get measurably better at
predicting *this particular person's* words the longer they use it. A generic
model guesses what someone might say; Relay should learn that Maya says "Give me
a minute", never "Please hold on", and that "Tuesday" almost always means speech
therapy.

Every committed utterance is recorded and fed back into the next prediction's
system prompt. Backed by AgentCore Memory when configured; a local JSON file
otherwise, so the learning story is demonstrable before AWS is wired up.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .config import settings


class RelayMemory:
    def __init__(self, path: str) -> None:
        self._path = Path(path)
        self._entries: list[dict[str, Any]] = []
        self._load()

    # --- backend selection ------------------------------------------------

    @property
    def backend(self) -> str:
        return "agentcore" if settings.agentcore_memory_id else "local-json"

    def _load(self) -> None:
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

    # --- the API the predictor uses ---------------------------------------

    def record_choice(self, text: str, channel: str) -> None:
        self._entries.append({"text": text, "channel": channel, "at": int(time.time())})
        self._save()

    def recent_choices(self, limit: int = 12) -> list[str]:
        """Most recent first, de-duplicated, so repeats do not crowd the prompt."""
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

    def stats(self) -> dict[str, Any]:
        return {"backend": self.backend, "recorded": len(self._entries)}


memory = RelayMemory(settings.memory_path)


def agentcore_session_manager() -> Any | None:
    """Strands session manager backed by AgentCore Memory, when available.

    Returns None unless AGENTCORE_MEMORY_ID is set and the bedrock-agentcore
    package is installed, so the server starts fine without either.
    """
    if not settings.agentcore_memory_id:
        return None
    try:
        from bedrock_agentcore.memory.integrations.strands.config import (
            AgentCoreMemoryConfig,
        )
        from bedrock_agentcore.memory.integrations.strands.session_manager import (
            AgentCoreMemorySessionManager,
        )
    except ImportError:
        print("[relay] AGENTCORE_MEMORY_ID set but bedrock-agentcore is not installed")
        return None

    config = AgentCoreMemoryConfig(
        memory_id=settings.agentcore_memory_id,
        session_id="relay-demo",
        actor_id="maya",
    )
    return AgentCoreMemorySessionManager(
        agentcore_memory_config=config, region_name=settings.aws_region
    )
