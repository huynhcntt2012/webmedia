"""Domain, authentication, media, playback, comic assets and reader through stage 09."""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    FetchedValue,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        server_onupdate=FetchedValue(),
    )


class Identity:
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )


class Plan(Timestamps, Base):
    __tablename__ = "plans"
    __table_args__ = (
        CheckConstraint("code IN ('free', 'vip', 'premium')", name="ck_plans_code"),
        CheckConstraint("length(btrim(name)) > 0", name="ck_plans_name"),
        CheckConstraint("price_vnd IS NULL OR price_vnd >= 0", name="ck_plans_price"),
        CheckConstraint("duration_days IS NULL OR duration_days > 0", name="ck_plans_duration"),
        CheckConstraint("device_limit IS NULL OR device_limit > 0", name="ck_plans_devices"),
        CheckConstraint(
            "NOT is_available_for_purchase OR (code <> 'free' AND is_active "
            "AND price_vnd IS NOT NULL AND price_vnd > 0 "
            "AND duration_days IS NOT NULL AND device_limit IS NOT NULL)",
            name="ck_plans_purchasable",
        ),
        CheckConstraint(
            "code <> 'free' OR (price_vnd = 0 AND price_vnd IS NOT NULL "
            "AND duration_days IS NULL AND is_active AND NOT is_available_for_purchase)",
            name="ck_plans_free",
        ),
    )
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    price_vnd: Mapped[int | None] = mapped_column(BigInteger)
    duration_days: Mapped[int | None] = mapped_column(Integer)
    device_limit: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    is_available_for_purchase: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class PaymentOrder(Identity, Base):
    __tablename__ = "payment_orders"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_order_user_key"),
        UniqueConstraint("payment_code", name="uq_order_code"),
        CheckConstraint(
            "environment = 'sandbox' AND currency = 'VND'", name="ck_order_environment"
        ),
        CheckConstraint("status IN ('pending','paid','expired')", name="ck_order_status"),
        CheckConstraint(
            "amount_vnd > 0 AND duration_days BETWEEN 1 AND 366 AND device_limit BETWEEN 1 AND 20",
            name="ck_order_snapshot",
        ),
        Index("ix_order_user_created", "user_id", "created_at"),
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL", name="fk_order_user")
    )
    plan_code: Mapped[str] = mapped_column(
        ForeignKey("plans.code", ondelete="RESTRICT", name="fk_order_plan")
    )
    idempotency_key: Mapped[uuid.UUID] = mapped_column(Uuid)
    payment_code: Mapped[str] = mapped_column(String(40))
    environment: Mapped[str] = mapped_column(String(16), server_default="sandbox")
    currency: Mapped[str] = mapped_column(String(3), server_default="VND")
    amount_vnd: Mapped[int] = mapped_column(BigInteger)
    duration_days: Mapped[int] = mapped_column(Integer)
    device_limit: Mapped[int] = mapped_column(Integer)
    bank: Mapped[str] = mapped_column(String(80))
    account: Mapped[str] = mapped_column(String(40))
    sub_account: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(16), server_default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PaymentEvent(Identity, Base):
    __tablename__ = "payment_events"
    __table_args__ = (
        UniqueConstraint(
            "environment", "provider_transaction_id", name="uq_payment_provider_transaction"
        ),
        CheckConstraint(
            "environment = 'sandbox' AND status IN ('received','accepted','rejected')",
            name="ck_payment_event_status",
        ),
    )
    environment: Mapped[str] = mapped_column(String(16), server_default="sandbox")
    provider_transaction_id: Mapped[int] = mapped_column(BigInteger)
    payload_sha256: Mapped[str] = mapped_column(String(64))
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("payment_orders.id", ondelete="SET NULL", name="fk_payment_event_order")
    )
    status: Mapped[str] = mapped_column(String(16), server_default="received")
    reason: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Subscription(Identity, Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        UniqueConstraint("order_id", name="uq_subscription_order"),
        CheckConstraint(
            "environment = 'sandbox' AND ends_at > starts_at AND device_limit > 0",
            name="ck_subscription_bounds",
        ),
        Index("ix_subscription_user_plan_end", "user_id", "plan_code", "ends_at"),
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("payment_orders.id", ondelete="RESTRICT", name="fk_subscription_order")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL", name="fk_subscription_user")
    )
    plan_code: Mapped[str] = mapped_column(
        ForeignKey("plans.code", ondelete="RESTRICT", name="fk_subscription_plan")
    )
    environment: Mapped[str] = mapped_column(String(16), server_default="sandbox")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    device_limit: Mapped[int] = mapped_column(Integer)


class User(Identity, Timestamps, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        CheckConstraint(
            "email = lower(btrim(email)) AND email LIKE '%_@_%._%'", name="ck_users_email"
        ),
        CheckConstraint("role IN ('user', 'admin')", name="ck_users_role"),
        CheckConstraint("password_hash LIKE '$argon2id$%'", name="ck_users_password_hash"),
        CheckConstraint("length(btrim(display_name)) > 0", name="ck_users_display_name"),
        Index("ix_users_plan_code", "plan_code"),
    )
    email: Mapped[str] = mapped_column(String(254))
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(16), server_default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    plan_code: Mapped[str] = mapped_column(
        ForeignKey("plans.code", ondelete="RESTRICT", name="fk_users_plan_code"),
        server_default="free",
    )
    plan: Mapped[Plan] = relationship()


class Movie(Identity, Timestamps, Base):
    __tablename__ = "movies"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_movies_slug"),
        CheckConstraint("slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="ck_movies_slug"),
        CheckConstraint("length(btrim(title)) > 0", name="ck_movies_title"),
        CheckConstraint("status IN ('draft', 'published', 'archived')", name="ck_movies_status"),
        CheckConstraint(
            "release_year IS NULL OR release_year BETWEEN 1888 AND 9999", name="ck_movies_year"
        ),
        Index("ix_movies_status_created_at", "status", "created_at"),
        Index("ix_movies_required_plan_code", "required_plan_code"),
    )
    slug: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(200))
    synopsis: Mapped[str] = mapped_column(Text, server_default="")
    release_year: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), server_default="draft")
    required_plan_code: Mapped[str] = mapped_column(
        ForeignKey("plans.code", ondelete="RESTRICT", name="fk_movies_required_plan_code"),
        server_default="free",
    )
    poster_url: Mapped[str | None] = mapped_column(String(2048))
    trailer_url: Mapped[str | None] = mapped_column(String(500))
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    genres: Mapped[list["Genre"]] = relationship(secondary="movie_genres", lazy="selectin")
    episodes: Mapped[list["Episode"]] = relationship(
        back_populates="movie",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Episode(Identity, Timestamps, Base):
    __tablename__ = "episodes"
    __table_args__ = (
        UniqueConstraint(
            "movie_id", "season_number", "episode_number", name="uq_episodes_position"
        ),
        CheckConstraint("season_number > 0 AND episode_number > 0", name="ck_episodes_position"),
        CheckConstraint("length(btrim(title)) > 0", name="ck_episodes_title"),
        CheckConstraint(
            "duration_seconds IS NULL OR duration_seconds > 0", name="ck_episodes_duration"
        ),
    )
    movie_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("movies.id", ondelete="CASCADE", name="fk_episodes_movie_id"),
    )
    season_number: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    episode_number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    movie: Mapped[Movie] = relationship(back_populates="episodes")


class Comic(Identity, Timestamps, Base):
    __tablename__ = "comics"
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    __table_args__ = (
        UniqueConstraint("slug", name="uq_comics_slug"),
        CheckConstraint("slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="ck_comics_slug"),
        CheckConstraint("length(btrim(title)) > 0", name="ck_comics_title"),
        CheckConstraint("status IN ('draft', 'published', 'archived')", name="ck_comics_status"),
        Index("ix_comics_status_created_at", "status", "created_at"),
        Index("ix_comics_required_plan_code", "required_plan_code"),
    )
    slug: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(200))
    synopsis: Mapped[str] = mapped_column(Text, server_default="")
    status: Mapped[str] = mapped_column(String(16), server_default="draft")
    required_plan_code: Mapped[str] = mapped_column(
        ForeignKey("plans.code", ondelete="RESTRICT", name="fk_comics_required_plan_code"),
        server_default="free",
    )
    chapters: Mapped[list["Chapter"]] = relationship(
        back_populates="comic",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Chapter(Identity, Timestamps, Base):
    __tablename__ = "chapters"
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    __table_args__ = (
        UniqueConstraint("comic_id", "chapter_number", name="uq_chapters_position"),
        CheckConstraint("chapter_number > 0", name="ck_chapters_position"),
        CheckConstraint("length(btrim(title)) > 0", name="ck_chapters_title"),
    )
    comic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("comics.id", ondelete="CASCADE", name="fk_chapters_comic_id"),
    )
    chapter_number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    comic: Mapped[Comic] = relationship(back_populates="chapters")
    pages: Mapped[list["ComicPage"]] = relationship(
        back_populates="chapter",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ComicPage.page_number",
    )


class ComicPage(Identity, Timestamps, Base):
    __tablename__ = "comic_pages"
    __table_args__ = (
        UniqueConstraint(
            "chapter_id",
            "page_number",
            name="uq_comic_pages_position",
            deferrable=True,
            initially="IMMEDIATE",
        ),
        UniqueConstraint("storage_key", name="uq_comic_pages_storage_key"),
        CheckConstraint("page_number > 0", name="ck_comic_pages_position"),
        CheckConstraint("width > 0 AND height > 0", name="ck_comic_pages_dimensions"),
        CheckConstraint(
            "storage_key ~ '^[a-zA-Z0-9][a-zA-Z0-9/_-]*[.](jpg|jpeg|png|webp|avif)$' "
            "AND position('..' in storage_key) = 0 AND position('//' in storage_key) = 0",
            name="ck_comic_pages_storage_key",
        ),
    )
    chapter_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE", name="fk_comic_pages_chapter_id"),
    )
    page_number: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(500))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    chapter: Mapped[Chapter] = relationship(back_populates="pages")


class ComicPageAsset(Base):
    __tablename__ = "comic_page_assets"
    __table_args__ = (
        UniqueConstraint("chapter_id", "upload_key", name="uq_comic_asset_upload"),
        CheckConstraint(
            "total_bytes > 0 AND total_bytes <= 4194304 AND octet_length(data) = total_bytes",
            name="ck_comic_asset_size",
        ),
    )
    page_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("comic_pages.id", ondelete="CASCADE", name="fk_comic_asset_page"),
        primary_key=True,
    )
    chapter_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE", name="fk_comic_asset_chapter")
    )
    upload_key: Mapped[uuid.UUID] = mapped_column(Uuid)
    source_sha256: Mapped[str] = mapped_column(String(64))
    total_bytes: Mapped[int] = mapped_column(Integer)
    data: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)


class AuthSession(Identity, Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        Index("ix_auth_sessions_user_id", "user_id"),
        Index("ix_auth_sessions_expires_at", "expires_at"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE", name="fk_auth_sessions_user_id")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (Index("ix_refresh_tokens_session_id", "session_id"),)
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("auth_sessions.id", ondelete="CASCADE", name="fk_refresh_tokens_session_id")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Genre(Identity, Base):
    __tablename__ = "genres"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_genres_slug"),
        UniqueConstraint("name", name="uq_genres_name"),
        CheckConstraint("slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="ck_genres_slug"),
        CheckConstraint("length(btrim(name)) > 0", name="ck_genres_name"),
    )
    slug: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(80))
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))


class MovieGenre(Base):
    __tablename__ = "movie_genres"
    movie_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("movies.id", ondelete="CASCADE", name="fk_movie_genres_movie"), primary_key=True
    )
    genre_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("genres.id", ondelete="RESTRICT", name="fk_movie_genres_genre"), primary_key=True
    )
    __table_args__ = (Index("ix_movie_genres_genre", "genre_id"),)


class AuditEvent(Identity, Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_created_at", "created_at"),)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL", name="fk_audit_events_actor")
    )
    action: Mapped[str] = mapped_column(String(16))
    entity_type: Mapped[str] = mapped_column(String(16))
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    changed_fields: Mapped[list[str]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UploadSession(Identity, Base):
    __tablename__ = "upload_sessions"
    __table_args__ = (
        UniqueConstraint("owner_id", "idempotency_key", name="uq_upload_owner_key"),
        CheckConstraint(
            "total_bytes > 0 AND received_bytes >= 0 AND received_bytes <= total_bytes",
            name="ck_upload_size",
        ),
        CheckConstraint(
            "status IN ('uploading','sealed','cancelled','expired')", name="ck_upload_status"
        ),
        Index("ix_upload_episode", "episode_id"),
        Index("ix_upload_cleanup", "reserved", "expires_at"),
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL", name="fk_upload_owner")
    )
    episode_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("episodes.id", ondelete="SET NULL", name="fk_upload_episode")
    )
    idempotency_key: Mapped[uuid.UUID] = mapped_column(Uuid)
    filename: Mapped[str] = mapped_column(String(200))
    total_bytes: Mapped[int] = mapped_column(BigInteger)
    received_bytes: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))
    status: Mapped[str] = mapped_column(String(16), server_default="uploading")
    reserved_bytes: Mapped[int] = mapped_column(BigInteger)
    reserved: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class UploadChunk(Base):
    __tablename__ = "upload_chunks"
    upload_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("upload_sessions.id", ondelete="CASCADE", name="fk_chunk_upload"),
        primary_key=True,
    )
    offset: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    __table_args__ = (CheckConstraint('"offset" >= 0 AND size > 0', name="ck_chunk_size"),)


class MediaJob(Identity, Base):
    __tablename__ = "media_jobs"
    __table_args__ = (
        UniqueConstraint("upload_id", name="uq_media_job_upload"),
        CheckConstraint(
            "status IN ('queued','processing','ready','failed','cancelled')",
            name="ck_media_job_status",
        ),
        Index("ix_media_job_dispatch", "status", "started_at"),
    )
    upload_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("upload_sessions.id", ondelete="CASCADE", name="fk_media_job_upload")
    )
    status: Mapped[str] = mapped_column(String(16), server_default="queued")
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    error_code: Mapped[str | None] = mapped_column(String(40))
    source_sha256: Mapped[str | None] = mapped_column(String(64))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MediaVariant(Identity, Base):
    __tablename__ = "media_variants"
    __table_args__ = (UniqueConstraint("job_id", "profile", name="uq_media_variant_profile"),)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("media_jobs.id", ondelete="CASCADE", name="fk_media_variant_job")
    )
    profile: Mapped[str] = mapped_column(String(24))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    total_bytes: Mapped[int] = mapped_column(BigInteger)


class SubtitleTrack(Identity, Base):
    __tablename__ = "subtitle_tracks"
    __table_args__ = (UniqueConstraint("job_id", "language", name="uq_subtitle_language"),)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("media_jobs.id", ondelete="CASCADE", name="fk_subtitle_job")
    )
    language: Mapped[str] = mapped_column(String(12))
    label: Mapped[str] = mapped_column(String(80))
    content: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))


class ContentGrant(Identity, Base):
    __tablename__ = "content_grants"
    __table_args__ = (
        CheckConstraint(
            "plan_code IN ('vip','premium') AND device_limit BETWEEN 1 AND 20 "
            "AND expires_at > starts_at",
            name="ck_content_grant",
        ),
        Index("ix_content_grant_user", "user_id", "expires_at"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE", name="fk_content_grant_user")
    )
    plan_code: Mapped[str] = mapped_column(String(16))
    device_limit: Mapped[int] = mapped_column(Integer)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ContentDevice(Base):
    __tablename__ = "content_devices"
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("auth_sessions.id", ondelete="CASCADE", name="fk_content_device_session"),
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE", name="fk_content_device_user")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (Index("ix_content_device_user_expiry", "user_id", "expires_at"),)


class ReadingProgress(Base):
    __tablename__ = "reading_progress"
    __table_args__ = (
        CheckConstraint(
            "offset_milli BETWEEN 0 AND 1000 AND version > 0", name="ck_reading_bounds"
        ),
        CheckConstraint("mode IN ('vertical','paged')", name="ck_reading_mode"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE", name="fk_reading_user"), primary_key=True
    )
    chapter_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE", name="fk_reading_chapter"), primary_key=True
    )
    page_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("comic_pages.id", ondelete="SET NULL", name="fk_reading_page")
    )
    offset_milli: Mapped[int] = mapped_column(Integer)
    mode: Mapped[str] = mapped_column(String(16))
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WatchProgress(Base):
    __tablename__ = "watch_progress"
    __table_args__ = (
        CheckConstraint(
            "position_ms BETWEEN 0 AND 3600000 AND version > 0", name="ck_watch_bounds"
        ),
        Index("ix_watch_recent", "user_id", "updated_at"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE", name="fk_watch_user"), primary_key=True
    )
    episode_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("episodes.id", ondelete="CASCADE", name="fk_watch_episode"), primary_key=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("media_jobs.id", ondelete="CASCADE", name="fk_watch_job")
    )
    position_ms: Mapped[int] = mapped_column(Integer)
    completed: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
