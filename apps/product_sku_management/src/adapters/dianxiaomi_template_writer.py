"""Writers that preserve Dianxiaomi workbook headers and unused columns."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Iterable

from openpyxl import load_workbook


def write_template_rows(template_path: str | Path, output_path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    """按店小秘模板表头写入数据。

    Args:
        template_path: 店小秘原始模板路径。
        output_path: 写入后的输出文件路径。
        rows: 待写入行；只填充能匹配到模板表头的字段。

    Returns:
        None: 文件写入到output_path，未匹配列保持空值和原表头格式。
    """
    workbook = load_workbook(template_path)
    sheet = workbook.worksheets[0]
    headers = [str(cell.value or "").strip() for cell in sheet[1]]

    if sheet.max_row > 1:
        sheet.delete_rows(2, sheet.max_row - 1)

    for row in rows:
        sheet.append([row.get(header, row.get(normalize_header_key(header), "")) for header in headers])

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output)


def normalize_header_key(header: str) -> str:
    """标准化模板表头键。

    Args:
        header: 模板中的原始表头。

    Returns:
        str: 移除空白和换行后的表头键。
    """
    return re.sub(r"\s+", "", header)
