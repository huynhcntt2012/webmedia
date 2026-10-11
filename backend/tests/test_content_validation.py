import uuid

import pytest
from pydantic import ValidationError

from app.content_access import GrantInput


@pytest.mark.parametrize(
    "invalid",
    [
        {"days": True},
        {"days": 0},
        {"days": 367},
        {"device_limit": 0},
        {"device_limit": 21},
        {"device_limit": "2"},
        {"plan_code": "free"},
        {"price_vnd": 1},
        {"user_id": "../other"},
    ],
)
def test_reject_unsafe_content_grant(invalid):
    with pytest.raises(ValidationError):
        GrantInput.model_validate(
            {
                "user_id": str(uuid.uuid4()),
                "days": 30,
                "device_limit": 2,
                "plan_code": "vip",
                **invalid,
            }
        )
