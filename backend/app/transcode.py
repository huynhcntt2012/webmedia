"""Bounded MP4 -> HLS transcode. No URLs, shell, input paths or output names from clients."""

import hashlib
import json
import math
import shutil
import subprocess
import sys
import tempfile
from fractions import Fraction

from app.media_storage import OUTPUT_RESERVE, mp4_magic


class InvalidMedia(Exception):
    pass


def run_media(binary, args, timeout=600, capture=False):
    with tempfile.TemporaryFile() as output:
        subprocess.run(
            [sys.executable, "-m", "app.media_exec", binary, *args],
            stdin=subprocess.DEVNULL,
            stdout=output if capture else subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=timeout,
            close_fds=True,
            env={"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C", "HOME": "/tmp"},
        )
        if capture:
            output.seek(0)
            data = output.read(1024 * 1024 + 1)
            if len(data) > 1024 * 1024:
                raise InvalidMedia("probe_limit")
            return data


def input_args(source):
    return [
        "-protocol_whitelist",
        "file,pipe",
        "-f",
        "mov",
        "-enable_drefs",
        "0",
        "-use_absolute_path",
        "0",
        "-i",
        str(source),
    ]


def probe(source):
    data = json.loads(
        run_media(
            "ffprobe",
            [
                "-v",
                "error",
                *input_args(source),
                "-show_entries",
                "stream=index,codec_type,codec_name,width,height,avg_frame_rate:format=duration",
                "-of",
                "json",
            ],
            timeout=20,
            capture=True,
        )
    )
    streams = data.get("streams", [])
    videos = [s for s in streams if s.get("codec_type") == "video"]
    if len(streams) > 4 or len(videos) != 1:
        raise InvalidMedia("unsupported_streams")
    video = videos[0]
    width, height = int(video.get("width", 0)), int(video.get("height", 0))
    duration = float(data.get("format", {}).get("duration", 0))
    fps = float(Fraction(video.get("avg_frame_rate", "0")))
    if (
        not math.isfinite(duration)
        or not 0 < duration <= 3600
        or not 16 <= width <= 4096
        or not 16 <= height <= 2160
        or width * height > 8847360
        or not 0 < fps <= 60
        or video.get("codec_name") not in {"h264", "hevc"}
    ):
        raise InvalidMedia("unsupported_video")
    return width, height, math.ceil(duration)


def verify_source(source, chunks, total):
    if not source.is_file() or source.is_symlink() or source.stat().st_size != total:
        raise InvalidMedia("source_size")
    digest = hashlib.sha256()
    offset = 0
    with source.open("rb") as stream:
        if not mp4_magic(stream.read(32)):
            raise InvalidMedia("source_type")
        stream.seek(0)
        for chunk in chunks:
            block = stream.read(chunk.size)
            if (
                chunk.offset != offset
                or len(block) != chunk.size
                or hashlib.sha256(block).hexdigest() != chunk.sha256
            ):
                raise InvalidMedia("source_hash")
            digest.update(block)
            offset += len(block)
    if offset != total:
        raise InvalidMedia("source_size")
    return digest.hexdigest()


def transcode(directory):
    source = directory / "source.mp4"
    width, height, duration = probe(source)
    work = directory / "work"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(mode=0o700)
    variants = []
    master = ["#EXTM3U", "#EXT-X-VERSION:3"]
    for target in sorted({min(360, height // 2 * 2), min(720, height // 2 * 2)}):
        target_width = max(2, round(width * target / height / 2) * 2)
        name = f"{target}p"
        folder = work / name
        folder.mkdir()
        bitrate = 800 if target <= 360 else 2500
        run_media(
            "ffmpeg",
            [
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-threads",
                "2",
                *input_args(source),
                "-t",
                str(duration),
                "-map",
                "0:v:0",
                "-map",
                "0:a:0?",
                "-vf",
                f"scale={target_width}:{target},setsar=1",
                "-filter_threads",
                "1",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-pix_fmt",
                "yuv420p",
                "-threads",
                "2",
                "-b:v",
                f"{bitrate}k",
                "-maxrate",
                f"{bitrate}k",
                "-bufsize",
                f"{bitrate * 2}k",
                "-r",
                "24",
                "-g",
                "96",
                "-keyint_min",
                "96",
                "-sc_threshold",
                "0",
                "-c:a",
                "aac",
                "-b:a",
                "96k",
                "-ac",
                "2",
                "-map_metadata",
                "-1",
                "-map_chapters",
                "-1",
                "-f",
                "hls",
                "-hls_time",
                "4",
                "-hls_playlist_type",
                "vod",
                "-hls_flags",
                "independent_segments",
                "-hls_segment_filename",
                str(folder / "segment_%05d.ts"),
                str(folder / "index.m3u8"),
            ],
        )
        files = list(folder.iterdir())
        if len(files) > 1002 or not any(p.suffix == ".ts" for p in files):
            raise InvalidMedia("output_limit")
        playlist = (folder / "index.m3u8").read_text()
        if "#EXT-X-ENDLIST" not in playlist:
            raise InvalidMedia("output_incomplete")
        size = sum(p.stat().st_size for p in files)
        variants.append(
            {"profile": name, "width": target_width, "height": target, "total_bytes": size}
        )
        master += [
            f"#EXT-X-STREAM-INF:BANDWIDTH={(bitrate + 128) * 1000},"
            f"RESOLUTION={target_width}x{target}",
            f"{name}/index.m3u8",
        ]
    run_media(
        "ffmpeg",
        [
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-threads",
            "2",
            *input_args(source),
            "-ss",
            str(min(1, duration / 2)),
            "-frames:v",
            "1",
            "-vf",
            "scale=320:-2",
            "-filter_threads",
            "1",
            "-threads",
            "1",
            str(work / "thumbnail.jpg"),
        ],
        timeout=30,
    )
    (work / "master.m3u8").write_text("\n".join(master) + "\n", encoding="utf-8")
    if sum(p.stat().st_size for p in work.rglob("*") if p.is_file()) > OUTPUT_RESERVE:
        raise InvalidMedia("output_limit")
    output = directory / "output"
    if output.exists():
        shutil.rmtree(output)
    work.rename(output)
    return variants, duration
