# AUREUS MVP — Gold Trading Platform (Paper-Safe)

A clean, runnable MVP of an automated gold trading platform: FastAPI backend,
React/TypeScript terminal-style frontend, PostgreSQL/TimescaleDB + Redis,
packaged with Docker Compose and a one-command verification script.

**This is a runnable MVP rebuild, not the full Phase 1–15 reconstruction.**
It is a smaller but complete and verifiable foundation.

> **Safety first.** Paper mode is the default. Live order placement is disabled
> in code. Only the paper broker can place orders. A DB kill switch and an
> env-level `GLOBAL_KILL_SWITCH` both halt trading.

## What's included
- FastAPI app: auth/login, command-center dashboard API, trading-mode + kill
  switch endpoints, simulated quotes, paper signal generation.
- PostgreSQL/TimescaleDB-ready models + Alembic migration (`0001_initial`).
  Tests run on in-memory SQLite, so `pytest` needs no infra.
- Redis-ready config (wired for future pub/sub; not required by the MVP path).
- Safety: settings singleton, DB kill switch, env `GLOBAL_KILL_SWITCH`,
  paper-only execution guard, live broker stubs that refuse `place_order`,
  audit logging.
- Simulated market data (deterministic) + one strategy (trend following).
- Frontend: login, protected command center, trading-mode control with the
  **ARM LIVE** typed confirmation, **single-confirm** kill switch, simulated
  live quotes, broker/status panel — all black-and-white terminal style.
- Verification: `scripts/verify_phase15.sh` + `make verify-phase15`, backend
  safety tests, frontend tests for ARM LIVE and the kill switch.

## Out of scope for this MVP (deliberately)
Backtesting engine, multi-strategy library, AI/LLM analysis, WebSocket live
streaming, the full 16-table schema, broker order reconciliation, notifications
delivery, and any live-ordering path. These existed in the larger design; the
MVP keeps the safety-critical core and a working end-to-end paper flow.

## Quick start
```bash
cp .env.example .env
docker compose up -d --build
# migrations + seed run automatically in the backend container
# Frontend: http://localhost:5173   API: http://localhost:8000/api/docs
# Login: admin@local / admin   (change ADMIN_PASSWORD in .env)
```

## Verify
```bash
make verify-phase15
```
Phase 15 is verified only when this prints `PHASE 15 PASS` on your machine.

See `FIRST_RUN.md` for exact laptop steps and `docs/SAFETY_CHECKLIST.md` for
the safety contract.

## Disclaimer
Research/educational use only. Not financial advice.
