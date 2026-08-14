"""Export Dianxiaomi bundle SKU template rows."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from ..adapters.dianxiaomi_template_writer import write_template_rows
from ..domain.logistics_attribute import dianxiaomi_dangerous_transport_code
from ..models.domain_models import BundleSkuRecord

TWO_DECIMAL_PLACES = Decimal("0.01")


def export_bundle_sku_template(
    template_path: str | Path,
    output_path: str | Path,
    records: list[BundleSkuRecord],
    *,
    exchange_rate_usd: float,
) -> None:
    """导出店小秘组合SKU模板。

    Args:
        template_path: 店小秘组合SKU模板路径。
        output_path: 输出文件路径。
        records: 本批次涉及的组合SKU记录。
        exchange_rate_usd: 人民币换美元汇率，用于申报金额。

    Returns:
        None: 生成Excel文件。
    """
    rows = []
    for record in unique_bundle_skus(records):
        for index, (product_sku, quantity) in enumerate(record.items):
            row = {
                "*组合sku": record.bundle_sku,
                "包含的商品sku": product_sku,
                "数量": quantity,
            }
            if index == 0:
                row.update(
                    {
                        "中文名称": record.bundle_name,
                        "组合SKU主图URL（必须以http://或https：//开头）": record.main_image_url,
                        "备注": record.note,
                        "中文报关名": record.chinese_customs_name,
                        "申报重量(g)": decimal_to_two_places(record.reference_total_weight_g),
                        "申报金额（USD）": decimal_divide(record.reference_total_purchase_price_rmb, exchange_rate_usd),
                        "来源URL(必须以http://或https://开头)": "\n".join(unique_source_urls(record.source_urls)),
                        "长（cm）": decimal_to_two_places(record.length_cm),
                        "宽（cm）": decimal_to_two_places(record.width_cm),
                        "高（cm）": decimal_to_two_places(record.height_cm),
                        "危险运输品": dianxiaomi_dangerous_transport_code(record.logistics_attribute),
                    }
                )
            rows.append(row)
    write_template_rows(template_path, output_path, rows)


def unique_source_urls(source_urls: tuple[str, ...]) -> tuple[str, ...]:
    """按出现顺序去重组合SKU来源链接。

    Args:
        source_urls: 组合内商品SKU对应的货源链接列表。

    Returns:
        tuple[str, ...]: 去重后的来源链接。
    """
    seen: set[str] = set()
    result: list[str] = []
    for source_url in source_urls:
        if not source_url or source_url in seen:
            continue
        seen.add(source_url)
        result.append(source_url)
    return tuple(result)


def unique_bundle_skus(records: list[BundleSkuRecord]) -> list[BundleSkuRecord]:
    """按组合SKU去重导出记录。

    Args:
        records: 组合SKU记录列表。

    Returns:
        list[BundleSkuRecord]: 每个组合SKU保留首次出现的记录。
    """
    seen: set[str] = set()
    unique_records: list[BundleSkuRecord] = []
    for record in records:
        if record.bundle_sku in seen:
            continue
        seen.add(record.bundle_sku)
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
