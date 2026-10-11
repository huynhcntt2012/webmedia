"""Session-authorized playback, private media, subtitles and per-user progress."""

import re
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

from app.admin_catalogue import DB, Actor, record
from app.auth import current_user, require_admin, write_guard
from app.content_access import ContentViewer, entitled
from app.media_storage import upload_dir
from app.models import (
    Episode,
    MediaJob,
    MediaVariant,
    Movie,
    SubtitleTrack,
    UploadSession,
    User,
    WatchProgress,
)
from app.subtitles import sanitize_vtt
from app.uploads import owned

router = APIRouter(tags=["playback"])
Viewer = Annotated[User, Depends(current_user)]
Admin = Annotated[User, Depends(require_admin)]
LANGUAGE = r"^[a-z]{2,3}(?:-[A-Z]{2})?$"


def ready_query(episode_id):
    return (
        select(MediaJob)
        .join(UploadSession, UploadSession.id == MediaJob.upload_id)
        .where(
            UploadSession.episode_id == episode_id,
            UploadSession.status == "sealed",
            UploadSession.reserved,
            UploadSession.owner_id.is_not(None),
            MediaJob.status == "ready",
        )
        .order_by(UploadSession.created_at.desc(), MediaJob.id.desc())
        .limit(1)
    )


def playable(db, episode_id, user):
    episode = db.get(Episode, episode_id)
    movie = db.get(Movie, episode.movie_id) if episode else None
    if not movie or movie.status != "published":
        raise HTTPException(404, "Không tìm thấy bản phát.")
    if not entitled(db, movie, user):
        raise HTTPException(403, "Nội dung này thuộc gói chưa mở quyền xem.")
    job = db.scalar(ready_query(episode.id))
    if not job:
        raise HTTPException(404, "Video chưa sẵn sàng.")
    return episode, movie, job


def playable_job(db, identifier, user):
    job = db.get(MediaJob, identifier)
    upload = db.get(UploadSession, job.upload_id) if job else None
    if not upload or not upload.episode_id:
        raise HTTPException(404, "Không tìm thấy bản phát.")
    _, _, latest = playable(db, upload.episode_id, user)
    if latest.id != identifier:
        raise HTTPException(404, "Bản phát đã thay đổi. Tải lại trang để tiếp tục.")
    return latest, upload


def track_info(track):
    return {"language": track.language, "label": track.label, "version": track.version}


@router.get("/movies/{slug}/episodes")
def episodes(slug: str, db: DB, page: int = Query(1, ge=1, le=1000)):
    movie = db.scalar(select(Movie).where(Movie.slug == slug, Movie.status == "published"))
    if not movie:
        raise HTTPException(404, "Không tìm thấy phim.")
    rows = db.scalars(
        select(Episode)
        .where(Episode.movie_id == movie.id)
        .order_by(Episode.season_number, Episode.episode_number)
        .offset((page - 1) * 20)
        .limit(20)
    )
    return {
        "items": [
            {
                "id": row.id,
                "title": row.title,
                "season_number": row.season_number,
                "episode_number": row.episode_number,
                "ready": db.scalar(ready_query(row.id)) is not None,
            }
            for row in rows
        ],
        "total": db.scalar(
            select(func.count()).select_from(Episode).where(Episode.movie_id == movie.id)
        ),
        "page": page,
        "page_size": 20,
    }


@router.get("/playback/episodes/{episode_id}")
def playback(episode_id: uuid.UUID, actor: ContentViewer, db: DB):
    episode, movie, job = playable(db, episode_id, actor)
    saved = db.get(WatchProgress, (actor.id, episode.id))
    matching = saved and saved.job_id == job.id
    tracks = db.scalars(
        select(SubtitleTrack).where(SubtitleTrack.job_id == job.id).order_by(SubtitleTrack.language)
    )
    return {
        "episode_id": episode.id,
        "title": episode.title,
        "movie_title": movie.title,
        "movie_slug": movie.slug,
        "job_id": job.id,
        "duration_ms": job.duration_seconds * 1000,
        "variants": [
            {"profile": v.profile, "height": v.height}
            for v in db.scalars(
                select(MediaVariant)
                .where(MediaVariant.job_id == job.id)
                .order_by(MediaVariant.height)
            )
        ],
        "subtitles": [track_info(t) for t in tracks],
        "progress": {
            "position_ms": saved.position_ms if matching else 0,
            "completed": saved.completed if matching else False,
            "version": saved.version if saved else 0,
        },
    }


@router.get("/playback/jobs/{identifier}/media/{asset:path}")
def media(identifier: uuid.UUID, asset: str, request: Request, actor: ContentViewer, db: DB):
    _, upload = playable_job(db, identifier, actor)
    if not re.fullmatch(r"master\.m3u8|\d{2,4}p/(?:index\.m3u8|segment_\d{5}\.ts)", asset):
        raise HTTPException(404, "Không tìm thấy tài nguyên.")
    root = upload_dir(request.app.state.settings, upload.id) / "output"
    path = root / asset
    if (
        root.is_symlink()
        or path.parent.is_symlink()
        or path.is_symlink()
        or not path.resolve().is_relative_to(root.resolve())
        or not path.is_file()
    ):
        raise HTTPException(404, "Không tìm thấy tài nguyên.")
    if request.headers.get("range") and not re.fullmatch(
        r"bytes=\d*-\d*", request.headers["range"]
    ):
        raise HTTPException(416, "Chỉ hỗ trợ một byte range.")
    return FileResponse(
        path,
        media_type="application/vnd.apple.mpegurl" if path.suffix == ".m3u8" else "video/mp2t",
        headers={"Cache-Control": "no-store", "Cross-Origin-Resource-Policy": "same-origin"},
    )


@router.get("/playback/jobs/{identifier}/subtitles/{language}")
def subtitle(identifier: uuid.UUID, language: str, actor: ContentViewer, db: DB):
    playable_job(db, identifier, actor)
    track = db.scalar(
        select(SubtitleTrack).where(
            SubtitleTrack.job_id == identifier, SubtitleTrack.language == language
        )
    )
    if not track:
        raise HTTPException(404, "Không tìm thấy phụ đề.")
    return Response(track.content, media_type="text/vtt", headers={"Cache-Control": "no-store"})


class ProgressInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    job_id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    position_ms: int = Field(ge=0, le=3600000)
    version: int = Field(ge=0, le=2147483646)


@router.put("/playback/episodes/{episode_id}/progress", dependencies=[Depends(write_guard)])
def save_progress(episode_id: uuid.UUID, data: ProgressInput, actor: ContentViewer, db: DB):
    _, _, job = playable(db, episode_id, actor)
    if str(job.id) != data.job_id:
        raise HTTPException(409, "Bản phát đã thay đổi. Tải lại trang.")
    duration = job.duration_seconds * 1000
    if data.position_ms > duration:
        raise HTTPException(422, "Vị trí vượt thời lượng video.")
    completed = data.position_ms >= duration - min(10000, duration // 20)
    values = dict(
        job_id=job.id,
        position_ms=data.position_ms,
        completed=completed,
        version=data.version + 1,
        updated_at=func.now(),
    )
    if data.version == 0:
        statement = insert(WatchProgress).values(user_id=actor.id, episode_id=episode_id, **values)
        statement = statement.on_conflict_do_nothing(index_elements=["user_id", "episode_id"])
        result = db.scalar(statement.returning(WatchProgress.version))
    else:
        from sqlalchemy import update

        result = db.scalar(
            update(WatchProgress)
            .where(
                WatchProgress.user_id == actor.id,
                WatchProgress.episode_id == episode_id,
                WatchProgress.version == data.version,
            )
            .values(**values)
            .returning(WatchProgress.version)
        )
    if result is None:
        raise HTTPException(409, "Tiến độ đã thay đổi ở tab hoặc thiết bị khác. Tải lại trang.")
    return {"position_ms": data.position_ms, "completed": completed, "version": result}


@router.get("/playback/continue")
def continue_watching(actor: Viewer, db: DB):
    latest = (
        ready_query(Episode.id).with_only_columns(MediaJob.id).correlate(Episode).scalar_subquery()
    )
    rows = db.execute(
        select(WatchProgress, Episode, Movie)
        .join(Episode, Episode.id == WatchProgress.episode_id)
        .join(Movie, Movie.id == Episode.movie_id)
        .where(
            WatchProgress.user_id == actor.id,
            ~WatchProgress.completed,
            WatchProgress.position_ms > 0,
            Movie.status == "published",
            WatchProgress.job_id == latest,
        )
        .order_by(WatchProgress.updated_at.desc())
        .limit(20)
    )
    return {
        "items": [
            {
                "episode_id": episode.id,
                "title": episode.title,
                "movie_title": movie.title,
                "position_ms": saved.position_ms,
            }
            for saved, episode, movie in rows
            if entitled(db, movie, actor)
        ]
    }


def editable_job(db, identifier, actor, lock=False):
    job = db.get(MediaJob, identifier, with_for_update=lock)
    if not job or job.status != "ready":
        raise HTTPException(404, "Video chưa sẵn sàng.")
    owned(db, job.upload_id, actor)
    return job


@router.get("/admin/media-jobs/{identifier}/subtitles")
def admin_subtitles(identifier: uuid.UUID, actor: Admin, db: DB):
    editable_job(db, identifier, actor)
    return {
        "items": [
            track_info(t) | {"content": t.content}
            for t in db.scalars(
                select(SubtitleTrack)
                .where(SubtitleTrack.job_id == identifier)
                .order_by(SubtitleTrack.language)
            )
        ]
    }


class SubtitleInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    label: str = Field(min_length=1, max_length=80)
    content: str = Field(min_length=1, max_length=131072)
    version: int = Field(ge=0)


@router.put("/admin/media-jobs/{identifier}/subtitles/{language}")
def put_subtitle(identifier: uuid.UUID, language: str, data: SubtitleInput, actor: Actor, db: DB):
    job = editable_job(db, identifier, actor, lock=True)
    if not re.fullmatch(LANGUAGE, language):
        raise HTTPException(422, "Mã ngôn ngữ không hợp lệ.")
    try:
        content = sanitize_vtt(data.content, job.duration_seconds)
    except ValueError:
        raise HTTPException(
            422, "Phụ đề cần WebVTT văn bản thuần, cue đúng thời lượng, tối đa 128 KiB."
        ) from None
    track = db.scalar(
        select(SubtitleTrack).where(
            SubtitleTrack.job_id == identifier, SubtitleTrack.language == language
        )
    )
    if (track.version if track else 0) != data.version:
        raise HTTPException(409, "Phụ đề đã thay đổi. Tải lại danh sách.")
    if not track:
        count = db.scalar(
            select(func.count())
            .select_from(SubtitleTrack)
            .where(SubtitleTrack.job_id == identifier)
        )
        if count >= 10:
            raise HTTPException(422, "Tối đa 10 ngôn ngữ phụ đề.")
        track = SubtitleTrack(job_id=identifier, language=language)
        db.add(track)
    track.label, track.content, track.version = data.label, content, data.version + 1
    record(
        db, actor, "update" if data.version else "create", "subtitle", track, {"label", "content"}
    )
    return track_info(track)


@router.delete("/admin/media-jobs/{identifier}/subtitles/{language}", status_code=204)
def delete_subtitle(
    identifier: uuid.UUID, language: str, actor: Actor, db: DB, version: int = Query(ge=1)
):
    editable_job(db, identifier, actor, lock=True)
    track = db.scalar(
        select(SubtitleTrack).where(
            SubtitleTrack.job_id == identifier, SubtitleTrack.language == language
        )
    )
    if not track:
        raise HTTPException(404, "Không tìm thấy phụ đề.")
    if track.version != version:
        raise HTTPException(409, "Phụ đề đã thay đổi.")
    record(db, actor, "delete", "subtitle", track)
    db.execute(delete(SubtitleTrack).where(SubtitleTrack.id == track.id))
