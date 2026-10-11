"""Admin-only catalogue mutations, atomic audit and optimistic concurrency."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.auth import require_admin, write_guard
from app.catalogue import search_pattern
from app.database import session_scope
from app.media_urls import poster_url, trailer_url
from app.models import AuditEvent, Episode, Genre, Movie, MovieGenre, User

router = APIRouter(prefix="/admin", tags=["admin catalogue"], dependencies=[Depends(require_admin)])


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class GenreInput(Input):
    name: str = Field(min_length=1, max_length=80)
    slug: str = Field(max_length=80, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")


class GenreEdit(GenreInput):
    version: int = Field(ge=1)


class MovieInput(Input):
    title: str = Field(min_length=1, max_length=200)
    slug: str = Field(max_length=200, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    synopsis: str = Field(default="", max_length=5000)
    release_year: int | None = Field(default=None, ge=1888, le=9999)
    status: Literal["draft", "published", "archived"] = "draft"
    required_plan_code: Literal["free", "vip", "premium"] = "free"
    poster_url: str | None = Field(default=None, max_length=2048)
    trailer_url: str | None = Field(default=None, max_length=500)
    genre_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)

    @field_validator("genre_ids")
    @classmethod
    def unique_genres(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("Duplicate genres")
        return value


class MovieEdit(MovieInput):
    version: int = Field(ge=1)


class EpisodeInput(Input):
    title: str = Field(min_length=1, max_length=200)
    season_number: int = Field(default=1, ge=1, le=10000)
    episode_number: int = Field(ge=1, le=100000)
    duration_seconds: int | None = Field(default=None, ge=1, le=604800)


class EpisodeEdit(EpisodeInput):
    version: int = Field(ge=1)


def admin_write(
    user: Annotated[User, Depends(require_admin)], guard: Annotated[None, Depends(write_guard)]
):
    return user


Actor = Annotated[User, Depends(admin_write)]


def database(request: Request):
    try:
        with session_scope(request.app.state.auth_engine) as db:
            yield db
    except IntegrityError:
        raise HTTPException(
            409, "Dữ liệu trùng hoặc đang được sử dụng. Kiểm tra slug, thể loại và số tập."
        ) from None
    except SQLAlchemyError:
        raise HTTPException(503, "Dịch vụ dữ liệu tạm thời không sẵn sàng.") from None


DB = Annotated[object, Depends(database, scope="function")]


def record(db, actor, action, kind, row, fields=()):
    db.flush()
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action=action,
            entity_type=kind,
            entity_id=row.id,
            changed_fields=sorted(fields),
        )
    )


def locked(db, model, identifier, version=None):
    row = db.get(model, identifier, with_for_update=True)
    if row is None:
        raise HTTPException(404, "Không tìm thấy bản ghi.")
    if version is not None and row.version != version:
        raise HTTPException(409, "Bản ghi đã thay đổi. Tải lại trước khi lưu hoặc xóa.")
    return row


def genre_view(row):
    return {"id": row.id, "name": row.name, "slug": row.slug, "version": row.version}


def movie_view(row):
    return {
        key: getattr(row, key)
        for key in (
            "id",
            "title",
            "slug",
            "synopsis",
            "release_year",
            "status",
            "required_plan_code",
            "poster_url",
            "trailer_url",
            "version",
        )
    } | {"genres": [genre_view(g) for g in sorted(row.genres, key=lambda x: x.name)]}


def episode_view(row):
    return {
        key: getattr(row, key)
        for key in (
            "id",
            "movie_id",
            "title",
            "season_number",
            "episode_number",
            "duration_seconds",
            "version",
        )
    }


def movie_values(data, request, db):
    values = data.model_dump(exclude={"genre_ids", "version"})
    try:
        values["poster_url"] = poster_url(
            values["poster_url"], request.app.state.settings.poster_allowed_hosts
        )
        values["trailer_url"] = trailer_url(values["trailer_url"])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    genres = list(
        db.scalars(
            select(Genre).where(Genre.id.in_(data.genre_ids)).order_by(Genre.id).with_for_update()
        )
    )
    if len(genres) != len(data.genre_ids):
        raise HTTPException(422, "Thể loại không tồn tại.")
    return values, genres


@router.get("/catalogue-settings")
def settings(request: Request):
    return {
        "upload_max_bytes": request.app.state.settings.upload_max_bytes,
        "poster_allowed_hosts": [
            h for h in request.app.state.settings.poster_allowed_hosts.split(",") if h
        ],
    }


@router.get("/genres")
def genres(db: DB, page: int = Query(1, ge=1, le=1000)):
    return {
        "items": [
            genre_view(g)
            for g in db.scalars(
                select(Genre).order_by(Genre.name, Genre.id).offset((page - 1) * 100).limit(100)
            )
        ],
        "total": db.scalar(select(func.count()).select_from(Genre)),
        "page": page,
    }


@router.post("/genres", status_code=201)
def create_genre(data: GenreInput, actor: Actor, db: DB):
    row = Genre(**data.model_dump())
    db.add(row)
    record(db, actor, "create", "genre", row, data.model_fields_set)
    return genre_view(row)


@router.put("/genres/{identifier}")
def edit_genre(identifier: uuid.UUID, data: GenreEdit, actor: Actor, db: DB):
    row = locked(db, Genre, identifier, data.version)
    for key, value in data.model_dump(exclude={"version"}).items():
        setattr(row, key, value)
    row.version += 1
    record(db, actor, "update", "genre", row, {"name", "slug"})
    return genre_view(row)


@router.delete("/genres/{identifier}", status_code=204)
def delete_genre(identifier: uuid.UUID, actor: Actor, db: DB, version: int = Query(ge=1)):
    row = locked(db, Genre, identifier, version)
    if db.scalar(select(MovieGenre.movie_id).where(MovieGenre.genre_id == identifier).limit(1)):
        raise HTTPException(409, "Thể loại đang gắn với phim; hãy bỏ liên kết trước.")
    record(db, actor, "delete", "genre", row)
    db.delete(row)


@router.get("/movies")
def movies(
    db: DB,
    page: int = Query(1, ge=1, le=1000),
    q: str = Query("", max_length=100),
    status: Literal["draft", "published", "archived"] | None = None,
):
    conditions = []
    if q.strip():
        conditions.append(func.normalize(Movie.title).ilike(search_pattern(q), escape="\\"))
    if status:
        conditions.append(Movie.status == status)
    rows = db.scalars(
        select(Movie)
        .where(*conditions)
        .order_by(Movie.created_at.desc(), Movie.id.desc())
        .offset((page - 1) * 20)
        .limit(20)
    )
    return {
        "items": [movie_view(row) for row in rows],
        "page": page,
        "total": db.scalar(select(func.count()).select_from(Movie).where(*conditions)),
    }


@router.get("/movies/{identifier}")
def movie(identifier: uuid.UUID, db: DB):
    row = db.get(Movie, identifier)
    if not row:
        raise HTTPException(404, "Không tìm thấy phim.")
    return movie_view(row)


@router.post("/movies", status_code=201)
def create_movie(data: MovieInput, request: Request, actor: Actor, db: DB):
    values, genres = movie_values(data, request, db)
    row = Movie(**values, genres=genres)
    db.add(row)
    record(db, actor, "create", "movie", row, data.model_fields_set)
    return movie_view(row)


@router.put("/movies/{identifier}")
def edit_movie(identifier: uuid.UUID, data: MovieEdit, request: Request, actor: Actor, db: DB):
    row = locked(db, Movie, identifier, data.version)
    values, genres = movie_values(data, request, db)
    for key, value in values.items():
        setattr(row, key, value)
    row.genres = genres
    row.version += 1
    record(db, actor, "update", "movie", row, set(values) | {"genre_ids"})
    return movie_view(row)


@router.delete("/movies/{identifier}", status_code=204)
def delete_movie(identifier: uuid.UUID, actor: Actor, db: DB, version: int = Query(ge=1)):
    row = locked(db, Movie, identifier, version)
    record(db, actor, "delete", "movie", row)
    db.delete(row)


def parent(db, movie_id):
    return locked(db, Movie, movie_id)


@router.get("/movies/{movie_id}/episodes")
def episodes(movie_id: uuid.UUID, db: DB, page: int = Query(1, ge=1, le=1000)):
    if not db.get(Movie, movie_id):
        raise HTTPException(404, "Không tìm thấy phim.")
    rows = db.scalars(
        select(Episode)
        .where(Episode.movie_id == movie_id)
        .order_by(Episode.season_number, Episode.episode_number)
        .offset((page - 1) * 50)
        .limit(50)
    )
    return {
        "items": [episode_view(row) for row in rows],
        "page": page,
        "total": db.scalar(
            select(func.count()).select_from(Episode).where(Episode.movie_id == movie_id)
        ),
    }


@router.post("/movies/{movie_id}/episodes", status_code=201)
def create_episode(movie_id: uuid.UUID, data: EpisodeInput, actor: Actor, db: DB):
    parent(db, movie_id)
    row = Episode(movie_id=movie_id, **data.model_dump())
    db.add(row)
    record(db, actor, "create", "episode", row, data.model_fields_set)
    return episode_view(row)


def owned_episode(db, movie_id, identifier, version):
    parent(db, movie_id)
    row = locked(db, Episode, identifier, version)
    if row.movie_id != movie_id:
        raise HTTPException(404, "Không tìm thấy tập trong phim này.")
    return row


@router.put("/movies/{movie_id}/episodes/{identifier}")
def edit_episode(
    movie_id: uuid.UUID, identifier: uuid.UUID, data: EpisodeEdit, actor: Actor, db: DB
):
    row = owned_episode(db, movie_id, identifier, data.version)
    for key, value in data.model_dump(exclude={"version"}).items():
        setattr(row, key, value)
    row.version += 1
    record(db, actor, "update", "episode", row, data.model_fields_set - {"version"})
    return episode_view(row)


@router.delete("/movies/{movie_id}/episodes/{identifier}", status_code=204)
def delete_episode(
    movie_id: uuid.UUID, identifier: uuid.UUID, actor: Actor, db: DB, version: int = Query(ge=1)
):
    row = owned_episode(db, movie_id, identifier, version)
    record(db, actor, "delete", "episode", row)
    db.delete(row)


@router.get("/audit-events")
def audit_events(db: DB, page: int = Query(1, ge=1, le=1000)):
    rows = db.scalars(
        select(AuditEvent)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .offset((page - 1) * 50)
        .limit(50)
    )
    return {
        "items": [
            {
                key: getattr(row, key)
                for key in (
                    "id",
                    "actor_id",
                    "action",
                    "entity_type",
                    "entity_id",
                    "changed_fields",
                    "created_at",
                )
            }
            for row in rows
        ],
        "page": page,
        "total": db.scalar(select(func.count()).select_from(AuditEvent)),
    }
