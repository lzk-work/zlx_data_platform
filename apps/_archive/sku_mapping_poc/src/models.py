"""SKU 映射 POC 的内部数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

MatchType = Literal[
    "initial_consistent",
    "source_key_matched",
    "source_key_missing",
    "ambiguous",
]

ProductSourceMode = Literal["excel", "db"]


@dataclass(slots=True)
class AppSettings:
    project_root: Path
    daily_input: Path
    product_sku_master: Path | None
    uploaded_product_skus: Path
    historical_ordered_platform_skus: Path
    product_sku_platform_sku_mapping: Path
    output_dir: Path
    first_category_codes: Path | None = None
    product_source_mode: ProductSourceMode = "excel"
    database_url: str = ""
    database_schema: str = "zlx_1"
    default_sheet_name: str | None = None
    erp_platform_sku_separator: str = "\n"
    allow_initialize_empty_state: bool = True
    write_failed_rows_to_history: bool = False
    batch_timezone: str = "Asia/Shanghai"


@dataclass(slots=True)
class DailyFirstOrderRow:
    row_number: int
    platform_sku: str
    initial_product_sku: str
    order_no: str
    platform_channel: str
    shop_account: str
    order_time: str
    corrected_source_url: str
    corrected_spec: str
    remark: str = ""
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
    first_level_category: str = ""
    category_code: str = ""
    temp_sku: str = ""
    supplier: str = ""


@dataclass(slots=True)
class ProductSkuMaster:
    product_sku: str
    source_url: str
    spec: str
    length: str = ""
    width: str = ""
    height: str = ""
    source_image_url: str = ""
    purchase_price: str = ""
    weight_g: str = ""
    color: str = ""
    material: str = ""
    quantity: str = ""
    chinese_customs_name: str = ""
    first_level_category: str = ""
    category_code: str = ""
    temp_sku: str = ""
    supplier: str = ""
    note: str = ""


@dataclass(slots=True)
class FirstCategoryCode:
    first_category: str = ""
    first_category_chinese: str = ""
    code: str = ""


@dataclass(slots=True)
class UploadedProductSku:
    product_sku: str
    first_uploaded_at: str = ""
    last_updated_at: str = ""
    remark: str = ""


@dataclass(slots=True)
class HistoricalOrderedPlatformSku:
    platform_sku: str
    order_no: str = ""
    platform_channel: str = ""
    shop_account: str = ""
    first_order_time: str = ""
    first_processed_at: str = ""
    batch_id: str = ""
    remark: str = ""


@dataclass(slots=True)
class SkuPlatformMapping:
    product_sku: str
    platform_sku: str
    bound_at: str = ""
    last_updated_at: str = ""
    source: str = ""
    remark: str = ""


@dataclass(slots=True)
class MatchResult:
    match_type: MatchType
    correct_product_sku: str | None = None
    source_consistent: bool = False
    message: str = ""


@dataclass(slots=True)
class GeneratedSkuResult:
    product_sku: str
    message: str = ""


@dataclass(slots=True)
class ErpRow:
    product_sku: str
    platform_skus: list[str]
    source_url: str
    spec: str
    length: str = ""
    width: str = ""
    height: str = ""
    source_image_url: str = ""
    purchase_price: str = ""
    weight_g: str = ""
    chinese_customs_name: str = ""
    note: str = ""
    remark: str = ""


@dataclass(slots=True)
class ExceptionRow:
    batch_id: str
    row_number: int
    platform_sku: str
    initial_product_sku: str
    order_no: str
    platform_channel: str
    shop_account: str
    order_time: str
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
    order_no: str
    platform_channel: str
    shop_account: str
    order_time: str
    source_check_result: str
    branch: str
    process_result: str
    erp_table_type: str
    message: str
    remark: str = ""


@dataclass(slots=True)
class RunSummary:
    batch_id: str
    input_rows: int = 0
    first_order_processed: int = 0
    historical_skipped: int = 0
    erp_new_product_skus: int = 0
    erp_update_product_skus: int = 0
    generated_product_skus: int = 0
    exceptions: int = 0
    output_dir: str = ""


@dataclass(slots=True)
class SystemStatusSummary:
    daily_input_rows: int = 0
    product_master_skus: int = 0
    first_category_codes: int = 0
    uploaded_product_skus: int = 0
    historical_platform_skus: int = 0
    mapped_product_skus: int = 0
    mapped_platform_skus: int = 0
    product_source_mode: ProductSourceMode = "excel"


@dataclass(slots=True)
class ProcessOutput:
    erp_new_rows: list[ErpRow] = field(default_factory=list)
    erp_update_rows: list[ErpRow] = field(default_factory=list)
    latest_product_sku_master: list[ProductSkuMaster] = field(default_factory=list)
    latest_uploaded_product_skus: list[UploadedProductSku] = field(default_factory=list)
    latest_historical_ordered_platform_skus: list[HistoricalOrderedPlatformSku] = field(default_factory=list)
    latest_sku_platform_mapping: list[SkuPlatformMapping] = field(default_factory=list)
    exception_rows: list[ExceptionRow] = field(default_factory=list)
    log_rows: list[ProcessLogRow] = field(default_factory=list)
    summary: RunSummary | None = None


WorkbookRow = dict[str, Any]
