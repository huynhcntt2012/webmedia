import uuid

import pytest
from pydantic import ValidationError

from app.reader import ReadingInput


@pytest.mark.parametrize(
    "change",
    [
        {"offset_milli": -1},
        {"offset_milli": 1001},
        {"offset_milli": True},
        {"version": -1},
        {"chapter_version": 0},
        {"mode": "script"},
        {"page_id": "../secret"},
        {"user_id": "other"},
    ],
)
def test_reader_rejects_untrusted_bookmark(change):
    with pytest.raises(ValidationError):
        ReadingInput(
            **(
                {
                    "page_id": str(uuid.uuid4()),
                    "offset_milli": 0,
                    "mode": "vertical",
                    "version": 0,
                    "chapter_version": 1,
                }
                | change
            )
        )
