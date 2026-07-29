"""新商品 SKU 编码生成。"""

from __future__ import annotations

import re

from .models import GeneratedSkuResult


def generate_product_sku(
    existing_skus: set[str],
    batch_generated_skus: set[str],
    *,
    category_code: str,
    sku_date: str,
) -> GeneratedSkuResult:
    """按 类目编码_YYMMDD_递增序号 生成新商品 SKU。"""
    code = category_code.strip()
    if not code:
        raise ValueError("生成商品SKU缺少一级类目编码")
    if not re.fullmatch(r"\d{6}", sku_date):
        raise ValueError("生成商品SKU日期必须为 YYMMDD")

    pattern = re.compile(rf"^[^_]+_{re.escape(sku_date)}_(\d+)$")
    max_number = 0
    for sku in existing_skus | batch_generated_skus:
        match = pattern.match(sku)
        if match:
            max_number = max(max_number, int(match.group(1)))

    next_number = max_number + 1
    while True:
        product_sku = f"{code}_{sku_date}_{next_number}"
        if product_sku not in existing_skus and product_sku not in batch_generated_skus:
            return GeneratedSkuResult(product_sku=product_sku, message="系统按类目编码和日期生成商品SKU")
        next_number += 1
