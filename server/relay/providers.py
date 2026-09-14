"""Builds Strands model objects for the two tiers Relay runs.

Relay uses two model tiers because its two workloads pull in opposite
directions:

  fast  — the prediction loop. Fires every time speech pauses, while someone is
          still mid-sentence. Latency IS the feature; a correct suggestion that
          lands two seconds late is a failed suggestion.
  smart — the action executor. Runs once, after the user has committed, and is
          allowed to take its time because it is booking real appointments.
"""

from __future__ import annotations

import functools
from typing import Any

from pydantic import BaseModel

from .config import settings

# Claude 4.6+ removed temperature/top_p/top_k; sending them returns a 400.
# Haiku 4.5 and Sonnet 4.6 still accept them.
_NO_SAMPLING = ("opus-5", "sonnet-5", "opus-4-7", "opus-4-8", "fable", "mythos")


def _supports_sampling(model_id: str) -> bool:
    return not any(marker in model_id for marker in _NO_SAMPLING)


def _build_bedrock(model_id: str, temperature: float | None) -> Any:
    from strands.models import BedrockModel

    kwargs: dict[str, Any] = {"model_id": model_id, "region_name": settings.aws_region}
    if temperature is not None and _supports_sampling(model_id):
        kwargs["temperature"] = temperature
    return BedrockModel(**kwargs)


def _build_anthropic(model_id: str, temperature: float | None, max_tokens: int) -> Any:
    import os

    from strands.models.anthropic import AnthropicModel

    params: dict[str, Any] = {}
    if temperature is not None and _supports_sampling(model_id):
        params["temperature"] = temperature
    return AnthropicModel(
        client_args={"api_key": os.environ["ANTHROPIC_API_KEY"]},
        model_id=model_id,
        max_tokens=max_tokens,
        params=params,
    )


def _openai_params(
    model_id: str, temperature: float | None, max_tokens: int, force_tool: str | None
) -> dict[str, Any]:
    params: dict[str, Any] = {"max_tokens": max_tokens}
    if temperature is not None:
        params["temperature"] = temperature
    # gpt-oss models reason before answering; on the fast tier that reasoning is
    # latency the user feels mid-sentence, so keep it minimal.
    if "gpt-oss" in model_id:
        params["reasoning_effort"] = "low" if temperature is not None else "medium"
    elif "qwen" in model_id:
        # Qwen thinks at length before a tool call and blows the token budget;
        # the prediction tier does not need it.
        params["reasoning_effort"] = "none" if temperature is not None else "default"
    # Strands only forces the structured-output tool on a *second* round trip,
    # after the model has answered in prose once. On the prediction loop that
    # doubles latency, so force it from the first request. `params` is merged
    # last into the request, which is what lets this override Strands' choice.
    if force_tool:
        params["tool_choice"] = {"type": "function", "function": {"name": force_tool}}
    return params


def _build_openai(
    model_id: str, temperature: float | None, max_tokens: int, force_tool: str | None
) -> Any:
    import os

    from strands.models.openai import OpenAIModel

    return OpenAIModel(
        client_args={"api_key": os.environ["OPENAI_API_KEY"]},
        model_id=model_id,
        params=_openai_params(model_id, temperature, max_tokens, force_tool),
    )


def _build_groq(
    model_id: str, temperature: float | None, max_tokens: int, force_tool: str | None
) -> Any:
    """Groq speaks the OpenAI wire protocol, so Strands' OpenAIModel with a
    different base_url is the whole integration."""
    import os

    from strands.models.openai import OpenAIModel

    return OpenAIModel(
        client_args={
            "api_key": os.environ["GROQ_API_KEY"],
            "base_url": "https://api.groq.com/openai/v1",
        },
        model_id=model_id,
        params=_openai_params(model_id, temperature, max_tokens, force_tool),
    )


@functools.lru_cache(maxsize=8)
def load_model(tier: str, structured: type[BaseModel] | None = None) -> Any | None:
    """Return a Strands model for 'fast' or 'smart', or None in scripted mode.

    Pass the Pydantic model an agent will be constrained to when the agent does
    nothing but structured output; providers that can force the tool from the
    first request will. Leave it out for real tool-using agents.

    Cached because model objects hold a provider client; rebuilding one per
    request would add a connection setup to the latency budget.
    """
    if settings.provider == "scripted":
        return None

    force_tool = structured.__name__ if structured else None

    if tier == "fast":
        model_id = settings.fast_model
        # A little spread here is deliberate: the four candidates need to cover
        # different intents, not four phrasings of one guess.
        temperature: float | None = 0.6
        max_tokens = 700
    else:
        model_id = settings.smart_model
        temperature = None
        max_tokens = 2000

    try:
        if settings.provider == "bedrock":
            return _build_bedrock(model_id, temperature)
        if settings.provider == "anthropic":
            return _build_anthropic(model_id, temperature, max_tokens)
        if settings.provider == "openai":
            return _build_openai(model_id, temperature, max_tokens, force_tool)
        if settings.provider == "groq":
            return _build_groq(model_id, temperature, max_tokens, force_tool)
    except Exception as exc:  # missing extra, bad credentials, unknown model id
        print(f"[relay] could not build {tier} model ({model_id}): {exc}")
        return None

    return None
