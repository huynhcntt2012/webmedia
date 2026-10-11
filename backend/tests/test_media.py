import hashlib
import uuid
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.media_storage import mp4_magic, remove_upload, upload_dir
from app.transcode import InvalidMedia, verify_source
from app.uploads import StartUpload


@pytest.mark.parametrize(
    "filename", ["../a.mp4", "a\\b.mp4", "a.mp4\n", "movie.svg", "https://host/a.mp4"]
)
def test_reject_unsafe_filename(filename):
    with pytest.raises(ValidationError):
        StartUpload(
            episode_id=uuid.uuid4(),
            idempotency_key=uuid.uuid4(),
            filename=filename,
            total_bytes=100,
            content_type="video/mp4",
        )


def test_generated_storage_and_checksum(tmp_path):
    settings = SimpleNamespace(media_root=str(tmp_path))
    with pytest.raises(ValueError):
        upload_dir(settings, "../outside", create=True)
    identifier = uuid.uuid4()
    directory = upload_dir(settings, identifier, create=True)
    data = b"\x00\x00\x00\x18ftypisom" + b"0" * 20
    source = directory / "source.mp4"
    source.write_bytes(data)
    chunk = SimpleNamespace(offset=0, size=len(data), sha256=hashlib.sha256(data).hexdigest())
    assert mp4_magic(data) and not mp4_magic(b"#EXTM3U")
    assert verify_source(source, [chunk], len(data)) == chunk.sha256
    source.write_bytes(data[:-1] + b"1")
    with pytest.raises(InvalidMedia, match="source_hash"):
        verify_source(source, [chunk], len(data))
    remove_upload(settings, identifier)
    assert not directory.exists() and tmp_path.exists()
