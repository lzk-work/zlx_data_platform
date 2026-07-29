"""Excel 结果导出。"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Iterable

from openpyxl import Workbook
from openpyxl.styles import Alignment

from .models import AppSettings, ErpRow, ExceptionRow, HistoricalOrderedPlatformSku, ProcessLogRow, ProcessOutput, ProductSkuMaster, SkuPlatformMapping, UploadedProductSku

ERP_HEADERS = [
    "*SKU\n(必填)",
    "平台SKU",
    "识别码",
    "中文名称",
    "英文名称",
    "分类ID",
    "图片URL\n（必须以http://或https：//开头）",
    "商品净重\n（g）",
    "采购参考价\n（RMB）",
    "采购员\n（输入子账号姓名或名称）",
    "长（cm）",
    "宽（cm）",
    "高（cm）",
    "来源URL\n（必须以http://或https：//开头）",
    "备注",
    "英文报关名",
    "中文报关名",
    "申报重量\n(g)",
    "申报金额\n（USD）",
    "出口申报金额（USD）",
    "危险运输品",
    "材质",
    "用途",
    "海关编码",
    "开发员\n（输入子账号姓名或名称）",
    "销售方式",
    "销售员\n（输入子账号姓名或名称）",
]
PRODUCT_MASTER_HEADERS = [
    "商品SKU",
    "货源图片链接",
    "货源链接",
    "规格",
    "采购价/￥",
    "重量/g",
    "长/cm",
    "宽/cm",
    "高/cm",
    "颜色",
    "材质",
    "数量",
    "中文报关名",
    "一级类目",
    "类目代号",
    "临时SKU",
    "供应商",
    "备注",
]
UPLOADED_HEADERS = ["商品SKU", "首次上传时间", "最后更新时间", "备注"]
HISTORICAL_HEADERS = ["平台SKU", "订单号", "平台渠道", "店铺账号", "首次出单时间", "首次处理时间", "处理批次", "备注"]
MAPPING_HEADERS = ["商品SKU", "平台SKU", "绑定时间", "最后更新时间", "绑定来源", "备注"]
EXCEPTION_HEADERS = ["批次号", "行号", "平台SKU", "初始商品SKU", "订单号", "平台渠道", "店铺账号", "出单时间", "校正后货源链接", "校正后规格", "异常类型", "异常说明", "建议处理方式", "备注"]
LOG_HEADERS = ["批次号", "行号", "平台SKU", "初始商品SKU", "正确商品SKU", "订单号", "平台渠道", "店铺账号", "出单时间", "货源核对结果", "处理分支", "处理结果", "ERP表类型", "说明", "备注"]


def export_process_output(settings: AppSettings, output: ProcessOutput, batch_id: str) -> Path:
    """导出处理结果到批次目录。"""
    output_dir = settings.output_dir / batch_id
    output_dir.mkdir(parents=True, exist_ok=True)

    _write_table(output_dir / "ERP新增表.xlsx", ERP_HEADERS, [_erp_row(row, settings) for row in output.erp_new_rows])
    _write_table(output_dir / "ERP更新表.xlsx", ERP_HEADERS, [_erp_row(row, settings) for row in output.erp_update_rows])
    _write_table(output_dir / "异常待处理表.xlsx", EXCEPTION_HEADERS, [_exception_row(row) for row in output.exception_rows])
    _write_table(output_dir / "处理日志表.xlsx", LOG_HEADERS, [_log_row(row) for row in output.log_rows])
    product_source_filename = "本次商品基础库变更表.xlsx" if settings.product_source_mode == "db" else "最新商品基础库留存表.xlsx"
    _write_table(output_dir / product_source_filename, PRODUCT_MASTER_HEADERS, [_product_master_row(row) for row in output.latest_product_sku_master])
    _write_table(output_dir / "最新已上传商品SKU产品表.xlsx", UPLOADED_HEADERS, [_uploaded_row(row) for row in output.latest_uploaded_product_skus])
    _write_table(output_dir / "最新历史出单平台SKU表.xlsx", HISTORICAL_HEADERS, [_historical_row(row) for row in output.latest_historical_ordered_platform_skus])
    _write_table(output_dir / "最新商品SKU-平台SKU映射关系表.xlsx", MAPPING_HEADERS, [_mapping_row(row) for row in output.latest_sku_platform_mapping])

    if output.summary:
        output.summary.output_dir = str(output_dir)
    return output_dir


def publish_state_files(settings: AppSettings, output_dir: Path, batch_id: str) -> None:
    """将成功批次的最新状态表发布为下一次运行入参。"""
    state_files = [
        ("最新已上传商品SKU产品表.xlsx", settings.uploaded_product_skus),
        ("最新历史出单平台SKU表.xlsx", settings.historical_ordered_platform_skus),
        ("最新商品SKU-平台SKU映射关系表.xlsx", settings.product_sku_platform_sku_mapping),
    ]
    for source_name, target_path in state_files:
        source_path = output_dir / source_name
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(source_path.read_bytes())


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


def _erp_row(row: ErpRow, settings: AppSettings) -> list[str]:
    return [
        row.product_sku,
        settings.erp_platform_sku_separator.join(row.platform_skus),
        "",
        row.spec,
        "",
        "",
        row.source_image_url,
        row.weight_g,
        row.purchase_price,
        "",
        row.length,
        row.width,
        row.height,
        row.source_url,
        row.note,
        "",
        row.chinese_customs_name,
        row.weight_g,
        _declaration_amount(row.purchase_price),
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
    ]


def _product_master_row(row: ProductSkuMaster) -> list[str]:
    return [
        row.product_sku,
        row.source_image_url,
        row.source_url,
        row.spec,
        row.purchase_price,
        row.weight_g,
        row.length,
        row.width,
        row.height,
        row.color,
        row.material,
        row.quantity,
        row.chinese_customs_name,
        row.first_level_category,
        row.category_code,
        row.temp_sku,
        row.supplier,
        row.note,
    ]


def _uploaded_row(row: UploadedProductSku) -> list[str]:
    return [row.product_sku, row.first_uploaded_at, row.last_updated_at, row.remark]


def _historical_row(row: HistoricalOrderedPlatformSku) -> list[str]:
    return [row.platform_sku, row.order_no, row.platform_channel, row.shop_account, row.first_order_time, row.first_processed_at, row.batch_id, row.remark]


def _mapping_row(row: SkuPlatformMapping) -> list[str]:
    return [row.product_sku, row.platform_sku, row.bound_at, row.last_updated_at, row.source, row.remark]


def _exception_row(row: ExceptionRow) -> list[str | int]:
    return [row.batch_id, row.row_number, row.platform_sku, row.initial_product_sku, row.order_no, row.platform_channel, row.shop_account, row.order_time, row.corrected_source_url, row.corrected_spec, row.exception_type, row.exception_message, row.suggestion, row.remark]


def _log_row(row: ProcessLogRow) -> list[str | int]:
    return [row.batch_id, row.row_number, row.platform_sku, row.initial_product_sku, row.correct_product_sku, row.order_no, row.platform_channel, row.shop_account, row.order_time, row.source_check_result, row.branch, row.process_result, row.erp_table_type, row.message, row.remark]


def _declaration_amount(purchase_price: str) -> str:
    if not purchase_price:
        return ""
    try:
        value = Decimal(str(purchase_price)) / Decimal("6.8")
    except (InvalidOperation, ValueError):
        return ""
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
