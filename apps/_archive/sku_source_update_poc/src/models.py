"""平台 SKU 货源预校正数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from apps.sku_mapping_poc.src.models import FirstCategoryCode, ProductSkuMaster

RunMode = Literal["platform", "source-only"]


@dataclass(slots=True)
class AppSettings:
    project_root: Path
    input: Path
    output_dir: Path
    database_url: str
    database_schema: str = "zlx_1"
    default_sheet_name: str | None = None
    batch_timezone: str = "Asia/Shanghai"
    run_mode: RunMode = "platform"


@dataclass(slots=True)
class SourceUpdateInputRow:
    row_number: int
    platform_sku: str
    initial_product_sku: str
    corrected_source_url: str
    corrected_spec: str
    first_level_category: str = ""
    category_code: str = ""
    source_image_url: str = ""
    purchase_price: str = ""
    weight_g: str = ""
    length_cm: str = ""
    width_cm: str = ""
    height_cm: str = ""
    color: str = ""
    material: str = ""
    quantity: str = ""
    chinese_customs_name: str = ""
    supplier: str = ""
    remark: str = ""


@dataclass(slots=True)
class PlatformSkuMappingRow:
    platform_sku: str
    initial_product_sku: str
    correct_product_sku: str
    corrected_source_url: str
    corrected_spec: str
    match_result: str
    remark: str = ""


@dataclass(slots=True)
class ExceptionRow:
    batch_id: str
    row_number: int
    platform_sku: str
    initial_product_sku: str
    corrected_source_url: str
    corrected_spec: str
    exception_type: str
    exception_message: str
    suggestion: str
    remark: str = ""


@dataclass(slots=True)
class ProcessLogRow:
    batch_id: str
    row_number: int
    platform_sku: str
    initial_product_sku: str
    correct_product_sku: str
    corrected_source_url: str
    corrected_spec: str
    match_result: str
    process_result: str
    message: str
    remark: str = ""


@dataclass(slots=True)
class RunSummary:
    batch_id: str
    input_rows: int = 0
    processed_rows: int = 0
    matched_existing_skus: int = 0
    source_only_skipped: int = 0
    generated_product_skus: int = 0
    exceptions: int = 0
    output_dir: str = ""


@dataclass(slots=True)
class ProcessOutput:
    new_product_source_rows: list[ProductSkuMaster] = field(default_factory=list)
    platform_mapping_rows: list[PlatformSkuMappingRow] = field(default_factory=list)
    exception_rows: list[ExceptionRow] = field(default_factory=list)
    log_rows: list[ProcessLogRow] = field(default_factory=list)
    summary: RunSummary | None = None


WorkbookRow = dict[str, object]


__all__ = [
    "AppSettings",
    "ExceptionRow",
    "FirstCategoryCode",
    "PlatformSkuMappingRow",
    "ProcessLogRow",
    "ProcessOutput",
    "ProductSkuMaster",
    "RunMode",
    "RunSummary",
    "SourceUpdateInputRow",
]
