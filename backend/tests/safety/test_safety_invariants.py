"""FINAL SAFETY CHECKLIST (MVP) — executable. Run: pytest tests/safety -q"""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.brokers.base import BrokerOrder
from app.brokers.factory import BrokerFactory
from app.core.exceptions import LiveOrderingNotEnabledError
from app.core.settings_service import (
    get_or_create_settings, set_kill_switch, set_trading_mode,
)
from app.execution.service import ExecutionService
from app.models.db import Account, Instrument, Order, Signal, SystemSetting
from app.models.enums import (
    BrokerType, NotificationChannel, NotificationStatus, OrderSide,
    SignalAction, SignalStatus, TradingMode,
)
from app.notifications import NotificationDispatcher
from app.strategies.runner import status_for_mode

pytestmark = pytest.mark.asyncio


async def _seed(db, mode=TradingMode.PAPER):
    inst = Instrument(symbol="XAU_USD", display_name="Gold", contract_size=Decimal("1"))
    db.add(inst)
    acct = Account(currency="USD", balance=Decimal("10000"), equity=Decimal("10000"))
    db.add(acct)
    await db.flush()
    await set_trading_mode(db, mode)
    return inst, acct


def _signal(inst, status=SignalStatus.SIMULATED):
    return Signal(instrument_id=inst.id, action=SignalAction.BUY, status=status,
                  score=75, confidence=0.7, entry_price=Decimal("2350"),
                  stop_loss=Decimal("2340"), take_profit=Decimal("2370"),
                  risk_reward=2.0, strategy="trend_following")


async def test_01_paper_mode_is_default(db):
    cfg = await get_or_create_settings(db)
    assert cfg.trading_mode == TradingMode.PAPER


@pytest.mark.parametrize("bt", BrokerFactory.live_broker_types())
async def test_02_live_order_placement_disabled(bt):
    broker = BrokerFactory.create(bt)
    order = BrokerOrder(client_order_id="c", symbol="XAU_USD", side=OrderSide.BUY,
                        quantity=Decimal("1"))
    with pytest.raises(LiveOrderingNotEnabledError):
        await broker.place_order(order, reference_price=Decimal("2350"))


def test_03_paper_is_only_order_capable():
    assert BrokerFactory.is_order_capable(BrokerType.PAPER) is True
    for bt in BrokerFactory.live_broker_types():
        assert BrokerFactory.is_order_capable(bt) is False


async def test_04_kill_switch_blocks_orders(db):
    inst, _ = await _seed(db)
    await set_kill_switch(db, True, reason="drill")
    sig = _signal(inst)
    db.add(sig); await db.flush()
    order = await ExecutionService().execute_signal(db, sig)
    assert order is None
    assert (await db.execute(select(Order))).scalars().first() is None


async def test_05_kill_switch_suppresses_emission(db):
    from app.market_data.simulated import SimulatedGoldFeed
    from app.strategies.runner import StrategyRunner
    from app.strategies.trend_following import TrendFollowingStrategy
    inst, _ = await _seed(db, mode=TradingMode.LIVE_AUTO)
    await set_kill_switch(db, True, reason="halt")
    bars = SimulatedGoldFeed(seed=1).generate_bars("XAU_USD", 80)
    runner = StrategyRunner([TrendFollowingStrategy(ema_fast=5, ema_slow=15, atr_period=5)])
    created = await runner.run_once(db, "XAU_USD", bars)
    assert created == []
    assert (await db.execute(select(Signal))).scalars().all() == []


@pytest.mark.parametrize("bt", BrokerFactory.live_broker_types())
async def test_06_live_stubs_refuse_place_order(bt):
    stub = BrokerFactory.create_live_stub(bt)
    with pytest.raises(LiveOrderingNotEnabledError):
        await stub.place_order(
            BrokerOrder(client_order_id="c", symbol="XAU_USD", side=OrderSide.BUY,
                        quantity=Decimal("1")),
            reference_price=Decimal("2350"))


async def test_08_notifications_log_only_by_default(db):
    for channel in NotificationChannel:
        n = await NotificationDispatcher().dispatch(db, channel=channel, body="x")
        assert n.status == NotificationStatus.SENT
        assert n.last_error == "log_only:not_configured"


def test_09_mode_status_mapping():
    assert status_for_mode(TradingMode.PAPER) == SignalStatus.SIMULATED
    assert status_for_mode(TradingMode.LIVE_MANUAL_APPROVAL) == SignalStatus.PENDING_APPROVAL
    assert status_for_mode(TradingMode.LIVE_AUTO) == SignalStatus.APPROVED


@pytest.mark.parametrize("bt", BrokerFactory.live_broker_types())
def test_10_execution_refuses_live_broker(bt):
    with pytest.raises(ValueError):
        ExecutionService(broker=BrokerFactory.create(bt))


async def test_11_rejected_signal_never_executes(db):
    inst, _ = await _seed(db)
    sig = _signal(inst, status=SignalStatus.REJECTED)
    db.add(sig); await db.flush()
    assert await ExecutionService().execute_signal(db, sig) is None


async def test_12_settings_singleton(db):
    a = await get_or_create_settings(db)
    b = await get_or_create_settings(db)
    assert a.id == b.id
    rows = (await db.execute(select(SystemSetting))).scalars().all()
    assert len(rows) == 1


async def test_13_paper_mode_places_paper_order(db):
    inst, _ = await _seed(db)
    sig = _signal(inst)
    db.add(sig); await db.flush()
    order = await ExecutionService().execute_signal(db, sig)
    assert order is not None
    assert order.broker_order_id.startswith("PAPER-")
    assert sig.status == SignalStatus.EXECUTED


async def test_14_risk_veto_marks_signal_rejected(db):
    inst, _ = await _seed(db)
    sig = _signal(inst)
    sig.stop_loss = Decimal("2360")  # invalid for a long => veto
    db.add(sig); await db.flush()
    order = await ExecutionService().execute_signal(db, sig)
    assert order is None
    assert sig.status == SignalStatus.REJECTED
    assert sig.veto_reason is not None
