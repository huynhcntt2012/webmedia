"""Private, generated paths only. Filenames from clients never become filesystem paths."""

import shutil
import uuid
from pathlib import Path

CHUNK_BYTES = 4 * 1024 * 1024
OUTPUT_RESERVE = 2 * 1024 * 1024 * 1024


def upload_dir(settings, identifier, create=False):
    root = Path(settings.media_root)
    if not root.is_absolute() or root.is_symlink():
        raise ValueError("Unsafe media root")
    root = root.resolve()
    path = root / str(uuid.UUID(str(identifier)))
    if path.is_symlink() or path.resolve().parent != root:
        raise ValueError("Unsafe media path")
    if create:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def remove_upload(settings, identifier):
    path = upload_dir(settings, identifier)
    if path.exists():
        shutil.rmtree(path)


def mp4_magic(data):
    return len(data) >= 12 and data[4:8] == b"ftyp" and 8 <= int.from_bytes(data[:4], "big") <= 4096


def lock_key(identifier):
    return int.from_bytes(uuid.UUID(str(identifier)).bytes[:8], "big", signed=True)
