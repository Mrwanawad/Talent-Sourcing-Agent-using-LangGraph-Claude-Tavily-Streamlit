"""Settings from env / .env / Streamlit secrets."""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # auto: Anthropic when its key is set, else Gemini, else rule-based fallbacks
    llm_provider: str = "auto"  # auto | anthropic | gemini
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-5-5"
    claude_fast_model: str = "claude-haiku-5-5"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.1-flash-lite"
    gemini_fast_model: str = "gemini-3.1-flash-lite"
    # requests per minute; free tier allows 15 for flash-lite (0 = no throttle)
    gemini_rpm: int = 14
    # USD per 1M tokens for models missing from llm.PRICING (0 = unknown)
    llm_price_in: float = 0.0
    llm_price_out: float = 0.0

    tavily_api_key: str = ""
    exa_api_key: str = ""
    # free DuckDuckGo search when no Tavily key
    use_ddg: bool = True

    embedding_model: str = "BAAI/bge-m3"
    use_embeddings: bool = False  # True needs requirements-embeddings.txt

    database_url: str = "sqlite:///talent_agent.db"
    ats_csv_path: str = ""

    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    use_playwright: bool = True
    max_pages: int = 40
    request_timeout: int = 20

    # weight of embedding similarity vs LLM judge before calibration
    embedding_weight: float = 0.3


def _load_streamlit_secrets() -> None:
    """Copy Streamlit secrets into env so pydantic-settings picks them up."""
    try:
        import streamlit as st

        for key, value in st.secrets.items():
            if isinstance(value, str | int | float | bool):
                os.environ.setdefault(key.upper(), str(value))
    except Exception:
        pass


@lru_cache
def get_settings() -> Settings:
    _load_streamlit_secrets()
    return Settings()
