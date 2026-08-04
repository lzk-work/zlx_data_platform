"""Dianxiaomi export planner tests."""

from decimal import Decimal

from apps.product_sku_management.src.constants import (
    DIANXIAOMI_OBJECT_PLATFORM_PAIR,
    EXPORT_ACTION_CREATE,
    EXPORT_ACTION_SKIP,
    EXPORT_ACTION_UPDATE,
)
from apps.product_sku_management.src.domain.dianxiaomi_export_planner import (
    bundle_sku_plan,
    build_export_plan,
    platform_pair_plan,
)
from apps.product_sku_management.src.models.domain_models import BundleSkuRecord
from apps.product_sku_management.src.models.output_models import PlatformPairExportRecord


def test_build_export_plan_creates_when_no_confirmed_hash() -> None:
    plan = build_export_plan(
        process_batch_id="batch_1",
        object_type="product_sku",
        object_key="YS_260731_1",
        payload_json={"sku": "YS_260731_1", "purchase_price": Decimal("10.0")},
        previous_hash=None,
        export_file="product.xlsx",
    )

    assert plan.action_type == EXPORT_ACTION_CREATE
    assert plan.export_file == "product.xlsx"
    assert plan.payload_json["purchase_price"] == "10"


def test_build_export_plan_skips_when_confirmed_hash_matches() -> None:
    first = build_export_plan(
        process_batch_id="batch_1",
        object_type="product_sku",
        object_key="YS_260731_1",
        payload_json={"sku": "YS_260731_1"},
        previous_hash=None,
        export_file="product.xlsx",
    )
    second = build_export_plan(
        process_batch_id="batch_2",
        object_type="product_sku",
        object_key="YS_260731_1",
        payload_json={"sku": "YS_260731_1"},
        previous_hash=first.current_hash,
        export_file="product.xlsx",
    )

    assert second.action_type == EXPORT_ACTION_SKIP
    assert second.export_file == ""


def test_build_export_plan_updates_when_confirmed_hash_differs() -> None:
    first = build_export_plan(
        process_batch_id="batch_1",
        object_type="product_sku",
        object_key="YS_260731_1",
        payload_json={"sku": "YS_260731_1", "name": "旧"},
        previous_hash=None,
        export_file="product.xlsx",
    )
    second = build_export_plan(
        process_batch_id="batch_2",
        object_type="product_sku",
        object_key="YS_260731_1",
        payload_json={"sku": "YS_260731_1", "name": "新"},
        previous_hash=first.current_hash,
        export_file="product.xlsx",
    )

    assert second.action_type == EXPORT_ACTION_UPDATE


def test_platform_pair_plan_hash_uses_full_sorted_platform_sku_set() -> None:
    first = platform_pair_plan(
        process_batch_id="batch_1",
        record=PlatformPairExportRecord("YS_260731_1", ("USW_B", "USW_A")),
        previous_hash=None,
        export_file="pair.xlsx",
    )
    second = platform_pair_plan(
        process_batch_id="batch_2",
        record=PlatformPairExportRecord("YS_260731_1", ("USW_A", "USW_B")),
        previous_hash=first.current_hash,
        export_file="pair.xlsx",
    )
    changed = platform_pair_plan(
        process_batch_id="batch_3",
        record=PlatformPairExportRecord("YS_260731_1", ("USW_A", "USW_B", "USW_C")),
        previous_hash=first.current_hash,
        export_file="pair.xlsx",
    )

    assert first.object_type == DIANXIAOMI_OBJECT_PLATFORM_PAIR
    assert second.action_type == EXPORT_ACTION_SKIP
    assert changed.action_type == EXPORT_ACTION_UPDATE


def test_bundle_sku_plan_includes_sales_unit_dimensions() -> None:
    plan = bundle_sku_plan(
        process_batch_id="batch_1",
        record=BundleSkuRecord(
            bundle_sku="ZH_260731_1_2_1",
            bundle_name="2 个/组，红色*2",
            total_product_count=2,
            distinct_product_sku_count=1,
            items=(("YS_260731_1", 2),),
            main_image_url="https://example.com/a.jpg",
            chinese_customs_name="玩具",
            reference_total_purchase_price_rmb=Decimal("20"),
            reference_total_weight_g=Decimal("300"),
            logistics_attribute="敏感",
            note="",
            source_urls=("https://detail.1688.com/offer/111.html",),
            length_cm=Decimal("10"),
            width_cm=Decimal("8"),
            height_cm=Decimal("3"),
        ),
        previous_hash=None,
        export_file="bundle.xlsx",
        exchange_rate_usd=7,
    )

    assert plan.payload_json["length_cm"] == "10"
    assert plan.payload_json["width_cm"] == "8"
    assert plan.payload_json["height_cm"] == "3"
    assert plan.payload_json["logistics_attribute"] == "敏感"
    assert plan.payload_json["source_urls"] == ["https://detail.1688.com/offer/111.html"]
