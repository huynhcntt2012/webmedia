"""URLs are references only: never fetched, resolved or proxied by the API."""

import re
from urllib.parse import parse_qs, urlsplit


def poster_url(value: str | None, hosts: str) -> str | None:
    if not value:
        return None
    if len(value) > 2048 or any(ord(c) < 33 for c in value) or "\\" in value:
        raise ValueError("Poster URL không hợp lệ.")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.netloc != parsed.hostname
        or parsed.hostname not in hosts.split(",")
        or parsed.query
        or parsed.fragment
        or not re.fullmatch(r"/[a-zA-Z0-9/_-]+\.(?:jpg|jpeg|png|webp|avif)", parsed.path)
        or "//" in parsed.path
    ):
        raise ValueError(
            "Poster cần HTTPS, hostname được phép và đường dẫn ảnh JPG/PNG/WebP/AVIF; không query."
        )
    return value


def trailer_url(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) > 500 or any(ord(c) < 33 for c in value) or "\\" in value:
        raise ValueError("Trailer URL không hợp lệ.")
    parsed = urlsplit(value)
    identifier = None
    if parsed.scheme == "https" and parsed.netloc == parsed.hostname and not parsed.fragment:
        if parsed.hostname in {"www.youtube.com", "youtube.com"} and parsed.path == "/watch":
            query = parse_qs(parsed.query, keep_blank_values=True)
            if set(query) == {"v"} and len(query["v"]) == 1:
                identifier = query["v"][0]
        elif parsed.hostname == "youtu.be" and not parsed.query:
            identifier = parsed.path[1:]
    if not identifier or not re.fullmatch(r"[a-zA-Z0-9_-]{11}", identifier):
        raise ValueError("Trailer cần URL YouTube /watch?v=… hoặc youtu.be/… hợp lệ.")
    return "https://www.youtube.com/watch?v=" + identifier
