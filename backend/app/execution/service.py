"""Execution: the ONLY order creator. Three gates: kill switch -> mode -> risk.
Paper broker only. A risk veto marks the signal rejected with a reason."""
from __future__ import annotations

import hashlib
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.brokers.base import BrokerInterface, BrokerOrder
from app.brokers.factory import BrokerFactory
from app.brokers.paper import PaperBroker
from app.core.audit import record_audit
from app.core.exceptions import KillSwitchActiveError
from app.core.settings_service import assert_trading_allowed, get_or_create_settings
from app.models.db import Account, Instrument, Order, Position, Signal
from app.models.enums import (
    OrderSide, OrderStatus, SignalAction, SignalStatus, TradingMode,
)

_EXECUTABLE = {
    TradingMode.PAPER: {SignalStatus.SIMULATED},
    TradingMode.LIVE_MANUAL_APPROVAL: {SignalStatus.APPROVED},
    TradingMode.LIVE_AUTO: {SignalStatus.APPROVED},
}


def make_client_order_id(signal_id: str, account_id: str) -> str:
    raw = f"{signal_id}:{account_id}".encode()
    return "coid_" + hashlib.sha256(raw).hexdigest()[:32]


def _validate_and_size(signal: Signal, balance: Decimal, risk_pct: Decimal,
                       contract_size: Decimal) -> tuple[Decimal | None, str | None]:
    entry, stop, tp = signal.entry_price, signal.stop_loss, signal.take_profit
    if stop is None or tp is None or entry is None:
        return None, "missing entry/stop/take_profit"
    if signal.action == SignalAction.BUY and stop >= entry:
        return None, "stop_loss must be below entry for a long"
    if signal.action == SignalAction.SELL and stop <= entry:
        return None, "stop_loss must be above entry for a short"
    risk = abs(entry - stop)
    reward = abs(tp - entry)
    if risk <= 0:
        return None, "zero risk distance"
    rr = reward / risk
    if rr < Decimal("1.0"):
        return None, f"risk_reward {rr:.2f} below minimum 1.0"
    risk_amount = balance * risk_pct / Decimal("100")
    qty = risk_amount / (risk * contract_size)
    if qty < Decimal("0.0001"):
        return None, f"computed quantity {qty} below minimum"
    return qty.quantize(Decimal("0.00000001")), None


class ExecutionService:
    def __init__(self, broker: BrokerInterface | None = None) -> None:
        self.broker = broker or PaperBroker()
        # Hard guard: execution may ONLY use an order-capable (paper) broker.
        if not BrokerFactory.is_order_capable(self.broker.broker_type):
            raise ValueError(
                f"Execution refuses non-order-capable broker "
                f"'{self.broker.broker_type.value}'; only paper may place orders"
            )

    def is_executable(self, mode: TradingMode, status: SignalStatus) -> bool:
        return status in _EXECUTABLE.get(mode, set())

    async def execute_signal(self, db: AsyncSession, signal: Signal) -> Order | None:
        cfg = await get_or_create_settings(db)

        # GATE 1: kill switch
        try:
            await assert_trading_allowed(db)
        except KillSwitchActiveError:
            await record_audit(db, action="ORDER_BLOCKED_KILL_SWITCH",
                               entity_type="signal", entity_id=signal.id,
                               detail={"action": signal.action.value})
            return None

        # GATE 2: mode executability
        if not self.is_executable(cfg.trading_mode, signal.status):
            return None

        account = (await db.execute(
            select(Account).where(Account.is_active.is_(True)).limit(1)
        )).scalar_one_or_none()
        if account is None or signal.entry_price is None:
            return None

        inst = (await db.execute(
            select(Instrument).where(Instrument.id == signal.instrument_id)
        )).scalar_one_or_none()
        contract_size = inst.contract_size if inst else Decimal("1")

        # GATE 3: risk veto
        qty, veto = _validate_and_size(
            signal, account.balance, Decimal(str(cfg.default_risk_per_trade_pct)),
            contract_size,
        )
        if veto is not None:
            signal.status = SignalStatus.REJECTED
            signal.veto_reason = veto
            await record_audit(db, action="SIGNAL_VETOED", entity_type="signal",
                               entity_id=signal.id, detail={"reason": veto})
            return None

        # Idempotent order
        coid = make_client_order_id(signal.id, account.id)
        existing = (await db.execute(
            select(Order).where(Order.client_order_id == coid)
        )).scalar_one_or_none()
        if existing is not None:
            return None

        side = OrderSide.BUY if signal.action == SignalAction.BUY else OrderSide.SELL
        order = Order(account_id=account.id, instrument_id=signal.instrument_id,
                      signal_id=signal.id, client_order_id=coid, side=side,
                      status=OrderStatus.PENDING, quantity=qty)
        db.add(order)
        await db.flush()
        await record_audit(db, action="ORDER_SUBMITTED", entity_type="order",
                           entity_id=order.id, detail={"qty": str(qty)})

        broker_order = BrokerOrder(client_order_id=coid, symbol=inst.symbol if inst else "",
                                   side=side, quantity=qty)
        fill = await self.broker.place_order(broker_order, reference_price=signal.entry_price)

        if fill.status == "filled":
            order.status = OrderStatus.FILLED
            order.broker_order_id = fill.broker_order_id
            order.avg_fill_price = fill.avg_fill_price
            pos = Position(account_id=account.id, instrument_id=signal.instrument_id,
                           side=side, quantity=fill.filled_quantity,
                           avg_entry_price=fill.avg_fill_price, status="open")
            db.add(pos)
            signal.status = SignalStatus.EXECUTED
            await record_audit(db, action="ORDER_FILLED", entity_type="order",
                               entity_id=order.id,
                               detail={"price": str(fill.avg_fill_price)})
        else:
            order.status = OrderStatus.REJECTED
            await record_audit(db, action="ORDER_REJECTED", entity_type="order",
                               entity_id=order.id, detail={})
        await db.flush()
        return order
