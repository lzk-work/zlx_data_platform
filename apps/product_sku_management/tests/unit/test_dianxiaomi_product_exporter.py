"""Dianxiaomi product SKU exporter tests."""

from decimal import Decimal

from openpyxl import Workbook, load_workbook

from apps.product_sku_management.src.exporters.dianxiaomi_product_sku_exporter import export_product_sku_template
from apps.product_sku_management.src.models.domain_models import ProductSkuRecord


def test_export_product_sku_template_writes_dangerous_transport_code(tmp_path) -> None:
    template_path = tmp_path / "template.xlsx"
    output_path = tmp_path / "product.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["*SKU(必填)", "中文名称", "危险运输品"])
    workbook.save(template_path)

    export_product_sku_template(
        template_path,
        output_path,
        [
            ProductSkuRecord(
                product_sku="YS_260731_1",
                source_url="https://detail.1688.com/offer/1.html",
                source_platform="1688",
                spec="白色",
                product_name="白色---数量1",
                main_image_url="https://example.com/a.jpg",
                first_level_category="Fashion",
                category_code="YS",
                reference_purchase_price_rmb=Decimal("10"),
                reference_weight_g=Decimal("100"),
                chinese_customs_name="饰品",
                logistics_attribute="普货",
                note="",
            )
        ],
        exchange_rate_usd=7,
    )

    saved = load_workbook(output_path, data_only=True)
    row = [cell.value for cell in saved.active[2]]
    saved.close()

    assert row == ["YS_260731_1", "白色---数量1", "0"]
