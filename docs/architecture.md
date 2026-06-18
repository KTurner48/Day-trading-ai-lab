# Architecture (MVP)

One FastAPI process. Modules: config -> models/db -> core (audit, settings,
security) -> brokers -> market_data -> strategies -> execution -> api.

## Flow (paper)
1. Simulated feed produces deterministic OHLCV bars.
2. StrategyRunner evaluates a strategy and creates Signal rows. Status is
   mode-derived (paper->simulated). The kill switch (DB or env) suppresses ALL
   emission.
3. ExecutionService is the only order creator. Three gates: kill switch -> mode
   executability -> risk sizing/veto. It refuses any non-paper broker at
   construction. Fills go through the paper broker only.
4. A risk veto marks the signal rejected with a reason; rejected signals never
   execute.

## Safety chokepoint
`assert_trading_allowed()` honors BOTH the DB `kill_switch_active` flag and the
process-level `GLOBAL_KILL_SWITCH` env var. Either one halts trading.

## Persistence
SQLAlchemy async models. PostgreSQL/TimescaleDB in Docker (Alembic migration
0001). Tests use in-memory SQLite, so the safety suite runs with no infra.
