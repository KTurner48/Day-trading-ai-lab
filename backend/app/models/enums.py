"""Domain enumerations (string-valued)."""
from __future__ import annotations

from enum import Enum


class TradingMode(str, Enum):
    PAPER = "paper"
    LIVE_MANUAL_APPROVAL = "live_manual_approval"
    LIVE_AUTO = "live_auto"


class BrokerType(str, Enum):
    PAPER = "paper"
    OANDA = "oanda"
    ALPACA = "alpaca"
    IBKR = "ibkr"
    TRADOVATE = "tradovate"
    MT5 = "mt5"


class SignalAction(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class SignalStatus(str, Enum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    SIMULATED = "simulated"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    PENDING = "pending"
    FILLED = "filled"
    REJECTED = "rejected"


class NotificationChannel(str, Enum):
    EMAIL = "email"
    SMS = "sms"
    DISCORD = "discord"
    TELEGRAM = "telegram"


class NotificationStatus(str, Enum):
    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"
