"""Conservative WebVTT subset: timed plain text, no markup, CSS or cue settings."""

import html
import re

STAMP = r"(?:\d{2}:)?[0-5]\d:[0-5]\d\.\d{3}"


def milliseconds(value):
    parts = value.split(":")
    if len(parts) == 2:
        parts.insert(0, "0")
    return int(parts[0]) * 3600000 + int(parts[1]) * 60000 + round(float(parts[2]) * 1000)


def timestamp(value):
    return (
        f"{value // 3600000:02}:{value // 60000 % 60:02}:{value // 1000 % 60:02}.{value % 1000:03}"
    )


def sanitize_vtt(content, duration_seconds):
    if len(content.encode("utf-8")) > 131072:
        raise ValueError("Subtitle exceeds 128 KiB")
    content = content.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n").strip()
    blocks = re.split(r"\n[ \t]*\n", content)
    if not blocks or blocks[0] != "WEBVTT" or not 2 <= len(blocks) <= 2001:
        raise ValueError("WEBVTT header and cues required")
    output = ["WEBVTT"]
    previous = -1
    for block in blocks[1:]:
        lines = block.splitlines()
        if lines and re.fullmatch(r"[\w -]{1,80}", lines[0]) and len(lines) >= 3:
            lines.pop(0)  # Optional cue identifier; never retained.
        match = re.fullmatch(f"({STAMP}) --> ({STAMP})", lines[0]) if lines else None
        if not match or not 2 <= len(lines) <= 5:
            raise ValueError("Unsupported cue syntax")
        start, end = map(milliseconds, match.groups())
        if start < previous or not start < end <= duration_seconds * 1000:
            raise ValueError("Cue outside video duration or order")
        previous = start
        text = html.unescape("\n".join(lines[1:]))
        if len(text) > 2000 or any(c in "<>" or ord(c) < 32 and c not in "\n\t" for c in text):
            raise ValueError("Plain subtitle text only")
        output.append(f"{timestamp(start)} --> {timestamp(end)}\n{html.escape(text, quote=False)}")
    return "\n\n".join(output) + "\n"
