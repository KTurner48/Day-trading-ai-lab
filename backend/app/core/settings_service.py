"""Trading safety state: mode + kill switch. The execution chokepoint lives here."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings as app_settings
from app.core.audit import record_audit
from app.core.exceptions import KillSwitchActiveError
from app.models.db import SystemSetting
from app.models.enums import TradingMode


async def get_or_create_settings(db: AsyncSession) -> SystemSetting:
    row = (await db.execute(select(SystemSetting).limit(1))).scalar_one_or_none()
    if row is None:
        row = SystemSetting(
            trading_mode=TradingMode.PAPER,
            kill_switch_active=False,
            max_daily_loss_pct=app_settings.MAX_DAILY_LOSS_PCT,
            max_drawdown_pct=app_settings.MAX_DRAWDOWN_PCT,
            default_risk_per_trade_pct=app_settings.DEFAULT_RISK_PER_TRADE_PCT,
            max_open_positions=app_settings.MAX_OPEN_POSITIONS,
        )
        db.add(row)
        await db.flush()
    return row


async def set_trading_mode(db: AsyncSession, mode: TradingMode) -> SystemSetting:
    row = await get_or_create_settings(db)
    prev = row.trading_mode
    row.trading_mode = mode
    await record_audit(db, action="TRADING_MODE_CHANGE",
                       entity_type="system_settings", entity_id=row.id,
                       detail={"from": prev.value, "to": mode.value})
    return row


async def set_kill_switch(db: AsyncSession, active: bool, *, reason: str | None = None) -> SystemSetting:
    row = await get_or_create_settings(db)
    row.kill_switch_active = active
    await record_audit(db, action="KILL_SWITCH_ON" if active else "KILL_SWITCH_OFF",
                       entity_type="system_settings", entity_id=row.id,
                       detail={"reason": reason})
    return row


async def assert_trading_allowed(db: AsyncSession) -> SystemSetting:
    """Honors BOTH the DB kill switch and the env-level GLOBAL_KILL_SWITCH."""
    row = await get_or_create_settings(db)
    if row.kill_switch_active or app_settings.GLOBAL_KILL_SWITCH:
        raise KillSwitchActiveError("Trading halted by kill switch")
    return row
