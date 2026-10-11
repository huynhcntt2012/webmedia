import pytest

from app.subtitles import sanitize_vtt


def test_canonical_vtt_is_idempotent():
    data = "\ufeffWEBVTT\r\n\r\ncue 1\r\n00:00.000 --> 00:01.500\r\nTiếng Việt & English\r\n"
    result = sanitize_vtt(data, 2)
    assert "00:00:01.500" in result and "&amp;" in result
    assert sanitize_vtt(result, 2) == result


@pytest.mark.parametrize(
    "content",
    [
        "WEBVTT\n\nSTYLE\n::cue { color: red }",
        "WEBVTT\n\n00:00.000 --> 00:01.000\n<script>alert(1)</script>",
        "WEBVTT\n\n00:00.000 --> 00:01.000\n&lt;img src=x&gt;",
        "WEBVTT\n\n00:00.000 --> 00:01.000 position:0%\nText",
        "WEBVTT\n\n00:02.000 --> 00:01.000\nText",
        "WEBVTT\n\n00:00.000 --> 00:10.000\nText",
        "WEBVTT\n\n00:00.000 --> 00:01.000\nText\x00",
        "WEBVTT\n\n00:00.000 --> 00:01.000\n" + "a" * 131073,
    ],
    ids=[
        "style",
        "markup",
        "encoded-markup",
        "settings",
        "reversed",
        "duration",
        "control",
        "size",
    ],
)
def test_vtt_rejects_unsafe_or_invalid_cues(content):
    with pytest.raises(ValueError):
        sanitize_vtt(content, 2)
