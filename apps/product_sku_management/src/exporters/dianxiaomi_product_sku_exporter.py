"""Export Dianxiaomi product SKU template rows."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from ..adapters.dianxiaomi_template_writer import write_template_rows
from ..domain.logistics_attribute import dianxiaomi_dangerous_transport_code
from ..models.domain_models import ProductSkuRecord

TWO_DECIMAL_PLACES = Decimal("0.01")


def export_product_sku_template(
    template_path: str | Path,
    output_path: str | Path,
    records: list[ProductSkuRecord],
    *,
    exchange_rate_usd: float,
) -> None:
    """导出店小秘商品SKU模板。

    Args:
        template_path: 店小秘商品SKU模板路径。
        output_path: 输出文件路径。
        records: 本批次涉及的商品SKU记录。
        exchange_rate_usd: 人民币换美元汇率，用于申报金额。

    Returns:
        None: 生成Excel文件。
    """
    rows = []
    for record in unique_product_skus(records):
        rows.append(
            {
                "*SKU(必填)": record.product_sku,
                "中文名称": record.product_name,
                "图片URL（必须以http://或https：//开头）": record.main_image_url,
                "商品净重（g）": decimal_to_two_places(record.reference_weight_g),
                "采购参考价（RMB）": record.reference_purchase_price_rmb,
                "长（cm）": decimal_to_two_places(record.length_cm),
                "宽（cm）": decimal_to_two_places(record.width_cm),
                "高（cm）": decimal_to_two_places(record.height_cm),
                "来源URL（必须以http://或https：//开头）": product_source_url_text(record),
                "备注": record.note,
                "中文报关名": record.chinese_customs_name,
                "申报重量(g)": decimal_to_two_places(record.reference_weight_g),
                "申报金额（USD）": decimal_divide(record.reference_purchase_price_rmb, exchange_rate_usd),
                "危险运输品": dianxiaomi_dangerous_transport_code(record.logistics_attribute),
            }
        )
    write_template_rows(template_path, output_path, rows)


def product_source_url_text(record: ProductSkuRecord) -> str:
    """生成店小秘商品SKU来源URL文本。

    Args:
        record: 商品SKU记录。

    Returns:
        str: 普通商品SKU返回单个来源URL；强制合包商品SKU返回去重后多行来源URL。
    """
    urls: list[str] = []
    for detail in record.package_details:
        source_url = str(detail.get("source_url") or "").strip()
        if source_url and source_url not in urls:
            urls.append(source_url)
    if not urls and record.source_url:
        urls.append(record.source_url)
    return "\n".join(urls)


def unique_product_skus(records: list[ProductSkuRecord]) -> list[ProductSkuRecord]:
    """按商品SKU去重导出记录。

    Args:
        records: 商品SKU记录列表。

    Returns:
        list[ProductSkuRecord]: 每个商品SKU保留首次出现的记录。
    """
    seen: set[str] = set()
    unique_records: list[ProductSkuRecord] = []
    for record in records:
        if record.product_sku in seen:
            continue
        seen.add(record.product_sku)
        unique_records.append(record)
    return unique_records


def decimal_divide(value: Decimal, divisor: float) -> Decimal:
    """Decimal除法工具，并按店小秘申报金额要求保留两位小数。

    Args:
        value: 被除数。
        divisor: 除数配置值。

    Returns:
        Decimal: 相除后四舍五入到两位小数的结果。
    """
    return (value / Decimal(str(divisor))).quantize(TWO_DECIMAL_PLACES, rounding=ROUND_HALF_UP)


def decimal_to_two_places(value: Decimal | None) -> Decimal | None:
    """按店小秘模板要求将可空数值保留两位小数。

    Args:
        value: 可空Decimal数值。

    Returns:
        Decimal | None: 四舍五入到两位小数的数值；空值保持为空。
    """
    if value is None:
        return None
    return value.quantize(TWO_DECIMAL_PLACES, rounding=ROUND_HALF_UP)
