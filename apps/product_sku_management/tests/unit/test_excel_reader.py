"""Excel reader tests."""

from decimal import Decimal

from apps.product_sku_management.src.adapters.excel_reader import optional_decimal, optional_dimension


def test_optional_dimension_treats_zero_as_blank() -> None:
    assert optional_dimension(None, "长/cm") is None
    assert optional_dimension("", "长/cm") is None
    assert optional_dimension(0, "长/cm") is None
    assert optional_dimension("0", "长/cm") is None
    assert optional_dimension("10.5", "长/cm") == Decimal("10.5000")
    assert optional_dimension("12.47775", "长/cm") == Decimal("12.4778")


def test_optional_decimal_ignores_invisible_format_characters() -> None:
    assert optional_decimal("19.26\u202c", "货源1采购价") == Decimal("19.26")
