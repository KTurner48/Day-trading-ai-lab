"""SQLAlchemy base, engine, session, and ORM models for the MVP."""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean, DateTime, Enum as SAEnum, ForeignKey, Integer, Numeric, String, Text, func,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import settings
from app.models.enums import (
    NotificationChannel, NotificationStatus, OrderSide, OrderStatus,
    SignalAction, SignalStatus, TradingMode,
)


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SystemSetting(Base):
    __tablename__ = "system_settings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    trading_mode: Mapped[TradingMode] = mapped_column(
        SAEnum(TradingMode, name="trading_mode"), default=TradingMode.PAPER
    )
    kill_switch_active: Mapped[bool] = mapped_column(Boolean, default=False)
    max_daily_loss_pct: Mapped[float] = mapped_column(Numeric(6, 2), default=2.0)
    max_drawdown_pct: Mapped[float] = mapped_column(Numeric(6, 2), default=10.0)
    default_risk_per_trade_pct: Mapped[float] = mapped_column(Numeric(6, 2), default=0.5)
    max_open_positions: Mapped[int] = mapped_column(Integer, default=3)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(60))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Instrument(Base):
    __tablename__ = "instruments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    symbol: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    contract_size: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("1"))


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("10000"))
    equity: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("10000"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Signal(Base):
    __tablename__ = "signals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id"))
    action: Mapped[SignalAction] = mapped_column(SAEnum(SignalAction, name="signal_action"))
    status: Mapped[SignalStatus] = mapped_column(
        SAEnum(SignalStatus, name="signal_status"),
        default=SignalStatus.PENDING_APPROVAL, index=True,
    )
    score: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float] = mapped_column(Numeric(5, 4), default=0.0)
    reasoning: Mapped[str | None] = mapped_column(Text)
    entry_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    stop_loss: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    take_profit: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    risk_reward: Mapped[float | None] = mapped_column(Numeric(8, 2))
    veto_reason: Mapped[str | None] = mapped_column(Text)
    strategy: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id"))
    signal_id: Mapped[str | None] = mapped_column(ForeignKey("signals.id"))
    client_order_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    broker_order_id: Mapped[str | None] = mapped_column(String(120))
    side: Mapped[OrderSide] = mapped_column(SAEnum(OrderSide, name="order_side"))
    status: Mapped[OrderStatus] = mapped_column(
        SAEnum(OrderStatus, name="order_status"), default=OrderStatus.PENDING
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    avg_fill_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Position(Base):
    __tablename__ = "positions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id"))
    side: Mapped[OrderSide] = mapped_column(SAEnum(OrderSide, name="order_side"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    avg_entry_price: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    status: Mapped[str] = mapped_column(String(12), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    channel: Mapped[NotificationChannel] = mapped_column(
        SAEnum(NotificationChannel, name="notification_channel")
    )
    status: Mapped[NotificationStatus] = mapped_column(
        SAEnum(NotificationStatus, name="notification_status"),
        default=NotificationStatus.QUEUED,
    )
    subject: Mapped[str | None] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20), default="admin")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


# ── Engine / session ────────────────────────────────────────
engine = create_async_engine(settings.DATABASE_URL, future=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
