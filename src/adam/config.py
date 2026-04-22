import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


@dataclass
class LLMConfig:
    provider: str
    model: str
    api_key: str
    base_url: str | None
    stream: bool
    prompt_cache: bool
    temperature: float
    max_tokens: int
    timeout_s: int


@dataclass
class HistoryConfig:
    history_dir: Path | None
    persistent: bool
    max_history_tokens: int
    max_history_messages: int
    max_message_chars: int


@dataclass
class CacheConfig:
    enabled: bool
    capacity: int


@dataclass
class Config:
    llm: LLMConfig
    history: HistoryConfig
    cache: CacheConfig


def _env_bool(key: str, default: bool) -> bool:
    return os.environ.get(key, str(default)).lower() in ("1", "true", "yes")


def load_config() -> Config:
    raw_dir = os.environ.get("HISTORY_DIR")
    provider = os.environ.get("LLM_PROVIDER", "gemini")
    return Config(
        llm=LLMConfig(
            provider=provider,
            model=os.environ.get("LLM_MODEL", "gemini/gemini-2.0-flash"),
            api_key=os.environ.get("LLM_API_KEY", ""),
            base_url=os.environ.get("LLM_BASE_URL") or None,
            stream=_env_bool("LLM_STREAM", False),
            prompt_cache=_env_bool("LLM_PROMPT_CACHE", True),
            temperature=float(os.environ.get("LLM_TEMPERATURE", "0.4")),
            max_tokens=int(os.environ.get("LLM_MAX_TOKENS", "768")),
            timeout_s=int(os.environ.get("LLM_TIMEOUT_S", "30")),
        ),
        history=HistoryConfig(
            history_dir=Path(raw_dir) if raw_dir else None,
            persistent=_env_bool("HISTORY_PERSIST", False),
            max_history_tokens=int(os.environ.get("HISTORY_MAX_TOKENS", "1200")),
            max_history_messages=int(os.environ.get("HISTORY_MAX_MESSAGES", "8")),
            max_message_chars=int(os.environ.get("HISTORY_MESSAGE_MAX_CHARS", "180")),
        ),
        cache=CacheConfig(
            enabled=_env_bool("MOTION_CACHE", True),
            capacity=int(os.environ.get("MOTION_CACHE_SIZE", "50")),
        ),
    )


config = load_config()
