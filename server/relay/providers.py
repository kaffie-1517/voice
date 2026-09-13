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


def _build_openai(model_id: str, temperature: float | None, max_tokens: int) -> Any:
    import os

    from strands.models.openai import OpenAIModel

    params: dict[str, Any] = {"max_tokens": max_tokens}
    if temperature is not None:
        params["temperature"] = temperature
    return OpenAIModel(
        client_args={"api_key": os.environ["OPENAI_API_KEY"]},
        model_id=model_id,
        params=params,
    )


@functools.lru_cache(maxsize=4)
def load_model(tier: str) -> Any | None:
    """Return a Strands model for 'fast' or 'smart', or None in scripted mode.

    Cached because model objects hold a provider client; rebuilding one per
    request would add a connection setup to the latency budget.
    """
    if settings.provider == "scripted":
        return None

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
            return _build_openai(model_id, temperature, max_tokens)
    except Exception as exc:  # missing extra, bad credentials, unknown model id
        print(f"[relay] could not build {tier} model ({model_id}): {exc}")
        return None

    return None
