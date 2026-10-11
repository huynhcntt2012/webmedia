import io
import struct
import zlib

import pytest
from PIL import Image, PngImagePlugin

from app.comic_image import normalize_image


def png(width=20, height=30):
    buffer = io.BytesIO()
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("private", "secret metadata")
    Image.new("RGBA", (width, height), (255, 0, 0, 128)).save(
        buffer, format="PNG", pnginfo=metadata
    )
    return buffer.getvalue()


def test_normalized_jpeg_strips_metadata_and_transparency():
    width, height, data = normalize_image(png())
    assert (width, height) == (20, 30) and data.startswith(b"\xff\xd8")
    with Image.open(io.BytesIO(data)) as image:
        assert image.mode == "RGB" and "private" not in image.info and not image.getexif()


@pytest.mark.parametrize(
    "data",
    [b'<svg xmlns="http://www.w3.org/2000/svg"/>', b"not an image", png()[:40]],
    ids=["svg", "invalid", "truncated"],
)
def test_reject_invalid_image(data):
    with pytest.raises((ValueError, OSError)):
        normalize_image(data)


def test_reject_animation_and_bomb():
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), "red").save(
        buffer,
        format="WEBP",
        save_all=True,
        append_images=[Image.new("RGB", (10, 10), "blue")],
        duration=100,
        loop=0,
    )
    with pytest.raises(ValueError):
        normalize_image(buffer.getvalue())
    content = bytearray(png())
    content[16:24] = struct.pack("!II", 50000, 50000)
    content[29:33] = struct.pack("!I", zlib.crc32(content[12:29]))
    with pytest.raises(Image.DecompressionBombError):
        normalize_image(bytes(content))
