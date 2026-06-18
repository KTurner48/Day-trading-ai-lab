"""Shared market-data types: Tick (provider-agnostic) and the Bar re-export.

A Tick carries the PROVIDER's timestamp (event time), never arrival time, so
downstream aggregation buckets by when the market printed the price.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.market_data.simulated import Bar  # re-export so callers have one home

__all__ = ["Tick", "Bar"]


@dataclass(slots=True)
class Tick:
    symbol: str
    time: datetime          # provider event time (UTC), used for aggregation
    bid: Decimal
    ask: Decimal
    source: str             # "oanda" | "simulated"

    @property
    def mid(self) -> Decimal:
        return (self.bid + self.ask) / Decimal("2")
