# Phase 16 — OANDA Market Data Only

## Scope
Adds OANDA as a **market-data source** for XAU_USD when credentials are
configured, running ALONGSIDE the simulated feed (which still serves GC, GLD,
and anything else). No order placement code is added or changed. Live ordering
remains disabled in `app/brokers` exactly as before.

## What was added (market-data layer only)
- `app/market_data/types.py` — `Tick` type (carries the provider's event time).
- `app/market_data/provider.py` — provider interface + `SimulatedProvider`.
- `app/market_data/oanda.py` — `OandaMarketDataProvider` + pure parsers
  (`parse_stream_message`, `parse_oanda_time`). Parses PRICE -> Tick, ignores
  HEARTBEAT and malformed frames, uses the OANDA event timestamp, and reconnects
  with exponential backoff. Imports `httpx` lazily; contains no broker imports.
- `app/market_data/aggregator.py` — `BarAggregator` that buckets ticks by
  PROVIDER event time via `floor_to_bucket` (not arrival order).
- `app/market_data/routing.py` — per-symbol routing: OANDA only for configured
  symbols WITH credentials; everything else simulated; all simulated if OANDA
  unconfigured. `split_symbols` groups symbols so both feeds run alongside.
- `app/config.py` — OANDA credentials + `OANDA_DATA_SYMBOLS` +
  `oanda_market_data_configured`. (Market-data gating only.)
- `app/main.py` — `quote` now reports its `source`; new `/api/v1/market/sources`
  shows per-symbol routing. Signal generation stays on the deterministic
  simulated path.

## Configuration
Set in `.env`:
```
OANDA_API_KEY=...           # required to enable OANDA data
OANDA_ACCOUNT_ID=...        # required to enable OANDA data
OANDA_ENV=practice          # practice | live  (OANDA pricing host only)
OANDA_DATA_SYMBOLS=XAU_USD  # symbols OANDA may serve; others stay simulated
```
Leaving the credentials empty keeps the entire system on the simulated feed.

## Safety
- The OANDA *broker* stub is untouched and still refuses `place_order`.
- Execution remains paper-only; configuring OANDA data does not make any live
  broker order-capable. Proven by `tests/safety/test_oanda_data_isolation.py`.
- The data source is orthogonal to execution: an OANDA-sourced price still fills
  through the paper broker (`PAPER-` id) and never a live one.

## Fallback behavior
- Missing credentials -> simulated for all symbols.
- Stream failure -> `OandaMarketDataProvider.stream` reconnects with backoff; the
  worker can also fall back to simulated for that symbol if desired.
