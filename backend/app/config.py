"""Typed, env-driven configuration. Safe paper defaults.

DATABASE_URL defaults to local SQLite so tests and `pytest` run with zero
infra, but in Docker it is set to PostgreSQL/TimescaleDB via .env. Both work:
the ORM and migrations are written portably.
"""
from __future__ import annotations

import os

from app.models.enums import TradingMode


def _bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _csv(name: str, default: list[str]) -> list[str]:
    val = os.environ.get(name)
    if not val:
        return default
    return [v.strip() for v in val.split(",") if v.strip()]


class Settings:
    def __init__(self) -> None:
        self.APP_ENV = os.environ.get("APP_ENV", "development")
        self.SECRET_KEY = os.environ.get("SECRET_KEY", "dev_secret_key_change_me_please")
        self.DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./gtp.db")
        self.REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

        # Auth
        self.JWT_ALGORITHM = "HS256"
        self.ACCESS_TOKEN_EXPIRE_MINUTES = int(
            os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "1440")
        )
        self.ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@local")
        self.ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")

        # CORS
        self.CORS_ORIGINS = _csv("CORS_ORIGINS", ["http://localhost:5173"])

        # Trading safety
        self.TRADING_MODE = TradingMode(os.environ.get("TRADING_MODE", "paper"))
        self.GLOBAL_KILL_SWITCH = _bool("GLOBAL_KILL_SWITCH", False)
        self.MAX_DAILY_LOSS_PCT = float(os.environ.get("MAX_DAILY_LOSS_PCT", "2.0"))
        self.MAX_DRAWDOWN_PCT = float(os.environ.get("MAX_DRAWDOWN_PCT", "10.0"))
        self.DEFAULT_RISK_PER_TRADE_PCT = float(
            os.environ.get("DEFAULT_RISK_PER_TRADE_PCT", "0.5")
        )
        self.MAX_OPEN_POSITIONS = int(os.environ.get("MAX_OPEN_POSITIONS", "3"))

        # OANDA market data ONLY (Phase 16). These never enable order placement;
        # they gate whether the OANDA *price stream* is used for XAU_USD.
        self.OANDA_API_KEY = os.environ.get("OANDA_API_KEY", "")
        self.OANDA_ACCOUNT_ID = os.environ.get("OANDA_ACCOUNT_ID", "")
        # practice | live  — refers to OANDA's pricing host, NOT our trading mode.
        self.OANDA_ENV = os.environ.get("OANDA_ENV", "practice")
        # Symbols OANDA is allowed to supply market data for. XAU_USD only by default.
        self.OANDA_DATA_SYMBOLS = _csv("OANDA_DATA_SYMBOLS", ["XAU_USD"])

    @property
    def oanda_market_data_configured(self) -> bool:
        """True only when both OANDA credentials are present. Market data only —
        this has no bearing on order placement, which stays disabled in code."""
        return bool(self.OANDA_API_KEY and self.OANDA_ACCOUNT_ID)

    @property
    def is_live_trading(self) -> bool:
        return self.TRADING_MODE in {
            TradingMode.LIVE_MANUAL_APPROVAL,
            TradingMode.LIVE_AUTO,
        }

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")


settings = Settings()
