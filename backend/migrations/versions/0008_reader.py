"""Stage 09: per-user stable page bookmark and reading mode."""

import sqlalchemy as sa
from alembic import op

revision = "0008_reader"
down_revision = "0007_comic_admin"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "reading_progress",
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_reading_user"),
            primary_key=True,
        ),
        sa.Column(
            "chapter_id",
            sa.Uuid(),
            sa.ForeignKey("chapters.id", ondelete="CASCADE", name="fk_reading_chapter"),
            primary_key=True,
        ),
        sa.Column(
            "page_id",
            sa.Uuid(),
            sa.ForeignKey("comic_pages.id", ondelete="SET NULL", name="fk_reading_page"),
            nullable=True,
        ),
        sa.Column("offset_milli", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "offset_milli BETWEEN 0 AND 1000 AND version > 0", name="ck_reading_bounds"
        ),
        sa.CheckConstraint("mode IN ('vertical','paged')", name="ck_reading_mode"),
    )


def downgrade():
    op.drop_table("reading_progress")
