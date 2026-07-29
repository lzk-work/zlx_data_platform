from __future__ import annotations

import pytest

from apps.sku_mapping_poc.src.db import _first_category_code_row, _product_source_params, _product_source_row, diff_product_source_rows
from apps.sku_mapping_poc.src.models import ProductSkuMaster


def test_product_source_row_maps_database_fields() -> None:
    product = _product_source_row(
        {
            "product_sku": "JT_260708_1",
            "source_image_url": "img",
            "source_url": "url",
            "spec": "spec",
            "purchase_price": 18,
            "weight_g": 387,
            "length_cm": 71.8,
            "width_cm": 21.7,
            "height_cm": 20.6,
            "color": "White",
            "material": "Plastic",
            "quantity": 6,
            "chinese_customs_name": "塑料风扇",
            "first_level_category": "Home",
            "category_code": "JT",
            "temp_sku": "TMP1",
            "supplier": "supplier-a",
            "note": "备注",
        }
    )

    assert product.product_sku == "JT_260708_1"
    assert product.source_image_url == "img"
    assert product.source_url == "url"
    assert product.spec == "spec"
    assert product.purchase_price == "18"
    assert product.weight_g == "387"
    assert product.length == "71.8"
    assert product.category_code == "JT"
    assert product.supplier == "supplier-a"
    assert product.note == "备注"


def test_first_category_code_row_maps_database_fields() -> None:
    row = _first_category_code_row({"first_category": "Home", "first_category_chinese": "家居", "code": "JT"})

    assert row.first_category == "Home"
    assert row.first_category_chinese == "家居"
    assert row.code == "JT"


def test_diff_product_source_rows_returns_new_and_changed_rows_only() -> None:
    before = [
        ProductSkuMaster("SKU_KEEP", "url-1", "spec-1", purchase_price="10"),
        ProductSkuMaster("SKU_CHANGE", "url-2", "spec-2", purchase_price="10"),
    ]
    after = [
        ProductSkuMaster("SKU_KEEP", "url-1", "spec-1", purchase_price="10"),
        ProductSkuMaster("SKU_CHANGE", "url-2", "spec-2", purchase_price="11"),
        ProductSkuMaster("SKU_NEW", "url-3", "spec-3", purchase_price="12"),
    ]

    changed = diff_product_source_rows(before, after)

    assert [row.product_sku for row in changed] == ["SKU_CHANGE", "SKU_NEW"]


def test_product_source_params_convert_blank_and_numeric_fields() -> None:
    params = _product_source_params(
        ProductSkuMaster(
            "SKU1",
            "url",
            "spec",
            length="71.8",
            width="",
            height="20.6",
            purchase_price="18",
            weight_g="387",
            quantity="6.0",
            note="",
        )
    )

    assert params["purchase_price"] == 18.0
    assert params["weight_g"] == 387.0
    assert params["length_cm"] == 71.8
    assert params["width_cm"] is None
    assert params["quantity"] == 6
    assert params["note"] is None


def test_database_module_requires_safe_schema_identifier() -> None:
    from apps.sku_mapping_poc.src.db import _safe_identifier

    assert _safe_identifier("zlx_1") == "zlx_1"
    with pytest.raises(ValueError):
        _safe_identifier('zlx_1"; drop table x; --')
