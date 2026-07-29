"""飞书录入 POC 的数据库写入封装。

通用数据库连接能力在 connectors.database.PostgresClient。
这个模块只放 POC 当前需要的业务 SQL：保存原始记录、写 biz 表、维护映射表。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb

from connectors.database import PostgresClient, PostgresConfig

from .mapper import normalize_feishu_value
from .settings import IntakeSettings


POC_BUSINESS_COLUMNS = {"product_name", "source_url", "develop_status"}
BEIJING_TZ = ZoneInfo("Asia/Shanghai")


class DatabaseClient(PostgresClient):
    """POC 数据库客户端。

    它继承通用 PostgresClient，然后增加 POC 相关的写入方法。
    后续正式产品开发流程可以参考这种模式，新建自己的 db_client。
    """

    @classmethod
    def from_settings(cls, settings: IntakeSettings) -> "DatabaseClient":
        """用 settings 中的 DATABASE_URL 创建数据库客户端。"""
        return cls(PostgresConfig(settings.database_url))

    def ensure_schema(self, sql_path: str) -> None:
        """执行 POC 建表 SQL。"""
        self.execute_sql_file(sql_path)

    def save_raw_record(
        self,
        *,
        settings: IntakeSettings,
        record: dict[str, Any],
        sync_batch_id: str,
    ) -> int:
        """保存飞书原始记录当前态到 ODS 表。

        正式设计要求一条飞书记录只有一个稳定 ods_id。
        因此这里使用 upsert：第一次读取插入，再次读取更新 raw_payload。
        """
        payload = Jsonb(record)
        row = self.fetch_one(
            """
            insert into ods.feishu_product_intake_raw (
                source_system,
                table_code,
                feishu_app_token,
                feishu_table_id,
                feishu_record_id,
                sync_batch_id,
                raw_payload,
                raw_hash,
                first_seen_at,
                last_seen_at,
                pulled_at,
                created_at,
                updated_at
            ) values (
                'feishu',
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                md5(%s::jsonb::text),
                now() at time zone 'Asia/Shanghai',
                now() at time zone 'Asia/Shanghai',
                now() at time zone 'Asia/Shanghai',
                now() at time zone 'Asia/Shanghai',
                now() at time zone 'Asia/Shanghai'
            )
            on conflict (feishu_app_token, feishu_table_id, feishu_record_id)
            do update set
                table_code = excluded.table_code,
                sync_batch_id = excluded.sync_batch_id,
                raw_payload = excluded.raw_payload,
                raw_hash = excluded.raw_hash,
                last_seen_at = now() at time zone 'Asia/Shanghai',
                pulled_at = now() at time zone 'Asia/Shanghai',
                updated_at = now() at time zone 'Asia/Shanghai'
            returning id
            """,
            (
                settings.node_code or "product_intake_poc",
                settings.feishu_app_token,
                settings.feishu_table_id,
                record.get("record_id"),
                sync_batch_id,
                payload,
                payload,
            ),
        )
        if not row:
            raise RuntimeError("Failed to upsert raw Feishu record")
        return int(row["id"])

    def mark_raw_record_synced(self, ods_raw_id: int) -> None:
        """标记 ODS 当前态记录已完成业务同步。"""
        self.execute(
            """
            update ods.feishu_product_intake_raw
            set last_synced_at = now() at time zone 'Asia/Shanghai',
                updated_at = now() at time zone 'Asia/Shanghai'
            where id = %s
            """,
            (ods_raw_id,),
        )

    def upsert_business_record(
        self,
        *,
        settings: IntakeSettings,
        mapped_record: dict[str, Any],
        ods_raw_id: int,
        validation_status: str,
        validation_message: str,
        sync_status: str,
    ) -> int:
        """写入或更新 POC 业务表。

        参数：
            mapped_record: mapper 输出结果，包含 column_fields 和 dynamic_attributes。

        注意：
            target=column 的字段应写入标准业务表中的具体物理列。
            product_name/source_url/develop_status 是当前 POC 已落表的固定列。
            dynamic_attributes 保存所有 target=dynamic_attributes 的动态字段。
        """
        column_fields = mapped_record.get("column_fields") or {}
        dynamic_attributes = mapped_record.get("dynamic_attributes") or {}
        validate_supported_column_fields(column_fields)

        row = self.fetch_one(
            """
            insert into biz.product_intake_poc (
                feishu_app_token,
                feishu_table_id,
                feishu_record_id,
                ods_raw_id,
                product_name,
                source_url,
                develop_status,
                dynamic_attributes,
                validation_status,
                validation_message,
                sync_status
            ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (feishu_app_token, feishu_table_id, feishu_record_id)
            do update set
                ods_raw_id = excluded.ods_raw_id,
                product_name = excluded.product_name,
                source_url = excluded.source_url,
                develop_status = excluded.develop_status,
                dynamic_attributes = excluded.dynamic_attributes,
                validation_status = excluded.validation_status,
                validation_message = excluded.validation_message,
                sync_status = excluded.sync_status,
                updated_at = now() at time zone 'Asia/Shanghai'
            returning db_intake_id
            """,
            (
                settings.feishu_app_token,
                settings.feishu_table_id,
                mapped_record.get("feishu_record_id"),
                ods_raw_id,
                column_fields.get("product_name"),
                column_fields.get("source_url"),
                column_fields.get("develop_status"),
                Jsonb(dynamic_attributes),
                validation_status,
                validation_message,
                sync_status,
            ),
        )
        if not row:
            raise RuntimeError("Failed to upsert business intake record")
        return int(row["db_intake_id"])

    def upsert_record_mapping(
        self,
        *,
        settings: IntakeSettings,
        feishu_record_id: str,
        db_intake_id: int | None,
        ods_raw_id: int | None,
        stage_code: str,
    ) -> None:
        """维护飞书记录和数据库记录的对应关系。

        这个表用于后续回写、排查、追踪一条飞书记录进入数据库后的去向。
        """
        self.execute(
            """
            insert into sync.feishu_record_mapping (
                feishu_app_token,
                feishu_table_id,
                feishu_record_id,
                ods_raw_id,
                db_intake_id,
                stage_code,
                last_synced_at
            ) values (%s, %s, %s, %s, %s, %s, now() at time zone 'Asia/Shanghai')
            on conflict (feishu_app_token, feishu_table_id, feishu_record_id)
            do update set
                ods_raw_id = excluded.ods_raw_id,
                db_intake_id = excluded.db_intake_id,
                stage_code = excluded.stage_code,
                last_synced_at = now() at time zone 'Asia/Shanghai'
            """,
            (
                settings.feishu_app_token,
                settings.feishu_table_id,
                feishu_record_id,
                ods_raw_id,
                db_intake_id,
                stage_code,
            ),
        )

    def create_distribution_task(self, task: dict[str, Any]) -> dict[str, Any]:
        """创建或更新一条飞书下游分发任务。

        同一条来源 ODS 记录分发到同一个目标表、同一种动作，只保留一条任务。
        返回任务状态信息，供主流程判断是否需要立即调用飞书目标表。
        """
        payload = Jsonb(task.get("payload") or {})
        row = self.fetch_one(
            """
            with incoming as (
                select
                    %s::text as source_table_code,
                    %s::text as source_record_id,
                    %s::bigint as source_ods_id,
                    %s::bigint as source_biz_id,
                    %s::text as target_table_code,
                    %s::text as target_app_token,
                    %s::text as target_table_id,
                    %s::text as action_type,
                    %s::jsonb as payload,
                    md5(%s::jsonb::text) as payload_hash,
                    %s::text as status
            ), existing as (
                select id, status, payload_hash, target_record_id
                from flow.feishu_distribution_task
                where source_ods_id = (select source_ods_id from incoming)
                  and target_table_code = (select target_table_code from incoming)
                  and action_type = (select action_type from incoming)
            ), upserted as (
                insert into flow.feishu_distribution_task (
                    source_table_code,
                    source_record_id,
                    source_ods_id,
                    source_biz_id,
                    target_table_code,
                    target_app_token,
                    target_table_id,
                    action_type,
                    payload,
                    payload_hash,
                    status
                )
                select
                    source_table_code,
                    source_record_id,
                    source_ods_id,
                    source_biz_id,
                    target_table_code,
                    target_app_token,
                    target_table_id,
                    action_type,
                    payload,
                    payload_hash,
                    status
                from incoming
                on conflict (source_ods_id, target_table_code, action_type)
                do update set
                    source_record_id = excluded.source_record_id,
                    source_biz_id = excluded.source_biz_id,
                    target_app_token = excluded.target_app_token,
                    target_table_id = excluded.target_table_id,
                    payload = excluded.payload,
                    payload_hash = excluded.payload_hash,
                    status = case
                        when flow.feishu_distribution_task.payload_hash is distinct from excluded.payload_hash
                             and flow.feishu_distribution_task.status <> 'processing'
                        then 'pending'
                        else flow.feishu_distribution_task.status
                    end,
                    error_message = case
                        when flow.feishu_distribution_task.payload_hash is distinct from excluded.payload_hash
                        then null
                        else flow.feishu_distribution_task.error_message
                    end,
                    processed_at = case
                        when flow.feishu_distribution_task.payload_hash is distinct from excluded.payload_hash
                        then null
                        else flow.feishu_distribution_task.processed_at
                    end,
                    updated_at = now() at time zone 'Asia/Shanghai'
                returning id, status, target_record_id
            )
            select
                upserted.id,
                upserted.status,
                upserted.target_record_id,
                existing.status as previous_status,
                existing.target_record_id as previous_target_record_id,
                existing.id is null as inserted,
                existing.payload_hash is distinct from (select payload_hash from incoming) as payload_changed
            from upserted
            left join existing on true
            """,
            (
                task.get("source_table_code"),
                task.get("source_record_id"),
                task.get("source_ods_id"),
                task.get("source_biz_id"),
                task.get("target_table_code"),
                task.get("target_app_token"),
                task.get("target_table_id"),
                task.get("action_type", "create"),
                payload,
                payload,
                task.get("status", "pending"),
            ),
        )
        if not row:
            raise RuntimeError("Failed to create or update distribution task")
        return row

    def mark_distribution_task_success(self, task_id: int, target_record_id: str | None) -> None:
        """标记分发任务成功。"""
        self.execute(
            """
            update flow.feishu_distribution_task
            set status = 'success',
                target_record_id = %s,
                processed_at = now() at time zone 'Asia/Shanghai',
                updated_at = now() at time zone 'Asia/Shanghai',
                error_message = null
            where id = %s
            """,
            (target_record_id, task_id),
        )

    def mark_distribution_task_failed(self, task_id: int, error_message: str) -> None:
        """标记分发任务失败。"""
        self.execute(
            """
            update flow.feishu_distribution_task
            set status = 'failed',
                retry_count = retry_count + 1,
                error_message = %s,
                processed_at = now() at time zone 'Asia/Shanghai',
                updated_at = now() at time zone 'Asia/Shanghai'
            where id = %s
            """,
            (error_message, task_id),
        )


def validate_supported_column_fields(column_fields: dict[str, Any]) -> None:
    """校验 target=column 字段是否都有明确的数据库物理列。

    POC 当前只落了 product_name/source_url/develop_status 三个固定列。
    如果 mapping.yaml 新增了 target=column 字段，必须先在建表 SQL 和写入 SQL 中
    增加对应物理列，不能静默丢弃，也不能退回 JSON 存储。
    """
    unsupported_columns = sorted(set(column_fields) - POC_BUSINESS_COLUMNS)
    if unsupported_columns:
        joined = ", ".join(unsupported_columns)
        raise ValueError(f"target=column fields are not backed by DB columns: {joined}")


def new_sync_batch_id(prefix: str = "feishu_intake_poc") -> str:
    """生成一次同步任务的批次 ID。"""
    return f"{prefix}_{uuid4().hex}"


def extract_source_updated_at(settings: IntakeSettings, record: dict[str, Any]) -> datetime | None:
    """从飞书原始记录中提取来源更新时间。

    字段名由 node.yaml 的 source.updated_at_field 指定。该字段属于来源元数据，
    不放到 table_mapping.yaml 的业务字段映射中。
    """
    field_name = settings.source_updated_at_field
    if not field_name:
        return None
    fields = record.get("fields") or {}
    return parse_source_updated_at(normalize_feishu_value(fields.get(field_name)))


def parse_source_updated_at(value: Any) -> datetime | None:
    """把飞书更新时间值解析为不带时区的北京时间 datetime。"""
    if value in (None, ""):
        return None

    if isinstance(value, int | float) and not isinstance(value, bool):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp = timestamp / 1000
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone(BEIJING_TZ).replace(tzinfo=None)

    text = str(value).strip()
    if not text:
        return None

    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        parsed = parse_common_datetime_text(text)

    if parsed is None:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(BEIJING_TZ).replace(tzinfo=None)
    return parsed


def parse_common_datetime_text(value: str) -> datetime | None:
    """解析常见的飞书/人工可读时间文本。"""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None
