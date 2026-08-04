"""Logistics attribute mapping tests."""

import pytest

from apps.product_sku_management.src.domain.logistics_attribute import dianxiaomi_dangerous_transport_code


def test_dianxiaomi_dangerous_transport_code_maps_supported_attributes() -> None:
    assert dianxiaomi_dangerous_transport_code("普货") == "0"
    assert dianxiaomi_dangerous_transport_code("带电") == "1"
    assert dianxiaomi_dangerous_transport_code("敏感") == "2"
    assert dianxiaomi_dangerous_transport_code("") == ""


def test_dianxiaomi_dangerous_transport_code_rejects_unknown_attribute() -> None:
    with pytest.raises(ValueError, match="属性必须是"):
        dianxiaomi_dangerous_transport_code("液体")
