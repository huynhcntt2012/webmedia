import pytest
from pydantic import ValidationError

from app.admin_catalogue import EpisodeInput, MovieInput
from app.media_urls import poster_url, trailer_url


@pytest.mark.parametrize(
    "url",
    [
        "http://media.sunifactory.com/a.jpg",
        "https://evil.com/a.jpg",
        "https://media.sunifactory.com.evil.com/a.jpg",
        "https://media.sunifactory.com@127.0.0.1/a.jpg",
        "https://media.sunifactory.com:443/a.jpg",
        "https://127.0.0.1/a.jpg",
        "https://media.sunifactory.com/a.svg",
        "https://media.sunifactory.com/%2e%2e/a.jpg",
        "https://media.sunifactory.com/../a.jpg",
        "https://media.sunifactory.com/a.jpg?token=secret",
        "https://media.sunifactory.com/a.jpg#x",
        "https://media.sunifactory.com\\@evil.com/a.jpg",
        "data:image/svg+xml,x",
        "javascript:alert(1)",
    ],
)
def test_reject_unsafe_poster_urls(url):
    with pytest.raises(ValueError):
        poster_url(url, "media.sunifactory.com")


def test_media_url_canonicalization():
    assert poster_url("https://media.sunifactory.com/posters/a.webp", "media.sunifactory.com")
    assert (
        trailer_url("https://youtu.be/abcdefghijk") == "https://www.youtube.com/watch?v=abcdefghijk"
    )
    assert poster_url(None, "") is None and trailer_url("") is None
    with pytest.raises(ValueError):
        poster_url("https://media.sunifactory.com/a.jpg", "")


@pytest.mark.parametrize(
    "url",
    [
        "http://youtu.be/abcdefghijk",
        "https://youtube.com.evil.com/watch?v=abcdefghijk",
        "https://www.youtube.com/watch?v=abcdefghijk&redirect=evil",
        "https://youtu.be/short",
        "https://www.youtube.com@127.0.0.1/watch?v=abcdefghijk",
        "https://youtu.be/abcdefghijk?x=1",
    ],
)
def test_reject_unsafe_trailers(url):
    with pytest.raises(ValueError):
        trailer_url(url)


@pytest.mark.parametrize(
    "payload",
    [
        {"title": " ", "slug": "good"},
        {"title": "Good", "slug": "../bad"},
        {"title": "Good", "slug": "good", "role": "admin"},
        {"title": "Good", "slug": "good", "release_year": 100},
        {"title": "Good", "slug": "good", "synopsis": "x" * 5001},
    ],
)
def test_movie_validation(payload):
    with pytest.raises(ValidationError):
        MovieInput(**payload)


def test_episode_validation():
    with pytest.raises(ValidationError):
        EpisodeInput(title="Episode", episode_number=0)
