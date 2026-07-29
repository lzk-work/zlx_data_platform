"""飞书录入 POC 分步骤集成测试。

这些测试用于把主流程拆开验证：

1. 从飞书按过滤条件读取记录。
2. 把飞书原始记录按 mapping 转成内部字段。
3. 校验映射后的数据。
4. upsert ODS 原始当前态。
5. 写入 biz 标准表和 sync 映射表。

测试会访问真实飞书和真实 PostgreSQL。是否执行由 RUN_POC_STEP_TESTS_IN_CODE
控制；环境变量 RUN_FEISHU_POC_STEP_TESTS=1 保留为命令行备用方式。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from apps.feishu_intake_poc.src.db_client import DatabaseClient, new_sync_batch_id
from apps.feishu_intake_poc.src.distribution import build_distribution_tasks
from apps.feishu_intake_poc.src.feishu_client import FeishuClient
from apps.feishu_intake_poc.src.filters import effective_filter_expression
from apps.feishu_intake_poc.src.mapper import build_writeback_fields, map_feishu_record, normalize_feishu_value
from apps.feishu_intake_poc.src.settings import IntakeSettings, load_mapping, load_settings, load_yaml_file
from apps.feishu_intake_poc.src.validator import validate_record


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ENV_PATH = PROJECT_ROOT / "apps" / "feishu_intake_poc" / "config" / "test.env"
NODE_CONFIG_ROOT = PROJECT_ROOT / "configs" / "feishu_nodes"
POC_NODE_CODE = "product_intake_poc"

# POC 分步骤真实环境测试开关。
# POC 阶段默认开启，方便在 PyCharm 中直接点击单个测试函数。
# 如需临时关闭真实外部调用，改为 False。
# 注意：开启后本文件会访问真实飞书和真实数据库。
RUN_POC_STEP_TESTS_IN_CODE = True


def integration_enabled() -> bool:
    """判断是否允许执行 POC 分步骤真实环境测试。"""
    return RUN_POC_STEP_TESTS_IN_CODE or os.getenv("RUN_FEISHU_POC_STEP_TESTS") == "1"


pytestmark = [
    pytest.mark.integration,
    pytest.mark.external,
    pytest.mark.skipif(
        not integration_enabled(),
        reason="Set RUN_POC_STEP_TESTS_IN_CODE=True or RUN_FEISHU_POC_STEP_TESTS=1 to run POC step tests.",
    ),
]


@pytest.fixture(scope="module")
def settings() -> IntakeSettings:
    """读取 POC 测试环境配置。"""
    return load_settings(TEST_ENV_PATH, node_code=POC_NODE_CODE, node_config_root=NODE_CONFIG_ROOT)


@pytest.fixture(scope="module")
def mapping(settings: IntakeSettings) -> dict[str, Any]:
    """读取字段映射配置。"""
    return load_mapping(settings.mapping_path)


@pytest.fixture(scope="module")
def writeback_config(settings: IntakeSettings) -> dict[str, Any]:
    """读取回写配置。"""
    return load_yaml_file(settings.writeback_config_path)


@pytest.fixture(scope="module")
def distribution_config(settings: IntakeSettings) -> dict[str, Any]:
    """读取分发配置。"""
    return load_yaml_file(settings.distribution_config_path)


@pytest.fixture(scope="module")
def filter_expression(settings: IntakeSettings, mapping: dict[str, Any]) -> str:
    """获取最终用于读取飞书记录的过滤表达式。"""
    expression = effective_filter_expression(settings.feishu_filter, settings.feishu_read_filter)
    assert expression, "请先在 node.yaml 的当前任务配置 read_filter，或在 test.env 临时配置 FEISHU_FILTER"
    return expression


@pytest.fixture(scope="module")
def filtered_records(settings: IntakeSettings, filter_expression: str) -> list[dict[str, Any]]:
    """按过滤表达式从飞书读取记录。"""

    with FeishuClient.from_settings(settings) as client:
        records = client.list_bitable_records(
            settings.feishu_app_token,
            settings.feishu_table_id,
            view_id=settings.feishu_view_id,
            filter_expression=filter_expression,
        )

    if not records:
        pytest.skip("飞书没有返回符合过滤条件的记录")
    return records


@pytest.fixture(scope="module")
def first_record(filtered_records: list[dict[str, Any]]) -> dict[str, Any]:
    """取第一条过滤后的记录，供后续步骤逐步验证。"""
    return filtered_records[0]


@pytest.fixture(scope="module")
def mapped_record(first_record: dict[str, Any], mapping: dict[str, Any]) -> dict[str, Any]:
    """把第一条飞书记录映射成内部标准形状。"""
    return map_feishu_record(first_record, mapping)


@pytest.fixture(scope="module")
def db(settings: IntakeSettings) -> DatabaseClient:
    """创建 POC 数据库客户端，并确保 POC 表存在。"""
    client = DatabaseClient.from_settings(settings)
    client.ensure_schema(str(settings.sql_path))
    return client


def test_01_feishu_records_can_be_read_by_develop_status_filter(
    filter_expression: str,
    filtered_records: list[dict[str, Any]],
) -> None:
    """步骤 1：验证飞书可以按“开发状态=已完成”过滤读取记录。"""
    assert "开发状态" in filter_expression
    assert "已完成" in filter_expression

    for record in filtered_records:
        fields = record.get("fields") or {}
        develop_status = normalize_feishu_value(fields.get("开发状态"))
        assert develop_status == "已完成"


def test_02_feishu_record_can_be_mapped(
    mapped_record: dict[str, Any],
    mapping: dict[str, Any],
) -> None:
    """步骤 2：验证飞书原始记录可以按 mapping 拆出固定字段和动态字段。"""
    assert mapped_record["feishu_record_id"]
    assert mapped_record["raw_fields"]
    assert mapped_record["column_fields"]

    dynamic_field_names = {
        field_name
        for field_name, rule in (mapping.get("fields") or {}).items()
        if rule.get("target") == "dynamic_attributes"
    }
    for field_name in dynamic_field_names:
        assert field_name in mapped_record["dynamic_attributes"]


def test_03_mapped_record_can_be_validated(
    mapped_record: dict[str, Any],
    mapping: dict[str, Any],
) -> None:
    """步骤 3：验证映射后的数据可以通过当前 mapping 校验。"""
    errors = validate_record(mapped_record, mapping)

    assert errors == []


def test_04_raw_record_can_be_saved_to_ods(
    db: DatabaseClient,
    settings: IntakeSettings,
    first_record: dict[str, Any],
) -> None:
    """步骤 4：验证飞书原始整行可以 upsert 到 ODS 当前态表。"""
    sync_batch_id = new_sync_batch_id("test_feishu_intake_steps")

    ods_raw_id = db.save_raw_record(
        settings=settings,
        record=first_record,
        sync_batch_id=sync_batch_id,
    )
    second_ods_raw_id = db.save_raw_record(
        settings=settings,
        record=first_record,
        sync_batch_id=new_sync_batch_id("test_feishu_intake_steps_repeat"),
    )
    saved = db.fetch_one(
        """
        select
            id,
            table_code,
            feishu_record_id,
            raw_payload,
            raw_hash,
            first_seen_at,
            last_seen_at,
            updated_at
        from ods.feishu_product_intake_raw
        where id = %s
        """,
        (ods_raw_id,),
    )

    assert second_ods_raw_id == ods_raw_id
    assert saved is not None
    assert saved["table_code"] == settings.node_code
    assert saved["feishu_record_id"] == first_record["record_id"]
    assert saved["raw_payload"]["record_id"] == first_record["record_id"]
    assert saved["raw_hash"]
    assert saved["first_seen_at"] is not None
    assert saved["last_seen_at"] is not None
    assert saved["updated_at"] is not None


def test_05_business_and_sync_records_can_be_written(
    db: DatabaseClient,
    settings: IntakeSettings,
    first_record: dict[str, Any],
    mapped_record: dict[str, Any],
    mapping: dict[str, Any],
) -> None:
    """步骤 5：验证校验通过的数据可以写入 biz 标准表和 sync 映射表。"""
    sync_batch_id = new_sync_batch_id("test_feishu_intake_steps")
    ods_raw_id = db.save_raw_record(
        settings=settings,
        record=first_record,
        sync_batch_id=sync_batch_id,
    )

    db_intake_id = db.upsert_business_record(
        settings=settings,
        mapped_record=mapped_record,
        ods_raw_id=ods_raw_id,
        validation_status="校验通过",
        validation_message="",
        sync_status="已入库",
    )
    db.upsert_record_mapping(
        settings=settings,
        feishu_record_id=first_record["record_id"],
        db_intake_id=db_intake_id,
        ods_raw_id=ods_raw_id,
        stage_code=mapping.get("table_code", "feishu_intake_poc"),
    )

    business_row = db.fetch_one(
        """
        select db_intake_id, ods_raw_id, product_name, develop_status, dynamic_attributes
        from biz.product_intake_poc
        where db_intake_id = %s
        """,
        (db_intake_id,),
    )
    sync_row = db.fetch_one(
        """
        select feishu_record_id, ods_raw_id, db_intake_id
        from sync.feishu_record_mapping
        where feishu_app_token = %s
          and feishu_table_id = %s
          and feishu_record_id = %s
        """,
        (settings.feishu_app_token, settings.feishu_table_id, first_record["record_id"]),
    )

    assert business_row is not None
    assert business_row["ods_raw_id"] == ods_raw_id
    assert business_row["product_name"] == mapped_record["column_fields"]["product_name"]
    assert business_row["develop_status"] == "已完成"
    assert isinstance(business_row["dynamic_attributes"], dict)

    assert sync_row is not None
    assert sync_row["ods_raw_id"] == ods_raw_id
    assert sync_row["db_intake_id"] == db_intake_id


def test_06_first_record_system_fields_can_be_written_back_to_feishu(
    db: DatabaseClient,
    settings: IntakeSettings,
    first_record: dict[str, Any],
    mapped_record: dict[str, Any],
    mapping: dict[str, Any],
    writeback_config: dict[str, Any],
) -> None:
    """步骤 6：只取过滤后的第一条记录，验证系统字段可以回写到飞书。"""
    sync_batch_id = new_sync_batch_id("test_feishu_intake_writeback")
    ods_raw_id = db.save_raw_record(
        settings=settings,
        record=first_record,
        sync_batch_id=sync_batch_id,
    )
    db_intake_id = db.upsert_business_record(
        settings=settings,
        mapped_record=mapped_record,
        ods_raw_id=ods_raw_id,
        validation_status="校验通过",
        validation_message="POC回写测试通过",
        sync_status="已入库",
    )

    writeback_fields = build_writeback_fields(
        mapping,
        db_intake_id=db_intake_id,
        validation_status="校验通过",
        validation_message="POC回写测试通过",
        sync_status="已入库",
        writeback_config=writeback_config,
    )
    assert writeback_fields

    with FeishuClient.from_settings(settings) as client:
        client.update_bitable_record(
            settings.feishu_app_token,
            settings.feishu_table_id,
            first_record["record_id"],
            writeback_fields,
        )
        refreshed = client.get_bitable_record(
            settings.feishu_app_token,
            settings.feishu_table_id,
            first_record["record_id"],
        )

    refreshed_fields = refreshed.get("fields") or {}
    writeback_mapping = {
        key: rule.get("feishu_field")
        for key, rule in (writeback_config.get("fields") or {}).items()
        if rule.get("feishu_field")
    }

    assert str(normalize_feishu_value(refreshed_fields.get(writeback_mapping["db_intake_id"]))) == str(db_intake_id)
    assert normalize_feishu_value(refreshed_fields.get(writeback_mapping["validation_status"])) == "校验通过"
    assert normalize_feishu_value(refreshed_fields.get(writeback_mapping["validation_message"])) == "POC回写测试通过"
    assert normalize_feishu_value(refreshed_fields.get(writeback_mapping["sync_status"])) == "已入库"


def test_07_distribution_task_can_be_created(
    db: DatabaseClient,
    settings: IntakeSettings,
    first_record: dict[str, Any],
    mapped_record: dict[str, Any],
    distribution_config: dict[str, Any],
) -> None:
    """步骤 7：验证配置可以生成并落库下游分发任务。

    这个测试只创建 flow.feishu_distribution_task 任务，不会真的新增下游飞书记录。
    """
    sync_batch_id = new_sync_batch_id("test_feishu_intake_distribution")
    ods_raw_id = db.save_raw_record(
        settings=settings,
        record=first_record,
        sync_batch_id=sync_batch_id,
    )
    db_intake_id = db.upsert_business_record(
        settings=settings,
        mapped_record=mapped_record,
        ods_raw_id=ods_raw_id,
        validation_status="校验通过",
        validation_message="POC分发任务测试通过",
        sync_status="已入库",
    )
    tasks = build_distribution_tasks(
        distribution_config,
        mapped_record=mapped_record,
        db_intake_id=db_intake_id,
        ods_raw_id=ods_raw_id,
        source_record_id=first_record["record_id"],
    )
    assert tasks

    task_id = db.create_distribution_task(tasks[0])
    saved = db.fetch_one(
        """
        select
            id,
            source_record_id,
            source_ods_id,
            source_biz_id,
            target_table_code,
            payload,
            status
        from flow.feishu_distribution_task
        where id = %s
        """,
        (task_id,),
    )

    assert saved is not None
    assert saved["source_record_id"] == first_record["record_id"]
    assert saved["source_ods_id"] == ods_raw_id
    assert saved["source_biz_id"] == db_intake_id
    assert saved["target_table_code"] == tasks[0]["target_table_code"]
    assert saved["payload"] == tasks[0]["payload"]
    assert saved["status"] == "pending"


def test_08_distribution_tasks_can_create_target_feishu_records(
    db: DatabaseClient,
    settings: IntakeSettings,
    first_record: dict[str, Any],
    mapped_record: dict[str, Any],
    distribution_config: dict[str, Any],
) -> None:
    """步骤 8：真实新增所有目标飞书测试表记录，并把分发任务标记为成功。

    使用前需要在 distribution.yaml 配置目标测试表的 app_token/table_id。
    这个测试会按 distribution.yaml 的 targets 逐个真实写入飞书测试多维表格。
    """
    sync_batch_id = new_sync_batch_id("test_feishu_intake_distribution_feishu")
    ods_raw_id = db.save_raw_record(
        settings=settings,
        record=first_record,
        sync_batch_id=sync_batch_id,
    )
    db_intake_id = db.upsert_business_record(
        settings=settings,
        mapped_record=mapped_record,
        ods_raw_id=ods_raw_id,
        validation_status="校验通过",
        validation_message="POC真实分发飞书测试通过",
        sync_status="已入库",
    )
    tasks = build_distribution_tasks(
        distribution_config,
        mapped_record=mapped_record,
        db_intake_id=db_intake_id,
        ods_raw_id=ods_raw_id,
        source_record_id=first_record["record_id"],
    )
    assert tasks

    missing_targets = [
        task.get("target_table_code") or "<未命名目标>"
        for task in tasks
        if not task.get("target_app_token") or not task.get("target_table_id")
    ]
    if missing_targets:
        pytest.skip(
            "请先在 distribution.yaml 为这些目标配置 target.app_token 和 target.table_id: "
            + ", ".join(missing_targets)
        )

    unsupported_actions = [
        task.get("target_table_code") or "<未命名目标>"
        for task in tasks
        if task.get("action_type") != "create"
    ]
    if unsupported_actions:
        pytest.skip("当前真实飞书分发测试只验证 action_type=create: " + ", ".join(unsupported_actions))

    created_results: list[tuple[int, str, str]] = []
    with FeishuClient.from_settings(settings) as client:
        for task in tasks:
            task_id = db.create_distribution_task(task)
            created = client.create_bitable_record(
                task["target_app_token"],
                task["target_table_id"],
                task.get("payload") or {},
            )
            target_record_id = created.get("record_id")
            assert target_record_id
            db.mark_distribution_task_success(task_id, target_record_id)
            created_results.append((task_id, task["target_table_code"], target_record_id))

    assert len(created_results) == len(tasks)

    for task_id, target_table_code, target_record_id in created_results:
        saved = db.fetch_one(
            """
            select target_table_code, status, target_record_id, retry_count, error_message
            from flow.feishu_distribution_task
            where id = %s
            """,
            (task_id,),
        )

        assert saved is not None
        assert saved["target_table_code"] == target_table_code
        assert saved["status"] == "success"
        assert saved["target_record_id"] == target_record_id
        assert saved["retry_count"] == 0
        assert saved["error_message"] is None
