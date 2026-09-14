"""Runtime configuration and provider selection.

Relay is written so that the model provider is a deployment detail, not an
architectural one. Strands normalises all three behind the same Agent API, so
switching providers is a config change with no code path of its own.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _has_aws_credentials() -> bool:
    return any(
        os.environ.get(key)
        for key in (
            "AWS_BEDROCK_API_KEY",
            "AWS_ACCESS_KEY_ID",
            "AWS_PROFILE",
            "AWS_ROLE_ARN",
        )
    )


def _resolve_provider() -> str:
    requested = os.environ.get("LLM_PROVIDER", "auto").strip().lower()

    if requested == "bedrock" and _has_aws_credentials():
        return "bedrock"
    if requested == "anthropic" and os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if requested == "openai" and os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if requested == "groq" and os.environ.get("GROQ_API_KEY"):
        return "groq"
    if requested == "scripted":
        return "scripted"

    # auto, or an explicit choice whose credentials are missing
    if _has_aws_credentials():
        return "bedrock"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("GROQ_API_KEY"):
        return "groq"
    return "scripted"


@dataclass(frozen=True)
class Settings:
    provider: str
    aws_region: str
    bedrock_fast_model: str
    bedrock_smart_model: str
    anthropic_fast_model: str
    anthropic_smart_model: str
    openai_fast_model: str
    openai_smart_model: str
    groq_fast_model: str
    groq_smart_model: str
    agentcore_memory_id: str
    agentcore_actor_id: str
    memory_path: str
    port: int

    @property
    def fast_model(self) -> str:
        return {
            "bedrock": self.bedrock_fast_model,
            "anthropic": self.anthropic_fast_model,
            "openai": self.openai_fast_model,
            "groq": self.groq_fast_model,
        }.get(self.provider, "scripted")

    @property
    def smart_model(self) -> str:
        return {
            "bedrock": self.bedrock_smart_model,
            "anthropic": self.anthropic_smart_model,
            "openai": self.openai_smart_model,
            "groq": self.groq_smart_model,
        }.get(self.provider, "scripted")


settings = Settings(
    provider=_resolve_provider(),
    aws_region=os.environ.get("AWS_REGION", "us-west-2"),
    # Bedrock ids carry a routing prefix and differ per account/region — check
    # yours in the Bedrock console under Model access before flipping over.
    bedrock_fast_model=os.environ.get(
        "BEDROCK_FAST_MODEL", "global.anthropic.claude-haiku-4-5"
    ),
    bedrock_smart_model=os.environ.get(
        "BEDROCK_SMART_MODEL", "global.anthropic.claude-sonnet-4-6"
    ),
    anthropic_fast_model=os.environ.get("ANTHROPIC_FAST_MODEL", "claude-haiku-4-5"),
    anthropic_smart_model=os.environ.get("ANTHROPIC_SMART_MODEL", "claude-opus-5"),
    openai_fast_model=os.environ.get("OPENAI_FAST_MODEL", "gpt-4o-mini"),
    openai_smart_model=os.environ.get("OPENAI_SMART_MODEL", "gpt-4o"),
    # 20b is ~400ms quicker but echoes fragments back ("Doc Tuesday.") instead
    # of completing them; 120b stays natural and spreads across intents.
    groq_fast_model=os.environ.get("GROQ_FAST_MODEL", "openai/gpt-oss-120b"),
    groq_smart_model=os.environ.get("GROQ_SMART_MODEL", "openai/gpt-oss-120b"),
    agentcore_memory_id=os.environ.get("AGENTCORE_MEMORY_ID", ""),
    agentcore_actor_id=os.environ.get("AGENTCORE_ACTOR_ID", "maya"),
    memory_path=os.environ.get("RELAY_MEMORY_PATH", ".relay-memory.json"),
    port=int(os.environ.get("PORT", "8787")),
)
