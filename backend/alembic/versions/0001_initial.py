"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-18

Mirrors app/models/db.py. Portable across PostgreSQL and SQLite (String-typed
ids and enums so no PG-only types are required). On TimescaleDB this runs as
plain Postgres; converting price history to a hypertable is a future phase.
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_settings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("trading_mode", sa.String(32), nullable=False, server_default="paper"),
        sa.Column("kill_switch_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("max_daily_loss_pct", sa.Numeric(6, 2), server_default="2.0"),
        sa.Column("max_drawdown_pct", sa.Numeric(6, 2), server_default="10.0"),
        sa.Column("default_risk_per_trade_pct", sa.Numeric(6, 2), server_default="0.5"),
        sa.Column("max_open_positions", sa.Integer(), server_default="3"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(120)),
        sa.Column("role", sa.String(20), server_default="admin"),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("entity_type", sa.String(60)),
        sa.Column("entity_id", sa.String(64)),
        sa.Column("detail", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_table(
        "instruments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("symbol", sa.String(32), nullable=False, unique=True),
        sa.Column("display_name", sa.String(80), nullable=False),
        sa.Column("contract_size", sa.Numeric(18, 4), server_default="1"),
    )
    op.create_index("ix_instruments_symbol", "instruments", ["symbol"], unique=True)
    op.create_table(
        "accounts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("currency", sa.String(8), server_default="USD"),
        sa.Column("balance", sa.Numeric(18, 2), server_default="10000"),
        sa.Column("equity", sa.Numeric(18, 2), server_default="10000"),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true()),
    )
    op.create_table(
        "signals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("instrument_id", sa.String(36), sa.ForeignKey("instruments.id"), nullable=False),
        sa.Column("action", sa.String(8), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending_approval"),
        sa.Column("score", sa.Integer(), server_default="0"),
        sa.Column("confidence", sa.Numeric(5, 4), server_default="0"),
        sa.Column("reasoning", sa.Text()),
        sa.Column("entry_price", sa.Numeric(18, 8)),
        sa.Column("stop_loss", sa.Numeric(18, 8)),
        sa.Column("take_profit", sa.Numeric(18, 8)),
        sa.Column("risk_reward", sa.Numeric(8, 2)),
        sa.Column("veto_reason", sa.Text()),
        sa.Column("strategy", sa.String(60)),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_signals_status", "signals", ["status"])
    op.create_table(
        "orders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("account_id", sa.String(36), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("instrument_id", sa.String(36), sa.ForeignKey("instruments.id"), nullable=False),
        sa.Column("signal_id", sa.String(36), sa.ForeignKey("signals.id")),
        sa.Column("client_order_id", sa.String(64), nullable=False, unique=True),
        sa.Column("broker_order_id", sa.String(120)),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("quantity", sa.Numeric(18, 8), nullable=False),
        sa.Column("avg_fill_price", sa.Numeric(18, 8)),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_orders_client_order_id", "orders", ["client_order_id"], unique=True)
    op.create_table(
        "positions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("account_id", sa.String(36), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("instrument_id", sa.String(36), sa.ForeignKey("instruments.id"), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 8), nullable=False),
        sa.Column("avg_entry_price", sa.Numeric(18, 8), nullable=False),
        sa.Column("status", sa.String(12), server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("subject", sa.String(200)),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    for t in ["notifications", "positions", "orders", "signals", "accounts",
              "instruments", "audit_logs", "users", "system_settings"]:
        op.drop_table(t)
