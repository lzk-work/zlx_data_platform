"""Dianxiaomi export action planning."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any

from ..constants import (
    DIANXIAOMI_OBJECT_BUNDLE_SKU,
    DIANXIAOMI_OBJECT_PLATFORM_PAIR,
    DIANXIAOMI_OBJECT_PRODUCT_SKU,
    EXPORT_ACTION_CREATE,
    EXPORT_ACTION_SKIP,
    EXPORT_ACTION_UPDATE,
)
from ..models.domain_models import BundleSkuRecord, ProductSkuRecord
from ..models.output_models import DianxiaomiExportPlan, PlatformPairExportRecord


def build_product_sku_payload(record: ProductSkuRecord, *, exchange_rate_usd: float) -> dict[str, Any]:
    """构建商品SKU店小秘导出状态。

    Args:
        record: 商品SKU记录。
        exchange_rate_usd: 人民币换美元汇率。

    Returns:
        dict[str, Any]: 参与哈希比较和模板导出的商品SKU字段。
    """
    return {
        "sku": record.product_sku,
        "name": record.product_name,
        "main_image_url": record.main_image_url,
        "weight_g": record.reference_weight_g,
        "purchase_price_rmb": record.reference_purchase_price_rmb,
        "source_url": record.source_url,
        "note": record.note,
        "chinese_customs_name": record.chinese_customs_name,
        "logistics_attribute": record.logistics_attribute,
        "declared_weight_g": record.reference_weight_g,
        "declared_amount_usd": decimal_divide(record.reference_purchase_price_rmb, exchange_rate_usd),
    }


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
    previous_hash: str | None,
    export_file: str,
) -> DianxiaomiExportPlan:
    """根据当前状态和店小秘确认态生成导出计划。

    Args:
        process_batch_id: 当前处理批次ID。
        object_type: 店小秘对象类型。
        object_key: 对象唯一键。
        payload_json: 当前系统状态。
        previous_hash: 店小秘侧已确认状态哈希；为空表示未确认过。
        export_file: 需要写入的导出文件名。

    Returns:
        DianxiaomiExportPlan: create、update或skip动作及原因。
    """
    normalized_payload = normalize_payload(payload_json)
    current_hash = payload_hash(normalized_payload)
    if not previous_hash:
        action_type = EXPORT_ACTION_CREATE
        reason = "店小秘未确认过该对象，按新建导出"
    elif previous_hash == current_hash:
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
    export_file: str,
    exchange_rate_usd: float,
) -> DianxiaomiExportPlan:
    """生成单个商品SKU导出计划。

    Args:
        process_batch_id: 当前处理批次ID。
        record: 商品SKU记录。
        previous_hash: 店小秘侧已确认状态哈希。
        export_file: 商品SKU导出文件名。
        exchange_rate_usd: 人民币换美元汇率。

    Returns:
        DianxiaomiExportPlan: 商品SKU导出动作。
    """
    return build_export_plan(
        process_batch_id=process_batch_id,
        object_type=DIANXIAOMI_OBJECT_PRODUCT_SKU,
        object_key=record.product_sku,
        payload_json=build_product_sku_payload(record, exchange_rate_usd=exchange_rate_usd),
        previous_hash=previous_hash,
        export_file=export_file,
    )


def bundle_sku_plan(
    *,
    process_batch_id: str,
    record: BundleSkuRecord,
    previous_hash: str | None,
    export_file: str,
    exchange_rate_usd: float,
) -> DianxiaomiExportPlan:
    """生成单个组合SKU导出计划。

    Args:
        process_batch_id: 当前处理批次ID。
        record: 组合SKU记录。
        previous_hash: 店小秘侧已确认状态哈希。
        export_file: 组合SKU导出文件名。
        exchange_rate_usd: 人民币换美元汇率。

    Returns:
        DianxiaomiExportPlan: 组合SKU导出动作。
    """
    return build_export_plan(
        process_batch_id=process_batch_id,
        object_type=DIANXIAOMI_OBJECT_BUNDLE_SKU,
        object_key=record.bundle_sku,
        payload_json=build_bundle_sku_payload(record, exchange_rate_usd=exchange_rate_usd),
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
    """Decimal除法工具。

    Args:
        value: 被除数。
        divisor: 除数配置值。

    Returns:
        Decimal: 相除结果。
    """
    return value / Decimal(str(divisor))
