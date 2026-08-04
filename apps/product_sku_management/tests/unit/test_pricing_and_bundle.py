"""Pricing, weight, naming, and bundle rule tests."""

from decimal import Decimal

from apps.product_sku_management.src.constants import (
    SALES_UNIT_TYPE_MULTI_PRODUCT_SET,
    SALES_UNIT_TYPE_SAME_PRODUCT_MULTI_QTY,
    SALES_UNIT_TYPE_SINGLE_PRODUCT,
)
from apps.product_sku_management.src.domain.bundle_service import decide_bundle
from apps.product_sku_management.src.domain.name_builder import build_bundle_name, build_product_name
from apps.product_sku_management.src.domain.pricing_weight_calculator import calculate_reference_value, kg_to_g
from apps.product_sku_management.src.domain.spec_parser import parse_spec
from apps.product_sku_management.src.models.domain_models import ParsedSourceItem


def test_pricing_weight_calculator_converts_kg_to_g_and_calculates_average() -> None:
    weight_g = kg_to_g(Decimal("0.3"))

    assert weight_g == Decimal("300.0")
    assert calculate_reference_value(Decimal("30"), 3, "采购价") == Decimal("10")
    assert calculate_reference_value(weight_g, 3, "重量") == Decimal("100.0")


def test_name_builder_uses_slashes_and_quantity_suffix() -> None:
    assert build_product_name(("白色", "均码"), 2) == "白色，均码---数量1"
    assert build_bundle_name(parse_spec("（白色||均码||1）（肤色||均码||2）")) == "3 个/组，白色，均码---数量1，肤色，均码---数量2"


def test_bundle_decision_single_quantity_one_maps_to_product_sku() -> None:
    decision = decide_bundle((item(quantity=1, spec="白色||均码"),))

    assert decision.needs_bundle is False
    assert decision.sales_unit_type == SALES_UNIT_TYPE_SINGLE_PRODUCT


def test_bundle_decision_single_quantity_gt_one_maps_to_bundle_sku() -> None:
    decision = decide_bundle((item(quantity=2, spec="白色||均码"),))

    assert decision.needs_bundle is True
    assert decision.sales_unit_type == SALES_UNIT_TYPE_SAME_PRODUCT_MULTI_QTY


def test_bundle_decision_multiple_items_maps_to_bundle_sku() -> None:
    decision = decide_bundle((item(quantity=1, spec="白色||均码"), item(quantity=1, spec="肤色||均码")))

    assert decision.needs_bundle is True
    assert decision.sales_unit_type == SALES_UNIT_TYPE_MULTI_PRODUCT_SET


def item(quantity: int, spec: str) -> ParsedSourceItem:
    """Build a minimal parsed source item."""
    return ParsedSourceItem(
        source_group_no=1,
        source_url="https://detail.1688.com/offer/1.htm",
        source_platform="1688",
        raw_spec=f"{spec}||{quantity}",
        spec=spec,
        display_spec_params=tuple(spec.split("||")),
        quantity=quantity,
        source_note="",
        group_purchase_price_rmb=Decimal("10"),
        group_weight_g=Decimal("100"),
        reference_purchase_price_rmb=Decimal("10"),
        reference_weight_g=Decimal("100"),
    )
