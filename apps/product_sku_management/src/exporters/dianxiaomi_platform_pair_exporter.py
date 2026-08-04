"""Export Dianxiaomi platform SKU pairing template rows."""

from __future__ import annotations

from pathlib import Path

from ..adapters.dianxiaomi_template_writer import write_template_rows
from ..models.output_models import PlatformPairExportRecord


def export_platform_pair_template(
    template_path: str | Path,
    output_path: str | Path,
    records: list[PlatformPairExportRecord],
) -> None:
    """导出店小秘平台SKU配对模板。

    Args:
        template_path: 店小秘平台SKU配对模板路径。
        output_path: 输出文件路径。
        records: 按商品SKU或组合SKU聚合后的完整平台SKU映射记录。

    Returns:
        None: 生成Excel文件。
    """
    rows = [
        {
            "*SKU(必填)": record.mapping_target_sku,
            "平台SKU": "\n".join(record.platform_skus),
        }
        for record in records
    ]
    write_template_rows(template_path, output_path, rows)
