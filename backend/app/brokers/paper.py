"""Paper broker — the ONLY order-capable adapter. Deterministic local fills."""
from __future__ import annotations

from decimal import Decimal

from app.brokers.base import BrokerFill, BrokerInterface, BrokerOrder
from app.models.enums import BrokerType, OrderSide

_SLIPPAGE_BPS = Decimal("1")


class PaperBroker(BrokerInterface):
    broker_type = BrokerType.PAPER
    is_live = False

    def __init__(self) -> None:
        self._counter = 0

    async def place_order(self, order: BrokerOrder, *, reference_price: Decimal) -> BrokerFill:
        self._counter += 1
        slip = reference_price * (_SLIPPAGE_BPS / Decimal("10000"))
        fill = reference_price + slip if order.side == OrderSide.BUY else reference_price - slip
        return BrokerFill(
            client_order_id=order.client_order_id,
            broker_order_id=f"PAPER-{self._counter:08d}",
            filled_quantity=order.quantity,
            avg_fill_price=fill.quantize(Decimal("0.00001")),
            status="filled",
        )
