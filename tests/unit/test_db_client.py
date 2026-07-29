"""POC 数据库写入封装的单元测试。

这里不连接真实数据库，只验证写入前的字段保护逻辑。
"""

import pytest

from apps.feishu_intake_poc.src.db_client import parse_source_updated_at, validate_supported_column_fields


def test_validate_supported_column_fields_accepts_physical_columns() -> None:
    validate_supported_column_fields(
        {
            "product_name": "测试产品",
            "source_url": "https://example.com/item",
            "develop_status": "已完成",
        }
    )


def test_validate_supported_column_fields_rejects_column_without_db_column() -> None:
    with pytest.raises(ValueError, match="product_sku"):
        validate_supported_column_fields({"product_sku": "260714_1"})


def test_parse_source_updated_at_accepts_text_datetime() -> None:
    parsed = parse_source_updated_at("2026-07-20 10:30:00")

    assert parsed is not None
    assert parsed.year == 2026
    assert parsed.month == 7
    assert parsed.day == 20
    assert parsed.hour == 10
    assert parsed.minute == 30


def test_parse_source_updated_at_converts_millisecond_timestamp_to_beijing_time() -> None:
    parsed = parse_source_updated_at(1784671200000)

    assert parsed is not None
    assert parsed.tzinfo is None