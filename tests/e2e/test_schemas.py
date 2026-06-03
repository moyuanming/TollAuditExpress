"""Schema 校验测试"""

from apps.api.models.schemas import ProcessRequest, ActionType
from pydantic import ValidationError
import pytest


def test_process_request_valid_action():
    req = ProcessRequest(action="CONFIRMED")
    assert req.action == ActionType.CONFIRMED


def test_process_request_invalid_action():
    with pytest.raises(ValidationError):
        ProcessRequest(action="HACKED")
