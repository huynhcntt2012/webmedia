"""Stage 06: resumable uploads and durable media jobs; no public media routes."""

import sqlalchemy as sa
from alembic import op

revision = "0005_media_uploads"
down_revision = "0004_admin_catalogue"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "upload_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "owner_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_upload_owner"),
        ),
        sa.Column(
            "episode_id",
            sa.Uuid(),
            sa.ForeignKey("episodes.id", ondelete="SET NULL", name="fk_upload_episode"),
        ),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(200), nullable=False),
        sa.Column("total_bytes", sa.BigInteger(), nullable=False),
        sa.Column("received_bytes", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String(16), nullable=False, server_default="uploading"),
        sa.Column("reserved_bytes", sa.BigInteger(), nullable=False),
        sa.Column("reserved", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_id", "idempotency_key", name="uq_upload_owner_key"),
        sa.CheckConstraint(
            "total_bytes > 0 AND received_bytes >= 0 AND received_bytes <= total_bytes",
            name="ck_upload_size",
        ),
        sa.CheckConstraint(
            "status IN ('uploading','sealed','cancelled','expired')", name="ck_upload_status"
        ),
    )
    op.create_index("ix_upload_episode", "upload_sessions", ["episode_id"])
    op.create_index("ix_upload_cleanup", "upload_sessions", ["reserved", "expires_at"])
    op.create_table(
        "upload_chunks",
        sa.Column(
            "upload_id",
            sa.Uuid(),
            sa.ForeignKey("upload_sessions.id", ondelete="CASCADE", name="fk_chunk_upload"),
            primary_key=True,
        ),
        sa.Column("offset", sa.BigInteger(), primary_key=True),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.CheckConstraint('"offset" >= 0 AND size > 0', name="ck_chunk_size"),
    )
    op.create_table(
        "media_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "upload_id",
            sa.Uuid(),
            sa.ForeignKey("upload_sessions.id", ondelete="CASCADE", name="fk_media_job_upload"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_code", sa.String(40)),
        sa.Column("source_sha256", sa.String(64)),
        sa.Column("duration_seconds", sa.Integer()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("upload_id", name="uq_media_job_upload"),
        sa.CheckConstraint(
            "status IN ('queued','processing','ready','failed','cancelled')",
            name="ck_media_job_status",
        ),
    )
    op.create_index("ix_media_job_dispatch", "media_jobs", ["status", "started_at"])
    op.create_table(
        "media_variants",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("media_jobs.id", ondelete="CASCADE", name="fk_media_variant_job"),
            nullable=False,
        ),
        sa.Column("profile", sa.String(24), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("total_bytes", sa.BigInteger(), nullable=False),
        sa.UniqueConstraint("job_id", "profile", name="uq_media_variant_profile"),
    )


def downgrade():
    op.drop_table("media_variants")
    op.drop_table("media_jobs")
    op.drop_table("upload_chunks")
    op.drop_table("upload_sessions")
