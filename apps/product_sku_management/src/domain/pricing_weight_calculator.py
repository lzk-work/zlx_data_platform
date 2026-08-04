"""Purchase price and weight calculations."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation


def to_decimal(value: object, field_name: str) -> Decimal:
    """将业务输入转换为Decimal。

    Args:
        value: 输入值。
        field_name: 字段名称，用于异常提示。

    Returns:
        Decimal: 转换后的非负数字。

    Raises:
        ValueError: 值为空、非数字或小于0时抛出。
    """
    if value is None or value == "":
        raise ValueError(f"{field_name}不能为空")
    try:
        decimal_value = Decimal(str(value).strip())
    except (InvalidOperation, AttributeError) as exc:
        raise ValueError(f"{field_name}必须是数字") from exc
    if decimal_value < 0:
        raise ValueError(f"{field_name}不能小于 0")
    return decimal_value


def kg_to_g(weight_kg: Decimal) -> Decimal:
    """将千克转换为克。

    Args:
        weight_kg: 千克重量。

    Returns:
        Decimal: 克重量。
    """
    return weight_kg * Decimal("1000")


def calculate_reference_value(group_total: Decimal, group_product_count: int, field_name: str) -> Decimal:
    """按货源组总值拆分单个商品SKU参考值。

    Args:
        group_total: 货源组采购价或重量总值。
        group_product_count: 货源组内商品总数量。
        field_name: 字段名称，用于异常提示。

    Returns:
        Decimal: 拆分后的单件参考值。

    Raises:
        ValueError: 商品总数量小于等于0时抛出。
    """
    if group_product_count <= 0:
        raise ValueError(f"{field_name}无法按 0 数量拆分")
    return group_total / Decimal(group_product_count)
