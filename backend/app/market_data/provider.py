"""Market-data provider interface + a deterministic simulated provider that
emits Ticks. The OANDA provider (oanda.py) implements the same interface for
its configured symbols; routing picks per symbol."""
from __future__ import annotations

import abc
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.market_data.simulated import SimulatedGoldFeed
from app.market_data.types import Tick


class MarketDataProvider(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    async def stream(self, symbols: list[str]) -> AsyncIterator[Tick]:
        """Yield Ticks for the given symbols. Implementations must set each
        Tick.time to the PROVIDER event time, not the local arrival time."""
        raise NotImplementedError
        yield  # pragma: no cover  (marks this as an async generator)


class SimulatedProvider(MarketDataProvider):
    """Wraps SimulatedGoldFeed to emit Ticks with deterministic event times."""

    name = "simulated"

    def __init__(self, *, seed: int = 42, step_seconds: int = 5) -> None:
        self._feed = SimulatedGoldFeed(seed=seed)
        self._step = step_seconds

    def ticks(self, symbol: str, n: int, *, start: datetime | None = None) -> list[Tick]:
        """Synchronous helper (used by tests and the quote endpoint)."""
        bars = self._feed.generate_bars(symbol, n, start=start, step_seconds=self._step)
        out: list[Tick] = []
        for b in bars:
            spread = Decimal("0.05")
            out.append(Tick(symbol=symbol, time=b.time,
                            bid=b.close - spread, ask=b.close + spread,
                            source="simulated"))
        return out

    async def stream(self, symbols: list[str]) -> AsyncIterator[Tick]:
        # Deterministic, finite-free async emission for the worker path.
        t = datetime(2026, 1, 1, tzinfo=timezone.utc)
        feeds = {s: SimulatedGoldFeed(seed=abs(hash(s)) % 1000) for s in symbols}
        while True:
            for s in symbols:
                bar = feeds[s].generate_bars(s, 1, start=t, step_seconds=self._step)[0]
                spread = Decimal("0.05")
                yield Tick(symbol=s, time=bar.time, bid=bar.close - spread,
                           ask=bar.close + spread, source="simulated")
            t += timedelta(seconds=self._step)
