from __future__ import annotations

from apps.sku_mapping_poc.src.models import (
    DailyFirstOrderRow,
    FirstCategoryCode,
    HistoricalOrderedPlatformSku,
    ProductSkuMaster,
    SkuPlatformMapping,
    UploadedProductSku,
)
from apps.sku_mapping_poc.src.report import build_system_status_message, build_system_status_summary


def test_system_status_summary_counts_current_state() -> None:
    summary = build_system_status_summary(
        daily_rows=[
            DailyFirstOrderRow(2, "P1", "S1", "O1", "Walmart", "shop", "2026-07-23", "url", "spec"),
            DailyFirstOrderRow(3, "P2", "S2", "O2", "Walmart", "shop", "2026-07-23", "url", "spec"),
        ],
        product_master_rows=[
            ProductSkuMaster("S1", "url", "spec"),
            ProductSkuMaster("S2", "url", "spec"),
            ProductSkuMaster("S2", "url", "spec"),
        ],
        first_category_code_rows=[
            FirstCategoryCode("Home", "家居", "JT"),
            FirstCategoryCode("Home2", "家居2", "JT"),
            FirstCategoryCode("Sports", "运动", "YD"),
        ],
        uploaded_rows=[UploadedProductSku("S1"), UploadedProductSku("S1"), UploadedProductSku("S2")],
        historical_rows=[HistoricalOrderedPlatformSku("P1"), HistoricalOrderedPlatformSku("P1"), HistoricalOrderedPlatformSku("P2")],
        mapping_rows=[
            SkuPlatformMapping("S1", "P1"),
            SkuPlatformMapping("S1", "P2"),
            SkuPlatformMapping("S2", "P3"),
            SkuPlatformMapping("", "P4"),
        ],
        product_source_mode="excel",
    )

    assert summary.daily_input_rows == 2
    assert summary.product_master_skus == 2
    assert summary.first_category_codes == 2
    assert summary.uploaded_product_skus == 2
    assert summary.historical_platform_skus == 2
    assert summary.mapped_product_skus == 2
    assert summary.mapped_platform_skus == 3
    assert "映射关系平台SKU数: 3" in build_system_status_message(summary)
