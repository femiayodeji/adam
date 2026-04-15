from dataclasses import dataclass, field


@dataclass
class Session:
    id: str
    messages: list[dict] = field(default_factory=list)


@dataclass
class AppState:
    sessions: dict[str, Session] = field(default_factory=dict)
    active_session_id: str | None = None
    _session_counter: int = 0

    def next_session_id(self) -> str:
        self._session_counter += 1
        return f"session_{self._session_counter}"
