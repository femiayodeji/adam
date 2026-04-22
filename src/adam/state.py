from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field


@dataclass
class Session:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    # asyncio Task for the current in-flight LLM call.
    active_task: asyncio.Task | None = field(default=None, repr=False, compare=False)
    # Backend queue depth-1 to smooth command bursts.
    current_command: str | None = None
    pending_command: str | None = None
    pending_msg_id: str | None = None

