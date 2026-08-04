"""SKU code counter tests."""

from typing import Any

from apps.product_sku_management.src.repositories.db import ProductSkuDatabase


class FakeConn:
    """Placeholder connection for counter tests."""


class CounterCaptureDatabase(ProductSkuDatabase):
    """Capture code counter calls without a database."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def next_code_counter_value(self, conn: Any, counter_type: str, counter_key: str) -> int:  # type: ignore[override]
        self.calls.append((counter_type, counter_key))
        return 7


def test_product_sku_code_uses_one_global_counter_per_date() -> None:
    db = CounterCaptureDatabase()

    product_sku = db.next_product_sku_code(FakeConn(), "YS")

    assert product_sku.startswith("YS_")
    assert product_sku.endswith("_7")
    assert db.calls == [("product_sku", product_sku.split("_")[1])]
