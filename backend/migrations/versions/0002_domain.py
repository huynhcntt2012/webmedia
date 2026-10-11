"""Stage 02: domain schema and timestamp triggers (frozen DDL)."""
# ruff: noqa: E501 -- preserve readable, frozen PostgreSQL DDL

from alembic import op

revision = "0002_domain"
down_revision = "0001_bootstrap"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
CREATE TABLE plans (
	code VARCHAR(16) NOT NULL, 
	name VARCHAR(80) NOT NULL, 
	price_vnd BIGINT, 
	duration_days INTEGER, 
	device_limit INTEGER, 
	is_active BOOLEAN DEFAULT false NOT NULL, 
	is_available_for_purchase BOOLEAN DEFAULT false NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (code), 
	CONSTRAINT ck_plans_code CHECK (code IN ('free', 'vip', 'premium')), 
	CONSTRAINT ck_plans_name CHECK (length(btrim(name)) > 0), 
	CONSTRAINT ck_plans_price CHECK (price_vnd IS NULL OR price_vnd >= 0), 
	CONSTRAINT ck_plans_duration CHECK (duration_days IS NULL OR duration_days > 0), 
	CONSTRAINT ck_plans_devices CHECK (device_limit IS NULL OR device_limit > 0), 
	CONSTRAINT ck_plans_purchasable CHECK (NOT is_available_for_purchase OR (code <> 'free' AND is_active AND price_vnd IS NOT NULL AND price_vnd > 0 AND duration_days IS NOT NULL AND device_limit IS NOT NULL)), 
	CONSTRAINT ck_plans_free CHECK (code <> 'free' OR (price_vnd = 0 AND price_vnd IS NOT NULL AND duration_days IS NULL AND is_active AND NOT is_available_for_purchase))
)
""")
    op.execute("""
CREATE TABLE comics (
	slug VARCHAR(200) NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	synopsis TEXT DEFAULT '' NOT NULL, 
	status VARCHAR(16) DEFAULT 'draft' NOT NULL, 
	required_plan_code VARCHAR(16) DEFAULT 'free' NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_comics_slug UNIQUE (slug), 
	CONSTRAINT ck_comics_slug CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'), 
	CONSTRAINT ck_comics_title CHECK (length(btrim(title)) > 0), 
	CONSTRAINT ck_comics_status CHECK (status IN ('draft', 'published', 'archived')), 
	CONSTRAINT fk_comics_required_plan_code FOREIGN KEY(required_plan_code) REFERENCES plans (code) ON DELETE RESTRICT
)
""")
    op.execute("CREATE INDEX ix_comics_required_plan_code ON comics (required_plan_code)")
    op.execute("CREATE INDEX ix_comics_status_created_at ON comics (status, created_at)")
    op.execute("""
CREATE TABLE movies (
	slug VARCHAR(200) NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	synopsis TEXT DEFAULT '' NOT NULL, 
	release_year INTEGER, 
	status VARCHAR(16) DEFAULT 'draft' NOT NULL, 
	required_plan_code VARCHAR(16) DEFAULT 'free' NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_movies_slug UNIQUE (slug), 
	CONSTRAINT ck_movies_slug CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'), 
	CONSTRAINT ck_movies_title CHECK (length(btrim(title)) > 0), 
	CONSTRAINT ck_movies_status CHECK (status IN ('draft', 'published', 'archived')), 
	CONSTRAINT ck_movies_year CHECK (release_year IS NULL OR release_year BETWEEN 1888 AND 9999), 
	CONSTRAINT fk_movies_required_plan_code FOREIGN KEY(required_plan_code) REFERENCES plans (code) ON DELETE RESTRICT
)
""")
    op.execute("CREATE INDEX ix_movies_required_plan_code ON movies (required_plan_code)")
    op.execute("CREATE INDEX ix_movies_status_created_at ON movies (status, created_at)")
    op.execute("""
CREATE TABLE users (
	email VARCHAR(254) NOT NULL, 
	display_name VARCHAR(120) NOT NULL, 
	password_hash TEXT NOT NULL, 
	role VARCHAR(16) DEFAULT 'user' NOT NULL, 
	is_active BOOLEAN DEFAULT true NOT NULL, 
	plan_code VARCHAR(16) DEFAULT 'free' NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_users_email UNIQUE (email), 
	CONSTRAINT ck_users_email CHECK (email = lower(btrim(email)) AND email LIKE '%%_@_%%._%%'), 
	CONSTRAINT ck_users_role CHECK (role IN ('user', 'admin')), 
	CONSTRAINT ck_users_password_hash CHECK (password_hash LIKE '$argon2id$%%'), 
	CONSTRAINT ck_users_display_name CHECK (length(btrim(display_name)) > 0), 
	CONSTRAINT fk_users_plan_code FOREIGN KEY(plan_code) REFERENCES plans (code) ON DELETE RESTRICT
)
""")
    op.execute("CREATE INDEX ix_users_plan_code ON users (plan_code)")
    op.execute("""
CREATE TABLE chapters (
	comic_id UUID NOT NULL, 
	chapter_number INTEGER NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_chapters_position UNIQUE (comic_id, chapter_number), 
	CONSTRAINT ck_chapters_position CHECK (chapter_number > 0), 
	CONSTRAINT ck_chapters_title CHECK (length(btrim(title)) > 0), 
	CONSTRAINT fk_chapters_comic_id FOREIGN KEY(comic_id) REFERENCES comics (id) ON DELETE CASCADE
)
""")
    op.execute("""
CREATE TABLE episodes (
	movie_id UUID NOT NULL, 
	season_number INTEGER DEFAULT 1 NOT NULL, 
	episode_number INTEGER NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	duration_seconds INTEGER, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_episodes_position UNIQUE (movie_id, season_number, episode_number), 
	CONSTRAINT ck_episodes_position CHECK (season_number > 0 AND episode_number > 0), 
	CONSTRAINT ck_episodes_title CHECK (length(btrim(title)) > 0), 
	CONSTRAINT ck_episodes_duration CHECK (duration_seconds IS NULL OR duration_seconds > 0), 
	CONSTRAINT fk_episodes_movie_id FOREIGN KEY(movie_id) REFERENCES movies (id) ON DELETE CASCADE
)
""")
    op.execute("""
CREATE TABLE comic_pages (
	chapter_id UUID NOT NULL, 
	page_number INTEGER NOT NULL, 
	storage_key VARCHAR(500) NOT NULL, 
	width INTEGER NOT NULL, 
	height INTEGER NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_comic_pages_position UNIQUE (chapter_id, page_number) DEFERRABLE INITIALLY IMMEDIATE, 
	CONSTRAINT uq_comic_pages_storage_key UNIQUE (storage_key), 
	CONSTRAINT ck_comic_pages_position CHECK (page_number > 0), 
	CONSTRAINT ck_comic_pages_dimensions CHECK (width > 0 AND height > 0), 
	CONSTRAINT ck_comic_pages_storage_key CHECK (storage_key ~ '^[a-zA-Z0-9][a-zA-Z0-9/_-]*[.](jpg|jpeg|png|webp|avif)$' AND position('..' in storage_key) = 0 AND position('//' in storage_key) = 0), 
	CONSTRAINT fk_comic_pages_chapter_id FOREIGN KEY(chapter_id) REFERENCES chapters (id) ON DELETE CASCADE
)
""")
    op.execute("""
CREATE FUNCTION suni_touch_updated_at() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN
    NEW.created_at := OLD.created_at;
    NEW.updated_at := clock_timestamp();
    RETURN NEW;
END;
$$
""")
    op.execute("REVOKE ALL ON FUNCTION suni_touch_updated_at() FROM PUBLIC")
    op.execute(
        "CREATE TRIGGER trg_plans_updated_at BEFORE UPDATE ON plans "
        "FOR EACH ROW EXECUTE FUNCTION suni_touch_updated_at()"
    )
    op.execute(
        "CREATE TRIGGER trg_comics_updated_at BEFORE UPDATE ON comics "
        "FOR EACH ROW EXECUTE FUNCTION suni_touch_updated_at()"
    )
    op.execute(
        "CREATE TRIGGER trg_movies_updated_at BEFORE UPDATE ON movies "
        "FOR EACH ROW EXECUTE FUNCTION suni_touch_updated_at()"
    )
    op.execute(
        "CREATE TRIGGER trg_users_updated_at BEFORE UPDATE ON users "
        "FOR EACH ROW EXECUTE FUNCTION suni_touch_updated_at()"
    )
    op.execute(
        "CREATE TRIGGER trg_chapters_updated_at BEFORE UPDATE ON chapters "
        "FOR EACH ROW EXECUTE FUNCTION suni_touch_updated_at()"
    )
    op.execute(
        "CREATE TRIGGER trg_episodes_updated_at BEFORE UPDATE ON episodes "
        "FOR EACH ROW EXECUTE FUNCTION suni_touch_updated_at()"
    )
    op.execute(
        "CREATE TRIGGER trg_comic_pages_updated_at BEFORE UPDATE ON comic_pages "
        "FOR EACH ROW EXECUTE FUNCTION suni_touch_updated_at()"
    )


def downgrade():
    op.drop_table("comic_pages")
    op.drop_table("episodes")
    op.drop_table("chapters")
    op.drop_table("users")
    op.drop_table("movies")
    op.drop_table("comics")
    op.drop_table("plans")
    op.execute("DROP FUNCTION suni_touch_updated_at()")
