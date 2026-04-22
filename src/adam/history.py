"""Session history — per-connection, with optional file persistence.

HistoryStore protocol has two implementations:
  MemoryStore  — in-process dict, resets on restart (default)
  FileStore    — appends JSONL to HISTORY_DIR/{session_id}.jsonl

Context passed to the LLM is token-budgeted (rolling window).
The full LLM JSON is stored in Message.motion_summary but only the
description string is sent back to the LLM, reducing token usage ~90%.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from adam.models import Message


# ── Store protocol ────────────────────────────────────────────────────────────

class HistoryStore(Protocol):
    def load(self, session_id: str) -> list[Message]: ...
    def append(self, session_id: str, msg: Message) -> None: ...
    def delete(self, session_id: str) -> None: ...
    def session_ids(self) -> list[str]: ...


class MemoryStore:
    def __init__(self) -> None:
        self._store: dict[str, list[Message]] = {}

    def load(self, session_id: str) -> list[Message]:
        return list(self._store.get(session_id, []))

    def append(self, session_id: str, msg: Message) -> None:
        self._store.setdefault(session_id, []).append(msg)

    def delete(self, session_id: str) -> None:
        self._store.pop(session_id, None)

    def session_ids(self) -> list[str]:
        return list(self._store.keys())


class FileStore:
    def __init__(self, directory: Path) -> None:
        self._dir = directory
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        return self._dir / f"{session_id}.jsonl"

    def load(self, session_id: str) -> list[Message]:
        p = self._path(session_id)
        if not p.exists():
            return []
        messages: list[Message] = []
        with p.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    messages.append(Message(**d))
                except Exception:
                    pass
        return messages

    def append(self, session_id: str, msg: Message) -> None:
        with self._path(session_id).open("a") as f:
            f.write(json.dumps({
                "role": msg.role,
                "content": msg.content,
                "motion_summary": msg.motion_summary,
                "timestamp": msg.timestamp,
            }) + "\n")

    def delete(self, session_id: str) -> None:
        p = self._path(session_id)
        if p.exists():
            p.unlink()

    def session_ids(self) -> list[str]:
        return [f.stem for f in self._dir.glob("*.jsonl")]


# ── Context window builder ────────────────────────────────────────────────────

def _compact_text(text: str, max_chars: int) -> str:
    compact = " ".join(text.split())
    if max_chars <= 0 or len(compact) <= max_chars:
        return compact
    # Preserve intent while preventing long turns from bloating context.
    return compact[: max_chars - 1].rstrip() + "…"


def build_context(
    messages: list[Message],
    max_tokens: int,
    max_messages: int,
    max_message_chars: int,
) -> list[dict]:
    """Return compact, recent messages that fit in the history budget."""
    recent = messages[-max_messages:] if max_messages > 0 else list(messages)

    compacted: list[tuple[dict, int]] = []
    for msg in recent:
        content = _compact_text(msg.content, max_message_chars)
        if not content:
            continue
        token_estimate = max(1, len(content) // 4)
        compacted.append(({"role": msg.role, "content": content}, token_estimate))

    budget = max_tokens
    result: list[dict] = []
    for msg, token_estimate in reversed(compacted):
        if token_estimate > budget:
            break
        budget -= token_estimate
        result.append(msg)

    return list(reversed(result))

