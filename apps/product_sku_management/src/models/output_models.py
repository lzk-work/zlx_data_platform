"""Output models for exports and process logs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RowLog:
    """A per-row processing log entry."""

    row_no: int
    business_key: str
    sales_unit_type: str = ""
    mapping_target_type: str = ""
    mapping_target_sku: str = ""
    product_skus: tuple[str, ...] = field(default_factory=tuple)
    bundle_sku: str | None = None
    branch_name: str = ""
    result: str = "success"
    message: str = ""


@dataclass(frozen=True)
class ExceptionRecord:
    """A row-level exception that did not write business tables."""

    row_no: int
    business_key: str
    raw_row: dict[str, Any]
    exception_type: str
    exception_message: str
    suggested_action: str = ""


@dataclass(frozen=True)
class BatchSummary:
    """Summary fields for one workflow run."""

    process_batch_id: str
    workflow_type: str
    input_file: str
    output_dir: str
    input_rows: int
    success_rows: int
    exception_rows: int
    created_product_sku_count: int
    created_bundle_sku_count: int
    created_sales_unit_count: int
    created_mapping_count: int


@dataclass(frozen=True)
class PlatformPairExportRecord:
    """A full platform-SKU set under one mapping target SKU."""

    mapping_target_sku: str
    platform_skus: tuple[str, ...]


@dataclass(frozen=True)
class DianxiaomiExportPlan:
    """One Dianxiaomi object action for the current batch."""

    process_batch_id: str
    object_type: str
    object_key: str
    action_type: str
    reason: str
    current_hash: str
    previous_hash: str | None
    payload_json: dict[str, Any]
    export_file: str = ""
