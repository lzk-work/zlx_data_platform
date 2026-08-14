"""Build Chinese names for Dianxiaomi templates."""

from __future__ import annotations

from .spec_parser import ParsedSpecDetail


def build_product_name(display_spec_params: tuple[str, ...], quantity: int) -> str:
    """生成商品SKU中文名称。

    Args:
        display_spec_params: 用于展示的规格参数，不包含数量。
        quantity: 商品SKU身份数量。

    Returns:
        str: 店小秘模板可用的商品SKU名称。
    """
    spec_text = "，".join(display_spec_params)
    if quantity > 1:
        return f"{quantity}个/组，{spec_text}---数量{quantity}"
    return f"{spec_text}---数量{quantity}"


def build_forced_package_name(details: tuple[ParsedSpecDetail, ...]) -> str:
    """生成强制合包商品SKU中文名称。

    Args:
        details: 强制合包内各货源规格明细。

    Returns:
        str: 店小秘商品SKU模板可用的合包名称。
    """
    total_count = sum(detail.quantity for detail in details)
    item_names = [
        f"{'，'.join(detail.display_spec_params)}---数量{detail.quantity}"
        for detail in details
    ]
    return f"{total_count}个/组，{'，'.join(item_names)}"


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
