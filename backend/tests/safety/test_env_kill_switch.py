"""Env-level hard stop (GLOBAL_KILL_SWITCH) — dedicated MVP safety tests.

Prove the ENV kill switch blocks trading BY ITSELF with the DB switch FALSE.
They SKIP unless GLOBAL_KILL_SWITCH=true is loaded, so they never produce a
false green. verify_phase15.sh Step 5 sets the env true and runs this file.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.config import settings
from app.core.settings_service import get_or_create_settings, set_trading_mode
from app.execution.service import ExecutionService
from app.market_data.simulated import SimulatedGoldFeed
from app.models.db import Account, AuditLog, Instrument, Order, Signal, SystemSetting
from app.models.enums import SignalAction, SignalStatus, TradingMode
from app.strategies.runner import StrategyRunner
from app.strategies.trend_following import TrendFollowingStrategy

pytestmark = pytest.mark.asyncio

requires_env_kill = pytest.mark.skipif(
    not settings.GLOBAL_KILL_SWITCH,
    reason="GLOBAL_KILL_SWITCH not true in this process; env hard-stop assertions "
           "are only valid when it is. Step 5 of verify_phase15.sh sets it true.",
)


async def _seed(db, mode):
    inst = Instrument(symbol="XAU_USD", display_name="Gold", contract_size=Decimal("1"))
    db.add(inst)
    db.add(Account(currency="USD", balance=Decimal("10000"), equity=Decimal("10000")))
    await db.flush()
    await set_trading_mode(db, mode)
    return inst


def _signal(inst):
    return Signal(instrument_id=inst.id, action=SignalAction.BUY,
                  status=SignalStatus.SIMULATED, score=75, confidence=0.7,
                  entry_price=Decimal("2350"), stop_loss=Decimal("2340"),
                  take_profit=Decimal("2370"), risk_reward=2.0, strategy="trend_following")


async def _assert_db_switch_false(db) -> SystemSetting:
    row = await get_or_create_settings(db)
    assert row.kill_switch_active is False, "DB kill switch must be FALSE for env-only test"
    return row


@requires_env_kill
async def test_env_kill_switch_blocks_orders_without_db_kill_switch(db):
    inst = await _seed(db, TradingMode.PAPER)
    row = await _assert_db_switch_false(db)
    assert settings.GLOBAL_KILL_SWITCH is True
    sig = _signal(inst)
    db.add(sig); await db.flush()
    order = await ExecutionService().execute_signal(db, sig)
    assert order is None
    assert (await db.execute(select(Order))).scalars().first() is None
    actions = {a.action for a in (await db.execute(select(AuditLog))).scalars().all()}
    assert "ORDER_BLOCKED_KILL_SWITCH" in actions
    assert row.kill_switch_active is False


@requires_env_kill
async def test_env_kill_switch_suppresses_emission_without_db_kill_switch(db):
    inst = await _seed(db, TradingMode.LIVE_AUTO)
    await _assert_db_switch_false(db)
    assert settings.GLOBAL_KILL_SWITCH is True
    bars = SimulatedGoldFeed(seed=1).generate_bars("XAU_USD", 80)
    runner = StrategyRunner([TrendFollowingStrategy(ema_fast=5, ema_slow=15, atr_period=5)])
    created = await runner.run_once(db, "XAU_USD", bars)
    assert created == []
    assert (await db.execute(select(Signal))).scalars().all() == []


@pytest.mark.skipif(settings.GLOBAL_KILL_SWITCH,
                    reason="env kill switch engaged; cannot show execution while halted")
async def test_signal_executes_when_neither_kill_switch_is_active(db):
    inst = await _seed(db, TradingMode.PAPER)
    await _assert_db_switch_false(db)
    assert settings.GLOBAL_KILL_SWITCH is False
    sig = _signal(inst)
    db.add(sig); await db.flush()
    order = await ExecutionService().execute_signal(db, sig)
    assert order is not None
    assert order.broker_order_id.startswith("PAPER-")
    assert sig.status == SignalStatus.EXECUTED
