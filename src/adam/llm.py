import json
import logging
import re

import litellm

from adam.config import config
from adam.prompt import SYSTEM_PROMPT

log = logging.getLogger("adam.llm")

_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?\s*```$", re.DOTALL)


def _strip_code_fences(text: str) -> str:
    m = _FENCE_RE.match(text.strip())
    return m.group(1).strip() if m else text


def complete(conversation: list[dict]) -> dict:
    """Returns {"ok": True, "motion": ..., "raw": ...} on success,
    or {"ok": False, "error": ..., "raw": ...} on failure.
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *conversation]
    response = litellm.completion(
        model=config.llm.model,
        api_key=config.llm.api_key,
        max_tokens=2048,
        messages=messages,
    )
    raw = (response.choices[0].message.content or "").strip()  # type: ignore[union-attr]
    raw = _strip_code_fences(raw)

    try:
        parsed = json.loads(raw)
        log.info("Motion: %s", parsed.get("description", "?"))
        return {"ok": True, "motion": parsed, "raw": raw}
    except json.JSONDecodeError:
        log.error("LLM returned invalid JSON: %.200s", raw)
        return {"ok": False, "error": "LLM returned invalid JSON", "raw": raw}
