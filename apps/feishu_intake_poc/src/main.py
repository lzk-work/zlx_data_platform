"""飞书录入 POC 程序入口。

运行位置：项目根目录 E:/WorkSpace/zlx_data_platform

常用命令：

    python -m apps.feishu_intake_poc.src.main --check
    python -m apps.feishu_intake_poc.src.main --check --init-db
    python -m apps.feishu_intake_poc.src.main --task incremental
    python -m apps.feishu_intake_poc.src.main --task reconcile

这个文件只负责编排流程，不直接写底层飞书请求和数据库连接逻辑。
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any

from .db_client import DatabaseClient, new_sync_batch_id
from .distribution import build_distribution_tasks
from .feishu_client import FeishuClient
from .filters import effective_filter_expression, filter_records_by_read_filter
from .mapper import build_writeback_fields, map_feishu_record
from .settings import load_mapping, load_settings, load_yaml_file
from .validator import validate_record


@dataclass
class RunStats:
    """一次 POC 同步运行的统计结果。"""

    pulled: int = 0
    api_pulled: int = 0
    raw_saved: int = 0
    valid: int = 0
    invalid: int = 0
    db_written: int = 0
    writeback_success: int = 0
    writeback_failed: int = 0
    distribution_created: int = 0
    distribution_success: int = 0
    distribution_failed: int = 0


def main() -> None:
    """POC 主入口。

    入口负责三件事：读取配置、决定运行模式、调用具体流程。
    """
    args = parse_args()
    settings = load_settings(
        args.env,
        node_code=args.node,
        node_config_root=args.node_config_root,
        task_code=args.task,
    )
    mapping = load_mapping(settings.mapping_path)
    writeback_config = load_yaml_file(settings.writeback_config_path)
    distribution_config = load_yaml_file(settings.distribution_config_path)

    db = DatabaseClient.from_settings(settings)
    if args.init_db or not args.check:
        db.ensure_schema(str(settings.sql_path))

    if args.check:
        run_health_check(settings, mapping, db)
        return

    sync_batch_id = new_sync_batch_id()
    stats = RunStats()

    with FeishuClient.from_settings(settings) as feishu:
        records = feishu.list_bitable_records(
            settings.feishu_app_token,
            settings.feishu_table_id,
            view_id=settings.feishu_view_id,
            filter_expression=effective_filter_expression(settings.feishu_filter, settings.feishu_read_filter),
        )
        stats.api_pulled = len(records)
        if not settings.feishu_filter:
            records = filter_records_by_read_filter(records, settings.feishu_read_filter)
        stats.pulled = len(records)

        for record in records:
            process_record(
                settings=settings,
                mapping=mapping,
                writeback_config=writeback_config,
                distribution_config=distribution_config,
                sync_batch_id=sync_batch_id,
                feishu=feishu,
                db=db,
                record=record,
                stats=stats,
            )

        if settings.notification_receive_id:
            feishu.send_text_message(
                settings.notification_receive_id,
                build_summary_message(sync_batch_id, stats),
                receive_id_type=settings.notification_receive_id_type,
            )

    print(build_summary_message(sync_batch_id, stats))


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="Run the Feishu intake POC")
    parser.add_argument("--env", help="Path to local .env file")
    parser.add_argument("--node", help="POC 要执行的飞书录入节点编码")
    parser.add_argument("--node-config-root", help="飞书节点配置根目录")
    parser.add_argument("--task", help="要执行的节点任务编码，例如 incremental 或 reconcile")
    parser.add_argument("--check", action="store_true", help="Check Feishu and database connectivity")
    parser.add_argument("--init-db", action="store_true", help="Create POC schemas/tables and exit when used with --check")
    return parser.parse_args()


def run_health_check(settings: Any, mapping: dict[str, Any], db: DatabaseClient) -> None:
    """检查飞书和数据库连接。

    这个检查不会读写多维表格业务数据，只验证凭证和数据库连接是否可用。
    """
    db_status = db.health_check()
    with FeishuClient.from_settings(settings) as feishu:
        feishu_status = feishu.health_check()
    print("POC配置检查通过")
    if settings.node_code:
        print(f"节点: {settings.node_code}")
        print(f"任务: {settings.task_code}")
    print(f"数据库: {db_status.get('database_name')} / {db_status.get('user_name')}")
    print(f"飞书token前缀: {feishu_status.get('tenant_access_token_prefix')}")
    print(f"字段映射数量: {len(mapping.get('fields') or {})}")


def process_record(
    *,
    settings: Any,
    mapping: dict[str, Any],
    writeback_config: dict[str, Any],
    distribution_config: dict[str, Any],
    sync_batch_id: str,
    feishu: FeishuClient,
    db: DatabaseClient,
    record: dict[str, Any],
    stats: RunStats,
) -> None:
    """处理一条飞书记录。

    流程：upsert 原始当前态并获得 ods_raw_id -> 字段映射 -> 校验 -> 写 biz 表 -> 回写飞书。
    校验失败的数据只回写错误信息，不进入 biz 标准表。
    """
    record_id = record.get("record_id")
    if not record_id:
        return

    # ODS 原始当前态先保存，方便排查“飞书当前给了什么”。
    ods_raw_id = db.save_raw_record(settings=settings, record=record, sync_batch_id=sync_batch_id)
    stats.raw_saved += 1

    mapped = map_feishu_record(record, mapping)
    errors = validate_record(mapped, mapping)

    db_intake_id: int | None = None
    if errors:
        stats.invalid += 1
        validation_status = "校验失败"
        validation_message = "; ".join(errors)
        sync_status = "未入库"
    else:
        stats.valid += 1
        validation_status = "校验通过"
        validation_message = ""
        sync_status = "已入库"
        db_intake_id = db.upsert_business_record(
            settings=settings,
            mapped_record=mapped,
            ods_raw_id=ods_raw_id,
            validation_status=validation_status,
            validation_message=validation_message,
            sync_status=sync_status,
        )
        db.upsert_record_mapping(
            settings=settings,
            feishu_record_id=record_id,
            db_intake_id=db_intake_id,
            ods_raw_id=ods_raw_id,
            stage_code=mapping.get("table_code", "feishu_intake_poc"),
        )
        db.mark_raw_record_synced(ods_raw_id)
        stats.db_written += 1
        create_distribution_tasks(
            mapping=mapping,
            distribution_config=distribution_config,
            mapped_record=mapped,
            db_intake_id=db_intake_id,
            ods_raw_id=ods_raw_id,
            record_id=record_id,
            feishu=feishu,
            db=db,
            stats=stats,
            allow_execute_immediately=settings.allow_execute_distribution_immediately,
        )

    writeback_fields = build_writeback_fields(
        mapping,
        db_intake_id=db_intake_id,
        validation_status=validation_status,
        validation_message=validation_message,
        sync_status=sync_status,
        writeback_config=writeback_config,
    )
    if not writeback_fields:
        return

    try:
        feishu.update_bitable_record(
            settings.feishu_app_token,
            settings.feishu_table_id,
            record_id,
            writeback_fields,
        )
        stats.writeback_success += 1
    except Exception as exc:  # noqa: BLE001 - POC 阶段不中断整批，先记录失败并继续处理。
        stats.writeback_failed += 1
        print(f"Failed to write back Feishu record {record_id}: {exc}")


def create_distribution_tasks(
    *,
    mapping: dict[str, Any],
    distribution_config: dict[str, Any],
    mapped_record: dict[str, Any],
    db_intake_id: int,
    ods_raw_id: int,
    record_id: str,
    feishu: FeishuClient,
    db: DatabaseClient,
    stats: RunStats,
    allow_execute_immediately: bool,
) -> None:
    """根据 distribution.yaml 创建并可选执行下游分发任务。"""
    tasks = build_distribution_tasks(
        distribution_config,
        mapped_record=mapped_record,
        db_intake_id=db_intake_id,
        ods_raw_id=ods_raw_id,
        source_record_id=record_id,
    )
    for task in tasks:
        task_state = db.create_distribution_task(task)
        task_id = int(task_state["id"])
        stats.distribution_created += 1
        if not (allow_execute_immediately and task.get("execute_immediately")):
            continue
        if task_state.get("previous_status") == "success" and not task_state.get("payload_changed"):
            continue
        if not task.get("target_app_token") or not task.get("target_table_id"):
            db.mark_distribution_task_failed(task_id, "Target app_token/table_id is not configured")
            stats.distribution_failed += 1
            continue
        try:
            target_record_id = task_state.get("target_record_id") or task_state.get("previous_target_record_id")
            if target_record_id:
                feishu.update_bitable_record(
                    task["target_app_token"],
                    task["target_table_id"],
                    str(target_record_id),
                    task.get("payload") or {},
                )
                db.mark_distribution_task_success(task_id, str(target_record_id))
            else:
                created = feishu.create_bitable_record(
                    task["target_app_token"],
                    task["target_table_id"],
                    task.get("payload") or {},
                )
                db.mark_distribution_task_success(task_id, created.get("record_id") or created.get("id"))
            stats.distribution_success += 1
        except Exception as exc:  # noqa: BLE001 - 分发失败不影响主入库，记录任务状态后允许重试。
            db.mark_distribution_task_failed(task_id, str(exc))
            stats.distribution_failed += 1


def build_summary_message(sync_batch_id: str, stats: RunStats) -> str:
    """生成终端输出和飞书通知共用的同步摘要。"""
    return (
        "飞书录入POC同步完成\n"
        f"批次: {sync_batch_id}\n"
        f"API读取: {stats.api_pulled}\n"
        f"任务过滤后: {stats.pulled}\n"
        f"原始当前态: {stats.raw_saved}\n"
        f"校验通过: {stats.valid}\n"
        f"校验失败: {stats.invalid}\n"
        f"入库: {stats.db_written}\n"
        f"回写成功: {stats.writeback_success}\n"
        f"回写失败: {stats.writeback_failed}\n"
        f"分发任务: {stats.distribution_created}\n"
        f"分发成功: {stats.distribution_success}\n"
        f"分发失败: {stats.distribution_failed}"
    )


if __name__ == "__main__":
    main()
