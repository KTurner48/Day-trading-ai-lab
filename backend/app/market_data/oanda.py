"""OANDA market-data adapter — MARKET DATA ONLY.

This module reads OANDA's pricing stream and converts PRICE messages into the
shared Tick type. It contains NO order-placement code and imports nothing from
the brokers layer. OANDA order placement remains disabled in app/brokers and is
untouched by this file.

Stream reference: GET /v3/accounts/{accountID}/pricing/stream returns
newline-delimited JSON objects with "type" of "PRICE" or "HEARTBEAT".
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from app.config import settings
from app.market_data.provider import MarketDataProvider
from app.market_data.types import Tick

# OANDA uses dash-style instrument names (XAU_USD is already correct).
_HOSTS = {
    "practice": "https://stream-fxpractice.oanda.com",
    "live": "https://stream-fxtrade.oanda.com",
}


def parse_oanda_time(raw: str) -> datetime:
    """OANDA timestamps are RFC3339 with nanoseconds, e.g.
    '2026-06-18T13:45:30.123456789Z'. Python's fromisoformat handles up to
    microseconds, so trim excess fractional digits and the trailing Z."""
    s = raw.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    # Trim fractional seconds to 6 digits if longer.
    if "." in s:
        head, frac_tz = s.split(".", 1)
        # frac_tz looks like "123456789+00:00"
        if "+" in frac_tz:
            frac, tz = frac_tz.split("+", 1)
            tz = "+" + tz
        elif "-" in frac_tz:
            frac, tz = frac_tz.split("-", 1)
            tz = "-" + tz
        else:
            frac, tz = frac_tz, ""
        frac = frac[:6]
        s = f"{head}.{frac}{tz}"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_stream_message(line: str) -> Tick | None:
    """Parse one line of the OANDA pricing stream.

    Returns a Tick for a PRICE message, or None for HEARTBEAT / blank / non-PRICE
    lines. Uses the provider's own timestamp (the 'time' field), never local
    arrival time. Malformed lines return None rather than raising, so a single
    bad frame cannot kill the stream loop.
    """
    line = line.strip()
    if not line:
        return None
    try:
        msg = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return None

    mtype = msg.get("type")
    if mtype == "HEARTBEAT":
        return None
    if mtype != "PRICE":
        return None

    instrument = msg.get("instrument")
    bids = msg.get("bids") or []
    asks = msg.get("asks") or []
    t = msg.get("time")
    if not instrument or not t or not bids or not asks:
        return None

    try:
        bid = Decimal(str(bids[0]["price"]))
        ask = Decimal(str(asks[0]["price"]))
    except (KeyError, IndexError, InvalidOperation, TypeError):
        return None

    try:
        event_time = parse_oanda_time(t)
    except (ValueError, TypeError):
        return None

    return Tick(symbol=instrument, time=event_time, bid=bid, ask=ask, source="oanda")


class OandaMarketDataProvider(MarketDataProvider):
    """Streams live prices from OANDA for the configured symbols.

    Reconnects with exponential backoff. This provider is selected per-symbol
    only when credentials are configured; otherwise the simulated provider is
    used. It NEVER places orders.
    """

    name = "oanda"

    def __init__(self, *, max_backoff: float = 30.0, base_backoff: float = 1.0,
                 max_retries: int | None = None) -> None:
        self._max_backoff = max_backoff
        self._base_backoff = base_backoff
        self._max_retries = max_retries  # None = retry forever
        self._host = _HOSTS.get(settings.OANDA_ENV, _HOSTS["practice"])

    def _url(self, symbols: list[str]) -> str:
        instruments = "%2C".join(symbols)  # comma-separated, URL-encoded
        return (f"{self._host}/v3/accounts/{settings.OANDA_ACCOUNT_ID}"
                f"/pricing/stream?instruments={instruments}")

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {settings.OANDA_API_KEY}"}

    async def stream(self, symbols: list[str]) -> AsyncIterator[Tick]:
        """Yield Ticks from the live stream, reconnecting on failure with
        exponential backoff. Requires httpx; imported lazily so the module loads
        without it (e.g. during pure unit tests of the parser)."""
        import httpx

        attempt = 0
        backoff = self._base_backoff
        while True:
            try:
                async with httpx.AsyncClient(timeout=None) as client:
                    async with client.stream("GET", self._url(symbols),
                                             headers=self._headers) as resp:
                        resp.raise_for_status()
                        attempt = 0
                        backoff = self._base_backoff
                        async for line in resp.aiter_lines():
                            tick = parse_stream_message(line)
                            if tick is not None:
                                yield tick
            except Exception:
                attempt += 1
                if self._max_retries is not None and attempt > self._max_retries:
                    raise
                await asyncio.sleep(min(backoff, self._max_backoff))
                backoff = min(backoff * 2, self._max_backoff)
