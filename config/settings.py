from __future__ import annotations

import os
from dataclasses import dataclass


def _get_env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_env_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _get_env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class AppSettings:
    llm_enabled: bool = False
    llm_api_key: str | None = None
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-chat"
    llm_mode: str = "async"

    llm_timeout_connect: float = 5.0
    llm_timeout_read: float = 60.0
    llm_timeout_stream_first: float = 10.0
    llm_timeout_stream_total: float = 120.0

    llm_retries: int = 2
    llm_retry_backoff_base: float = 0.5

    llm_temperature: float = 0.7
    llm_max_tokens: int = 512


def load_settings() -> AppSettings:
    return AppSettings(
        llm_enabled=_get_env_bool("LLM_ENABLED", False),
        llm_api_key=os.getenv("LLM_API_KEY"),
        llm_base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
        llm_model=os.getenv("LLM_MODEL", "deepseek-chat"),
        llm_mode=os.getenv("LLM_MODE", "async"),
        llm_timeout_connect=_get_env_float("LLM_TIMEOUT_CONNECT", 5.0),
        llm_timeout_read=_get_env_float("LLM_TIMEOUT_READ", 60.0),
        llm_timeout_stream_first=_get_env_float("LLM_TIMEOUT_STREAM_FIRST", 10.0),
        llm_timeout_stream_total=_get_env_float("LLM_TIMEOUT_STREAM_TOTAL", 120.0),
        llm_retries=_get_env_int("LLM_RETRIES", 2),
        llm_retry_backoff_base=_get_env_float("LLM_RETRY_BACKOFF_BASE", 0.5),
        llm_temperature=_get_env_float("LLM_TEMPERATURE", 0.7),
        llm_max_tokens=_get_env_int("LLM_MAX_TOKENS", 512),
    )