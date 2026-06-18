"""SAFETY: OANDA market data must NOT affect order execution or live-order
refusal. These tests prove the data source is orthogonal to the broker layer.

Phase 16 added market data only. The invariants here guard against scope creep:
no matter how prices are sourced, execution stays paper-only and live brokers
still refuse place_order.
"""
from __future__ import annotations

import importlib
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

import app.config as config_module
from app.brokers.base import BrokerOrder
from app.brokers.factory import BrokerFactory
from app.core.exceptions import LiveOrderingNotEnabledError
from app.core.settings_service import set_trading_mode
from app.execution.service import ExecutionService
from app.market_data.oanda import parse_stream_message
from app.models.db import Account, Instrument, Order, Signal
from app.models.enums import (
    BrokerType, OrderSide, SignalAction, SignalStatus, TradingMode,
)

pytestmark = pytest.mark.asyncio


def _configure_oanda(monkeypatch):
    """Turn ON OANDA market data for this process, then reload config."""
    monkeypatch.setenv("OANDA_API_KEY", "test_key")
    monkeypatch.setenv("OANDA_ACCOUNT_ID", "test_acct")
    monkeypatch.setenv("OANDA_DATA_SYMBOLS", "XAU_USD")
    importlib.reload(config_module)


def _reset_config():
    importlib.reload(config_module)


async def _seed(db):
    inst = Instrument(symbol="XAU_USD", display_name="Gold", contract_size=Decimal("1"))
    db.add(inst)
    db.add(Account(currency="USD", balance=Decimal("10000"), equity=Decimal("10000")))
    await db.flush()
    await set_trading_mode(db, TradingMode.PAPER)
    return inst


def _oanda_price_tick():
    """A realistic OANDA PRICE frame -> Tick, used as the 'data source'."""
    line = (
        '{"type":"PRICE","instrument":"XAU_USD",'
        '"time":"2026-06-18T13:45:30.123Z",'
        '"bids":[{"price":"2351.20"}],"asks":[{"price":"2351.40"}]}'
    )
    return parse_stream_message(line)


async def test_oanda_sourced_price_still_executes_via_paper_only(db, monkeypatch):
    """Even with OANDA configured and an OANDA-sourced entry price, execution
    fills through the PAPER broker (PAPER- id), never a live one."""
    _configure_oanda(monkeypatch)
    try:
        inst = await _seed(db)
        tick = _oanda_price_tick()
        assert tick is not None and tick.source == "oanda"

        sig = Signal(instrument_id=inst.id, action=SignalAction.BUY,
                     status=SignalStatus.SIMULATED, score=80, confidence=0.8,
                     entry_price=tick.mid, stop_loss=tick.mid - Decimal("10"),
                     take_profit=tick.mid + Decimal("20"), risk_reward=2.0,
                     strategy="trend_following")
        db.add(sig)
        await db.flush()

        order = await ExecutionService().execute_signal(db, sig)
        assert order is not None
        assert order.broker_order_id.startswith("PAPER-")  # paper, not OANDA
        assert sig.status == SignalStatus.EXECUTED
    finally:
        _reset_config()


async def test_oanda_configured_does_not_make_live_broker_order_capable(db, monkeypatch):
    """Configuring OANDA *market data* must not flip any live broker to
    order-capable, and execution must still refuse a live broker."""
    _configure_oanda(monkeypatch)
    try:
        assert BrokerFactory.is_order_capable(BrokerType.OANDA) is False
        for bt in BrokerFactory.live_broker_types():
            assert BrokerFactory.is_order_capable(bt) is False
        with pytest.raises(ValueError):
            ExecutionService(broker=BrokerFactory.create(BrokerType.OANDA))
    finally:
        _reset_config()


async def test_oanda_broker_still_refuses_place_order_with_data_configured(db, monkeypatch):
    """The OANDA *broker* stub still refuses place_order even when OANDA market
    data is configured. Data and ordering are separate code paths."""
    _configure_oanda(monkeypatch)
    try:
        stub = BrokerFactory.create_live_stub(BrokerType.OANDA)
        with pytest.raises(LiveOrderingNotEnabledError):
            await stub.place_order(
                BrokerOrder(client_order_id="c", symbol="XAU_USD",
                            side=OrderSide.BUY, quantity=Decimal("1")),
                reference_price=Decimal("2351.30"))
    finally:
        _reset_config()


async def test_no_orders_created_from_parsing_oanda_data(db, monkeypatch):
    """Parsing OANDA market data must never, by itself, create Order rows."""
    _configure_oanda(monkeypatch)
    try:
        await _seed(db)
        for _ in range(5):
            tick = _oanda_price_tick()
            assert tick is not None
        # Parsing ticks does not touch the orders table.
        assert (await db.execute(select(Order))).scalars().all() == []
    finally:
        _reset_config()
