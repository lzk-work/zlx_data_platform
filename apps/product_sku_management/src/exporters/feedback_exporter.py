"""Export feedback, logs, exceptions, and snapshots."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..adapters.excel_writer import write_rows
from ..models.domain_models import SalesUnitResult
from ..models.output_models import BatchSummary, DianxiaomiExportPlan, ExceptionRecord, RowLog


def export_supporting_files(
    output_dir: str | Path,
    *,
    sales_units: list[SalesUnitResult],
    row_logs: list[RowLog],
    exceptions: list[ExceptionRecord],
    export_plans: list[DianxiaomiExportPlan],
    summary: BatchSummary,
) -> None:
    """导出批次辅助文件。

    Args:
        output_dir: 输出目录。
        sales_units: 本批次生成的销售单元结果。
        row_logs: 本批次逐行处理日志。
        exceptions: 本批次异常记录。
        export_plans: 本批次店小秘导出计划。
        summary: 本批次汇总。

    Returns:
        None: 写入反馈、异常、日志、快照、导出计划和汇总文件。
    """
    output = Path(output_dir)
    write_rows(
        output / "sales_unit_feedback.xlsx",
        ["row_no", "platform_sku", "shop_name", "sales_unit_type", "mapping_target_type", "mapping_target_sku", "product_skus", "bundle_sku"],
        sales_unit_rows(sales_units, row_logs),
    )
    write_rows(
        output / "exception_records.xlsx",
        ["row_no", "business_key", "exception_type", "exception_message", "suggested_action", "raw_row_json"],
        exception_rows(exceptions),
    )
    write_rows(
        output / "process_row_log.xlsx",
        ["row_no", "business_key", "sales_unit_type", "mapping_target_type", "mapping_target_sku", "product_skus", "bundle_sku", "branch_name", "result", "message"],
        row_log_rows(row_logs),
    )
    write_rows(
        output / "platform_mapping_snapshot.xlsx",
        ["platform_sku", "shop_name", "mapping_target_type", "mapping_target_sku", "sales_unit_id"],
        snapshot_rows(sales_units),
    )
    write_rows(
        output / "dianxiaomi_export_plan.xlsx",
        ["object_type", "object_key", "action_type", "reason", "current_hash", "previous_hash", "export_file", "payload_json"],
        export_plan_rows(export_plans),
    )
    with (output / "batch_summary.json").open("w", encoding="utf-8") as file:
        json.dump(asdict(summary), file, ensure_ascii=False, indent=2, default=str)


def sales_unit_rows(sales_units: list[SalesUnitResult], row_logs: list[RowLog]) -> list[dict[str, Any]]:
    """构建销售单元反馈行。

    Args:
        sales_units: 销售单元结果列表。
        row_logs: 逐行处理日志，用于补充输入行号。

    Returns:
        list[dict[str, Any]]: 可写入Excel的反馈行。
    """
    row_no_by_platform_sku = {log.business_key: log.row_no for log in row_logs}
    return [
        {
            "row_no": row_no_by_platform_sku.get(result.platform_sku, ""),
            "platform_sku": result.platform_sku,
            "shop_name": result.shop_name,
            "sales_unit_type": result.sales_unit_type,
            "mapping_target_type": result.mapping_target_type,
            "mapping_target_sku": result.mapping_target_sku,
            "product_skus": "\n".join(result.product_skus),
            "bundle_sku": result.bundle_sku or "",
        }
        for result in sales_units
    ]


def exception_rows(exceptions: list[ExceptionRecord]) -> list[dict[str, Any]]:
    """构建异常导出行。

    Args:
        exceptions: 异常记录列表。

    Returns:
        list[dict[str, Any]]: 可写入Excel的异常行。
    """
    return [
        {
            "row_no": exception.row_no,
            "business_key": exception.business_key,
            "exception_type": exception.exception_type,
            "exception_message": exception.exception_message,
            "suggested_action": exception.suggested_action,
            "raw_row_json": json.dumps(exception.raw_row, ensure_ascii=False, default=str),
        }
        for exception in exceptions
    ]


def row_log_rows(row_logs: list[RowLog]) -> list[dict[str, Any]]:
    """构建逐行日志导出行。

    Args:
        row_logs: 逐行处理日志列表。

    Returns:
        list[dict[str, Any]]: 可写入Excel的日志行。
    """
    return [
        {
            "row_no": log.row_no,
            "business_key": log.business_key,
            "sales_unit_type": log.sales_unit_type,
            "mapping_target_type": log.mapping_target_type,
            "mapping_target_sku": log.mapping_target_sku,
            "product_skus": "\n".join(log.product_skus),
            "bundle_sku": log.bundle_sku or "",
            "branch_name": log.branch_name,
            "result": log.result,
            "message": log.message,
        }
        for log in row_logs
    ]


def snapshot_rows(sales_units: list[SalesUnitResult]) -> list[dict[str, Any]]:
    """构建平台SKU映射快照行。

    Args:
        sales_units: 销售单元结果列表。

    Returns:
        list[dict[str, Any]]: 可写入Excel的映射快照行。
    """
    return [
        {
            "platform_sku": result.platform_sku,
            "shop_name": result.shop_name,
            "mapping_target_type": result.mapping_target_type,
            "mapping_target_sku": result.mapping_target_sku,
            "sales_unit_id": result.sales_unit_id or "",
        }
        for result in sales_units
    ]


def export_plan_rows(export_plans: list[DianxiaomiExportPlan]) -> list[dict[str, Any]]:
    """构建店小秘导出计划行。

    Args:
        export_plans: 导出计划列表。

    Returns:
        list[dict[str, Any]]: 可写入Excel的导出计划行。
    """
    return [
        {
            "object_type": plan.object_type,
            "object_key": plan.object_key,
            "action_type": plan.action_type,
            "reason": plan.reason,
            "current_hash": plan.current_hash,
            "previous_hash": plan.previous_hash or "",
            "export_file": plan.export_file,
            "payload_json": json.dumps(plan.payload_json, ensure_ascii=False, default=str),
        }
        for plan in export_plans
    ]
