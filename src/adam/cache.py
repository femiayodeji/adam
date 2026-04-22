"""Simple LRU animation cache keyed by normalised command text."""
from __future__ import annotations

import hashlib
from collections import OrderedDict

from adam.models import AnimationResponse


class MotionCache:
    def __init__(self, capacity: int = 50) -> None:
        self._capacity = capacity
        self._store: OrderedDict[str, AnimationResponse] = OrderedDict()

    @staticmethod
    def _key(command: str) -> str:
        normalised = command.strip().lower()
        return hashlib.sha256(normalised.encode()).hexdigest()[:16]

    def get(self, command: str) -> AnimationResponse | None:
        key = self._key(command)
        if key not in self._store:
            return None
        self._store.move_to_end(key)   # mark as recently used
        return self._store[key]

    def put(self, command: str, plan: AnimationResponse) -> None:
        key = self._key(command)
        if key in self._store:
            self._store.move_to_end(key)
        elif len(self._store) >= self._capacity:
            self._store.popitem(last=False)   # evict LRU
        self._store[key] = plan

    def __len__(self) -> int:
        return len(self._store)
