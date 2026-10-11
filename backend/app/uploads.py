"""Admin-owned, fixed-size chunks with checksums and durable completion."""

import hashlib
import os
import shutil
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, or_, select, text

from app.admin_catalogue import DB, Actor, record
from app.auth import require_admin
from app.media_storage import CHUNK_BYTES, OUTPUT_RESERVE, mp4_magic, upload_dir
from app.models import Episode, MediaJob, MediaVariant, UploadChunk, UploadSession, User

router = APIRouter(prefix="/admin", tags=["video uploads"], dependencies=[Depends(require_admin)])
Admin = Annotated[User, Depends(require_admin)]


def enqueue(identifier):
    from app.media_tasks import enqueue as dispatch

    return dispatch(identifier)


class StartUpload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    episode_id: uuid.UUID
    idempotency_key: uuid.UUID
    filename: str = Field(min_length=5, max_length=200)
    total_bytes: int = Field(gt=0, le=2147483648)
    content_type: Literal["video/mp4"]

    @field_validator("filename")
    @classmethod
    def filename_only(cls, value):
        if (
            not value.lower().endswith(".mp4")
            or any(c in value for c in "/\\\x00")
            or ".." in value
            or any(ord(c) < 32 for c in value)
        ):
            raise ValueError("MP4 filename required")
        return value


def owned(db, identifier, actor, lock=False):
    row = db.get(UploadSession, identifier, with_for_update=lock)
    if not row or row.owner_id != actor.id or not row.episode_id:
        raise HTTPException(404, "Không tìm thấy phiên upload.")
    return row


def describe(db, row):
    job = db.scalar(select(MediaJob).where(MediaJob.upload_id == row.id))
    variants = (
        []
        if not job
        else list(db.scalars(select(MediaVariant).where(MediaVariant.job_id == job.id)))
    )
    chunks = db.scalars(
        select(UploadChunk).where(UploadChunk.upload_id == row.id).order_by(UploadChunk.offset)
    )
    return {
        "id": row.id,
        "episode_id": row.episode_id,
        "filename": row.filename,
        "total_bytes": row.total_bytes,
        "received_bytes": row.received_bytes,
        "status": row.status,
        "expires_at": row.expires_at,
        "chunk_bytes": CHUNK_BYTES,
        "chunks": [{"offset": c.offset, "size": c.size, "sha256": c.sha256} for c in chunks],
        "job": None
        if not job
        else {
            "id": job.id,
            "status": job.status,
            "attempts": job.attempts,
            "error_code": job.error_code,
            "duration_seconds": job.duration_seconds,
            "variants": [
                {"profile": v.profile, "width": v.width, "height": v.height} for v in variants
            ],
        },
    }


@router.post("/uploads", status_code=201)
def start(data: StartUpload, request: Request, actor: Actor, db: DB):
    settings = request.app.state.settings
    if data.total_bytes > settings.upload_max_bytes:
        raise HTTPException(413, "Video vượt giới hạn dung lượng cho phép.")
    db.execute(text("SELECT pg_advisory_xact_lock(731006)"))
    previous = db.scalar(
        select(UploadSession).where(
            UploadSession.owner_id == actor.id,
            UploadSession.idempotency_key == data.idempotency_key,
        )
    )
    if previous:
        if (previous.episode_id, previous.filename, previous.total_bytes) != (
            data.episode_id,
            data.filename,
            data.total_bytes,
        ):
            raise HTTPException(409, "Khóa upload đã dùng cho dữ liệu khác.")
        return describe(db, previous)
    if not db.get(Episode, data.episode_id):
        raise HTTPException(404, "Không tìm thấy tập phim.")
    active = (
        select(UploadSession)
        .outerjoin(MediaJob, MediaJob.upload_id == UploadSession.id)
        .where(
            UploadSession.reserved,
            or_(UploadSession.status == "uploading", MediaJob.status.in_(["queued", "processing"])),
        )
    )
    if db.scalar(active.where(UploadSession.episode_id == data.episode_id).limit(1)):
        raise HTTPException(409, "Tập này đang có upload hoặc tác vụ xử lý.")
    count = db.scalar(
        select(func.count()).select_from(
            active.where(UploadSession.owner_id == actor.id).subquery()
        )
    )
    if count >= settings.upload_active_limit:
        raise HTTPException(429, "Đã đạt giới hạn upload đồng thời.")
    used = db.scalar(
        select(func.coalesce(func.sum(UploadSession.reserved_bytes), 0)).where(
            UploadSession.reserved
        )
    )
    if used + data.total_bytes + OUTPUT_RESERVE > settings.media_quota_bytes:
        raise HTTPException(507, "Đã đạt quota lưu trữ video.")
    if shutil.disk_usage(settings.media_root).free < data.total_bytes + OUTPUT_RESERVE + 104857600:
        raise HTTPException(507, "Không đủ dung lượng đĩa an toàn.")
    row = UploadSession(
        owner_id=actor.id,
        episode_id=data.episode_id,
        idempotency_key=data.idempotency_key,
        filename=data.filename,
        total_bytes=data.total_bytes,
        reserved_bytes=data.total_bytes + OUTPUT_RESERVE,
        expires_at=datetime.now(UTC) + timedelta(hours=24),
    )
    db.add(row)
    record(db, actor, "create", "upload", row, {"episode_id", "total_bytes"})
    return describe(db, row)


@router.get("/uploads/{identifier}")
def status(identifier: uuid.UUID, actor: Admin, db: DB):
    return describe(db, owned(db, identifier, actor))


@router.get("/episodes/{episode_id}/uploads")
def history(episode_id: uuid.UUID, actor: Admin, db: DB):
    rows = db.scalars(
        select(UploadSession)
        .where(UploadSession.episode_id == episode_id, UploadSession.owner_id == actor.id)
        .order_by(UploadSession.created_at.desc())
        .limit(10)
    )
    return {"items": [describe(db, row) for row in rows]}


@router.put("/uploads/{identifier}/chunks")
def chunk(
    identifier: uuid.UUID,
    request: Request,
    actor: Actor,
    db: DB,
    data: Annotated[bytes, Body(media_type="application/octet-stream")],
    sha256: Annotated[str, Header(alias="X-Chunk-SHA256", pattern=r"^[a-f0-9]{64}$")],
    offset: int = Query(ge=0, le=2147483648),
):
    row = owned(db, identifier, actor, lock=True)
    if row.status != "uploading" or row.expires_at <= datetime.now(UTC):
        raise HTTPException(409, "Phiên không còn nhận chunk.")
    if request.headers.get("content-type") != "application/octet-stream":
        raise HTTPException(415, "Chunk phải là application/octet-stream.")
    if not data or len(data) != min(CHUNK_BYTES, row.total_bytes - offset) or offset % CHUNK_BYTES:
        raise HTTPException(422, "Kích thước hoặc vị trí chunk không hợp lệ.")
    if hashlib.sha256(data).hexdigest() != sha256:
        raise HTTPException(422, "Checksum chunk không khớp.")
    existing = db.get(UploadChunk, (row.id, offset))
    if existing:
        if existing.sha256 != sha256 or existing.size != len(data):
            raise HTTPException(409, "Chunk đã tồn tại với nội dung khác.")
        return {"received_bytes": row.received_bytes}
    if offset != row.received_bytes:
        raise HTTPException(409, "Offset không khớp; đọc lại trạng thái upload.")
    if offset == 0 and not mp4_magic(data):
        raise HTTPException(415, "Nội dung không phải container MP4.")
    directory = upload_dir(request.app.state.settings, row.id, create=True)
    source = directory / "source.mp4"
    if source.is_symlink():
        raise HTTPException(409, "Đường dẫn lưu trữ không hợp lệ.")
    with source.open("r+b" if source.exists() else "w+b") as stream:
        if stream.seek(0, 2) < offset:
            raise HTTPException(409, "File upload thiếu dữ liệu; cần tạo phiên mới.")
        stream.truncate(offset)  # Recover a write that reached disk but not DB commit.
        stream.seek(offset)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    db.add(UploadChunk(upload_id=row.id, offset=offset, size=len(data), sha256=sha256))
    row.received_bytes += len(data)
    return {"received_bytes": row.received_bytes}


@router.post("/uploads/{identifier}/complete", status_code=202)
def complete(identifier: uuid.UUID, actor: Actor, db: DB):
    row = owned(db, identifier, actor, lock=True)
    if (
        row.status not in {"uploading", "sealed"}
        or row.expires_at <= datetime.now(UTC)
        or row.received_bytes != row.total_bytes
    ):
        raise HTTPException(409, "Upload chưa đủ dữ liệu hoặc đã hết hạn.")
    job = db.scalar(select(MediaJob).where(MediaJob.upload_id == row.id))
    if not job:
        row.status = "sealed"
        job = MediaJob(upload_id=row.id)
        db.add(job)
        record(db, actor, "create", "media_job", job, {"upload_id"})
    identifier = job.id
    db.commit()  # Durable outbox before attempting Redis; retries never create a second job.
    queued = enqueue(identifier) if job.status == "queued" else True
    return {"job_id": identifier, "dispatched": queued}


@router.post("/uploads/{identifier}/retry", status_code=202)
def retry(identifier: uuid.UUID, actor: Actor, db: DB):
    row = owned(db, identifier, actor, lock=True)
    job = db.scalar(select(MediaJob).where(MediaJob.upload_id == row.id).with_for_update())
    if (
        not job
        or job.status != "failed"
        or job.attempts >= 3
        or row.status != "sealed"
        or row.expires_at <= datetime.now(UTC)
    ):
        raise HTTPException(409, "Không thể thử lại; hãy tạo phiên upload mới.")
    job.status, job.error_code = "queued", None
    record(db, actor, "retry", "media_job", job)
    identifier = job.id
    db.commit()
    return {"job_id": identifier, "dispatched": enqueue(identifier)}


@router.delete("/uploads/{identifier}", status_code=202)
def cancel(identifier: uuid.UUID, actor: Actor, db: DB):
    row = owned(db, identifier, actor, lock=True)
    job = db.scalar(select(MediaJob).where(MediaJob.upload_id == row.id))
    if job and job.status == "ready":
        raise HTTPException(409, "Video đã sẵn sàng; xóa tập để dọn media liên quan.")
    row.status = "cancelled"
    if job:
        job.status = "cancelled"
    record(db, actor, "cancel", "upload", row)
    return {"status": "cancelled"}


@router.get("/media-jobs/{identifier}/thumbnail")
def thumbnail(identifier: uuid.UUID, request: Request, actor: Admin, db: DB):
    job = db.get(MediaJob, identifier)
    if not job or job.status != "ready":
        raise HTTPException(404, "Thumbnail chưa sẵn sàng.")
    upload = owned(db, job.upload_id, actor)
    path = upload_dir(request.app.state.settings, upload.id) / "output" / "thumbnail.jpg"
    if not path.is_file() or path.is_symlink():
        raise HTTPException(404, "Thumbnail chưa sẵn sàng.")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
