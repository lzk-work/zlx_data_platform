"""Dianxiaomi export planner tests."""

from dataclasses import replace
from decimal import Decimal

from apps.product_sku_management.src.constants import (
    DIANXIAOMI_OBJECT_PLATFORM_PAIR,
    EXPORT_ACTION_CREATE,
    EXPORT_ACTION_SKIP,
    EXPORT_ACTION_UPDATE,
    PRODUCT_SKU_TYPE_NORMAL,
)
from apps.product_sku_management.src.domain.dianxiaomi_export_planner import (
    bundle_sku_plan,
    build_bundle_sku_payload,
    build_export_plan,
    build_product_sku_payload,
    decimal_divide,
    platform_pair_plan,
    product_sku_plan,
)
from apps.product_sku_management.src.models.domain_models import BundleSkuRecord, ProductSkuRecord
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


def test_product_sku_plan_hash_includes_quantity_identity() -> None:
    first = product_sku_plan(
        process_batch_id="batch_1",
        record=product_record(quantity=1),
        previous_hash=None,
        export_file="product.xlsx",
        exchange_rate_usd=7,
    )
    changed = product_sku_plan(
        process_batch_id="batch_2",
        record=product_record(quantity=2),
        previous_hash=first.current_hash,
        export_file="product.xlsx",
        exchange_rate_usd=7,
    )

    assert changed.action_type == EXPORT_ACTION_UPDATE
    assert changed.payload_json["quantity"] == 2


def test_product_sku_plan_skips_when_only_main_image_changes() -> None:
    old_record = product_record(quantity=1)
    new_record = replace(old_record, main_image_url="https://example.com/new.jpg")
    previous_payload = build_product_sku_payload(old_record, exchange_rate_usd=7)
    first = product_sku_plan(
        process_batch_id="batch_1",
        record=old_record,
        previous_hash=None,
        export_file="product.xlsx",
        exchange_rate_usd=7,
    )
    changed = product_sku_plan(
        process_batch_id="batch_2",
        record=new_record,
        previous_hash=first.current_hash,
        previous_payload_json=previous_payload,
        export_file="product.xlsx",
        exchange_rate_usd=7,
    )

    assert changed.action_type == EXPORT_ACTION_SKIP
    assert changed.payload_json["main_image_url"] == "https://example.com/new.jpg"


def test_product_sku_plan_payload_includes_direct_sales_unit_dimensions() -> None:
    plan = product_sku_plan(
        process_batch_id="batch_1",
        record=product_record(
            quantity=1,
            length_cm=Decimal("10"),
            width_cm=Decimal("8"),
            height_cm=Decimal("3"),
            is_direct_sales_unit=True,
        ),
        previous_hash=None,
        export_file="product.xlsx",
        exchange_rate_usd=7,
    )

    assert plan.payload_json["length_cm"] == "10"
    assert plan.payload_json["width_cm"] == "8"
    assert plan.payload_json["height_cm"] == "3"
    assert plan.payload_json["is_direct_sales_unit"] is True


def test_product_sku_plan_payload_includes_forced_package_source_urls() -> None:
    record = product_record(quantity=1)
    record = ProductSkuRecord(
        **{
            **record.__dict__,
            "product_sku_type": "forced_package",
            "package_fingerprint": "fp",
            "package_details": (
                {"source_url": "https://detail.1688.com/offer/1.html"},
                {"source_url": "https://detail.1688.com/offer/2.html"},
                {"source_url": "https://detail.1688.com/offer/1.html"},
            ),
        }
    )
    plan = product_sku_plan(
        process_batch_id="batch_1",
        record=record,
        previous_hash=None,
        export_file="product.xlsx",
        exchange_rate_usd=7,
    )

    assert plan.payload_json["source_url"] == (
        "https://detail.1688.com/offer/1.html\nhttps://detail.1688.com/offer/2.html"
    )
    assert plan.payload_json["source_urls"] == [
        "https://detail.1688.com/offer/1.html",
        "https://detail.1688.com/offer/2.html",
    ]


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


def test_bundle_sku_plan_skips_when_only_main_image_changes() -> None:
    old_record = BundleSkuRecord(
        bundle_sku="ZH_260731_1_2_1",
        bundle_name="2 个/组，红色---数量1，蓝色---数量1",
        total_product_count=2,
        distinct_product_sku_count=2,
        items=(("YS_260731_1", 1), ("YS_260731_2", 1)),
        main_image_url="https://example.com/old.jpg",
        chinese_customs_name="玩具",
        reference_total_purchase_price_rmb=Decimal("20"),
        reference_total_weight_g=Decimal("300"),
        logistics_attribute="普货",
        note="",
        source_urls=("https://detail.1688.com/offer/111.html",),
    )
    new_record = replace(old_record, main_image_url="https://example.com/new.jpg")
    previous_payload = build_bundle_sku_payload(old_record, exchange_rate_usd=7)
    first = bundle_sku_plan(
        process_batch_id="batch_1",
        record=old_record,
        previous_hash=None,
        export_file="bundle.xlsx",
        exchange_rate_usd=7,
    )
    changed = bundle_sku_plan(
        process_batch_id="batch_2",
        record=new_record,
        previous_hash=first.current_hash,
        previous_payload_json=previous_payload,
        export_file="bundle.xlsx",
        exchange_rate_usd=7,
    )

    assert changed.action_type == EXPORT_ACTION_SKIP
    assert changed.payload_json["main_image_url"] == "https://example.com/new.jpg"


def product_record(
    quantity: int,
    *,
    length_cm: Decimal | None = None,
    width_cm: Decimal | None = None,
    height_cm: Decimal | None = None,
    is_direct_sales_unit: bool = False,
) -> ProductSkuRecord:
    """Build a minimal product SKU record for export planning tests."""
    return ProductSkuRecord(
        product_sku="YS_260731_1",
        source_url="https://detail.1688.com/offer/1.html",
        source_platform="1688",
        spec="白色",
        quantity=quantity,
        product_sku_type=PRODUCT_SKU_TYPE_NORMAL,
        package_fingerprint=None,
        package_details=(),
        product_name=f"白色---数量{quantity}",
        main_image_url="https://example.com/a.jpg",
        first_level_category="Fashion",
        category_code="YS",
        reference_purchase_price_rmb=Decimal("10"),
        reference_weight_g=Decimal("100"),
        chinese_customs_name="饰品",
        logistics_attribute="普货",
        note="",
        length_cm=length_cm,
        width_cm=width_cm,
        height_cm=height_cm,
        is_direct_sales_unit=is_direct_sales_unit,
    )


def test_build_product_sku_payload_uses_package_weight_and_price() -> None:
    """商品SKU导出按整包(单品值×数量)输出重量与采购价，与 sales_unit 总重等价。"""
    single = build_product_sku_payload(product_record(quantity=1), exchange_rate_usd=7)
    multi = build_product_sku_payload(product_record(quantity=3), exchange_rate_usd=7)

    # 单品(quantity=1)：整包 == 单品值
    assert single["weight_g"] == Decimal("100")
    assert single["purchase_price_rmb"] == Decimal("10")
    assert single["declared_weight_g"] == Decimal("100")
    assert single["declared_amount_usd"] == decimal_divide(Decimal("10"), 7)

    # 多件(quantity=3)：整包 == 单品值 × 数量
    assert multi["weight_g"] == Decimal("300")
    assert multi["purchase_price_rmb"] == Decimal("30")
    assert multi["declared_weight_g"] == Decimal("300")
    assert multi["declared_amount_usd"] == decimal_divide(Decimal("30"), 7)


def test_declared_amount_usd_uses_min_floor() -> None:
    """申报金额低于店小秘下限0.1时按下限输出，正常价位与采购参考价不受影响。"""
    # 商品SKU：0.5 / 7 ≈ 0.0714 低于下限
    low_product = replace(product_record(quantity=1), reference_purchase_price_rmb=Decimal("0.5"))
    low_payload = build_product_sku_payload(low_product, exchange_rate_usd=7)

    assert low_payload["declared_amount_usd"] == Decimal("0.1")
    # 采购参考价仍按整包原值输出，不被申报下限改写
    assert low_payload["purchase_price_rmb"] == Decimal("0.5")
    # 正常价位不被下限干扰
    normal_payload = build_product_sku_payload(product_record(quantity=1), exchange_rate_usd=7)
    assert normal_payload["declared_amount_usd"] > Decimal("0.1")

    # 组合SKU同样受下限保护
    low_bundle = BundleSkuRecord(
        bundle_sku="ZH_260731_1_2_1",
        bundle_name="2 个/组，红色*2",
        total_product_count=2,
        distinct_product_sku_count=1,
        items=(("YS_260731_1", 2),),
        main_image_url="https://example.com/a.jpg",
        chinese_customs_name="玩具",
        reference_total_purchase_price_rmb=Decimal("0.4"),
        reference_total_weight_g=Decimal("300"),
        logistics_attribute="普货",
        note="",
        source_urls=("https://detail.1688.com/offer/111.html",),
    )

    assert build_bundle_sku_payload(low_bundle, exchange_rate_usd=7)["declared_amount_usd"] == Decimal("0.1")
