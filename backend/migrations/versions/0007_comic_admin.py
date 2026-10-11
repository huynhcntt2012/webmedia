"""Stage 08: versioned comics/chapters and transactional normalized image assets."""

import sqlalchemy as sa
from alembic import op

revision = "0007_comic_admin"
down_revision = "0006_playback"
branch_labels = depends_on = None


def upgrade():
    op.add_column(
        "comics", sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1"))
    )
    op.add_column(
        "chapters", sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1"))
    )
    op.create_table(
        "comic_page_assets",
        sa.Column(
            "page_id",
            sa.Uuid(),
            sa.ForeignKey("comic_pages.id", ondelete="CASCADE", name="fk_comic_asset_page"),
            primary_key=True,
        ),
        sa.Column(
            "chapter_id",
            sa.Uuid(),
            sa.ForeignKey("chapters.id", ondelete="CASCADE", name="fk_comic_asset_chapter"),
            nullable=False,
        ),
        sa.Column("upload_key", sa.Uuid(), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("total_bytes", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.UniqueConstraint("chapter_id", "upload_key", name="uq_comic_asset_upload"),
        sa.CheckConstraint(
            "total_bytes > 0 AND total_bytes <= 4194304 AND octet_length(data) = total_bytes",
            name="ck_comic_asset_size",
        ),
    )


def downgrade():
    op.drop_table("comic_page_assets")
    op.drop_column("chapters", "version")
    op.drop_column("comics", "version")
