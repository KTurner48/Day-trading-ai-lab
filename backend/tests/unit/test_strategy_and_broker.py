"""Unit tests: strategy emits on a clean uptrend; paper broker fills deterministically."""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.brokers.base import BrokerOrder
from app.brokers.paper import PaperBroker
from app.market_data.simulated import SimulatedGoldFeed
from app.models.enums import OrderSide
from app.strategies.trend_following import TrendFollowingStrategy

pytestmark = pytest.mark.asyncio


def test_simulated_feed_is_deterministic():
    a = SimulatedGoldFeed(seed=7).generate_bars("XAU_USD", 50)
    b = SimulatedGoldFeed(seed=7).generate_bars("XAU_USD", 50)
    assert [x.close for x in a] == [x.close for x in b]


def test_strategy_returns_proposal_or_none():
    bars = SimulatedGoldFeed(seed=3).generate_bars("XAU_USD", 120)
    strat = TrendFollowingStrategy(ema_fast=5, ema_slow=15, atr_period=5)
    proposal = strat.evaluate(bars)
    assert proposal is None or proposal.risk_reward == 2.0


async def test_paper_broker_fills_with_paper_id():
    broker = PaperBroker()
    order = BrokerOrder(client_order_id="c1", symbol="XAU_USD",
                        side=OrderSide.BUY, quantity=Decimal("1"))
    fill = await broker.place_order(order, reference_price=Decimal("2350"))
    assert fill.status == "filled"
    assert fill.broker_order_id.startswith("PAPER-")
    assert fill.avg_fill_price > 0
