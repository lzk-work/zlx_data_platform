"""Bundle decision rules."""

from __future__ import annotations

from ..constants import (
    SALES_UNIT_TYPE_MULTI_PRODUCT_SET,
    SALES_UNIT_TYPE_SAME_PRODUCT_MULTI_QTY,
    SALES_UNIT_TYPE_SINGLE_PRODUCT,
)
from ..models.domain_models import BundleDecision, ParsedSourceItem


def decide_bundle(items: tuple[ParsedSourceItem, ...]) -> BundleDecision:
    """判断销售单元是否需要生成组合SKU。

    Args:
        items: 已解析并匹配到商品SKU的货源明细。

    Returns:
        BundleDecision: 是否需要组合SKU、销售单元类型、总件数和不同商品数。

    Raises:
        ValueError: 明细为空时抛出。
    """
    if not items:
        raise ValueError("组合明细不能为空")

    total_product_count = sum(item.quantity for item in items)
    distinct_count = len({(item.source_url, item.spec) for item in items})

    if len(items) == 1 and items[0].quantity == 1:
        return BundleDecision(
            needs_bundle=False,
            sales_unit_type=SALES_UNIT_TYPE_SINGLE_PRODUCT,
            total_product_count=1,
            distinct_product_sku_count=1,
        )

    sales_unit_type = (
        SALES_UNIT_TYPE_SAME_PRODUCT_MULTI_QTY if len(items) == 1 else SALES_UNIT_TYPE_MULTI_PRODUCT_SET
    )
    return BundleDecision(
        needs_bundle=True,
        sales_unit_type=sales_unit_type,
        total_product_count=total_product_count,
        distinct_product_sku_count=distinct_count,
    )


def bundle_fingerprint(items: tuple[tuple[str, int], ...]) -> str:
    """生成组合SKU明细指纹。

    Args:
        items: 商品SKU和数量元组列表。

    Returns:
        str: 排序后的稳定指纹，用于判断组合是否已存在。
    """
    normalized = sorted(items, key=lambda item: item[0])
    return "|".join(f"{product_sku}*{quantity}" for product_sku, quantity in normalized)
