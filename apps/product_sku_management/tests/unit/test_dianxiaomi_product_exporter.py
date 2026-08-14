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
    sheet.append(
        [
            "*SKU(必填)",
            "中文名称",
            "商品净重（g）",
            "长（cm）",
            "宽（cm）",
            "高（cm）",
            "申报重量(g)",
            "申报金额（USD）",
            "危险运输品",
        ]
    )
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
                quantity=1,
                product_sku_type="normal",
                package_fingerprint=None,
                package_details=(),
                product_name="白色---数量1",
                main_image_url="https://example.com/a.jpg",
                first_level_category="Fashion",
                category_code="YS",
                reference_purchase_price_rmb=Decimal("10"),
                reference_weight_g=Decimal("100.235"),
                chinese_customs_name="饰品",
                logistics_attribute="普货",
                note="",
                length_cm=Decimal("10.235"),
                width_cm=Decimal("8.234"),
                height_cm=Decimal("3.235"),
                is_direct_sales_unit=True,
            )
        ],
        exchange_rate_usd=6.8,
    )

    saved = load_workbook(output_path, data_only=True)
    row = [cell.value for cell in saved.active[2]]
    saved.close()

    assert row[:2] == ["YS_260731_1", "白色---数量1"]
    assert Decimal(str(row[2])) == Decimal("100.24")
    assert Decimal(str(row[3])) == Decimal("10.24")
    assert Decimal(str(row[4])) == Decimal("8.23")
    assert Decimal(str(row[5])) == Decimal("3.24")
    assert Decimal(str(row[6])) == Decimal("100.24")
    assert Decimal(str(row[7])) == Decimal("1.47")
    assert row[8] == "0"


def test_export_product_sku_template_writes_forced_package_source_urls(tmp_path) -> None:
    template_path = tmp_path / "template.xlsx"
    output_path = tmp_path / "product.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["*SKU(必填)", "来源URL（必须以http://或https：//开头）", "备注"])
    workbook.save(template_path)

    export_product_sku_template(
        template_path,
        output_path,
        [
            ProductSkuRecord(
                product_sku="YS_260731_2",
                source_url="https://detail.1688.com/offer/1.html",
                source_platform="1688",
                spec="红色",
                quantity=1,
                product_sku_type="forced_package",
                package_fingerprint="fp",
                package_details=(
                    {"source_url": "https://detail.1688.com/offer/1.html"},
                    {"source_url": "https://detail.1688.com/offer/2.html"},
                    {"source_url": "https://detail.1688.com/offer/1.html"},
                ),
                product_name="2个/组，红色---数量1，蓝色---数量1",
                main_image_url="https://example.com/a.jpg",
                first_level_category="Fashion",
                category_code="YS",
                reference_purchase_price_rmb=Decimal("10"),
                reference_weight_g=Decimal("100"),
                chinese_customs_name="饰品",
                logistics_attribute="普货",
                note="原备注\n强制合并",
                is_direct_sales_unit=True,
            )
        ],
        exchange_rate_usd=7,
    )

    saved = load_workbook(output_path, data_only=True)
    row = [cell.value for cell in saved.active[2]]
    saved.close()

    assert row == [
        "YS_260731_2",
        "https://detail.1688.com/offer/1.html\nhttps://detail.1688.com/offer/2.html",
        "原备注\n强制合并",
    ]
