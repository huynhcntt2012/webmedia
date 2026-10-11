"""Decode/re-encode still images in a resource-limited child, never trust extension/MIME."""

import io
import struct
import subprocess
import sys
import tempfile
import warnings
from threading import BoundedSemaphore

from PIL import Image, ImageOps

MAX_INPUT = 8 * 1024 * 1024
MAX_OUTPUT = 4 * 1024 * 1024
DECODERS = BoundedSemaphore(2)


class ImageBusy(Exception):
    pass


def normalize_image(data):
    Image.MAX_IMAGE_PIXELS = 12000000
    if not 0 < len(data) <= MAX_INPUT:
        raise ValueError("image size")
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(data), formats=["JPEG", "PNG", "WEBP"]) as source:
            if source.format not in {"JPEG", "PNG", "WEBP"} or getattr(source, "n_frames", 1) != 1:
                raise ValueError("still image required")
            width, height = source.size
            if not (1 <= width <= 8192 and 1 <= height <= 20000 and width * height <= 12000000):
                raise ValueError("image dimensions")
            source.load()
            oriented = ImageOps.exif_transpose(source)
            if oriented.width > 8192 or oriented.height > 20000:
                raise ValueError("oriented image dimensions")
            canvas = Image.new("RGB", oriented.size, "white")
            if oriented.mode in {"RGBA", "LA"} or "transparency" in oriented.info:
                rgba = oriented.convert("RGBA")
                canvas.paste(rgba, mask=rgba.getchannel("A"))
            else:
                canvas.paste(oriented.convert("RGB"))
            output = io.BytesIO()
            canvas.save(output, format="JPEG", quality=88, optimize=True)
            encoded = output.getvalue()
            if len(encoded) > MAX_OUTPUT:
                raise ValueError("output size")
            return canvas.width, canvas.height, encoded


def decode_private_image(data):
    if not DECODERS.acquire(blocking=False):
        raise ImageBusy()
    try:
        return _decode(data)
    finally:
        DECODERS.release()


def _decode(data):
    with tempfile.TemporaryFile() as output:
        try:
            subprocess.run(
                [sys.executable, "-m", "app.comic_image"],
                input=data,
                stdout=output,
                stderr=subprocess.DEVNULL,
                timeout=15,
                check=True,
                close_fds=True,
                env={"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C", "HOME": "/tmp"},
            )
            output.seek(0)
            encoded = output.read(MAX_OUTPUT + 9)
            if not 10 < len(encoded) <= MAX_OUTPUT + 8 or encoded[8:10] != b"\xff\xd8":
                raise ValueError("invalid output")
            width, height = struct.unpack("!II", encoded[:8])
            return width, height, encoded[8:]
        except (subprocess.SubprocessError, ValueError, OSError):
            raise ValueError("invalid image") from None


def main():
    import resource

    from app.media_exec import sandbox

    sandbox()
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_OUTPUT + 8,) * 2)
    width, height, data = normalize_image(sys.stdin.buffer.read(MAX_INPUT + 1))
    sys.stdout.buffer.write(struct.pack("!II", width, height) + data)


if __name__ == "__main__":
    main()
