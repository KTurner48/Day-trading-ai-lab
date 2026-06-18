"""Seed admin user, instruments, an account, and the settings singleton."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import hash_password
from app.core.settings_service import get_or_create_settings
from app.models.db import Account, Instrument, User

INSTRUMENTS = [
    ("XAU_USD", "Gold Spot / USD", Decimal("1")),
    ("GC", "Gold Futures (COMEX)", Decimal("100")),
    ("GLD", "SPDR Gold Shares ETF", Decimal("1")),
]


async def seed(db: AsyncSession) -> None:
    await get_or_create_settings(db)

    admin = (await db.execute(
        select(User).where(User.email == settings.ADMIN_EMAIL)
    )).scalar_one_or_none()
    if admin is None:
        db.add(User(
            email=settings.ADMIN_EMAIL,
            hashed_password=hash_password(settings.ADMIN_PASSWORD),
            full_name="Administrator", role="admin",
        ))

    for symbol, name, contract in INSTRUMENTS:
        present = (await db.execute(
            select(Instrument).where(Instrument.symbol == symbol)
        )).scalar_one_or_none()
        if present is None:
            db.add(Instrument(symbol=symbol, display_name=name, contract_size=contract))

    acct = (await db.execute(select(Account).limit(1))).scalar_one_or_none()
    if acct is None:
        db.add(Account(currency="USD", balance=Decimal("10000"), equity=Decimal("10000")))
    await db.flush()
