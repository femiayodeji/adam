"""LLM completion — async, streaming-aware, with retry and Pydantic validation.

Flow:
  complete_async(conversation) -> MotionPlan | None
    1. asyncio.to_thread (non-streaming) or litellm.acompletion (streaming)
    2. Strip code fences
    3. JSON parse — retry once on failure
    4. MotionPlan validation + rotation clamping
    5. Exponential backoff on RateLimitError (up to 3 attempts)

Streaming (LLM_STREAM=true):
    complete_streaming(conversation, on_token) yields tokens via callback and
    returns MotionPlan | None when complete.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable
from copy import deepcopy
from typing import Any, cast

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

    _apply_prompt_caching(kw)
    return kw


def _apply_prompt_caching(kw: dict) -> None:
    """Apply prompt-caching hints only where supported.

    Current support:
      - Anthropic/Claude message prefix caching via cache_control + beta header

    For unsupported providers this is a no-op.
    """
    if not config.llm.prompt_cache:
        return

    provider = config.llm.provider.lower()
    model = config.llm.model.lower()
    is_anthropic = "anthropic" in provider or "claude" in model
    if not is_anthropic:
        return

    original_messages = kw.get("messages")
    if not isinstance(original_messages, list) or not original_messages:
        return

    messages = deepcopy(original_messages)
    last_index = len(messages) - 1

    # Mark stable prefix content as cacheable; keep the final user turn uncached.
    for idx, msg in enumerate(messages):
        content = msg.get("content")
        if not isinstance(content, str):
            continue

        text_block: dict = {"type": "text", "text": content}
        if idx < last_index:
            text_block["cache_control"] = {"type": "ephemeral"}
        msg["content"] = [text_block]

    kw["messages"] = messages
    headers = kw.get("extra_headers") or {}
    headers["anthropic-beta"] = "prompt-caching-2024-07-31"
    kw["extra_headers"] = headers


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


async def complete_streaming(
    conversation: list[dict],
    on_token: Callable[[str], Awaitable[None]],
    last_description: str | None = None,
) -> MotionPlan | None:
    """Streaming completion. Calls on_token for each delta chunk.
    Returns a MotionPlan on success, None on failure."""
    messages = [
        {"role": "system", "content": build_system_prompt(last_description)},
        *conversation,
    ]
    kw = _llm_kwargs(messages)
    kw["stream"] = True

    accumulated = ""
    for attempt in range(3):
        try:
            stream = await litellm.acompletion(**kw)
            async for chunk in cast(Any, stream):
                delta = (chunk.choices[0].delta.content or "") if chunk.choices else ""  # type: ignore[union-attr]
                if delta:
                    accumulated += delta
                    await on_token(delta)
            break  # stream complete

        except Exception as exc:
            if not _is_rate_limited(exc):
                raise
            if attempt == 2:
                raise
            wait = min(2 ** attempt, 16)
            log.warning("Rate limited (streaming) — retrying in %d s", wait)
            await asyncio.sleep(wait)
            accumulated = ""

    raw = _strip_fences(accumulated)
    plan = _parse(raw)
    if plan:
        log.info("Streamed motion: %s", plan.description)
    else:
        log.error("Streaming produced invalid JSON: %.200s", raw)
    return plan

