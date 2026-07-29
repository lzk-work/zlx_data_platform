"""字段映射单元测试。

这些测试不访问飞书或数据库，只验证 mapping 配置如何拆分固定字段和动态字段。
"""

from apps.feishu_intake_poc.src.mapper import build_writeback_fields, map_feishu_record


def test_map_feishu_record_splits_column_and_dynamic_attributes() -> None:
    mapping = {
        "fields": {
            "product_name": {
                "feishu_field": "产品名称",
                "target": "column",
                "required": True,
            },
            "age_group": {
                "feishu_field": "Age Group",
                "target": "dynamic_attributes",
                "required": False,
            },
        }
    }
    record = {
        "record_id": "rec_001",
        "fields": {
            "产品名称": "测试产品",
            "Age Group": ["Adult", "Teen"],
        },
    }

    mapped = map_feishu_record(record, mapping)

    assert mapped["feishu_record_id"] == "rec_001"
    assert mapped["product_name"] == "测试产品"
    assert mapped["column_fields"] == {"product_name": "测试产品"}
    assert mapped["dynamic_attributes"] == {"age_group": ["Adult", "Teen"]}
    assert mapped["raw_fields"] == record["fields"]


def test_map_feishu_record_defaults_to_column_target() -> None:
    mapping = {
        "fields": {
            "source_url": {
                "feishu_field": "来源链接",
            }
        }
    }
    record = {
        "record_id": "rec_002",
        "fields": {"来源链接": "https://example.com/item"},
    }

    mapped = map_feishu_record(record, mapping)

    assert mapped["column_fields"] == {"source_url": "https://example.com/item"}
    assert mapped["dynamic_attributes"] == {}


def test_build_writeback_fields_converts_db_intake_id_to_text() -> None:
    mapping = {
        "system_writeback_fields": {
            "db_intake_id": "中台录入ID",
            "validation_status": "校验状态",
            "validation_message": "校验结果",
            "sync_status": "同步状态",
        }
    }

    fields = build_writeback_fields(
        mapping,
        db_intake_id=123,
        validation_status="校验通过",
        validation_message="",
        sync_status="已入库",
    )

    assert fields["中台录入ID"] == "123"
    assert fields["校验状态"] == "校验通过"


def test_build_writeback_fields_uses_writeback_config_first() -> None:
    """验证 writeback.yaml 可以独立控制回写字段。"""
    mapping = {
        "system_writeback_fields": {
            "db_intake_id": "旧中台录入ID",
        }
    }
    writeback_config = {
        "fields": {
            "db_intake_id": {
                "feishu_field": "中台录入ID",
                "value_from": "db_intake_id",
                "type": "text",
            },
            "sync_status": {
                "feishu_field": "同步状态",
                "value_from": "sync_status",
                "type": "text",
            },
        }
    }

    fields = build_writeback_fields(
        mapping,
        db_intake_id=456,
        validation_status="校验通过",
        validation_message="",
        sync_status="已入库",
        writeback_config=writeback_config,
    )

    assert fields == {"中台录入ID": "456", "同步状态": "已入库"}
