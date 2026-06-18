"""Strategy runner: creates Signal rows only. Never orders. Kill switch suppresses
emission entirely. Signal status is mode-derived."""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings as app_settings
from app.core.audit import record_audit
from app.core.settings_service import get_or_create_settings
from app.market_data.simulated import Bar
from app.models.db import Instrument, Signal
from app.models.enums import SignalAction, SignalStatus, TradingMode

_MODE_STATUS = {
    TradingMode.PAPER: SignalStatus.SIMULATED,
    TradingMode.LIVE_MANUAL_APPROVAL: SignalStatus.PENDING_APPROVAL,
    TradingMode.LIVE_AUTO: SignalStatus.APPROVED,
}


def status_for_mode(mode: TradingMode) -> SignalStatus:
    return _MODE_STATUS.get(mode, SignalStatus.SIMULATED)


class StrategyRunner:
    def __init__(self, strategies: list) -> None:
        self.strategies = strategies

    async def run_once(self, db: AsyncSession, symbol: str, bars: list[Bar]) -> list[Signal]:
        cfg = await get_or_create_settings(db)

        # Kill switch (DB or env) suppresses ALL emission.
        if cfg.kill_switch_active or app_settings.GLOBAL_KILL_SWITCH:
            return []

        status = status_for_mode(cfg.trading_mode)
        inst = (await db.execute(
            select(Instrument).where(Instrument.symbol == symbol)
        )).scalar_one_or_none()
        if inst is None:
            return []

        created: list[Signal] = []
        for strat in self.strategies:
            proposal = strat.evaluate(bars)
            if proposal is None or proposal.action == SignalAction.HOLD:
                continue
            sig = Signal(
                instrument_id=inst.id, action=proposal.action, status=status,
                score=proposal.score, confidence=proposal.confidence,
                reasoning=proposal.reasoning, entry_price=proposal.entry_price,
                stop_loss=proposal.stop_loss, take_profit=proposal.take_profit,
                risk_reward=proposal.risk_reward, strategy=proposal.strategy,
            )
            db.add(sig)
            await db.flush()
            await record_audit(db, action="SIGNAL_CREATED", entity_type="signal",
                               entity_id=sig.id,
                               detail={"strategy": proposal.strategy,
                                       "status": status.value, "score": proposal.score})
            created.append(sig)
        return created
