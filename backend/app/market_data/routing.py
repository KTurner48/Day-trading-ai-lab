"""Per-symbol provider routing.

OANDA supplies market data ONLY for its configured symbols (default XAU_USD) and
ONLY when credentials are present. Every other symbol (GC, GLD, ...) stays on the
simulated feed. If OANDA is not configured, everything falls back to simulated.

This is a market-data decision only; it has no effect on broker selection or
order placement (execution is paper-only regardless of where prices came from).
"""
from __future__ import annotations

from app.config import settings
from app.market_data.oanda import OandaMarketDataProvider
from app.market_data.provider import MarketDataProvider, SimulatedProvider


def provider_name_for_symbol(symbol: str) -> str:
    """Return 'oanda' or 'simulated' for a symbol, without constructing anything."""
    if (settings.oanda_market_data_configured
            and symbol in settings.OANDA_DATA_SYMBOLS):
        return "oanda"
    return "simulated"


def select_provider(symbol: str) -> MarketDataProvider:
    """Pick the data provider for one symbol. OANDA only for configured symbols
    with credentials present; simulated otherwise."""
    if provider_name_for_symbol(symbol) == "oanda":
        return OandaMarketDataProvider()
    return SimulatedProvider()


def split_symbols(symbols: list[str]) -> dict[str, list[str]]:
    """Group symbols by the provider that should serve them. Lets the worker run
    OANDA and simulated ALONGSIDE each other (e.g. OANDA XAU_USD + sim GC/GLD)."""
    groups: dict[str, list[str]] = {"oanda": [], "simulated": []}
    for s in symbols:
        groups[provider_name_for_symbol(s)].append(s)
    return {k: v for k, v in groups.items() if v}
