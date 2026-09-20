from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw else default


@dataclass(slots=True)
class Settings:
    db_path: Path = field(
        default_factory=lambda: Path(os.getenv("MONEY_AGENT_DB", "data/money_agent.db"))
    )
    min_budget_usd: float = field(
        default_factory=lambda: _float_env("MONEY_AGENT_MIN_BUDGET_USD", 20.0)
    )
    github_token: str | None = field(default_factory=lambda: os.getenv("GITHUB_TOKEN"))
    github_min_stars: int = field(
        default_factory=lambda: int(os.getenv("MONEY_AGENT_GITHUB_MIN_STARS", "10"))
    )
    github_min_age_days: int = field(
        default_factory=lambda: int(os.getenv("MONEY_AGENT_GITHUB_MIN_AGE_DAYS", "180"))
    )
    llm_api_key: str | None = field(default_factory=lambda: os.getenv("LLM_API_KEY"))
    llm_base_url: str = field(
        default_factory=lambda: os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    )
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "gpt-5-mini"))
