"""Domain models for product SKU management."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class CleanedSourceUrl:
    """Normalized source URL and its source platform."""

    source_url: str
    source_platform: str


@dataclass(frozen=True)
class ParsedSourceItem:
    """One purchasable item parsed from a source group spec."""

    source_group_no: int
    source_url: str
    source_platform: str
    raw_spec: str
    spec: str
    display_spec_params: tuple[str, ...]
    quantity: int
    source_note: str
    group_purchase_price_rmb: Decimal
    group_weight_g: Decimal
    reference_purchase_price_rmb: Decimal
    reference_weight_g: Decimal


@dataclass(frozen=True)
class BundleDecision:
    """The sales-unit type implied by parsed item quantities."""

    needs_bundle: bool
    sales_unit_type: str
    total_product_count: int
    distinct_product_sku_count: int


@dataclass(frozen=True)
class ProductSkuRecord:
    """Product SKU data needed by workflow and exporters."""

    product_sku: str
    source_url: str
    source_platform: str
    spec: str
    quantity: int
    product_sku_type: str
    package_fingerprint: str | None
    package_details: tuple[dict[str, Any], ...]
    product_name: str
    main_image_url: str
    first_level_category: str
    category_code: str
    reference_purchase_price_rmb: Decimal
    reference_weight_g: Decimal
    chinese_customs_name: str
    logistics_attribute: str
    note: str
    length_cm: Decimal | None = None
    width_cm: Decimal | None = None
    height_cm: Decimal | None = None
    is_direct_sales_unit: bool = False
    created: bool = False


@dataclass(frozen=True)
class BundleSkuRecord:
    """Bundle SKU data needed by workflow and exporters."""

    bundle_sku: str
    bundle_name: str
    total_product_count: int
    distinct_product_sku_count: int
    items: tuple[tuple[str, int], ...]
    main_image_url: str
    chinese_customs_name: str
    reference_total_purchase_price_rmb: Decimal
    reference_total_weight_g: Decimal
    logistics_attribute: str
    note: str
    source_urls: tuple[str, ...] = ()
    length_cm: Decimal | None = None
    width_cm: Decimal | None = None
    height_cm: Decimal | None = None
    created: bool = False


@dataclass(frozen=True)
class SalesUnitResult:
    """Result of processing one sales unit row."""

    sales_unit_id: int | None
    platform_sku: str
    shop_name: str
    sales_unit_type: str
    mapping_target_type: str
    mapping_target_sku: str
    product_skus: tuple[str, ...]
    bundle_sku: str | None
