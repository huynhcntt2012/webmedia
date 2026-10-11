import unicodedata

import pytest

from app.catalogue import search_pattern


@pytest.mark.parametrize(
    "value,expected",
    [
        ("  Mùa Hè  ", "%Mùa Hè%"),
        ("100%_\\", r"%100\%\_\\%"),
        (unicodedata.normalize("NFD", "Đường về"), "%Đường về%"),
    ],
)
def test_search_literal_and_unicode(value, expected):
    assert search_pattern(value) == expected
