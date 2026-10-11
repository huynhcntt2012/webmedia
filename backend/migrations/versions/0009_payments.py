"""Stage 10: isolated sandbox orders, immutable event identity and subscriptions."""

import sqlalchemy as sa
from alembic import op

revision = "0009_payments"
down_revision = "0008_reader"
branch_labels = depends_on = None


def identity():
    return sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()"))


def upgrade():
    op.create_table(
        "payment_orders",
        identity(),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_order_user"),
        ),
        sa.Column(
            "plan_code",
            sa.String(16),
            sa.ForeignKey("plans.code", ondelete="RESTRICT", name="fk_order_plan"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("payment_code", sa.String(40), nullable=False),
        sa.Column("environment", sa.String(16), nullable=False, server_default="sandbox"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="VND"),
        sa.Column("amount_vnd", sa.BigInteger(), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("device_limit", sa.Integer(), nullable=False),
        sa.Column("bank", sa.String(80), nullable=False),
        sa.Column("account", sa.String(40), nullable=False),
        sa.Column("sub_account", sa.String(40), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_order_user_key"),
        sa.UniqueConstraint("payment_code", name="uq_order_code"),
        sa.CheckConstraint(
            "environment = 'sandbox' AND currency = 'VND'", name="ck_order_environment"
        ),
        sa.CheckConstraint("status IN ('pending','paid','expired')", name="ck_order_status"),
        sa.CheckConstraint(
            "amount_vnd > 0 AND duration_days BETWEEN 1 AND 366 AND device_limit BETWEEN 1 AND 20",
            name="ck_order_snapshot",
        ),
    )
    op.create_index("ix_order_user_created", "payment_orders", ["user_id", "created_at"])
    op.create_table(
        "payment_events",
        identity(),
        sa.Column("environment", sa.String(16), nullable=False, server_default="sandbox"),
        sa.Column("provider_transaction_id", sa.BigInteger(), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column(
            "order_id",
            sa.Uuid(),
            sa.ForeignKey("payment_orders.id", ondelete="SET NULL", name="fk_payment_event_order"),
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="received"),
        sa.Column("reason", sa.String(40)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "environment", "provider_transaction_id", name="uq_payment_provider_transaction"
        ),
        sa.CheckConstraint(
            "environment = 'sandbox' AND status IN ('received','accepted','rejected')",
            name="ck_payment_event_status",
        ),
    )
    op.create_table(
        "subscriptions",
        identity(),
        sa.Column(
            "order_id",
            sa.Uuid(),
            sa.ForeignKey("payment_orders.id", ondelete="RESTRICT", name="fk_subscription_order"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_subscription_user"),
        ),
        sa.Column(
            "plan_code",
            sa.String(16),
            sa.ForeignKey("plans.code", ondelete="RESTRICT", name="fk_subscription_plan"),
            nullable=False,
        ),
        sa.Column("environment", sa.String(16), nullable=False, server_default="sandbox"),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("device_limit", sa.Integer(), nullable=False),
        sa.UniqueConstraint("order_id", name="uq_subscription_order"),
        sa.CheckConstraint(
            "environment = 'sandbox' AND ends_at > starts_at AND device_limit > 0",
            name="ck_subscription_bounds",
        ),
    )
    op.create_index(
        "ix_subscription_user_plan_end", "subscriptions", ["user_id", "plan_code", "ends_at"]
    )


def downgrade():
    op.drop_table("subscriptions")
    op.drop_table("payment_events")
    op.drop_table("payment_orders")
