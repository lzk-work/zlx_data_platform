"""飞书录入 POC 校验工具。

当前只做最小可用校验：必填、枚举、基础类型。
后续正式业务可以在这里扩展 URL、日期、数字范围、唯一性等规则。
"""

from __future__ import annotations

from typing import Any


class ValidationError(Exception):
    """业务校验失败异常。当前 POC 主要返回错误列表，暂不主动抛出。"""


def validate_record(record: dict[str, Any], mapping: dict[str, Any]) -> list[str]:
    """校验一条标准化后的记录。

    参数：
        record: mapper 输出的记录，包含 column_fields 和 dynamic_attributes。
        mapping: table_mapping.yaml 映射配置。

    返回：
        错误信息列表；空列表表示校验通过。
    """
    errors: list[str] = []
    field_rules = mapping.get("fields") or {}

    for field_name, rule in field_rules.items():
        value = get_mapped_value(record, field_name, rule)
        label = rule.get("label") or rule.get("feishu_field") or field_name

        if rule.get("required") and is_blank(value):
            errors.append(f"{label}不能为空")
            continue

        if is_blank(value):
            continue

        allowed_values = rule.get("allowed_values")
        if allowed_values and value not in allowed_values:
            errors.append(f"{label}不在允许范围内: {value}")

        expected_type = rule.get("type")
        if expected_type and not matches_type(value, expected_type):
            errors.append(f"{label}类型错误，期望 {expected_type}")

    return errors


def get_mapped_value(record: dict[str, Any], field_name: str, rule: dict[str, Any]) -> Any:
    """根据字段去向读取待校验值。"""
    target = rule.get("target", "column")
    if target == "dynamic_attributes":
        return (record.get("dynamic_attributes") or {}).get(field_name)
    return (record.get("column_fields") or {}).get(field_name, record.get(field_name))


def is_blank(value: Any) -> bool:
    """判断值是否为空。"""
    return value is None or value == "" or value == [] or value == {}


def matches_type(value: Any, expected_type: str) -> bool:
    """按配置检查基础类型。"""
    if expected_type == "text":
        return isinstance(value, str)
    if expected_type == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "list":
        return isinstance(value, list)
    return True
