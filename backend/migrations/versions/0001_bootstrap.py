"""Stage 01: migration baseline; domain tables start at Stage 02.

Alembic creates its version table. Deliberately no domain schema mutation.
"""

revision = "0001_bootstrap"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
