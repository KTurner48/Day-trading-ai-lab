"""Tick -> Bar aggregation, bucketed by PROVIDER event time.

Critical for the run-alongside design: OANDA (real-time) and simulated feeds
have different cadences and clocks, so bars MUST key off each tick's own
timestamp, not arrival order. floor_to_bucket does exactly that.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from app.market_data.types import Bar, Tick


def floor_to_bucket(ts: datetime, timeframe_seconds: int) -> datetime:
    """Floor a timestamp to the start of its timeframe bucket (UTC)."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    ts = ts.astimezone(timezone.utc)
    epoch = int(ts.timestamp())
    floored = epoch - (epoch % timeframe_seconds)
    return datetime.fromtimestamp(floored, tz=timezone.utc)


@dataclass
class _Working:
    bucket: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


class BarAggregator:
    """Folds a stream of Ticks into OHLCV bars per symbol, by event-time bucket.

    Emitting model: feeding a tick whose bucket is newer than the working bar
    CLOSES and returns the working bar; ticks in the same bucket extend it.
    """

    def __init__(self, timeframe_seconds: int = 300) -> None:
        self._tf = timeframe_seconds
        self._working: dict[str, _Working] = {}

    def add(self, tick: Tick) -> Bar | None:
        price = tick.mid
        bucket = floor_to_bucket(tick.time, self._tf)
        cur = self._working.get(tick.symbol)

        if cur is None:
            self._working[tick.symbol] = _Working(bucket, price, price, price, price, 1)
            return None

        if bucket == cur.bucket:
            cur.high = max(cur.high, price)
            cur.low = min(cur.low, price)
            cur.close = price
            cur.volume += 1
            return None

        # New bucket: close out the previous bar and start a fresh one.
        completed = Bar(symbol=tick.symbol, time=cur.bucket, open=cur.open,
                        high=cur.high, low=cur.low, close=cur.close, volume=cur.volume)
        self._working[tick.symbol] = _Working(bucket, price, price, price, price, 1)
        return completed

    def current(self, symbol: str) -> Bar | None:
        cur = self._working.get(symbol)
        if cur is None:
            return None
        return Bar(symbol=symbol, time=cur.bucket, open=cur.open, high=cur.high,
                   low=cur.low, close=cur.close, volume=cur.volume)
