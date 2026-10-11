"""Stage 11 explicit content grants and session-bound device leases."""

import sqlalchemy as sa
from alembic import op

revision = "0010_content_access"
down_revision = "0009_payments"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "content_grants",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_content_grant_user"),
            nullable=False,
        ),
        sa.Column("plan_code", sa.String(16), nullable=False),
        sa.Column("device_limit", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "plan_code IN ('vip','premium') AND device_limit BETWEEN 1 AND 20 "
            "AND expires_at > starts_at",
            name="ck_content_grant",
        ),
    )
    op.create_index("ix_content_grant_user", "content_grants", ["user_id", "expires_at"])
    op.create_table(
        "content_devices",
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey("auth_sessions.id", ondelete="CASCADE", name="fk_content_device_session"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_content_device_user"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_content_device_user_expiry", "content_devices", ["user_id", "expires_at"])


def downgrade():
    op.drop_table("content_devices")
    op.drop_table("content_grants")
