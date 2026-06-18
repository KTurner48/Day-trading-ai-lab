"""Broker interface + DTOs."""
from __future__ import annotations

import abc
from dataclasses import dataclass
from decimal import Decimal

from app.models.enums import BrokerType, OrderSide


@dataclass(slots=True)
class BrokerOrder:
    client_order_id: str
    symbol: str
    side: OrderSide
    quantity: Decimal


@dataclass(slots=True)
class BrokerFill:
    client_order_id: str
    broker_order_id: str
    filled_quantity: Decimal
    avg_fill_price: Decimal
    status: str  # "filled" | "rejected"


class BrokerInterface(abc.ABC):
    broker_type: BrokerType = BrokerType.PAPER
    is_live: bool = False

    @abc.abstractmethod
    async def place_order(self, order: BrokerOrder, *, reference_price: Decimal) -> BrokerFill: ...
