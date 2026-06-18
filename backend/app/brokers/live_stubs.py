"""Live broker stubs. They may validate credentials and report status, but the
shared base REFUSES place_order unconditionally. No live order code exists."""
from __future__ import annotations

import os
from decimal import Decimal

from app.brokers.base import BrokerFill, BrokerInterface, BrokerOrder
from app.core.exceptions import LiveOrderingNotEnabledError
from app.models.enums import BrokerType


class LiveBrokerStub(BrokerInterface):
    is_live = True
    required_env: tuple[str, ...] = ()

    def missing_credentials(self) -> list[str]:
        return [name for name in self.required_env if not os.environ.get(name)]

    @property
    def is_configured(self) -> bool:
        return not self.missing_credentials()

    async def place_order(self, order: BrokerOrder, *, reference_price: Decimal) -> BrokerFill:
        raise LiveOrderingNotEnabledError(
            f"Live order placement is disabled for {self.broker_type.value}; "
            "real-money trading requires a separate future approval phase.",
            detail={"broker": self.broker_type.value},
        )


class OandaBroker(LiveBrokerStub):
    broker_type = BrokerType.OANDA
    required_env = ("OANDA_API_KEY", "OANDA_ACCOUNT_ID")


class AlpacaBroker(LiveBrokerStub):
    broker_type = BrokerType.ALPACA
    required_env = ("ALPACA_API_KEY", "ALPACA_SECRET_KEY")


class IBKRBroker(LiveBrokerStub):
    broker_type = BrokerType.IBKR
    required_env = ("IBKR_HOST", "IBKR_PORT")


class TradovateBroker(LiveBrokerStub):
    broker_type = BrokerType.TRADOVATE
    required_env = ("TRADOVATE_USERNAME", "TRADOVATE_PASSWORD")


class MT5Broker(LiveBrokerStub):
    broker_type = BrokerType.MT5
    required_env = ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER")
