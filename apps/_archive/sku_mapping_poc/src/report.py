"""运行摘要。"""

from __future__ import annotations

from .models import (
    DailyFirstOrderRow,
    FirstCategoryCode,
    HistoricalOrderedPlatformSku,
    ProductSkuMaster,
    RunSummary,
    SkuPlatformMapping,
    SystemStatusSummary,
    UploadedProductSku,
)


def build_summary_message(summary: RunSummary) -> str:
    """生成终端摘要。"""
    return (
        "商品SKU映射POC处理完成\n"
        f"批次: {summary.batch_id}\n"
        f"每日输入: {summary.input_rows}\n"
        f"首单处理: {summary.first_order_processed}\n"
        f"历史跳过: {summary.historical_skipped}\n"
        f"ERP新增商品SKU: {summary.erp_new_product_skus}\n"
        f"ERP更新商品SKU: {summary.erp_update_product_skus}\n"
        f"系统生成新商品SKU: {summary.generated_product_skus}\n"
        f"异常: {summary.exceptions}\n"
        f"输出目录: {summary.output_dir}"
    )


def build_system_status_summary(
    *,
    daily_rows: list[DailyFirstOrderRow],
    product_master_rows: list[ProductSkuMaster],
    first_category_code_rows: list[FirstCategoryCode],
    uploaded_rows: list[UploadedProductSku],
    historical_rows: list[HistoricalOrderedPlatformSku],
    mapping_rows: list[SkuPlatformMapping],
    product_source_mode: str,
) -> SystemStatusSummary:
    """构建执行前系统状态摘要。"""
    return SystemStatusSummary(
        daily_input_rows=len(daily_rows),
        product_master_skus=len({row.product_sku for row in product_master_rows if row.product_sku}),
        first_category_codes=len({row.code for row in first_category_code_rows if row.code}),
        uploaded_product_skus=len({row.product_sku for row in uploaded_rows if row.product_sku}),
        historical_platform_skus=len({row.platform_sku for row in historical_rows if row.platform_sku}),
        mapped_product_skus=len({row.product_sku for row in mapping_rows if row.product_sku and row.platform_sku}),
        mapped_platform_skus=len({row.platform_sku for row in mapping_rows if row.product_sku and row.platform_sku}),
        product_source_mode=product_source_mode,  # type: ignore[arg-type]
    )


def build_system_status_message(summary: SystemStatusSummary) -> str:
    """生成执行前系统状态摘要文本。"""
    return (
        "执行前系统状态\n"
        f"商品基础库来源: {summary.product_source_mode}\n"
        f"今日输入订单行数: {summary.daily_input_rows}\n"
        f"商品基础库商品SKU数: {summary.product_master_skus}\n"
        f"一级类目编码数: {summary.first_category_codes}\n"
        f"已上传商品SKU数: {summary.uploaded_product_skus}\n"
        f"历史出单平台SKU数: {summary.historical_platform_skus}\n"
        f"映射关系商品SKU数: {summary.mapped_product_skus}\n"
        f"映射关系平台SKU数: {summary.mapped_platform_skus}"
    )
