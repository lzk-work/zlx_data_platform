"""Build Chinese names for Dianxiaomi templates."""

from __future__ import annotations

from .spec_parser import ParsedSpecDetail


def build_product_name(display_spec_params: tuple[str, ...], quantity: int) -> str:
    """生成商品SKU中文名称。

    Args:
        display_spec_params: 用于展示的规格参数，不包含数量。
        quantity: 该明细数量；商品SKU中文名称固定按数量1展示。

    Returns:
        str: 店小秘模板可用的商品SKU名称。
    """
    return f"{'，'.join(display_spec_params)}---数量1"


def build_bundle_name(details: tuple[ParsedSpecDetail, ...]) -> str:
    """生成组合SKU中文名称。

    Args:
        details: 组合内各货源规格明细。

    Returns:
        str: 店小秘组合SKU模板可用的组合名称。
    """
    total_count = sum(detail.quantity for detail in details)
    item_names = [
        f"{'，'.join(detail.display_spec_params)}---数量{detail.quantity}"
        for detail in details
    ]
    return f"{total_count} 个/组，{'，'.join(item_names)}"
