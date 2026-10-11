"""Admin comic CRUD and atomic, bounded image uploads and page ordering."""

import hashlib
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select, text

from app.admin_catalogue import DB, Actor, locked, record
from app.auth import require_admin
from app.catalogue import search_pattern
from app.comic_image import ImageBusy, decode_private_image
from app.models import Chapter, Comic, ComicPage, ComicPageAsset

router = APIRouter(
    prefix="/admin/comics", tags=["admin comics"], dependencies=[Depends(require_admin)]
)


class ComicInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=200)
    slug: str = Field(max_length=200, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    synopsis: str = Field(default="", max_length=5000)
    status: Literal["draft", "published", "archived"] = "draft"
    required_plan_code: Literal["free", "vip", "premium"] = "free"


class ComicEdit(ComicInput):
    version: int = Field(ge=1)


class ChapterInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=200)
    chapter_number: int = Field(ge=1, le=100000)


class ChapterEdit(ChapterInput):
    version: int = Field(ge=1)


class Reorder(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)
    page_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)


def comic_view(row):
    return {
        key: getattr(row, key)
        for key in ("id", "title", "slug", "synopsis", "status", "required_plan_code", "version")
    }


def chapter_view(row):
    return {
        key: getattr(row, key) for key in ("id", "comic_id", "title", "chapter_number", "version")
    }


def page_view(row):
    return {key: getattr(row, key) for key in ("id", "page_number", "width", "height")}


def chapter_for(db, comic_id, chapter_id, version=None, lock=False):
    row = (
        db.scalar(
            select(Chapter)
            .where(Chapter.id == chapter_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if lock
        else db.get(Chapter, chapter_id)
    )
    if not row or row.comic_id != comic_id:
        raise HTTPException(404, "Không tìm thấy chương.")
    if version is not None and row.version != version:
        raise HTTPException(409, "Chương đã thay đổi. Tải lại trước khi lưu.")
    return row


@router.get("")
def list_comics(db: DB, q: str = Query("", max_length=100), page: int = Query(1, ge=1, le=1000)):
    query = select(Comic)
    if q.strip():
        query = query.where(Comic.title.ilike(search_pattern(q), escape="\\"))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(
        query.order_by(Comic.created_at.desc(), Comic.id).offset((page - 1) * 20).limit(20)
    )
    return {"items": [comic_view(r) for r in rows], "total": total, "page": page, "page_size": 20}


@router.post("", status_code=201)
def create_comic(data: ComicInput, actor: Actor, db: DB):
    row = Comic(**data.model_dump())
    db.add(row)
    record(db, actor, "create", "comic", row, data.model_fields_set)
    return comic_view(row)


@router.get("/{identifier}")
def read_comic(identifier: uuid.UUID, db: DB):
    row = db.get(Comic, identifier)
    if not row:
        raise HTTPException(404, "Không tìm thấy truyện.")
    return comic_view(row)


@router.put("/{identifier}")
def update_comic(identifier: uuid.UUID, data: ComicEdit, actor: Actor, db: DB):
    row = locked(db, Comic, identifier, data.version)
    for key, value in data.model_dump(exclude={"version"}).items():
        setattr(row, key, value)
    row.version += 1
    record(db, actor, "update", "comic", row, data.model_fields_set)
    return comic_view(row)


@router.delete("/{identifier}", status_code=204)
def delete_comic(identifier: uuid.UUID, actor: Actor, db: DB, version: int = Query(ge=1)):
    row = locked(db, Comic, identifier, version)
    record(db, actor, "delete", "comic", row)
    db.delete(row)


@router.get("/{identifier}/chapters")
def list_chapters(identifier: uuid.UUID, db: DB, page: int = Query(1, ge=1, le=1000)):
    read_comic(identifier, db)
    query = select(Chapter).where(Chapter.comic_id == identifier)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(Chapter.chapter_number).offset((page - 1) * 20).limit(20))
    return {"items": [chapter_view(r) for r in rows], "total": total, "page": page, "page_size": 20}


@router.post("/{identifier}/chapters", status_code=201)
def create_chapter(identifier: uuid.UUID, data: ChapterInput, actor: Actor, db: DB):
    locked(db, Comic, identifier)
    row = Chapter(comic_id=identifier, **data.model_dump())
    db.add(row)
    record(db, actor, "create", "chapter", row, data.model_fields_set)
    return chapter_view(row)


@router.put("/{identifier}/chapters/{chapter_id}")
def update_chapter(
    identifier: uuid.UUID, chapter_id: uuid.UUID, data: ChapterEdit, actor: Actor, db: DB
):
    row = chapter_for(db, identifier, chapter_id, data.version, True)
    row.title, row.chapter_number = data.title, data.chapter_number
    row.version += 1
    record(db, actor, "update", "chapter", row, {"title", "chapter_number"})
    return chapter_view(row)


@router.delete("/{identifier}/chapters/{chapter_id}", status_code=204)
def delete_chapter(
    identifier: uuid.UUID, chapter_id: uuid.UUID, actor: Actor, db: DB, version: int = Query(ge=1)
):
    row = chapter_for(db, identifier, chapter_id, version, True)
    record(db, actor, "delete", "chapter", row)
    db.delete(row)


@router.get("/{identifier}/chapters/{chapter_id}/pages")
def list_pages(identifier: uuid.UUID, chapter_id: uuid.UUID, db: DB):
    chapter = chapter_for(db, identifier, chapter_id)
    pages = db.scalars(
        select(ComicPage)
        .where(ComicPage.chapter_id == chapter_id)
        .order_by(ComicPage.page_number)
        .limit(500)
    )
    return {"chapter": chapter_view(chapter), "items": [page_view(p) for p in pages]}


@router.post("/{identifier}/chapters/{chapter_id}/pages", status_code=201)
def upload_page(
    identifier: uuid.UUID,
    chapter_id: uuid.UUID,
    request: Request,
    actor: Actor,
    db: DB,
    data: Annotated[bytes, Body(media_type="application/octet-stream")],
    sha256: Annotated[str, Header(alias="X-Chunk-SHA256", pattern=r"^[a-f0-9]{64}$")],
    upload_key: uuid.UUID,
    version: int = Query(ge=1),
):
    chapter_for(db, identifier, chapter_id)
    if (
        request.headers.get("content-type") != "application/octet-stream"
        or hashlib.sha256(data).hexdigest() != sha256
    ):
        raise HTTPException(422, "Kiểu dữ liệu hoặc checksum không hợp lệ.")
    # Repeated request after a lost response must not create another page.
    existing = db.scalar(
        select(ComicPageAsset).where(
            ComicPageAsset.chapter_id == chapter_id, ComicPageAsset.upload_key == upload_key
        )
    )
    if existing:
        if existing.source_sha256 != sha256:
            raise HTTPException(409, "Khóa upload đã dùng cho ảnh khác.")
        return {
            "page": page_view(db.get(ComicPage, existing.page_id)),
            "chapter": chapter_view(chapter_for(db, identifier, chapter_id)),
        }
    try:
        width, height, encoded = decode_private_image(data)
    except ImageBusy:
        raise HTTPException(
            429, "Đang xử lý ảnh khác. Thử lại sau.", headers={"Retry-After": "3"}
        ) from None
    except ValueError:
        raise HTTPException(
            422, "Ảnh cần JPEG/PNG/WebP tĩnh, tối đa 8 MiB và 12 triệu pixel; không SVG/ảnh động."
        ) from None
    db.execute(text("SELECT pg_advisory_xact_lock(731008)"))
    chapter = chapter_for(db, identifier, chapter_id, lock=True)
    existing = db.scalar(
        select(ComicPageAsset).where(
            ComicPageAsset.chapter_id == chapter_id, ComicPageAsset.upload_key == upload_key
        )
    )
    if existing:
        if existing.source_sha256 != sha256:
            raise HTTPException(409, "Khóa upload đã dùng cho ảnh khác.")
        return {
            "page": page_view(db.get(ComicPage, existing.page_id)),
            "chapter": chapter_view(chapter),
        }
    if chapter.version != version:
        raise HTTPException(409, "Chương đã thay đổi. Tải lại trước khi upload tiếp.")
    count = db.scalar(
        select(func.count()).select_from(ComicPage).where(ComicPage.chapter_id == chapter_id)
    )
    if count >= 500:
        raise HTTPException(422, "Tối đa 500 trang/chương.")
    used = db.scalar(select(func.coalesce(func.sum(ComicPageAsset.total_bytes), 0)))
    if used + len(encoded) > request.app.state.settings.comic_quota_bytes:
        raise HTTPException(507, "Đã đạt quota ảnh truyện.")
    position = (
        db.scalar(
            select(func.coalesce(func.max(ComicPage.page_number), 0)).where(
                ComicPage.chapter_id == chapter_id
            )
        )
        + 1
    )
    page_id = uuid.uuid4()
    page = ComicPage(
        id=page_id,
        chapter_id=chapter_id,
        page_number=position,
        width=width,
        height=height,
        storage_key=f"comics/{chapter_id}/{page_id}.jpg",
    )
    db.add(page)
    db.flush()
    db.add(
        ComicPageAsset(
            page_id=page_id,
            chapter_id=chapter_id,
            upload_key=upload_key,
            source_sha256=sha256,
            total_bytes=len(encoded),
            data=encoded,
        )
    )
    chapter.version += 1
    record(
        db, actor, "create", "comic_page", page, {"chapter_id", "page_number", "width", "height"}
    )
    return {"page": page_view(page), "chapter": chapter_view(chapter)}


@router.get("/{identifier}/chapters/{chapter_id}/pages/{page_id}/image")
def page_image(identifier: uuid.UUID, chapter_id: uuid.UUID, page_id: uuid.UUID, db: DB):
    chapter_for(db, identifier, chapter_id)
    page = db.get(ComicPage, page_id)
    asset = db.get(ComicPageAsset, page_id)
    if not page or page.chapter_id != chapter_id or not asset:
        raise HTTPException(404, "Không tìm thấy ảnh.")
    return Response(asset.data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.put("/{identifier}/chapters/{chapter_id}/pages/order")
def reorder_pages(
    identifier: uuid.UUID, chapter_id: uuid.UUID, data: Reorder, actor: Actor, db: DB
):
    chapter = chapter_for(db, identifier, chapter_id, data.version, True)
    pages = list(db.scalars(select(ComicPage).where(ComicPage.chapter_id == chapter_id)))
    if len(set(data.page_ids)) != len(data.page_ids) or set(data.page_ids) != {p.id for p in pages}:
        raise HTTPException(422, "Danh sách phải chứa đúng mỗi trang của chương một lần.")
    db.execute(text("SET CONSTRAINTS uq_comic_pages_position DEFERRED"))
    by_id = {p.id: p for p in pages}
    for index, page_id in enumerate(data.page_ids, 1):
        by_id[page_id].page_number = index
    chapter.version += 1
    record(db, actor, "reorder", "chapter", chapter, {"page_order"})
    return list_pages(identifier, chapter_id, db)


@router.delete("/{identifier}/chapters/{chapter_id}/pages/{page_id}", status_code=204)
def delete_page(
    identifier: uuid.UUID,
    chapter_id: uuid.UUID,
    page_id: uuid.UUID,
    actor: Actor,
    db: DB,
    version: int = Query(ge=1),
):
    chapter = chapter_for(db, identifier, chapter_id, version, True)
    page = db.get(ComicPage, page_id)
    if not page or page.chapter_id != chapter_id:
        raise HTTPException(404, "Không tìm thấy trang.")
    record(db, actor, "delete", "comic_page", page)
    db.execute(delete(ComicPage).where(ComicPage.id == page_id))
    db.execute(text("SET CONSTRAINTS uq_comic_pages_position DEFERRED"))
    remaining = db.scalars(
        select(ComicPage).where(ComicPage.chapter_id == chapter_id).order_by(ComicPage.page_number)
    )
    for index, row in enumerate(remaining, 1):
        row.page_number = index
    chapter.version += 1
