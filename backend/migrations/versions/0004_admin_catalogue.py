"""Stage 05: catalogue metadata, classification and operator audit."""

import sqlalchemy as sa
from alembic import op

revision = "0004_admin_catalogue"
down_revision = "0003_auth"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("movies", sa.Column("poster_url", sa.String(2048)))
    op.add_column("movies", sa.Column("trailer_url", sa.String(500)))
    for table in ("movies", "episodes"):
        op.add_column(
            table, sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False)
        )
    op.create_table(
        "genres",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.UniqueConstraint("slug", name="uq_genres_slug"),
        sa.UniqueConstraint("name", name="uq_genres_name"),
        sa.CheckConstraint("slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="ck_genres_slug"),
        sa.CheckConstraint("length(btrim(name)) > 0", name="ck_genres_name"),
    )
    op.create_table(
        "movie_genres",
        sa.Column(
            "movie_id",
            sa.Uuid(),
            sa.ForeignKey("movies.id", ondelete="CASCADE", name="fk_movie_genres_movie"),
            primary_key=True,
        ),
        sa.Column(
            "genre_id",
            sa.Uuid(),
            sa.ForeignKey("genres.id", ondelete="RESTRICT", name="fk_movie_genres_genre"),
            primary_key=True,
        ),
    )
    op.create_index("ix_movie_genres_genre", "movie_genres", ["genre_id"])
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "actor_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_audit_events_actor"),
        ),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("entity_type", sa.String(16), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("changed_fields", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])


def downgrade():
    op.drop_table("audit_events")
    op.drop_table("movie_genres")
    op.drop_table("genres")
    for table in ("movies", "episodes"):
        op.drop_column(table, "version")
    op.drop_column("movies", "trailer_url")
    op.drop_column("movies", "poster_url")
