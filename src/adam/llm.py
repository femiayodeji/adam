"""LLM completion — async, with retry and Pydantic validation.

Flow:
  complete_async(conversation) -> MotionPlan | None
    1. asyncio.to_thread via litellm.completion
    2. Strip code fences
    3. JSON parse — retry once on failure
    4. MotionPlan validation + rotation clamping
    5. Exponential backoff on RateLimitError (up to 3 attempts)
"""
from __future__ import annotations

import asyncio
import json
import logging
import re

import litellm

from adam.config import config
from adam.models import MotionPlan
from adam.prompt import build_system_prompt

log = logging.getLogger("adam.llm")

_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?\s*```$", re.DOTALL)


def _strip_fences(text: str) -> str:
    m = _FENCE_RE.match(text.strip())
    return m.group(1).strip() if m else text.strip()


def _parse(raw: str) -> MotionPlan | None:
    try:
        data = json.loads(raw)
        plan = MotionPlan.model_validate(data)
        plan.clamp_rotations()
        return plan
    except Exception as exc:
        log.warning("Motion parse failed: %s", exc)
        return None


def _is_rate_limited(exc: Exception) -> bool:
    """Return True when provider error is a rate-limit style failure."""
    status_code = getattr(exc, "status_code", None)
    if status_code == 429:
        return True
    text = str(exc).lower()
    return "rate limit" in text or "too many requests" in text


def _llm_kwargs(messages: list[dict]) -> dict:
    kw: dict = {
        "model": config.llm.model,
        "custom_llm_provider": config.llm.provider,
        "api_key": config.llm.api_key,
        "messages": messages,
        "temperature": config.llm.temperature,
        "max_tokens": config.llm.max_tokens,
        "timeout": config.llm.timeout_s,
    }

    if config.llm.base_url:
        kw["api_base"] = config.llm.base_url

    return kw


async def complete_async(
    conversation: list[dict],
    last_description: str | None = None,
) -> MotionPlan | None:
    """Non-streaming completion with retry logic."""
    messages = [
        {"role": "system", "content": build_system_prompt(last_description)},
        *conversation,
    ]

    for attempt in range(3):
        try:
            response = await asyncio.to_thread(
                litellm.completion, **_llm_kwargs(messages)
            )
            raw = _strip_fences((response.choices[0].message.content or "").strip())  # type: ignore[union-attr]

            plan = _parse(raw)
            if plan is not None:
                log.info("Motion: %s", plan.description)
                return plan

            # Retry with correction hint on bad JSON
            if attempt < 2:
                log.warning("Retrying after bad JSON (attempt %d)", attempt + 1)
                messages.append({"role": "assistant", "content": raw})
                messages.append({
                    "role": "user",
                    "content": "Your previous response was not valid JSON. Return only the JSON object.",
                })
                continue

            log.error("LLM returned invalid JSON after retry: %.200s", raw)
            return None

        except Exception as exc:
            if not _is_rate_limited(exc):
                raise
            if attempt == 2:
                log.error("Rate limit hit — no more retries")
                raise
            wait = min(2 ** attempt, 16)
            log.warning("Rate limited — retrying in %d s", wait)
            await asyncio.sleep(wait)

    return None

