"""飞书下游分发配置工具。

分发和回写是两件事：
- 回写：更新来源表当前 record_id。
- 分发：把业务数据投递到其他目标表，通常是新增下游任务。
"""

from __future__ import annotations

from typing import Any


def build_distribution_tasks(
    config: dict[str, Any],
    *,
    mapped_record: dict[str, Any],
    db_intake_id: int,
    ods_raw_id: int,
    source_record_id: str,
) -> list[dict[str, Any]]:
    """根据 distribution.yaml 构造分发任务列表。"""
    tasks: list[dict[str, Any]] = []
    for target in config.get("targets") or []:
        if not target.get("enabled", True):
            continue

        target_table = target.get("target") or {}
        payload = build_distribution_payload(target, mapped_record)
        tasks.append(
            {
                "source_table_code": config.get("source_table_code"),
                "source_record_id": source_record_id,
                "source_ods_id": ods_raw_id,
                "source_biz_id": db_intake_id,
                "target_table_code": target.get("target_table_code"),
                "target_app_token": target_table.get("app_token"),
                "target_table_id": target_table.get("table_id"),
                "action_type": target.get("action_type", "create"),
                "execute_immediately": bool(target.get("execute_immediately")),
                "payload": payload,
            }
        )
    return tasks


def build_distribution_payload(target_config: dict[str, Any], mapped_record: dict[str, Any]) -> dict[str, Any]:
    """构造目标飞书表字段 payload。"""
    payload: dict[str, Any] = {}
    for rule in (target_config.get("fields") or {}).values():
        feishu_field = rule.get("feishu_field")
        value_from = rule.get("value_from")
        if not feishu_field or not value_from:
            continue
        value = get_path_value(mapped_record, value_from)
        if value is not None:
            payload[feishu_field] = value
    return payload


def get_path_value(data: dict[str, Any], path: str) -> Any:
    """按点号路径从字典中取值。"""
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current
