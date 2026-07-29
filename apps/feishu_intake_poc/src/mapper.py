"""飞书字段映射工具。

飞书字段面向业务人员，可以是中文；数据库和代码字段使用英文。
这里负责把飞书原始记录转换成内部标准字段形状。

映射时会区分字段去向：

- target: column，进入数据库标准业务表中的具体物理字段。
- target: dynamic_attributes，进入动态属性 JSON。
- raw_payload 不需要配置，ODS 会自动保存飞书原始整行。
"""

from __future__ import annotations

from typing import Any

COLUMN_TARGET = "column"
DYNAMIC_ATTRIBUTES_TARGET = "dynamic_attributes"


def map_feishu_record(record: dict[str, Any], mapping: dict[str, Any]) -> dict[str, Any]:
    """把一条飞书记录转换为内部字段。

    参数：
        record: 飞书 API 返回的一条记录，通常包含 record_id 和 fields。
        mapping: table_mapping.yaml 读取后的映射配置。

    返回：
        包含普通扁平字段、column_fields、dynamic_attributes 和 raw_fields 的字典。

    注意：
        为了兼容早期 POC，固定列字段仍会同步放在返回字典顶层，
        例如 mapped["product_name"]。新逻辑优先读取 column_fields。
    """
    fields = record.get("fields", {}) or {}
    mapped: dict[str, Any] = {
        "feishu_record_id": record.get("record_id"),
        "raw_fields": fields,
        "column_fields": {},
        "dynamic_attributes": {},
    }

    for target_field, rule in (mapping.get("fields") or {}).items():
        feishu_field = rule.get("feishu_field")
        if not feishu_field:
            continue

        value = normalize_feishu_value(fields.get(feishu_field))
        target = rule.get("target", COLUMN_TARGET)

        if target == DYNAMIC_ATTRIBUTES_TARGET:
            mapped["dynamic_attributes"][target_field] = value
        else:
            mapped["column_fields"][target_field] = value
            mapped[target_field] = value

    return mapped


def build_writeback_fields(
    mapping: dict[str, Any],
    *,
    db_intake_id: int | None,
    validation_status: str,
    validation_message: str,
    sync_status: str,
    writeback_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """根据配置构造要回写到飞书的系统字段。

    参数：
        mapping: table_mapping.yaml 映射配置，兼容旧的 system_writeback_fields。
        db_intake_id: 数据库业务表主键，校验失败时可以为空。
        validation_status: 校验状态，例如“校验通过”“校验失败”。
        validation_message: 校验说明或错误信息。
        sync_status: 同步状态，例如“已入库”“未入库”。
        writeback_config: writeback.yaml 配置，优先级高于旧 mapping 写法。

    返回：
        飞书字段名到回写值的字典。
    """
    values = {
        # 飞书文本字段不会总是自动把整数转成文本，先按 POC 系统字段约定转成字符串。
        "db_intake_id": str(db_intake_id) if db_intake_id is not None else None,
        "validation_status": validation_status,
        "validation_message": validation_message,
        "sync_status": sync_status,
    }

    if writeback_config and writeback_config.get("fields"):
        return build_configured_writeback_fields(writeback_config, values)

    writeback = mapping.get("system_writeback_fields") or {}
    result: dict[str, Any] = {}
    for key, feishu_field in writeback.items():
        if feishu_field and key in values:
            result[feishu_field] = values[key]
    return result


def build_configured_writeback_fields(config: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
    """根据 writeback.yaml 构造飞书回写字段。"""
    result: dict[str, Any] = {}
    for field_rule in (config.get("fields") or {}).values():
        feishu_field = field_rule.get("feishu_field")
        value_from = field_rule.get("value_from")
        if not feishu_field or not value_from:
            continue
        value = values.get(value_from)
        if value is None:
            continue
        result[feishu_field] = format_writeback_value(value, field_rule.get("type"))
    return result


def format_writeback_value(value: Any, field_type: str | None) -> Any:
    """按回写字段类型格式化值。"""
    if field_type == "text":
        return str(value)
    return value


def normalize_feishu_value(value: Any) -> Any:
    """把飞书单元格的常见结构简化成 Python 值。

    参数：
        value: 飞书字段原始值，可能是字符串、数字、列表或字典。

    返回：
        归一化后的 Python 值。

    注意：
        飞书字段可能返回 list/dict，例如人员、链接、单选、多选等。
        POC 阶段先做轻量归一化，复杂字段后续再按字段类型扩展。
    """
    if value is None:
        return None
    if isinstance(value, list):
        normalized = [normalize_feishu_value(item) for item in value]
        if len(normalized) == 1:
            return normalized[0]
        return normalized
    if isinstance(value, dict):
        for key in ("text", "name", "link", "url", "value"):
            if key in value:
                return normalize_feishu_value(value[key])
        return {key: normalize_feishu_value(item) for key, item in value.items()}
    return value
