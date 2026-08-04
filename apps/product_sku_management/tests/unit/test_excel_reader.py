"""Excel reader tests."""

from decimal import Decimal

from apps.product_sku_management.src.adapters.excel_reader import optional_dimension


def test_optional_dimension_treats_zero_as_blank() -> None:
    assert optional_dimension(None, "长/cm") is None
    assert optional_dimension("", "长/cm") is None
    assert optional_dimension(0, "长/cm") is None
    assert optional_dimension("0", "长/cm") is None
    assert optional_dimension("10.5", "长/cm") == Decimal("10.5")
