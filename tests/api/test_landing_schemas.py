"""Landing Lead Pydantic 模型 — 字段级校验单元测试"""
import pytest
from pydantic import ValidationError

from packages.contracts.types.schemas import LandingLeadCreate


class TestLandingLeadCreateValidation:
    def test_valid_payload(self):
        lead = LandingLeadCreate(
            name="张三", phone="13800001234", org="某高速运营公司",
            email="zhang@example.com", message="希望了解产品",
        )
        assert lead.name == "张三"
        assert lead.phone == "13800001234"
        assert lead.source == "landing-page"  # 默认值

    def test_phone_too_short_invalid(self):
        with pytest.raises(ValidationError) as exc:
            LandingLeadCreate(name="张三", phone="1380000", org="某公司")
        assert "phone" in str(exc.value)

    def test_phone_invalid_prefix(self):
        with pytest.raises(ValidationError) as exc:
            LandingLeadCreate(name="张三", phone="12800001234", org="某公司")
        assert "phone" in str(exc.value)

    def test_email_invalid_format(self):
        with pytest.raises(ValidationError) as exc:
            LandingLeadCreate(name="张三", phone="13800001234", org="某公司", email="not-an-email")
        assert "email" in str(exc.value)

    def test_name_blank_rejected(self):
        with pytest.raises(ValidationError):
            LandingLeadCreate(name="   ", phone="13800001234", org="某公司")

    def test_message_max_length(self):
        with pytest.raises(ValidationError):
            LandingLeadCreate(
                name="张三", phone="13800001234", org="某公司",
                message="x" * 501,
            )

    def test_email_optional(self):
        lead = LandingLeadCreate(name="张三", phone="13800001234", org="某公司")
        assert lead.email is None
