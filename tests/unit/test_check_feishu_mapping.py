"""飞书字段映射检查工具的单元测试。"""

from scripts.dev_utils.check_feishu_mapping import check_mapping


def test_check_mapping_passes_when_mapping_fields_exist() -> None:
    mapping = {
        "fields": {
            "product_name": {"feishu_field": "产品名称", "target": "column"},
            "feature": {"feishu_field": "产品特点", "target": "dynamic_attributes"},
        },
        "system_writeback_fields": {
            "sync_status": "同步状态",
        },
    }
    feishu_fields = [
        {"field_name": "产品名称", "field_id": "fld1"},
        {"field_name": "产品特点", "field_id": "fld2"},
        {"field_name": "同步状态", "field_id": "fld3"},
        {"field_name": "临时备注", "field_id": "fld4"},
    ]

    result = check_mapping(mapping=mapping, feishu_fields=feishu_fields)

    assert result.passed is True
    assert result.missing == []
    assert result.writeback_missing == []
    assert result.unmapped_feishu_fields == ["临时备注"]


def test_check_mapping_fails_when_declared_field_is_missing() -> None:
    mapping = {
        "fields": {
            "product_name": {"feishu_field": "产品名称", "target": "column"},
        },
        "system_writeback_fields": {
            "sync_status": "同步状态",
        },
    }
    feishu_fields = [
        {"field_name": "产品名称", "field_id": "fld1"},
    ]

    result = check_mapping(mapping=mapping, feishu_fields=feishu_fields)

    assert result.passed is False
    assert result.missing == []
    assert result.writeback_missing == ["sync_status: 回写字段不存在 -> 同步状态"]
