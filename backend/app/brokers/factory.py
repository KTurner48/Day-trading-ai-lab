"""Broker factory. PAPER is the only order-capable adapter."""
from __future__ import annotations

from app.brokers.base import BrokerInterface
from app.brokers.live_stubs import (
    AlpacaBroker, IBKRBroker, LiveBrokerStub, MT5Broker, OandaBroker, TradovateBroker,
)
from app.brokers.paper import PaperBroker
from app.models.enums import BrokerType

_LIVE: dict[BrokerType, type[LiveBrokerStub]] = {
    BrokerType.OANDA: OandaBroker,
    BrokerType.ALPACA: AlpacaBroker,
    BrokerType.IBKR: IBKRBroker,
    BrokerType.TRADOVATE: TradovateBroker,
    BrokerType.MT5: MT5Broker,
}


class BrokerFactory:
    @staticmethod
    def create(broker_type: BrokerType) -> BrokerInterface:
        if broker_type == BrokerType.PAPER:
            return PaperBroker()
        cls = _LIVE.get(broker_type)
        if cls is None:
            raise ValueError(f"Unknown broker type: {broker_type}")
        return cls()

    @staticmethod
    def create_live_stub(broker_type: BrokerType) -> LiveBrokerStub:
        cls = _LIVE.get(broker_type)
        if cls is None:
            raise ValueError(f"'{broker_type.value}' is not a live broker")
        return cls()

    @staticmethod
    def is_order_capable(broker_type: BrokerType) -> bool:
        return broker_type == BrokerType.PAPER

    @staticmethod
    def live_broker_types() -> list[BrokerType]:
        return list(_LIVE.keys())
