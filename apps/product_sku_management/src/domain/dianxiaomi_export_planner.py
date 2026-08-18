"""Dianxiaomi export action planning."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any

from ..constants import (
    DIANXIAOMI_MIN_DECLARED_AMOUNT_USD,
    DIANXIAOMI_OBJECT_BUNDLE_SKU,
    DIANXIAOMI_OBJECT_PLATFORM_PAIR,
    DIANXIAOMI_OBJECT_PRODUCT_SKU,
    EXPORT_ACTION_CREATE,
    EXPORT_ACTION_SKIP,
    EXPORT_ACTION_UPDATE,
)
from ..models.domain_models import BundleSkuRecord, ProductSkuRecord
from ..models.output_models import DianxiaomiExportPlan, PlatformPairExportRecord

MIN_DECLARED_AMOUNT_USD = Decimal(DIANXIAOMI_MIN_DECLARED_AMOUNT_USD)


def build_product_sku_payload(record: ProductSkuRecord, *, exchange_rate_usd: float) -> dict[str, Any]:
    """构建商品SKU店小秘导出状态。

    Args:
        record: 商品SKU记录。
        exchange_rate_usd: 人民币换美元汇率。

    Returns:
        dict[str, Any]: 参与哈希比较和模板导出的商品SKU字段。
    """
    # 商品SKU按单品存储参考重量/采购价，导出店小秘时按整包（单品值 × 数量）输出，
    # 与 sales_unit.total_weight_g / total_purchase_price_rmb 数学等价，无需改动数据库。
    quantity = record.quantity
    package_weight_g = record.reference_weight_g * quantity
    package_purchase_price_rmb = record.reference_purchase_price_rmb * quantity
    return {
        "sku": record.product_sku,
        "name": record.product_name,
        "main_image_url": record.main_image_url,
        "weight_g": package_weight_g,
        "purchase_price_rmb": package_purchase_price_rmb,
        "source_url": product_source_url_text(record),
        "source_urls": product_source_urls(record),
        "spec": record.spec,
        "quantity": quantity,
        "product_sku_type": record.product_sku_type,
        "package_fingerprint": record.package_fingerprint,
        "package_details": record.package_details,
        "note": record.note,
        "chinese_customs_name": record.chinese_customs_name,
        "logistics_attribute": record.logistics_attribute,
        "declared_weight_g": package_weight_g,
        "declared_amount_usd": decimal_divide(package_purchase_price_rmb, exchange_rate_usd),
        "length_cm": record.length_cm,
        "width_cm": record.width_cm,
        "height_cm": record.height_cm,
        "is_direct_sales_unit": record.is_direct_sales_unit,
    }


def product_source_urls(record: ProductSkuRecord) -> list[str]:
    """生成商品SKU来源URL列表。

    Args:
        record: 商品SKU记录。

    Returns:
        list[str]: 普通商品SKU为单链接；强制合包商品SKU为去重后的多链接。
    """
    urls: list[str] = []
    for detail in record.package_details:
        source_url = str(detail.get("source_url") or "").strip()
        if source_url and source_url not in urls:
            urls.append(source_url)
    if not urls and record.source_url:
        urls.append(record.source_url)
    return urls


def product_source_url_text(record: ProductSkuRecord) -> str:
    """生成商品SKU来源URL文本。

    Args:
        record: 商品SKU记录。

    Returns:
        str: 以换行拼接后的来源URL。
    """
    return "\n".join(product_source_urls(record))


def build_bundle_sku_payload(record: BundleSkuRecord, *, exchange_rate_usd: float) -> dict[str, Any]:
    """构建组合SKU店小秘导出状态。

    Args:
        record: 组合SKU记录。
        exchange_rate_usd: 人民币换美元汇率。

    Returns:
        dict[str, Any]: 参与哈希比较和模板导出的组合SKU字段。
    """
    return {
        "bundle_sku": record.bundle_sku,
        "name": record.bundle_name,
        "main_image_url": record.main_image_url,
        "items": [{"product_sku": product_sku, "quantity": quantity} for product_sku, quantity in record.items],
        "source_urls": sorted(set(record.source_urls)),
        "note": record.note,
        "chinese_customs_name": record.chinese_customs_name,
        "logistics_attribute": record.logistics_attribute,
        "declared_weight_g": record.reference_total_weight_g,
        "declared_amount_usd": decimal_divide(record.reference_total_purchase_price_rmb, exchange_rate_usd),
        "length_cm": record.length_cm,
        "width_cm": record.width_cm,
        "height_cm": record.height_cm,
    }


def build_platform_pair_payload(record: PlatformPairExportRecord) -> dict[str, Any]:
    """构建平台SKU配对导出状态。

    Args:
        record: 某个商品SKU或组合SKU对应的全部平台SKU映射。

    Returns:
        dict[str, Any]: 参与哈希比较和模板导出的平台SKU配对字段。
    """
    return {
        "mapping_target_sku": record.mapping_target_sku,
        "platform_skus": sorted(record.platform_skus),
    }


def build_export_plan(
    *,
    process_batch_id: str,
    object_type: str,
    object_key: str,
    payload_json: dict[str, Any],
    hash_payload_json: dict[str, Any] | None = None,
    previous_payload_json: dict[str, Any] | None = None,
    previous_hash: str | None,
    export_file: str,
) -> DianxiaomiExportPlan:
    """根据当前状态和店小秘确认态生成导出计划。

    Args:
        process_batch_id: 当前处理批次ID。
        object_type: 店小秘对象类型。
        object_key: 对象唯一键。
        payload_json: 当前系统状态。
        hash_payload_json: 当前参与同步状态比较的系统状态；为空时使用payload_json。
        previous_payload_json: 上次确认哈希对应的历史状态，用于兼容哈希口径调整。
        previous_hash: 店小秘侧已确认状态哈希；为空表示未确认过。
        export_file: 需要写入的导出文件名。

    Returns:
        DianxiaomiExportPlan: create、update或skip动作及原因。
    """
    normalized_payload = normalize_payload(payload_json)
    normalized_hash_payload = normalize_payload(hash_payload_json or payload_json)
    current_hash = payload_hash(normalized_hash_payload)
    comparable_previous_hash = previous_hash
    if previous_payload_json is not None:
        comparable_previous_hash = payload_hash(normalize_payload(previous_payload_json))
    if not previous_hash:
        action_type = EXPORT_ACTION_CREATE
        reason = "店小秘未确认过该对象，按新建导出"
    elif comparable_previous_hash == current_hash:
        action_type = EXPORT_ACTION_SKIP
        reason = "系统当前态与店小秘已确认状态一致，跳过导出"
    else:
        action_type = EXPORT_ACTION_UPDATE
        reason = "系统当前态与店小秘已确认状态不一致，按更新导出"

    return DianxiaomiExportPlan(
        process_batch_id=process_batch_id,
        object_type=object_type,
        object_key=object_key,
        action_type=action_type,
        reason=reason,
        current_hash=current_hash,
        previous_hash=previous_hash,
        payload_json=normalized_payload,
        export_file=export_file if action_type != EXPORT_ACTION_SKIP else "",
    )


def product_sku_plan(
    *,
    process_batch_id: str,
    record: ProductSkuRecord,
    previous_hash: str | None,
    previous_payload_json: dict[str, Any] | None = None,
    export_file: str,
    exchange_rate_usd: float,
) -> DianxiaomiExportPlan:
    """生成单个商品SKU导出计划。

    Args:
        process_batch_id: 当前处理批次ID。
        record: 商品SKU记录。
        previous_hash: 店小秘侧已确认状态哈希。
        previous_payload_json: 上次确认的商品SKU导出状态，用于兼容哈希口径调整。
        export_file: 商品SKU导出文件名。
        exchange_rate_usd: 人民币换美元汇率。

    Returns:
        DianxiaomiExportPlan: 商品SKU导出动作。
    """
    payload = build_product_sku_payload(record, exchange_rate_usd=exchange_rate_usd)
    return build_export_plan(
        process_batch_id=process_batch_id,
        object_type=DIANXIAOMI_OBJECT_PRODUCT_SKU,
        object_key=record.product_sku,
        payload_json=payload,
        hash_payload_json=payload_without_non_sync_fields(payload),
        previous_payload_json=payload_without_non_sync_fields(previous_payload_json) if previous_payload_json else None,
        previous_hash=previous_hash,
        export_file=export_file,
    )


def bundle_sku_plan(
    *,
    process_batch_id: str,
    record: BundleSkuRecord,
    previous_hash: str | None,
    previous_payload_json: dict[str, Any] | None = None,
    export_file: str,
    exchange_rate_usd: float,
) -> DianxiaomiExportPlan:
    """生成单个组合SKU导出计划。

    Args:
        process_batch_id: 当前处理批次ID。
        record: 组合SKU记录。
        previous_hash: 店小秘侧已确认状态哈希。
        previous_payload_json: 上次确认的组合SKU导出状态，用于兼容哈希口径调整。
        export_file: 组合SKU导出文件名。
        exchange_rate_usd: 人民币换美元汇率。

    Returns:
        DianxiaomiExportPlan: 组合SKU导出动作。
    """
    payload = build_bundle_sku_payload(record, exchange_rate_usd=exchange_rate_usd)
    return build_export_plan(
        process_batch_id=process_batch_id,
        object_type=DIANXIAOMI_OBJECT_BUNDLE_SKU,
        object_key=record.bundle_sku,
        payload_json=payload,
        hash_payload_json=payload_without_non_sync_fields(payload),
        previous_payload_json=payload_without_non_sync_fields(previous_payload_json) if previous_payload_json else None,
        previous_hash=previous_hash,
        export_file=export_file,
    )


def platform_pair_plan(
    *,
    process_batch_id: str,
    record: PlatformPairExportRecord,
    previous_hash: str | None,
    export_file: str,
) -> DianxiaomiExportPlan:
    """生成单个映射目标的平台SKU配对导出计划。

    Args:
        process_batch_id: 当前处理批次ID。
        record: 映射目标及其全部平台SKU记录。
        previous_hash: 店小秘侧已确认状态哈希。
        export_file: 平台SKU配对导出文件名。

    Returns:
        DianxiaomiExportPlan: 平台SKU配对导出动作。
    """
    return build_export_plan(
        process_batch_id=process_batch_id,
        object_type=DIANXIAOMI_OBJECT_PLATFORM_PAIR,
        object_key=record.mapping_target_sku,
        payload_json=build_platform_pair_payload(record),
        previous_hash=previous_hash,
        export_file=export_file,
    )


def payload_hash(payload_json: dict[str, Any]) -> str:
    """计算导出状态哈希。

    Args:
        payload_json: 需要比较的结构化状态。

    Returns:
        str: 稳定JSON序列化后的SHA256哈希。
    """
    payload_text = json.dumps(normalize_payload(payload_json), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload_text.encode("utf-8")).hexdigest()


def payload_without_non_sync_fields(payload_json: dict[str, Any]) -> dict[str, Any]:
    """移除不参与店小秘同步状态判断的展示字段。

    Args:
        payload_json: 完整导出状态。

    Returns:
        dict[str, Any]: 去掉主图等非业务同步字段后的状态。
    """
    return {key: value for key, value in payload_json.items() if key != "main_image_url"}


def normalize_payload(value: Any) -> Any:
    """标准化可JSON化的数据。

    Args:
        value: 任意导出状态值。

    Returns:
        Any: Decimal转字符串、tuple转list后的值，便于存储和哈希。
    """
    if isinstance(value, Decimal):
        normalized = value.normalize()
        return format(normalized, "f")
    if isinstance(value, tuple | list):
        return [normalize_payload(item) for item in value]
    if isinstance(value, dict):
        return {key: normalize_payload(item) for key, item in value.items()}
    return value


def decimal_divide(value: Decimal, divisor: float) -> Decimal:
    """按配置汇率折算店小秘申报金额，并保证不低于申报金额下限。

    Args:
        value: 被除数，通常为整包采购价（RMB）。
        divisor: 除数配置值，即人民币换美元汇率。

    Returns:
        Decimal: 相除结果；低于申报金额下限时返回下限值。
    """
    return max(value / Decimal(str(divisor)), MIN_DECLARED_AMOUNT_USD)
