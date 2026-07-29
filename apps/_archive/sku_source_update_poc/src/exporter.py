"""平台 SKU 货源预校正结果导出。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from openpyxl import Workbook
from openpyxl.styles import Alignment

from .models import AppSettings, ExceptionRow, PlatformSkuMappingRow, ProcessLogRow, ProcessOutput, ProductSkuMaster

PRODUCT_HEADERS = ["商品SKU", "货源图片链接", "货源链接", "规格", "采购价/￥", "重量/g", "长/cm", "宽/cm", "高/cm", "颜色", "材质", "数量", "中文报关名", "一级类目", "类目代号", "供应商", "备注"]
MAPPING_HEADERS = ["平台SKU", "初始商品SKU", "正确商品SKU", "校正后货源链接", "校正后规格", "匹配结果", "备注"]
EXCEPTION_HEADERS = ["批次号", "行号", "平台SKU", "初始商品SKU", "校正后货源链接", "校正后规格", "异常类型", "异常说明", "建议处理方式", "备注"]
LOG_HEADERS = ["批次号", "行号", "平台SKU", "初始商品SKU", "正确商品SKU", "校正后货源链接", "校正后规格", "匹配结果", "处理结果", "说明", "备注"]


def export_output(settings: AppSettings, output: ProcessOutput, batch_id: str) -> Path:
    output_dir = settings.output_dir / batch_id
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_table(output_dir / "本次商品基础库新增表.xlsx", PRODUCT_HEADERS, [_product_row(row) for row in output.new_product_source_rows])
    _write_table(output_dir / "本次平台SKU映射关系表.xlsx", MAPPING_HEADERS, [_mapping_row(row) for row in output.platform_mapping_rows])
    _write_table(output_dir / "异常待处理表.xlsx", EXCEPTION_HEADERS, [_exception_row(row) for row in output.exception_rows])
    _write_table(output_dir / "处理日志表.xlsx", LOG_HEADERS, [_log_row(row) for row in output.log_rows])
    if output.summary:
        output.summary.output_dir = str(output_dir)
    return output_dir


def _write_table(path: Path, headers: list[str], rows: Iterable[list[Any]]) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sheet1"
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    for row in sheet.iter_rows():
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    workbook.save(path)


def _product_row(row: ProductSkuMaster) -> list[str]:
    return [row.product_sku, row.source_image_url, row.source_url, row.spec, row.purchase_price, row.weight_g, row.length, row.width, row.height, row.color, row.material, row.quantity, row.chinese_customs_name, row.first_level_category, row.category_code, row.supplier, row.note]


def _mapping_row(row: PlatformSkuMappingRow) -> list[str]:
    return [row.platform_sku, row.initial_product_sku, row.correct_product_sku, row.corrected_source_url, row.corrected_spec, row.match_result, row.remark]


def _exception_row(row: ExceptionRow) -> list[str | int]:
    return [row.batch_id, row.row_number, row.platform_sku, row.initial_product_sku, row.corrected_source_url, row.corrected_spec, row.exception_type, row.exception_message, row.suggestion, row.remark]


def _log_row(row: ProcessLogRow) -> list[str | int]:
    return [row.batch_id, row.row_number, row.platform_sku, row.initial_product_sku, row.correct_product_sku, row.corrected_source_url, row.corrected_spec, row.match_result, row.process_result, row.message, row.remark]
