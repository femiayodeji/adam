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


@dataclass
class Config:
    llm: LLMConfig


def load_config() -> Config:
    return Config(
        llm=LLMConfig(
            provider=os.environ.get("LLM_PROVIDER", "gemini"),
            model=os.environ.get("LLM_MODEL", "gemini/gemini-2.0-flash"),
            api_key=os.environ.get("LLM_API_KEY", ""),
        ),
    )


config = load_config()
