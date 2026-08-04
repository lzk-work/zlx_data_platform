"""Category code lookup tests."""

from apps.product_sku_management.src.repositories.db import ProductSkuDatabase


class FakeProductSkuDatabase(ProductSkuDatabase):
    """Fake DB that captures category lookup SQL."""

    def __init__(self, row: dict[str, str] | None) -> None:
        self.row = row
        self.sql = ""

    def fetch_one(self, sql: str, params: object | None = None) -> dict[str, str] | None:  # type: ignore[override]
        self.sql = sql
        return self.row


def test_get_category_code_reads_existing_code_column() -> None:
    db = FakeProductSkuDatabase({"code": "YS"})
    db.schema_name = "sku_mgmt"

    assert db.get_category_code("Health") == "YS"
    assert "select code" in db.sql


def test_get_category_code_returns_none_for_blank_code() -> None:
    db = FakeProductSkuDatabase({"code": ""})
    db.schema_name = "sku_mgmt"

    assert db.get_category_code("Health") is None
