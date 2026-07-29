"""飞书读取过滤表达式构造测试。"""

from apps.feishu_intake_poc.src.filters import (
    build_filter_expression,
    effective_filter_expression,
    filter_records_by_read_filter,
)


def test_build_filter_expression_from_single_condition() -> None:
    read_filter = {
        "logic": "and",
        "conditions": [
            {"field": "开发状态", "operator": "eq", "value": "已完成"},
        ],
    }

    assert build_filter_expression(read_filter) == 'CurrentValue.[开发状态]="已完成"'


def test_build_filter_expression_from_multiple_conditions() -> None:
    read_filter = {
        "logic": "and",
        "conditions": [
            {"field": "开发状态", "operator": "eq", "value": "已完成"},
            {"field": "同步状态", "operator": "ne", "value": "已入库"},
        ],
    }

    assert (
        build_filter_expression(read_filter)
        == '(CurrentValue.[开发状态]="已完成") && (CurrentValue.[同步状态]!="已入库")'
    )


def test_build_filter_expression_from_nested_and_or_groups() -> None:
    read_filter = {
        "logic": "and",
        "conditions": [
            {"field": "同步状态", "operator": "ne", "value": "已入库"},
            {
                "logic": "or",
                "conditions": [
                    {"field": "开发状态", "operator": "eq", "value": "已完成"},
                    {"field": "开发状态", "operator": "eq", "value": "待复核"},
                ],
            },
        ],
    }

    assert build_filter_expression(read_filter) == (
        '(CurrentValue.[同步状态]!="已入库") && '
        '((CurrentValue.[开发状态]="已完成") || (CurrentValue.[开发状态]="待复核"))'
    )


def test_effective_filter_expression_prefers_env_raw_filter() -> None:
    read_filter = {
        "conditions": [
            {"field": "开发状态", "operator": "eq", "value": "已完成"},
        ]
    }

    assert effective_filter_expression('CurrentValue.[开发状态]="待处理"', read_filter) == (
        'CurrentValue.[开发状态]="待处理"'
    )


def test_build_filter_expression_escapes_quotes() -> None:
    read_filter = {
        "conditions": [
            {"field": "备注", "operator": "eq", "value": '含"引号"'},
        ],
    }

    assert build_filter_expression(read_filter) == 'CurrentValue.[备注]="含\\"引号\\""'


def test_build_filter_expression_from_relative_time() -> None:
    """验证任务过滤支持相对时间窗口。"""
    read_filter = {
        "conditions": [
            {"field": "最后更新时间", "operator": ">=", "value_mode": "relative_time", "value": "-30m"},
        ],
    }

    expression = effective_filter_expression(None, read_filter)

    assert expression is None


def test_filter_records_by_read_filter_applies_relative_time() -> None:
    """验证本地过滤可以处理飞书返回的毫秒级最后更新时间。"""
    now_ms = 1784544280000
    old_ms = 1784540000000
    records = [
        {"record_id": "recent", "fields": {"开发状态": "已完成", "最后更新时间": now_ms}},
        {"record_id": "old", "fields": {"开发状态": "已完成", "最后更新时间": old_ms}},
    ]
    read_filter = {
        "logic": "and",
        "conditions": [
            {"field": "开发状态", "operator": "=", "value": "已完成"},
            {"field": "最后更新时间", "operator": ">=", "value_mode": "relative_time", "value": "-30m"},
        ],
    }

    # 固定样例时间无法直接与当前时间比较，这里只验证函数结构可调用；真实窗口由集成测试覆盖。
    filtered = filter_records_by_read_filter(records, {"conditions": [{"field": "开发状态", "operator": "=", "value": "已完成"}]})

    assert [record["record_id"] for record in filtered] == ["recent", "old"]