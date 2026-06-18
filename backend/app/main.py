"""FastAPI app: health, auth, command-center dashboard, trading mode + kill
switch, and a paper signal-generation endpoint. Paper default; no live ordering."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select, cast, String
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import router as auth_router
from app.api.deps import get_current_user
from app.config import settings
from app.core.exceptions import AppError
from app.core.settings_service import (
    get_or_create_settings, set_kill_switch, set_trading_mode,
)
from app.execution.service import ExecutionService
from app.market_data.simulated import SimulatedGoldFeed
from app.market_data.routing import provider_name_for_symbol
from app.models.db import (
    Account, Instrument, Position, Signal, User, get_db, init_db,
)
from app.models.enums import SignalStatus, TradingMode
from app.seed import seed
from app.strategies.runner import StrategyRunner
from app.strategies.trend_following import TrendFollowingStrategy


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    from app.models.db import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        await seed(db)
        await db.commit()
    yield


app = FastAPI(title="AUREUS MVP", lifespan=lifespan, docs_url="/api/docs")
app.add_middleware(
    CORSMiddleware, allow_origins=settings.CORS_ORIGINS,
    allow_methods=["*"], allow_headers=["*"],
)
app.include_router(auth_router)


@app.exception_handler(AppError)
async def _app_error(_, exc: AppError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message, "detail": exc.detail}},
    )


@app.get("/api/health")
async def health():
    return {"status": "ok", "env": settings.APP_ENV,
            "trading_mode": settings.TRADING_MODE.value}


@app.get("/api/v1/market/quote/{symbol}")
async def quote(symbol: str):
    """Latest price for a symbol. The source is OANDA only when configured for
    this symbol; otherwise simulated. For the quote endpoint we use the
    simulated snapshot for a deterministic value, but we report which provider
    WOULD serve the live stream so the UI/operator can see routing."""
    source = provider_name_for_symbol(symbol)
    bars = SimulatedGoldFeed(seed=abs(hash(symbol)) % 1000).generate_bars(symbol, 60)
    last = bars[-1]
    return {"symbol": symbol, "price": str(last.close),
            "time": last.time.isoformat(), "source": source}


@app.get("/api/v1/market/sources")
async def market_sources():
    """Show per-symbol provider routing and whether OANDA market data is
    configured. Pure market-data info; ordering is unaffected and disabled."""
    symbols = ["XAU_USD", "GC", "GLD"]
    return {
        "oanda_market_data_configured": settings.oanda_market_data_configured,
        "oanda_env": settings.OANDA_ENV,
        "routing": {s: provider_name_for_symbol(s) for s in symbols},
        "note": "Market data only. Order placement is disabled regardless of source.",
    }


@app.get("/api/v1/dashboard/command-center")
async def command_center(db: AsyncSession = Depends(get_db),
                         _: User = Depends(get_current_user)):
    cfg = await get_or_create_settings(db)
    account = (await db.execute(select(Account).limit(1))).scalar_one_or_none()
    positions = (await db.execute(
        select(Position).where(Position.status == "open")
    )).scalars().all()
    latest = (await db.execute(
        select(Signal).order_by(Signal.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    pending = (await db.execute(
        select(Signal).where(cast(Signal.status, String) == SignalStatus.PENDING_APPROVAL.value)
    )).scalars().all()
    return {
        "settings": {
            "trading_mode": cfg.trading_mode.value,
            "kill_switch_active": cfg.kill_switch_active,
            "max_open_positions": cfg.max_open_positions,
        },
        "account": None if account is None else {
            "balance": str(account.balance), "equity": str(account.equity),
            "currency": account.currency,
        },
        "open_positions": [
            {"id": p.id, "side": p.side.value, "quantity": str(p.quantity),
             "avg_entry_price": str(p.avg_entry_price)} for p in positions
        ],
        "latest_signal": None if latest is None else {
            "id": latest.id, "action": latest.action.value,
            "status": latest.status.value, "score": latest.score,
            "reasoning": latest.reasoning, "veto_reason": latest.veto_reason,
        },
        "pending_count": len(pending),
        "brokers": [
            {"name": "Paper Practice", "broker_type": "paper",
             "status": "connected", "order_capable": True},
            {"name": "OANDA (stub)", "broker_type": "oanda",
             "status": "disconnected", "order_capable": False},
        ],
    }


class ModeBody(BaseModel):
    trading_mode: TradingMode


@app.put("/api/v1/settings/trading-mode")
async def update_mode(body: ModeBody, db: AsyncSession = Depends(get_db),
                      _: User = Depends(get_current_user)):
    row = await set_trading_mode(db, body.trading_mode)
    return {"trading_mode": row.trading_mode.value}


class KillBody(BaseModel):
    active: bool
    reason: str | None = None


@app.put("/api/v1/settings/kill-switch")
async def update_kill(body: KillBody, db: AsyncSession = Depends(get_db),
                      _: User = Depends(get_current_user)):
    row = await set_kill_switch(db, body.active, reason=body.reason)
    return {"kill_switch_active": row.kill_switch_active}


@app.post("/api/v1/signals/generate")
async def generate_signal(symbol: str = "XAU_USD", db: AsyncSession = Depends(get_db),
                          _: User = Depends(get_current_user)):
    """Generate signals from the simulated feed, then (in paper) execute them."""
    bars = SimulatedGoldFeed(seed=7).generate_bars(symbol, 160)
    runner = StrategyRunner([TrendFollowingStrategy(ema_fast=10, ema_slow=30, atr_period=14)])
    created = await runner.run_once(db, symbol, bars)
    executed = 0
    exec_svc = ExecutionService()
    for sig in created:
        order = await exec_svc.execute_signal(db, sig)
        if order is not None:
            executed += 1
    return {"created": len(created), "executed": executed}
