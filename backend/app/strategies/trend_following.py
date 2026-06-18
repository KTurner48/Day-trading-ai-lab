"""One real strategy for the MVP: EMA-stack trend following."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.market_data.simulated import Bar
from app.models.enums import SignalAction
from app.strategies.indicators import atr, ema


@dataclass(slots=True)
class StrategyProposal:
    action: SignalAction
    score: int
    confidence: float
    reasoning: str
    entry_price: Decimal
    stop_loss: Decimal
    take_profit: Decimal
    risk_reward: float
    strategy: str = "trend_following"
    factors: dict = field(default_factory=dict)


class TrendFollowingStrategy:
    name = "trend_following"

    def __init__(self, *, ema_fast: int = 20, ema_slow: int = 50,
                 atr_period: int = 14, slope_lookback: int = 3,
                 atr_mult: float = 1.5, rr: float = 2.0) -> None:
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.atr_period = atr_period
        self.slope_lookback = slope_lookback
        self.atr_mult = atr_mult
        self.rr = rr

    def evaluate(self, bars: list[Bar]) -> StrategyProposal | None:
        closes = [float(b.close) for b in bars]
        highs = [float(b.high) for b in bars]
        lows = [float(b.low) for b in bars]
        if len(closes) < self.ema_slow + self.slope_lookback:
            return None
        fast = ema(closes, self.ema_fast)
        slow = ema(closes, self.ema_slow)
        a = atr(highs, lows, closes, self.atr_period)
        f, s, av = fast[-1], slow[-1], a[-1]
        if None in (f, s, av) or av == 0:
            return None
        prior_f = fast[-1 - self.slope_lookback]
        if prior_f is None:
            return None
        slope = f - prior_f
        price = closes[-1]
        entry = bars[-1].close
        risk = Decimal(str(av)) * Decimal(str(self.atr_mult))

        if f > s and price > f and slope > 0:
            strength = min(1.0, abs(f - s) / av)
            return StrategyProposal(
                action=SignalAction.BUY,
                score=int(max(0, min(100, round(55 + strength * 40)))),
                confidence=max(0.0, min(1.0, 0.5 + strength * 0.4)),
                reasoning="Uptrend confirmed: fast EMA above slow EMA, positive slope.",
                entry_price=entry, stop_loss=entry - risk,
                take_profit=entry + risk * Decimal(str(self.rr)), risk_reward=self.rr,
            )
        if f < s and price < f and slope < 0:
            strength = min(1.0, abs(f - s) / av)
            return StrategyProposal(
                action=SignalAction.SELL,
                score=int(max(0, min(100, round(55 + strength * 40)))),
                confidence=max(0.0, min(1.0, 0.5 + strength * 0.4)),
                reasoning="Downtrend confirmed: fast EMA below slow EMA, negative slope.",
                entry_price=entry, stop_loss=entry + risk,
                take_profit=entry - risk * Decimal(str(self.rr)), risk_reward=self.rr,
            )
        return None
