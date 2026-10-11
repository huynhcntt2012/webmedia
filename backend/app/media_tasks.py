"""Durable job rows are the outbox; duplicate Celery deliveries cannot duplicate publication."""

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, or_, select, text

from app.config import get_settings
from app.database import make_engine, session_scope
from app.media_storage import OUTPUT_RESERVE, lock_key, remove_upload, upload_dir
from app.models import (
    MediaJob,
    MediaVariant,
    SubtitleTrack,
    UploadChunk,
    UploadSession,
    WatchProgress,
)
from app.transcode import InvalidMedia, transcode, verify_source
from app.worker import celery_app


@contextmanager
def media_lock(engine, identifier):
    with engine.connect() as conn:
        acquired = conn.scalar(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_key(identifier)}
        )
        conn.commit()
        try:
            yield acquired
        finally:
            if acquired:
                conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key(identifier)})
                conn.commit()


@celery_app.task(
    name="suni.transcode",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=1260,
    time_limit=1300,
)
def transcode_job(identifier):
    settings = get_settings()
    engine = make_engine(settings)
    try:
        with session_scope(engine) as db:
            job = db.get(MediaJob, uuid.UUID(identifier))
            if not job:
                return {"status": "missing"}
            upload_id = job.upload_id
        with media_lock(engine, upload_id) as acquired:
            if not acquired:
                return {"status": "busy"}
            with session_scope(engine) as db:
                job = db.get(MediaJob, uuid.UUID(identifier), with_for_update=True)
                upload = db.get(UploadSession, upload_id)
                if (
                    job.status not in {"queued", "processing"}
                    or upload.status != "sealed"
                    or not upload.episode_id
                    or not upload.reserved
                ):
                    return {"status": "ignored"}
                if job.attempts >= 3:
                    job.status, job.error_code = "failed", "attempt_limit"
                    return {"status": "failed"}
                job.status, job.started_at = "processing", datetime.now(UTC)
                job.attempts += 1
                job.error_code = None
                total = upload.total_bytes
                chunks = list(
                    db.scalars(
                        select(UploadChunk)
                        .where(UploadChunk.upload_id == upload_id)
                        .order_by(UploadChunk.offset)
                    )
                )
            directory = upload_dir(settings, upload_id)
            try:
                digest = verify_source(directory / "source.mp4", chunks, total)
                variants, duration = transcode(directory)
                with session_scope(engine) as db:
                    upload = db.get(UploadSession, upload_id, with_for_update=True)
                    job = db.get(MediaJob, uuid.UUID(identifier), with_for_update=True)
                    if (
                        upload.status != "sealed"
                        or not upload.episode_id
                        or job.status == "cancelled"
                    ):
                        return {"status": "cancelled"}
                    db.execute(delete(MediaVariant).where(MediaVariant.job_id == job.id))
                    db.add_all([MediaVariant(job_id=job.id, **variant) for variant in variants])
                    job.status, job.source_sha256, job.duration_seconds = "ready", digest, duration
                    job.finished_at = datetime.now(UTC)
                (directory / "source.mp4").unlink(missing_ok=True)
                with session_scope(engine) as db:
                    row = db.get(UploadSession, upload_id, with_for_update=True)
                    row.reserved_bytes = sum(
                        p.stat().st_size for p in (directory / "output").rglob("*") if p.is_file()
                    )
                return {"status": "ready"}
            except Exception as exc:
                # No subprocess stderr, filenames, credentials or untrusted parser output in logs.
                code = str(exc) if isinstance(exc, InvalidMedia) else "processing_failed"
                if code not in {
                    "probe_limit",
                    "unsupported_streams",
                    "unsupported_video",
                    "source_size",
                    "source_hash",
                    "source_type",
                    "output_limit",
                    "output_incomplete",
                }:
                    code = "processing_failed"
                with session_scope(engine) as db:
                    job = db.get(MediaJob, uuid.UUID(identifier), with_for_update=True)
                    if job and job.status != "cancelled":
                        job.status, job.error_code, job.finished_at = (
                            "failed",
                            code,
                            datetime.now(UTC),
                        )
                # Source is retained for at most the upload TTL; partial output is never served.
                import shutil

                for name in ("work", "output"):
                    path = directory / name
                    if path.exists():
                        shutil.rmtree(path)
                return {"status": "failed", "error_code": code}
    finally:
        engine.dispose()


def enqueue(identifier):
    try:
        transcode_job.apply_async(args=[str(identifier)], task_id=str(identifier), retry=False)
        return True
    except Exception:
        return False  # Persisted queued row will be picked up by maintenance after broker recovery.


@celery_app.task(name="suni.media_maintenance", soft_time_limit=45, time_limit=55)
def media_maintenance():
    settings = get_settings()
    engine = make_engine(settings)
    now = datetime.now(UTC)
    dispatched = cleaned = 0
    try:
        with session_scope(engine) as db:
            ids = list(
                db.scalars(
                    select(UploadSession.id)
                    .outerjoin(MediaJob, MediaJob.upload_id == UploadSession.id)
                    .where(
                        UploadSession.reserved,
                        or_(
                            UploadSession.status.in_(["cancelled", "expired"]),
                            UploadSession.owner_id.is_(None),
                            UploadSession.episode_id.is_(None),
                            (UploadSession.expires_at <= now)
                            & or_(MediaJob.id.is_(None), MediaJob.status != "ready"),
                            (MediaJob.status == "ready")
                            & (
                                UploadSession.reserved_bytes
                                >= UploadSession.total_bytes + OUTPUT_RESERVE
                            ),
                        ),
                    )
                    .order_by(UploadSession.created_at)
                    .limit(1000)
                )
            )
        for identifier in ids:
            with media_lock(engine, identifier) as acquired:
                if not acquired:
                    continue
                with session_scope(engine) as db:
                    upload = db.get(UploadSession, identifier, with_for_update=True)
                    job = db.scalar(select(MediaJob).where(MediaJob.upload_id == identifier))
                    expired = upload.expires_at <= now and (not job or job.status != "ready")
                    if (
                        upload.status in {"cancelled", "expired"}
                        or not upload.owner_id
                        or not upload.episode_id
                        or expired
                    ):
                        upload.status = "expired" if expired else "cancelled"
                        if job:
                            job.status = "cancelled"
                            db.execute(delete(MediaVariant).where(MediaVariant.job_id == job.id))
                            db.execute(delete(SubtitleTrack).where(SubtitleTrack.job_id == job.id))
                            db.execute(delete(WatchProgress).where(WatchProgress.job_id == job.id))
                        remove_upload(settings, identifier)
                        db.execute(delete(UploadChunk).where(UploadChunk.upload_id == identifier))
                        upload.reserved = False
                        cleaned += 1
                    elif job and job.status == "ready":
                        directory = upload_dir(settings, identifier)
                        (directory / "source.mp4").unlink(missing_ok=True)
                        upload.reserved_bytes = sum(
                            p.stat().st_size
                            for p in (directory / "output").rglob("*")
                            if p.is_file()
                        )
        with session_scope(engine) as db:
            jobs = list(
                db.scalars(
                    select(MediaJob)
                    .where(
                        or_(
                            MediaJob.status == "queued",
                            (MediaJob.status == "processing")
                            & (MediaJob.started_at < now - timedelta(minutes=30)),
                        )
                    )
                    .order_by(MediaJob.created_at)
                    .limit(100)
                )
            )
            identifiers = [job.id for job in jobs]
        for identifier in identifiers:
            dispatched += int(enqueue(identifier))
        return {"dispatched": dispatched, "cleaned": cleaned}
    finally:
        engine.dispose()
