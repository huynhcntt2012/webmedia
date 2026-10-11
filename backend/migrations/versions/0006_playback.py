"""Stage 07: versioned watch progress and private subtitle tracks."""

import sqlalchemy as sa
from alembic import op

revision = "0006_playback"
down_revision = "0005_media_uploads"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "subtitle_tracks",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("media_jobs.id", ondelete="CASCADE", name="fk_subtitle_job"),
            nullable=False,
        ),
        sa.Column("language", sa.String(12), nullable=False),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.UniqueConstraint("job_id", "language", name="uq_subtitle_language"),
    )
    op.create_table(
        "watch_progress",
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_watch_user"),
            primary_key=True,
        ),
        sa.Column(
            "episode_id",
            sa.Uuid(),
            sa.ForeignKey("episodes.id", ondelete="CASCADE", name="fk_watch_episode"),
            primary_key=True,
        ),
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("media_jobs.id", ondelete="CASCADE", name="fk_watch_job"),
            nullable=False,
        ),
        sa.Column("position_ms", sa.Integer(), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "position_ms BETWEEN 0 AND 3600000 AND version > 0", name="ck_watch_bounds"
        ),
    )
    op.create_index("ix_watch_recent", "watch_progress", ["user_id", "updated_at"])


def downgrade():
    op.drop_table("watch_progress")
    op.drop_table("subtitle_tracks")
