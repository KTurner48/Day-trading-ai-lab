"""Deterministic simulated gold feed + OHLCV bar type."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

_BASE_PRICES = {"XAU_USD": 2350.0, "GC": 2352.0, "GLD": 216.5}


@dataclass(slots=True)
class Bar:
    symbol: str
    time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


class SimulatedGoldFeed:
    """Seeded mean-reverting GBM. Same seed => same price path."""

    def __init__(self, *, seed: int = 42, volatility: float = 0.0008,
                 mean_reversion: float = 0.02) -> None:
        self._rng = random.Random(seed)
        self._vol = volatility
        self._kappa = mean_reversion

    def generate_bars(self, symbol: str, n: int, *,
                      start: datetime | None = None,
                      step_seconds: int = 300) -> list[Bar]:
        base = _BASE_PRICES.get(symbol, 2350.0)
        price = base
        t = start or datetime(2026, 1, 1, tzinfo=timezone.utc)
        step = timedelta(seconds=step_seconds)
        bars: list[Bar] = []
        for _ in range(n):
            o = price
            sub = []
            for _ in range(4):
                shock = self._rng.gauss(0.0, 1.0)
                reversion = self._kappa * math.log(base / price)
                price = price * math.exp(reversion + self._vol * shock)
                sub.append(price)
            c = sub[-1]
            hi = max(o, *sub)
            lo = min(o, *sub)
            bars.append(Bar(
                symbol=symbol, time=t,
                open=Decimal(str(round(o, 5))), high=Decimal(str(round(hi, 5))),
                low=Decimal(str(round(lo, 5))), close=Decimal(str(round(c, 5))),
                volume=self._rng.randint(50, 500),
            ))
            t += step
        return bars
