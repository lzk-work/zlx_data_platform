"""飞书多维表格读取过滤表达式构造工具。

常规筛选条件写在 node.yaml 的 tasks[].read_filter 中。

注意：飞书系统“最后更新时间”字段返回毫秒时间戳，但 records.list 的 filter
对精确分钟窗口支持不稳定。因此 POC 使用两段过滤：
1. 飞书 API 端执行普通条件，例如开发状态=已完成。
2. Python 端执行 value_mode=relative_time 的精确时间窗口判断。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from .mapper import normalize_feishu_value


BEIJING_TZ = ZoneInfo("Asia/Shanghai")

OPERATOR_SYMBOLS = {
    "eq": "=",
    "=": "=",
    "ne": "!=",
    "!=": "!=",
    "gt": ">",
    ">": ">",
    "gte": ">=",
    ">=": ">=",
    "lt": "<",
    "<": "<",
    "lte": "<=",
    "<=": "<=",
}

LOGIC_SYMBOLS = {
    "and": "&&",
    "&&": "&&",
    "or": "||",
    "||": "||",
}


def effective_filter_expression(raw_filter: str | None, read_filter: dict[str, Any] | None) -> str | None:
    """返回最终用于飞书记录读取接口的过滤表达式。

    优先级：
    1. .env 中的 FEISHU_FILTER，有值时直接使用。
    2. node.yaml 当前任务的 read_filter 结构化配置，但跳过 relative_time 条件。
    3. 都没有时返回 None，表示不加 API 过滤。
    """
    if raw_filter:
        return raw_filter
    return build_filter_expression(read_filter, include_relative_time=False)


def build_filter_expression(config: dict[str, Any] | None, *, include_relative_time: bool = True) -> str | None:
    """根据 read_filter 配置生成飞书 filter 表达式。"""
    if not config:
        return None

    expression = config.get("expression")
    if expression:
        return str(expression)

    return build_filter_node(config, include_relative_time=include_relative_time)


def build_filter_node(node: dict[str, Any], *, include_relative_time: bool = True) -> str | None:
    """递归构造过滤表达式节点。"""
    if "field" in node:
        return build_condition_expression(node, include_relative_time=include_relative_time)

    conditions = node.get("conditions") or []
    child_expressions = [build_filter_node(condition, include_relative_time=include_relative_time) for condition in conditions]
    expressions = [item for item in child_expressions if item]
    if not expressions:
        return None
    if len(expressions) == 1:
        return expressions[0]

    logic = str(node.get("logic", "and")).lower()
    joiner = f" {LOGIC_SYMBOLS.get(logic, '&&')} "
    return joiner.join(f"({item})" for item in expressions)


def build_condition_expression(condition: dict[str, Any], *, include_relative_time: bool = True) -> str | None:
    """把单个结构化条件转换成飞书 filter 子表达式。"""
    if condition.get("value_mode") == "relative_time" and not include_relative_time:
        return None

    field = condition.get("field")
    if not field:
        raise ValueError("read_filter condition must include field")

    operator = str(condition.get("operator", "eq")).lower()
    symbol = OPERATOR_SYMBOLS.get(operator)
    if not symbol:
        raise ValueError(f"Unsupported read_filter operator: {operator}")

    value = format_filter_value(resolve_filter_value(condition))
    return f"CurrentValue.[{field}]{symbol}{value}"


def filter_records_by_read_filter(records: list[dict[str, Any]], read_filter: dict[str, Any] | None) -> list[dict[str, Any]]:
    """用 Python 对飞书返回记录做本地精确过滤。

    主要用于处理 value_mode=relative_time 的分钟级窗口。
    普通字段也会再次校验一次，避免 API 端粗筛和本地逻辑不一致。
    """
    if not read_filter or read_filter.get("expression"):
        return records
    return [record for record in records if record_matches_filter(record, read_filter)]


def record_matches_filter(record: dict[str, Any], node: dict[str, Any]) -> bool:
    """判断单条飞书记录是否符合 read_filter 节点。"""
    if "field" in node:
        return record_matches_condition(record, node)

    conditions = [condition for condition in node.get("conditions") or [] if isinstance(condition, dict)]
    if not conditions:
        return True

    logic = str(node.get("logic", "and")).lower()
    results = [record_matches_filter(record, condition) for condition in conditions]
    if logic in {"or", "||"}:
        return any(results)
    return all(results)


def record_matches_condition(record: dict[str, Any], condition: dict[str, Any]) -> bool:
    """判断单条飞书记录是否符合单个条件。"""
    field = condition.get("field")
    if not field:
        return True
    fields = record.get("fields") or {}
    actual = normalize_feishu_value(fields.get(field))
    expected = resolve_filter_value(condition)
    return compare_values(actual, expected, str(condition.get("operator", "eq")).lower())


def compare_values(actual: Any, expected: Any, operator: str) -> bool:
    """按 read_filter operator 比较两个值。"""
    if isinstance(expected, datetime):
        actual_dt = parse_datetime_value(actual)
        if actual_dt is None:
            return False
        return compare_ordered_values(actual_dt, expected, operator)

    if operator in {"eq", "="}:
        return actual == expected
    if operator in {"ne", "!="}:
        return actual != expected
    return compare_ordered_values(actual, expected, operator)


def compare_ordered_values(actual: Any, expected: Any, operator: str) -> bool:
    """比较支持大小关系的值。"""
    try:
        if operator in {"gt", ">"}:
            return actual > expected
        if operator in {"gte", ">="}:
            return actual >= expected
        if operator in {"lt", "<"}:
            return actual < expected
        if operator in {"lte", "<="}:
            return actual <= expected
    except TypeError:
        return False
    raise ValueError(f"Unsupported read_filter operator: {operator}")


def resolve_filter_value(condition: dict[str, Any]) -> Any:
    """解析过滤值。"""
    if condition.get("value_mode") != "relative_time":
        return condition.get("value")
    return datetime.now(BEIJING_TZ).replace(tzinfo=None) + parse_relative_delta(str(condition.get("value") or ""))


def parse_datetime_value(value: Any) -> datetime | None:
    """把飞书日期/更新时间值解析为不带时区的北京时间 datetime。"""
    value = normalize_feishu_value(value)
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
    """解析常见文本时间。"""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def parse_relative_delta(value: str) -> timedelta:
    """解析相对时间配置，支持 -30m、-2h、-3d。"""
    if len(value) < 3 or not value.startswith("-"):
        raise ValueError(f"Unsupported relative_time value: {value}")
    amount_text = value[1:-1]
    unit = value[-1]
    if not amount_text.isdigit():
        raise ValueError(f"Unsupported relative_time value: {value}")

    amount = int(amount_text)
    if unit == "m":
        return -timedelta(minutes=amount)
    if unit == "h":
        return -timedelta(hours=amount)
    if unit == "d":
        return -timedelta(days=amount)
    raise ValueError(f"Unsupported relative_time unit: {unit}")


def format_filter_value(value: Any) -> str:
    """把 Python 值格式化成飞书 filter 表达式中的字面量。"""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float) and not isinstance(value, bool):
        return str(value)
    if value is None:
        return '""'
    if isinstance(value, datetime):
        return f'"{value.strftime("%Y-%m-%d %H:%M:%S")}"'

    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'
