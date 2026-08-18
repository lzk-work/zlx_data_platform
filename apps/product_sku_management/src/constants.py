"""Constants for product SKU management."""

from __future__ import annotations

SCHEMA_NAME = "sku_mgmt"
EXCHANGE_RATE_USD = 6.8

# 店小秘申报金额（USD）下限，计算值低于该下限时按下限申报。
DIANXIAOMI_MIN_DECLARED_AMOUNT_USD = "0.1"

WORKFLOW_PLATFORM_LISTING_SUPPLEMENT = "platform_listing_supplement"
WORKFLOW_PLATFORM_LISTING_UPDATE = "platform_listing_update"

WORKFLOW_MODE_SUPPLEMENT = "supplement"
WORKFLOW_MODE_UPDATE = "update"

DIANXIAOMI_OBJECT_PRODUCT_SKU = "product_sku"
DIANXIAOMI_OBJECT_BUNDLE_SKU = "bundle_sku"
DIANXIAOMI_OBJECT_PLATFORM_PAIR = "platform_pair"

EXPORT_ACTION_CREATE = "create"
EXPORT_ACTION_UPDATE = "update"
EXPORT_ACTION_SKIP = "skip"
EXPORT_ACTION_MANUAL_REVIEW = "manual_review"

# 店小秘导出模板文件名（中文，便于业务识别）。
# key 为 (对象类型, 动作)，value 为输出文件名。
DIANXIAOMI_EXPORT_TEMPLATE_NAMES = {
    ("product_sku", "create"): "商品SKU建立.xlsx",
    ("product_sku", "update"): "商品SKU更新.xlsx",
    ("bundle_sku", "create"): "组合SKU建立.xlsx",
    ("bundle_sku", "update"): "组合SKU更新.xlsx",
    ("platform_pair", "create"): "配对关系建立.xlsx",
    ("platform_pair", "update"): "配对关系更新.xlsx",
}


def dianxiaomi_export_template_name(object_name: str, action_type: str) -> str:
    """返回店小秘导出模板的中文文件名。

    Args:
        object_name: 对象类型，如 product_sku / bundle_sku / platform_pair。
        action_type: 动作，如 create / update。

    Returns:
        str: 中文输出文件名；未知组合回退为英文拼接名。
    """
    return DIANXIAOMI_EXPORT_TEMPLATE_NAMES.get(
        (object_name, action_type), f"dianxiaomi_{object_name}_{action_type}.xlsx"
    )


SYNC_STATUS_EXPORTED = "exported"

MAPPING_TARGET_PRODUCT_SKU = "product_sku"
MAPPING_TARGET_BUNDLE_SKU = "bundle_sku"

SALES_UNIT_SOURCE_PLATFORM_LISTING = "platform_listing"
SALES_UNIT_TYPE_SINGLE_PRODUCT = "single_product"
SALES_UNIT_TYPE_SAME_PRODUCT_MULTI_QTY = "same_product_multi_qty"
SALES_UNIT_TYPE_MULTI_PRODUCT_SET = "multi_product_set"
SALES_UNIT_TYPE_FORCED_PRODUCT_SKU = "forced_product_sku"

PRODUCT_SKU_TYPE_NORMAL = "normal"
PRODUCT_SKU_TYPE_FORCED_PACKAGE = "forced_package"

SOURCE_STATUS_ACTIVE = "active"
SOURCE_PLATFORM_1688 = "1688"
SOURCE_PLATFORM_TAOBAO = "taobao"
SOURCE_PLATFORM_TMALL = "tmall"
SOURCE_PLATFORM_OTHER = "other"
