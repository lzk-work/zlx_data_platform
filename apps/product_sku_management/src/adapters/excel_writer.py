"""Small Excel writing helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from openpyxl import Workbook


def write_rows(path: str | Path, headers: list[str], rows: Iterable[dict[str, Any]]) -> None:
    """写入普通Excel工作簿。

    Args:
        path: 输出Excel文件路径。
        headers: 输出表头顺序。
        rows: 字典行数据，按headers取值。

    Returns:
        None: 文件写入到path。
    """
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers)
    for row in rows:
        sheet.append([row.get(header, "") for header in headers])
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)
