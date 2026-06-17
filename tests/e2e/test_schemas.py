"""Schema 校验测试"""

import pytest
from pydantic import ValidationError

from apps.api.models.schemas import ActionType, ProcessRequest


def test_process_request_valid_action():
    req = ProcessRequest(action="CONFIRMED")
    assert req.action == ActionType.CONFIRMED


def test_process_request_invalid_action():
    with pytest.raises(ValidationError):
        ProcessRequest(action="HACKED")
