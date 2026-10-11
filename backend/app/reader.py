"""Published comic metadata and session-authorized private reader."""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert

from app.admin_catalogue import DB
from app.admin_comics import page_view
from app.auth import write_guard
from app.catalogue import search_pattern
from app.content_access import ContentViewer, entitled
from app.models import Chapter, Comic, ComicPage, ComicPageAsset, ReadingProgress

router = APIRouter(tags=["comic reader"])


def comic_info(row):
    return {key: getattr(row, key) for key in ("title", "slug", "synopsis", "required_plan_code")}


def published(db, slug):
    row = db.scalar(select(Comic).where(Comic.slug == slug, Comic.status == "published"))
    if not row:
        raise HTTPException(404, "Không tìm thấy truyện.")
    return row


@router.get("/comics")
def comics(db: DB, q: str = Query("", max_length=100), page: int = Query(1, ge=1, le=1000)):
    filters = [Comic.status == "published"]
    if q.strip():
        filters.append(Comic.title.ilike(search_pattern(q.strip()), escape="\\"))
    rows = db.scalars(
        select(Comic)
        .where(*filters)
        .order_by(Comic.title, Comic.id)
        .offset((page - 1) * 20)
        .limit(20)
    )
    return {
        "items": [comic_info(row) for row in rows],
        "page": page,
        "total": db.scalar(select(func.count()).select_from(Comic).where(*filters)),
    }


@router.get("/comics/{slug}")
def comic_detail(slug: str, db: DB, page: int = Query(1, ge=1, le=1000)):
    row = published(db, slug)
    chapters = db.scalars(
        select(Chapter)
        .where(Chapter.comic_id == row.id)
        .order_by(Chapter.chapter_number)
        .offset((page - 1) * 20)
        .limit(20)
    )
    return {
        "comic": comic_info(row),
        "page": page,
        "total": db.scalar(
            select(func.count()).select_from(Chapter).where(Chapter.comic_id == row.id)
        ),
        "items": [
            {"id": ch.id, "title": ch.title, "chapter_number": ch.chapter_number} for ch in chapters
        ],
    }


def readable(db, identifier, user, lock=False):
    statement = select(Chapter).where(Chapter.id == identifier)
    if lock:
        statement = statement.with_for_update()
    chapter = db.scalar(statement)
    comic = db.get(Comic, chapter.comic_id) if chapter else None
    if not comic or comic.status != "published":
        raise HTTPException(404, "Chương không còn được xuất bản.")
    if not entitled(db, comic, user):
        raise HTTPException(403, "Nội dung thuộc gói chưa mở quyền đọc.")
    return chapter, comic


def page_query(chapter_id):
    return (
        select(ComicPage)
        .join(ComicPageAsset, ComicPageAsset.page_id == ComicPage.id)
        .where(ComicPage.chapter_id == chapter_id, ComicPageAsset.chapter_id == chapter_id)
    )


@router.get("/reader/chapters/{identifier}")
def reader(identifier: uuid.UUID, actor: ContentViewer, db: DB):
    chapter, comic = readable(db, identifier, actor)
    pages = list(db.scalars(page_query(identifier).order_by(ComicPage.page_number).limit(500)))
    saved = db.get(ReadingProgress, (actor.id, identifier))
    valid = saved and any(p.id == saved.page_id for p in pages)
    return {
        "title": chapter.title,
        "comic": comic_info(comic),
        "chapter_version": chapter.version,
        "pages": [page_view(p) for p in pages],
        "progress": {
            "page_id": saved.page_id if valid else (pages[0].id if pages else None),
            "offset_milli": saved.offset_milli if valid else 0,
            "mode": saved.mode if saved else "vertical",
            "version": saved.version if saved else 0,
        },
    }


@router.get("/reader/chapters/{identifier}/pages/{page_id}/image")
def image(identifier: uuid.UUID, page_id: uuid.UUID, actor: ContentViewer, db: DB):
    readable(db, identifier, actor)
    page = db.scalar(page_query(identifier).where(ComicPage.id == page_id))
    if not page:
        raise HTTPException(404, "Không tìm thấy trang.")
    asset = db.get(ComicPageAsset, page_id)
    return Response(asset.data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


class ReadingInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    page_id: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
    offset_milli: int = Field(ge=0, le=1000)
    mode: Literal["vertical", "paged"]
    version: int = Field(ge=0, le=2147483646)
    chapter_version: int = Field(ge=1, le=2147483646)


@router.put("/reader/chapters/{identifier}/progress", dependencies=[Depends(write_guard)])
def save_progress(identifier: uuid.UUID, data: ReadingInput, actor: ContentViewer, db: DB):
    chapter, _ = readable(db, identifier, actor, lock=True)
    if chapter.version != data.chapter_version:
        raise HTTPException(409, "Chương đã thay đổi. Tải lại trước khi lưu vị trí.")
    page = db.scalar(page_query(identifier).where(ComicPage.id == uuid.UUID(data.page_id)))
    if not page:
        raise HTTPException(422, "Trang không thuộc chương này hoặc chưa sẵn sàng.")
    values = dict(
        page_id=page.id,
        offset_milli=data.offset_milli,
        mode=data.mode,
        version=data.version + 1,
        updated_at=func.now(),
    )
    if data.version == 0:
        statement = (
            insert(ReadingProgress)
            .values(user_id=actor.id, chapter_id=identifier, **values)
            .on_conflict_do_nothing(index_elements=["user_id", "chapter_id"])
        )
    else:
        statement = (
            update(ReadingProgress)
            .where(
                ReadingProgress.user_id == actor.id,
                ReadingProgress.chapter_id == identifier,
                ReadingProgress.version == data.version,
            )
            .values(**values)
        )
    version = db.scalar(statement.returning(ReadingProgress.version))
    if version is None:
        raise HTTPException(409, "Vị trí đã đổi ở tab hoặc thiết bị khác. Tải lại trang.")
    return {"version": version}
