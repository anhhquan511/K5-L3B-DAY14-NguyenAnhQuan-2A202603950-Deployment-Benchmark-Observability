"""
Config — 12-Factor: mọi cấu hình đọc từ biến môi trường.
"""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv(override=False)


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass
class Settings:
    port: int = _get_int("PORT", 8000)
    environment: str = os.getenv("ENVIRONMENT", "development")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    agent_api_key: str = os.getenv("AGENT_API_KEY", "")
    redis_url: str = os.getenv("REDIS_URL", "")
    rate_limit_per_minute: int = _get_int("RATE_LIMIT_PER_MINUTE", 10)
    daily_budget_usd: float = _get_float("DAILY_BUDGET_USD", 10.0)
    monthly_budget_usd: float = _get_float("MONTHLY_BUDGET_USD", 10.0)


settings = Settings()
