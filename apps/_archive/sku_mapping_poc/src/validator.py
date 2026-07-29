"""输入和状态表校验。"""

from __future__ import annotations

from collections import Counter, defaultdict

from .models import DailyFirstOrderRow, ProductSkuMaster, SkuPlatformMapping
from .normalizer import build_source_key


def find_duplicate_product_skus(master_rows: list[ProductSkuMaster]) -> dict[str, int]:
    """找出商品基础库中重复的商品 SKU。"""
    counts = Counter(row.product_sku for row in master_rows if row.product_sku)
    return {product_sku: count for product_sku, count in counts.items() if count > 1}


def find_invalid_product_source_rows(master_rows: list[ProductSkuMaster]) -> list[str]:
    """找出商品基础库关键字段为空的商品 SKU。"""
    invalid: list[str] = []
    for index, row in enumerate(master_rows, start=1):
        if not row.product_sku or not row.source_url or not row.spec:
            invalid.append(row.product_sku or f"第{index}行")
    return invalid


def find_duplicate_daily_platform_skus(rows: list[DailyFirstOrderRow]) -> set[str]:
    """找出同批重复的平台 SKU。"""
    counts = Counter(row.platform_sku for row in rows if row.platform_sku)
    return {platform_sku for platform_sku, count in counts.items() if count > 1}


def find_ambiguous_source_keys(master_rows: list[ProductSkuMaster]) -> dict[tuple[str, str], list[str]]:
    """找出同一货源键对应多个商品 SKU 的情况。"""
    index: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in master_rows:
        if row.source_url and row.spec and row.product_sku:
            index[build_source_key(row.source_url, row.spec)].add(row.product_sku)
    return {key: sorted(values) for key, values in index.items() if len(values) > 1}


def find_duplicate_mapping_platform_skus(rows: list[SkuPlatformMapping]) -> dict[str, list[str]]:
    """找出一个平台 SKU 对应多个商品 SKU 的状态表问题。"""
    index: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if row.platform_sku and row.product_sku:
            index[row.platform_sku].add(row.product_sku)
    return {platform_sku: sorted(values) for platform_sku, values in index.items() if len(values) > 1}


def validate_daily_required(row: DailyFirstOrderRow) -> list[tuple[str, str, str]]:
    """校验每日输入必填字段。"""
    checks = [
        ("platform_sku_missing", row.platform_sku, "平台SKU为空"),
        ("order_no_missing", row.order_no, "订单号为空"),
        ("platform_channel_missing", row.platform_channel, "平台渠道为空"),
        ("shop_account_missing", row.shop_account, "店铺账号为空"),
        ("order_time_missing", row.order_time, "出单时间为空"),
        ("corrected_source_url_missing", row.corrected_source_url, "校正后货源链接为空"),
        ("corrected_spec_missing", row.corrected_spec, "校正后规格为空"),
    ]
    return [(code, message, "补充每日出单平台SKU输入表中的必填字段") for code, value, message in checks if not value]
