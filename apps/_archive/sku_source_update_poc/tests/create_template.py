"""Create blank input template for sku_source_update_poc."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook


def main() -> None:
    base = Path(__file__).resolve().parents[1] / "data" / "input"
    base.mkdir(parents=True, exist_ok=True)
    headers = ["平台SKU", "初始商品SKU", "校正后货源链接", "校正后规格", "一级类目", "类目代号", "图片链接", "采购价/￥", "重量/g", "长/cm", "宽/cm", "高/cm", "数量", "颜色", "材质", "中文报关名", "供应商", "备注"]
    for filename in ["平台SKU货源预校正输入表.xlsx", "直接添加货源输入表.xlsx"]:
        path = base / filename
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(headers)
        workbook.save(path)
        print(path)


if __name__ == "__main__":
    main()
