"""CLI seed entrypoint: python -m scripts.seed_data"""
from __future__ import annotations

import asyncio

from app.models.db import AsyncSessionLocal, init_db
from app.seed import seed


async def main() -> None:
    await init_db()
    async with AsyncSessionLocal() as db:
        await seed(db)
        await db.commit()
    print("seed complete")


if __name__ == "__main__":
    asyncio.run(main())
