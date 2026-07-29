"""分发配置单元测试。

这些测试只验证 distribution.yaml 如何生成下游分发任务，
不访问飞书和数据库。
"""

from apps.feishu_intake_poc.src.distribution import build_distribution_tasks


def test_build_distribution_tasks_maps_payload_from_column_and_dynamic_fields() -> None:
    """验证分发配置可以从固定字段和动态字段取值。"""
    config = {
        "source_table_code": "product_intake_poc",
        "targets": [
            {
                "target_table_code": "sourcing_task_poc",
                "enabled": True,
                "execute_immediately": False,
                "action_type": "create",
                "target": {
                    "app_token": "target_app",
                    "table_id": "target_table",
                },
                "fields": {
                    "product_name": {
                        "feishu_field": "产品名称",
                        "value_from": "column_fields.product_name",
                    },
                    "feature": {
                        "feishu_field": "产品特点",
                        "value_from": "dynamic_attributes.product_features_1",
                    },
                },
            }
        ],
    }
    mapped_record = {
        "column_fields": {"product_name": "测试产品"},
        "dynamic_attributes": {"product_features_1": "轻便"},
    }

    tasks = build_distribution_tasks(
        config,
        mapped_record=mapped_record,
        db_intake_id=12,
        ods_raw_id=34,
        source_record_id="rec_001",
    )

    assert len(tasks) == 1
    assert tasks[0]["source_table_code"] == "product_intake_poc"
    assert tasks[0]["source_record_id"] == "rec_001"
    assert tasks[0]["source_ods_id"] == 34
    assert tasks[0]["source_biz_id"] == 12
    assert tasks[0]["target_table_code"] == "sourcing_task_poc"
    assert tasks[0]["execute_immediately"] is False
    assert tasks[0]["payload"] == {"产品名称": "测试产品", "产品特点": "轻便"}


def test_build_distribution_tasks_skips_disabled_targets() -> None:
    """验证禁用的分发目标不会生成任务。"""
    config = {
        "targets": [
            {
                "enabled": False,
                "fields": {
                    "product_name": {
                        "feishu_field": "产品名称",
                        "value_from": "column_fields.product_name",
                    }
                },
            }
        ]
    }

    tasks = build_distribution_tasks(
        config,
        mapped_record={"column_fields": {"product_name": "测试产品"}},
        db_intake_id=1,
        ods_raw_id=2,
        source_record_id="rec_001",
    )

    assert tasks == []
