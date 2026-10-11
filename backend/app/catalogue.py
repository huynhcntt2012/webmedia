"""Public metadata only. Playback authorization belongs to the media stage."""

import unicodedata
from typing import Literal

from fastapi import APIRouter, HTTPException, Path, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.media_urls import poster_url, trailer_url
from app.models import Movie

router = APIRouter(prefix="/movies", tags=["catalogue"])


class MovieView(BaseModel):
    slug: str
    title: str
    synopsis: str
    release_year: int | None
    required_plan_code: str
    poster_url: str | None
    trailer_url: str | None
    genres: list[str]


class MovieList(BaseModel):
    items: list[MovieView]
    total: int
    page: int
    page_size: int


def search_pattern(value: str) -> str:
    value = unicodedata.normalize("NFC", value.strip())
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def view(movie: Movie, hosts: str) -> MovieView:
    try:
        poster = poster_url(movie.poster_url, hosts)
    except ValueError:
        poster = None
    try:
        trailer = trailer_url(movie.trailer_url)
    except ValueError:
        trailer = None
    return MovieView(
        slug=movie.slug,
        title=movie.title,
        synopsis=movie.synopsis,
        release_year=movie.release_year,
        required_plan_code=movie.required_plan_code,
        poster_url=poster,
        trailer_url=trailer,
        genres=sorted(genre.name for genre in movie.genres),
    )


@router.get("", response_model=MovieList)
def movies(
    request: Request,
    q: str = Query(default="", max_length=100),
    page: int = Query(default=1, ge=1, le=1000),
    page_size: int = Query(default=24, ge=1, le=48),
    sort: Literal["newest", "title"] = "newest",
):
    conditions = [Movie.status == "published"]
    if q.strip():
        # PostgreSQL UTF-8 normalize handles composed/decomposed Vietnamese text.
        conditions.append(func.normalize(Movie.title).ilike(search_pattern(q), escape="\\"))
    order = (
        (Movie.created_at.desc(), Movie.id.desc())
        if sort == "newest"
        else (
            func.lower(Movie.title),
            Movie.id,
        )
    )
    try:
        with Session(request.app.state.auth_engine) as db:
            total = db.scalar(select(func.count()).select_from(Movie).where(*conditions))
            rows = db.scalars(
                select(Movie)
                .where(*conditions)
                .order_by(*order)
                .limit(page_size)
                .offset((page - 1) * page_size)
            )
            return MovieList(
                items=[view(row, request.app.state.settings.poster_allowed_hosts) for row in rows],
                total=total or 0,
                page=page,
                page_size=page_size,
            )
    except SQLAlchemyError:
        raise HTTPException(503, "Thư viện tạm thời không sẵn sàng.") from None


@router.get("/{slug}", response_model=MovieView)
def movie(request: Request, slug: str = Path(max_length=200, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")):
    try:
        with Session(request.app.state.auth_engine) as db:
            row = db.scalar(select(Movie).where(Movie.slug == slug, Movie.status == "published"))
            if row is None:
                raise HTTPException(404, "Không tìm thấy phim.")
            return view(row, request.app.state.settings.poster_allowed_hosts)
    except SQLAlchemyError:
        raise HTTPException(503, "Thư viện tạm thời không sẵn sàng.") from None
