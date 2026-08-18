"""Platform SKU supplement workflow."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

from ..adapters.excel_reader import read_platform_listing_rows
from ..constants import (
    DIANXIAOMI_OBJECT_BUNDLE_SKU,
    DIANXIAOMI_OBJECT_PLATFORM_PAIR,
    DIANXIAOMI_OBJECT_PRODUCT_SKU,
    EXPORT_ACTION_CREATE,
    EXPORT_ACTION_UPDATE,
    MAPPING_TARGET_BUNDLE_SKU,
    MAPPING_TARGET_PRODUCT_SKU,
    PRODUCT_SKU_TYPE_FORCED_PACKAGE,
    PRODUCT_SKU_TYPE_NORMAL,
    SALES_UNIT_TYPE_FORCED_PRODUCT_SKU,
    WORKFLOW_MODE_SUPPLEMENT,
    WORKFLOW_MODE_UPDATE,
    WORKFLOW_PLATFORM_LISTING_SUPPLEMENT,
    WORKFLOW_PLATFORM_LISTING_UPDATE,
    dianxiaomi_export_template_name,
)
from ..domain.bundle_service import bundle_fingerprint, decide_bundle
from ..domain.dianxiaomi_export_planner import bundle_sku_plan, platform_pair_plan, product_sku_plan
from ..domain.logistics_attribute import dianxiaomi_dangerous_transport_code
from ..domain.name_builder import build_bundle_name, build_forced_package_name, build_product_name
from ..domain.pricing_weight_calculator import calculate_reference_value, kg_to_g
from ..domain.source_cleaner import clean_source_url
from ..domain.spec_parser import ParsedSpecDetail, parse_spec
from ..exporters.dianxiaomi_bundle_sku_exporter import export_bundle_sku_template
from ..exporters.dianxiaomi_platform_pair_exporter import export_platform_pair_template
from ..exporters.dianxiaomi_product_sku_exporter import export_product_sku_template
from ..exporters.feedback_exporter import export_supporting_files
from ..models.domain_models import BundleSkuRecord, ParsedSourceItem, ProductSkuRecord, SalesUnitResult
from ..models.input_models import PlatformListingInputRow, SourceGroupInput
from ..models.output_models import BatchSummary, DianxiaomiExportPlan, ExceptionRecord, PlatformPairExportRecord, RowLog
from ..repositories.db import (
    ProductSkuDatabase,
    bundle_record_from_row,
    new_process_batch_id,
    product_record_from_row,
)
from ..settings import ProductSkuSettings


class DryRunContext:
    """试运行上下文，保存不入库的临时SKU和映射状态。"""

    def __init__(self, *, date_key: str, product_counter: int, bundle_counter: int) -> None:
        """初始化试运行上下文。

        Args:
            date_key: 当前日期键，格式YYMMDD。
            product_counter: 数据库商品SKU当前流水最大值。
            bundle_counter: 数据库组合SKU当前流水最大值。

        Returns:
            None: 初始化内存状态。
        """
        self.date_key = date_key
        self.product_counter = product_counter
        self.bundle_counter = bundle_counter
        self.products_by_source: dict[tuple[str, str, int], ProductSkuRecord] = {}
        self.forced_packages_by_fingerprint: dict[str, ProductSkuRecord] = {}
        self.bundles_by_fingerprint: dict[str, BundleSkuRecord] = {}
        self.platform_mapping_by_sku: dict[str, tuple[str, str]] = {}
        self.platform_skus_by_target: dict[str, set[str]] = {}
        self.removed_platform_skus_by_target: dict[str, set[str]] = {}
        self.sales_unit_keys: set[tuple[str, str, str]] = set()
        self.category_code_by_name: dict[str, str | None] = {}

    @classmethod
    def from_database(cls, db: ProductSkuDatabase, conn: Any) -> "DryRunContext":
        """从数据库当前流水创建试运行上下文。

        Args:
            db: 商品SKU数据库仓储。
            conn: 当前只读连接。

        Returns:
            DryRunContext: 从当前流水继续预测编码的上下文。
        """
        date_key = datetime.now().strftime("%y%m%d")
        return cls(
            date_key=date_key,
            product_counter=db.get_current_code_counter_value(conn, "product_sku", date_key),
            bundle_counter=db.get_current_code_counter_value(conn, "bundle_sku", f"ZH_{date_key}"),
        )

    def next_product_sku_code(self, category_code: str) -> str:
        """预测下一个商品SKU编码，不更新数据库流水。

        Args:
            category_code: 一级类目代号。

        Returns:
            str: 预测商品SKU编码。
        """
        self.product_counter += 1
        return f"{category_code}_{self.date_key}_{self.product_counter}"

    def next_bundle_sku_code(self, distinct_product_sku_count: int, total_product_count: int) -> str:
        """预测下一个组合SKU编码，不更新数据库流水。

        Args:
            distinct_product_sku_count: 组合内不同商品SKU数量。
            total_product_count: 组合内商品总件数。

        Returns:
            str: 预测组合SKU编码。
        """
        self.bundle_counter += 1
        return f"ZH_{self.date_key}_{distinct_product_sku_count}_{total_product_count}_{self.bundle_counter}"

    def remember_platform_mapping(self, platform_sku: str, mapping_target_type: str, mapping_target_sku: str) -> bool:
        """记录本次试运行预测的平台SKU映射。

        Args:
            platform_sku: 平台SKU。
            mapping_target_type: 映射目标类型。
            mapping_target_sku: 映射目标SKU编码。

        Returns:
            bool: 本次试运行第一次看到该平台SKU时返回True。

        Raises:
            ValueError: 同一试运行批次内平台SKU被预测绑定到不同目标时抛出。
        """
        existing = self.platform_mapping_by_sku.get(platform_sku)
        current = (mapping_target_type, mapping_target_sku)
        if existing and existing != current:
            raise ValueError("平台SKU在本次试运行中绑定到不同映射目标")
        self.platform_mapping_by_sku[platform_sku] = current
        self.platform_skus_by_target.setdefault(mapping_target_sku, set()).add(platform_sku)
        return existing is None

    def remember_platform_rebind(
        self,
        platform_sku: str,
        old_mapping_target_sku: str,
        mapping_target_type: str,
        mapping_target_sku: str,
    ) -> None:
        """记录试运行中的平台SKU改绑预测。

        Args:
            platform_sku: 平台SKU。
            old_mapping_target_sku: 数据库当前旧映射目标SKU。
            mapping_target_type: 新映射目标类型。
            mapping_target_sku: 新映射目标SKU。

        Returns:
            None: 在内存中记录旧目标移除和新目标新增。
        """
        self.platform_mapping_by_sku[platform_sku] = (mapping_target_type, mapping_target_sku)
        self.removed_platform_skus_by_target.setdefault(old_mapping_target_sku, set()).add(platform_sku)
        self.platform_skus_by_target.setdefault(mapping_target_sku, set()).add(platform_sku)

    def remember_sales_unit(self, platform_sku: str, mapping_target_type: str, mapping_target_sku: str) -> bool:
        """记录本次试运行预测的销售单元。

        Args:
            platform_sku: 平台SKU。
            mapping_target_type: 映射目标类型。
            mapping_target_sku: 映射目标SKU编码。

        Returns:
            bool: 本次试运行第一次看到该销售单元时返回True。
        """
        key = (platform_sku, mapping_target_type, mapping_target_sku)
        if key in self.sales_unit_keys:
            return False
        self.sales_unit_keys.add(key)
        return True

    def get_category_code(self, db: ProductSkuDatabase, conn: Any, first_level_category: str) -> str | None:
        """读取并缓存一级类目代号。

        Args:
            db: 商品SKU数据库仓储。
            conn: 当前只读数据库连接。
            first_level_category: 一级类目英文名或中文名。

        Returns:
            str | None: 类目代号；不存在时返回None。
        """
        if first_level_category not in self.category_code_by_name:
            self.category_code_by_name[first_level_category] = db.get_category_code_with_connection(
                conn,
                first_level_category,
            )
        return self.category_code_by_name[first_level_category]


def run_platform_listing_supplement(
    settings: ProductSkuSettings,
    *,
    init_db: bool = False,
    dry_run: bool = False,
    mode: str = WORKFLOW_MODE_SUPPLEMENT,
) -> BatchSummary:
    """运行平台SKU补充工作流。

    Args:
        settings: 商品SKU管理运行配置。
        init_db: 是否先执行建表SQL。
        dry_run: 是否只生成预期结果，不写入数据库。
        mode: 运行模式，supplement为普通补充，update允许平台SKU显式改绑。

    Returns:
        BatchSummary: 本批次输入、成功、异常、新建对象和输出目录汇总。
    """
    db = ProductSkuDatabase.from_settings(settings)
    if init_db:
        db.ensure_schema(settings.sql_path)

    workflow_type = WORKFLOW_PLATFORM_LISTING_UPDATE if mode == WORKFLOW_MODE_UPDATE else WORKFLOW_PLATFORM_LISTING_SUPPLEMENT
    input_file = platform_listing_file_for_mode(settings, mode)
    process_batch_id = new_process_batch_id("sku_mgmt_dry_run" if dry_run else "sku_mgmt")
    output_dir = settings.output_dir / process_batch_id
    output_dir.mkdir(parents=True, exist_ok=True)
    if not dry_run:
        db.create_process_batch(process_batch_id, str(input_file), str(output_dir), workflow_type)

    input_rows = read_platform_listing_rows(input_file)
    dry_run_context: DryRunContext | None = None
    dry_run_conn: Any | None = None
    dry_run_connection_manager: Any | None = None
    if dry_run:
        dry_run_connection_manager = db.connection()
        dry_run_conn = dry_run_connection_manager.__enter__()
        dry_run_context = DryRunContext.from_database(db, dry_run_conn)
    touched_products: list[ProductSkuRecord] = []
    touched_bundles: list[BundleSkuRecord] = []
    sales_units: list[SalesUnitResult] = []
    row_logs: list[RowLog] = []
    exceptions: list[ExceptionRecord] = []
    affected_mapping_target_skus: set[str] = set()

    created_product_sku_count = 0
    created_bundle_sku_count = 0
    created_sales_unit_count = 0
    created_mapping_count = 0

    for input_row in input_rows:
        try:
            if dry_run:
                if dry_run_context is None or dry_run_conn is None:
                    raise RuntimeError("试运行上下文未初始化")
                result = process_one_row_dry_run(
                    db,
                    dry_run_conn,
                    dry_run_context,
                    process_batch_id,
                    input_row,
                    allow_mapping_rebind=mode == WORKFLOW_MODE_UPDATE,
                )
            else:
                result = process_one_row(
                    db,
                    process_batch_id,
                    input_row,
                    allow_mapping_rebind=mode == WORKFLOW_MODE_UPDATE,
                )
        except Exception as exc:  # noqa: BLE001 - row-level exception must not stop the batch.
            exception = ExceptionRecord(
                row_no=input_row.row_no,
                business_key=input_row.platform_sku,
                raw_row=input_row.raw_row,
                exception_type=type(exc).__name__,
                exception_message=str(exc),
                suggested_action="修正该行后放入下一批继续处理",
            )
            exceptions.append(exception)
            row_log = RowLog(
                row_no=input_row.row_no,
                business_key=input_row.platform_sku,
                result="exception",
                message=str(exc),
            )
            row_logs.append(row_log)
            if not dry_run:
                db.insert_exception_record(process_batch_id, exception, workflow_type)
                db.insert_row_log(process_batch_id, row_log, workflow_type)
            continue

        touched_products.extend(result.product_records)
        if result.bundle_record:
            touched_bundles.append(result.bundle_record)
        sales_units.append(result.sales_unit_result)
        row_logs.append(result.row_log)
        if not dry_run:
            db.insert_row_log(process_batch_id, result.row_log, workflow_type)
        affected_mapping_target_skus.update(result.affected_mapping_target_skus)
        created_product_sku_count += sum(1 for record in result.product_records if record.created)
        created_bundle_sku_count += int(bool(result.bundle_record and result.bundle_record.created))
        created_sales_unit_count += int(result.created_sales_unit)
        created_mapping_count += int(result.created_mapping)

    summary = BatchSummary(
        process_batch_id=process_batch_id,
        workflow_type=workflow_type,
        input_file=str(input_file),
        output_dir=str(output_dir),
        input_rows=len(input_rows),
        success_rows=len(sales_units),
        exception_rows=len(exceptions),
        created_product_sku_count=created_product_sku_count,
        created_bundle_sku_count=created_bundle_sku_count,
        created_sales_unit_count=created_sales_unit_count,
        created_mapping_count=created_mapping_count,
    )

    export_result = build_dianxiaomi_export_plans(
        db=db,
        process_batch_id=process_batch_id,
        product_records=touched_products,
        bundle_records=touched_bundles,
        sales_units=sales_units,
        output_dir=output_dir,
        exchange_rate_usd=settings.exchange_rate_usd,
        additional_platform_skus_by_target=dry_run_context.platform_skus_by_target if dry_run_context else None,
        removed_platform_skus_by_target=dry_run_context.removed_platform_skus_by_target if dry_run_context else None,
        additional_mapping_target_skus=affected_mapping_target_skus,
    )

    if not dry_run:
        for plan in export_result.plans:
            db.insert_dianxiaomi_export_plan(plan)
            db.mark_dianxiaomi_exported(plan)

    export_dianxiaomi_templates(settings, output_dir, export_result)
    export_supporting_files(
        output_dir,
        sales_units=sales_units,
        row_logs=row_logs,
        exceptions=exceptions,
        export_plans=export_result.plans,
        summary=summary,
    )

    status = "success" if not exceptions else "partial_success"
    if not sales_units and exceptions:
        status = "failed"
    if dry_run_connection_manager is not None:
        dry_run_connection_manager.__exit__(None, None, None)
    if not dry_run:
        db.finish_process_batch(summary, status)
    return summary


def build_dianxiaomi_export_plans(
    *,
    db: ProductSkuDatabase,
    process_batch_id: str,
    product_records: list[ProductSkuRecord],
    bundle_records: list[BundleSkuRecord],
    sales_units: list[SalesUnitResult],
    output_dir: Path,
    exchange_rate_usd: float,
    additional_platform_skus_by_target: dict[str, set[str]] | None = None,
    removed_platform_skus_by_target: dict[str, set[str]] | None = None,
    additional_mapping_target_skus: set[str] | None = None,
) -> DianxiaomiExportResult:
    """生成店小秘导出计划和实际导出记录。

    Args:
        db: 商品SKU数据库仓储。
        process_batch_id: 当前处理批次ID。
        product_records: 本批次触达的商品SKU记录。
        bundle_records: 本批次触达的组合SKU记录。
        sales_units: 本批次生成的销售单元结果。
        output_dir: 本批次输出目录。
        exchange_rate_usd: 人民币换美元汇率。
        additional_platform_skus_by_target: 试运行中预测新增但尚未入库的平台SKU映射。
        removed_platform_skus_by_target: 试运行中预测从旧目标移除的平台SKU映射。
        additional_mapping_target_skus: 本批次除销售单元新目标外还需重算配对的目标SKU。

    Returns:
        DianxiaomiExportResult: 全部导出计划，以及按新增/更新拆分后的模板记录。
    """
    plans: list[DianxiaomiExportPlan] = []
    product_exports_by_action: dict[str, list[ProductSkuRecord]] = empty_export_buckets()
    bundle_exports_by_action: dict[str, list[BundleSkuRecord]] = empty_export_buckets()
    platform_pair_exports_by_action: dict[str, list[PlatformPairExportRecord]] = empty_export_buckets()

    for record in unique_product_records(product_records):
        previous_hash = db.get_dianxiaomi_confirmed_hash(DIANXIAOMI_OBJECT_PRODUCT_SKU, record.product_sku)
        plan = product_sku_plan(
            process_batch_id=process_batch_id,
            record=record,
            previous_hash=previous_hash,
            previous_payload_json=db.get_dianxiaomi_confirmed_payload(
                DIANXIAOMI_OBJECT_PRODUCT_SKU,
                record.product_sku,
            )
            if previous_hash
            else None,
            export_file=str(dianxiaomi_template_path(output_dir, "product_sku", EXPORT_ACTION_CREATE)),
            exchange_rate_usd=exchange_rate_usd,
        )
        plan = plan_with_action_export_file(plan, output_dir, "product_sku")
        plans.append(plan)
        if should_export(plan):
            product_exports_by_action[plan.action_type].append(record)

    for record in unique_bundle_records(bundle_records):
        previous_hash = db.get_dianxiaomi_confirmed_hash(DIANXIAOMI_OBJECT_BUNDLE_SKU, record.bundle_sku)
        plan = bundle_sku_plan(
            process_batch_id=process_batch_id,
            record=record,
            previous_hash=previous_hash,
            previous_payload_json=db.get_dianxiaomi_confirmed_payload(
                DIANXIAOMI_OBJECT_BUNDLE_SKU,
                record.bundle_sku,
            )
            if previous_hash
            else None,
            export_file=str(dianxiaomi_template_path(output_dir, "bundle_sku", EXPORT_ACTION_CREATE)),
            exchange_rate_usd=exchange_rate_usd,
        )
        plan = plan_with_action_export_file(plan, output_dir, "bundle_sku")
        plans.append(plan)
        if should_export(plan):
            bundle_exports_by_action[plan.action_type].append(record)

    additional_platform_skus_by_target = additional_platform_skus_by_target or {}
    removed_platform_skus_by_target = removed_platform_skus_by_target or {}
    additional_mapping_target_skus = additional_mapping_target_skus or set()
    mapping_target_skus = {result.mapping_target_sku for result in sales_units} | additional_mapping_target_skus
    for mapping_target_sku in sorted(mapping_target_skus):
        record = platform_pair_record_with_changes(
            db,
            mapping_target_sku,
            additional_platform_skus_by_target.get(mapping_target_sku, set()),
            removed_platform_skus_by_target.get(mapping_target_sku, set()),
        )
        plan = platform_pair_plan(
            process_batch_id=process_batch_id,
            record=record,
            previous_hash=db.get_dianxiaomi_confirmed_hash(DIANXIAOMI_OBJECT_PLATFORM_PAIR, mapping_target_sku),
            export_file=str(dianxiaomi_template_path(output_dir, "platform_pair", EXPORT_ACTION_CREATE)),
        )
        plan = plan_with_action_export_file(plan, output_dir, "platform_pair")
        plans.append(plan)
        if should_export(plan):
            platform_pair_exports_by_action[plan.action_type].append(record)

    return DianxiaomiExportResult(
        plans=plans,
        product_exports_by_action=product_exports_by_action,
        bundle_exports_by_action=bundle_exports_by_action,
        platform_pair_exports_by_action=platform_pair_exports_by_action,
    )


@dataclass(frozen=True)
class DianxiaomiExportResult:
    """按店小秘动作拆分后的导出结果。"""

    plans: list[DianxiaomiExportPlan]
    product_exports_by_action: dict[str, list[ProductSkuRecord]]
    bundle_exports_by_action: dict[str, list[BundleSkuRecord]]
    platform_pair_exports_by_action: dict[str, list[PlatformPairExportRecord]]


def platform_listing_file_for_mode(settings: ProductSkuSettings, mode: str) -> Path:
    """按运行模式选择输入文件。

    Args:
        settings: 商品SKU管理运行配置。
        mode: 运行模式，supplement或update。

    Returns:
        Path: 当前模式对应的输入Excel路径。
    """
    if mode == WORKFLOW_MODE_UPDATE:
        return settings.platform_listing_update_file
    return settings.platform_listing_supplement_file


def export_dianxiaomi_templates(
    settings: ProductSkuSettings,
    output_dir: Path,
    export_result: DianxiaomiExportResult,
) -> None:
    """按新增和更新分别导出店小秘模板。

    Args:
        settings: 商品SKU管理运行配置。
        output_dir: 本批次输出目录。
        export_result: 已按动作拆分的导出记录。

    Returns:
        None: 写入商品SKU、组合SKU、平台SKU配对的新增/更新模板。
    """
    for action_type in export_action_types():
        product_records = export_result.product_exports_by_action[action_type]
        if product_records:
            export_product_sku_template(
                settings.product_sku_template,
                dianxiaomi_template_path(output_dir, "product_sku", action_type),
                product_records,
                exchange_rate_usd=settings.exchange_rate_usd,
            )

        bundle_records = export_result.bundle_exports_by_action[action_type]
        if bundle_records:
            export_bundle_sku_template(
                settings.bundle_sku_template,
                dianxiaomi_template_path(output_dir, "bundle_sku", action_type),
                bundle_records,
                exchange_rate_usd=settings.exchange_rate_usd,
            )

        platform_pair_records = export_result.platform_pair_exports_by_action[action_type]
        if platform_pair_records:
            export_platform_pair_template(
                settings.platform_pair_template,
                dianxiaomi_template_path(output_dir, "platform_pair", action_type),
                platform_pair_records,
            )


def empty_export_buckets() -> dict[str, list[Any]]:
    """创建按店小秘动作拆分的导出桶。

    Args:
        无。

    Returns:
        dict[str, list[Any]]: create和update两个动作对应的空列表。
    """
    return {action_type: [] for action_type in export_action_types()}


def export_action_types() -> tuple[str, str]:
    """返回需要写入模板的店小秘动作。

    Args:
        无。

    Returns:
        tuple[str, str]: 新增和更新动作。
    """
    return (EXPORT_ACTION_CREATE, EXPORT_ACTION_UPDATE)


def dianxiaomi_template_path(output_dir: Path, object_name: str, action_type: str) -> Path:
    """生成按对象和动作拆分的店小秘模板路径（中文文件名，便于业务识别）。

    Args:
        output_dir: 本批次输出目录。
        object_name: 对象类型，如product_sku。
        action_type: 店小秘动作，create或update。

    Returns:
        Path: 目标导出文件路径。
    """
    return output_dir / dianxiaomi_export_template_name(object_name, action_type)


def plan_with_action_export_file(
    plan: DianxiaomiExportPlan,
    output_dir: Path,
    object_name: str,
) -> DianxiaomiExportPlan:
    """把导出计划的文件路径修正为动作拆分后的模板路径。

    Args:
        plan: 已计算出动作的导出计划。
        output_dir: 本批次输出目录。
        object_name: 对象文件名片段，如product_sku。

    Returns:
        DianxiaomiExportPlan: skip保持空路径，create/update写入对应模板路径。
    """
    if not should_export(plan):
        return plan
    return replace(plan, export_file=str(dianxiaomi_template_path(output_dir, object_name, plan.action_type)))


def platform_pair_record_with_changes(
    db: ProductSkuDatabase,
    mapping_target_sku: str,
    additional_platform_skus: set[str],
    removed_platform_skus: set[str],
) -> PlatformPairExportRecord:
    """读取平台SKU配对记录并合并试运行预测的新增和移除映射。

    Args:
        db: 商品SKU数据库仓储。
        mapping_target_sku: 商品SKU或组合SKU编码。
        additional_platform_skus: 试运行预测新增的平台SKU集合。
        removed_platform_skus: 试运行预测从当前目标移除的平台SKU集合。

    Returns:
        PlatformPairExportRecord: 数据库已有平台SKU叠加试运行变化后的完整集合。
    """
    record = db.get_platform_pair_export_record(mapping_target_sku)
    platform_skus = tuple(sorted((set(record.platform_skus) | additional_platform_skus) - removed_platform_skus))
    return PlatformPairExportRecord(mapping_target_sku=mapping_target_sku, platform_skus=platform_skus)


def should_export(plan: DianxiaomiExportPlan) -> bool:
    """判断导出计划是否需要写入店小秘模板。

    Args:
        plan: 单个店小秘导出计划。

    Returns:
        bool: create和update返回True，skip不写入模板。
    """
    return plan.action_type in {EXPORT_ACTION_CREATE, EXPORT_ACTION_UPDATE}


def unique_product_records(records: list[ProductSkuRecord]) -> list[ProductSkuRecord]:
    """按商品SKU去重记录。

    Args:
        records: 商品SKU记录列表。

    Returns:
        list[ProductSkuRecord]: 每个商品SKU保留首次出现的记录。
    """
    seen: set[str] = set()
    result: list[ProductSkuRecord] = []
    for record in records:
        if record.product_sku in seen:
            continue
        seen.add(record.product_sku)
        result.append(record)
    return result


def unique_bundle_records(records: list[BundleSkuRecord]) -> list[BundleSkuRecord]:
    """按组合SKU去重记录。

    Args:
        records: 组合SKU记录列表。

    Returns:
        list[BundleSkuRecord]: 每个组合SKU保留首次出现的记录。
    """
    seen: set[str] = set()
    result: list[BundleSkuRecord] = []
    for record in records:
        if record.bundle_sku in seen:
            continue
        seen.add(record.bundle_sku)
        result.append(record)
    return result


class RowProcessResult:
    """单行处理的内部结果容器。"""

    def __init__(
        self,
        *,
        product_records: list[ProductSkuRecord],
        bundle_record: BundleSkuRecord | None,
        sales_unit_result: SalesUnitResult,
        row_log: RowLog,
        created_sales_unit: bool,
        created_mapping: bool,
        affected_mapping_target_skus: tuple[str, ...] = (),
    ) -> None:
        """初始化单行处理结果。

        Args:
            product_records: 本行涉及的商品SKU记录。
            bundle_record: 本行涉及的组合SKU记录；单商品销售单元为空。
            sales_unit_result: 本行生成的销售单元结果。
            row_log: 本行处理日志。
            created_sales_unit: 是否新建销售单元。
            created_mapping: 是否新建或更新平台SKU映射。
            affected_mapping_target_skus: 本行需要重新计算平台配对的目标SKU集合。

        Returns:
            None: 属性写入当前对象。
        """
        self.product_records = product_records
        self.bundle_record = bundle_record
        self.sales_unit_result = sales_unit_result
        self.row_log = row_log
        self.created_sales_unit = created_sales_unit
        self.created_mapping = created_mapping
        self.affected_mapping_target_skus = affected_mapping_target_skus


def process_one_row(
    db: ProductSkuDatabase,
    process_batch_id: str,
    input_row: PlatformListingInputRow,
    *,
    allow_mapping_rebind: bool = False,
) -> RowProcessResult:
    """校验并处理单行平台SKU补充输入。

    Args:
        db: 商品SKU数据库仓储。
        process_batch_id: 当前处理批次ID。
        input_row: 已解析的Excel输入行。
        allow_mapping_rebind: 是否允许平台SKU从旧目标改绑到本行新目标。

    Returns:
        RowProcessResult: 本行涉及的商品SKU、组合SKU、销售单元、日志和创建标记。

    Raises:
        ValueError: 必填字段、类目代号、货源链接或规格不合法时抛出。
    """
    validate_required_row_fields(input_row)
    category_code = db.get_category_code(input_row.first_level_category)
    if not category_code:
        raise ValueError("一级类目无法匹配类目代号")

    parsed_items, parsed_details = parse_source_groups(input_row.source_groups)
    decision = decide_bundle(parsed_items)
    total_purchase_price_rmb = sum(item.group_purchase_price_rmb for item in dedupe_group_totals(parsed_items))
    total_weight_g = sum(item.group_weight_g for item in dedupe_group_totals(parsed_items))

    with db.transaction() as conn:
        product_records: list[ProductSkuRecord] = []
        product_items: list[tuple[str, int]] = []
        sales_unit_note = input_row.development_note

        if decision.sales_unit_type == SALES_UNIT_TYPE_FORCED_PRODUCT_SKU:
            package_details = package_details_from_items(parsed_items, parsed_details)
            package_fingerprint = package_fingerprint_from_details(package_details)
            product_name = build_forced_package_name(tuple(parsed_details))
            note = forced_package_note(input_row.development_note, package_details)
            sales_unit_note = note
            existing = db.find_forced_package_product_sku(conn, package_fingerprint)
            if existing:
                existing = db.update_product_sku_latest_fields(
                    conn,
                    product_sku=str(existing["product_sku"]),
                    logistics_attribute=input_row.logistics_attribute,
                    reference_purchase_price_rmb=total_purchase_price_rmb,
                    reference_weight_g=total_weight_g,
                    chinese_customs_name=input_row.chinese_customs_name,
                    note=note,
                    length_cm=input_row.length_cm,
                    width_cm=input_row.width_cm,
                    height_cm=input_row.height_cm,
                    is_direct_sales_unit=True,
                )
                product_record = product_record_from_row(existing, None, product_name, created=False)
                product_record = replace(
                    product_record,
                    main_image_url=input_row.main_image_url,
                    chinese_customs_name=product_record.chinese_customs_name or input_row.chinese_customs_name,
                )
            else:
                product_record = db.create_forced_package_product_sku(
                    conn,
                    package_fingerprint=package_fingerprint,
                    package_details=package_details,
                    category_code=category_code,
                    first_level_category=input_row.first_level_category,
                    main_image_url=input_row.main_image_url,
                    chinese_customs_name=input_row.chinese_customs_name,
                    logistics_attribute=input_row.logistics_attribute,
                    product_name=product_name,
                    total_purchase_price_rmb=total_purchase_price_rmb,
                    total_weight_g=total_weight_g,
                    note=note,
                    length_cm=input_row.length_cm,
                    width_cm=input_row.width_cm,
                    height_cm=input_row.height_cm,
                )
            product_records.append(product_record)
            product_items.append((product_record.product_sku, 1))
        else:
            for item, detail in zip(parsed_items, parsed_details, strict=True):
                product_name = build_product_name(detail.display_spec_params, detail.quantity)
                existing = db.find_product_sku_by_source(conn, item.source_url, item.spec, item.quantity)
                if existing:
                    existing = db.update_product_sku_latest_fields(
                        conn,
                        product_sku=str(existing["product_sku"]),
                        logistics_attribute=input_row.logistics_attribute,
                        reference_purchase_price_rmb=item.reference_purchase_price_rmb,
                        reference_weight_g=item.reference_weight_g,
                        chinese_customs_name=input_row.chinese_customs_name,
                        note=item.source_note,
                        length_cm=input_row.length_cm,
                        width_cm=input_row.width_cm,
                        height_cm=input_row.height_cm,
                        is_direct_sales_unit=not decision.needs_bundle,
                    )
                    product_record = product_record_from_row(existing, item, product_name, created=False)
                    product_record = replace(
                        product_record,
                        main_image_url=input_row.main_image_url,
                        chinese_customs_name=product_record.chinese_customs_name or input_row.chinese_customs_name,
                    )
                else:
                    product_record = db.create_product_sku(
                        conn,
                        item=item,
                        category_code=category_code,
                        first_level_category=input_row.first_level_category,
                        main_image_url=input_row.main_image_url,
                        chinese_customs_name=input_row.chinese_customs_name,
                        logistics_attribute=input_row.logistics_attribute,
                        product_name=product_name,
                        length_cm=input_row.length_cm if not decision.needs_bundle else None,
                        width_cm=input_row.width_cm if not decision.needs_bundle else None,
                        height_cm=input_row.height_cm if not decision.needs_bundle else None,
                        is_direct_sales_unit=not decision.needs_bundle,
                    )
                product_records.append(product_record)
                product_items.append((product_record.product_sku, 1))

        bundle_record: BundleSkuRecord | None = None
        if decision.needs_bundle:
            bundle_source_urls = unique_ordered_source_urls(record.source_url for record in product_records)
            fingerprint = bundle_fingerprint(tuple(product_items))
            existing_bundle = db.find_bundle_by_fingerprint(conn, fingerprint)
            if existing_bundle:
                existing_bundle = db.update_bundle_sku_latest_fields(
                    conn,
                    bundle_sku=str(existing_bundle["bundle_sku"]),
                    logistics_attribute=input_row.logistics_attribute,
                    reference_total_purchase_price_rmb=total_purchase_price_rmb,
                    reference_total_weight_g=total_weight_g,
                    chinese_customs_name=input_row.chinese_customs_name,
                    note=input_row.development_note,
                    length_cm=input_row.length_cm,
                    width_cm=input_row.width_cm,
                    height_cm=input_row.height_cm,
                )
                bundle_record = bundle_record_from_row(
                    existing_bundle,
                    db.list_bundle_items(conn, str(existing_bundle["bundle_sku"])),
                    created=False,
                    source_urls=db.list_bundle_source_urls(conn, str(existing_bundle["bundle_sku"])),
                )
            else:
                bundle_record = db.create_bundle_sku(
                    conn,
                    bundle_name=build_bundle_name(tuple(parsed_details)),
                    items=tuple(product_items),
                    main_image_url=input_row.main_image_url,
                    chinese_customs_name=input_row.chinese_customs_name,
                    total_purchase_price_rmb=total_purchase_price_rmb,
                    total_weight_g=total_weight_g,
                    logistics_attribute=input_row.logistics_attribute,
                    note=input_row.development_note,
                    source_urls=bundle_source_urls,
                    length_cm=input_row.length_cm,
                    width_cm=input_row.width_cm,
                    height_cm=input_row.height_cm,
                )
            bundle_record = replace(
                bundle_record,
                length_cm=input_row.length_cm,
                width_cm=input_row.width_cm,
                height_cm=input_row.height_cm,
            )
            mapping_target_type = MAPPING_TARGET_BUNDLE_SKU
            mapping_target_sku = bundle_record.bundle_sku
            branch_name = "bundle_sku"
        else:
            mapping_target_type = MAPPING_TARGET_PRODUCT_SKU
            mapping_target_sku = product_records[0].product_sku
            branch_name = "forced_product_sku" if decision.sales_unit_type == SALES_UNIT_TYPE_FORCED_PRODUCT_SKU else "product_sku"

        sales_unit_id, created_sales_unit = db.create_sales_unit(
            conn,
            platform_sku=input_row.platform_sku,
            shop_name=input_row.shop_name,
            sales_unit_type=decision.sales_unit_type,
            mapping_target_type=mapping_target_type,
            mapping_target_sku=mapping_target_sku,
            main_image_url=input_row.main_image_url,
            total_purchase_price_rmb=total_purchase_price_rmb,
            total_weight_g=total_weight_g,
            length_cm=input_row.length_cm,
            width_cm=input_row.width_cm,
            height_cm=input_row.height_cm,
            logistics_attribute=input_row.logistics_attribute,
            chinese_customs_name=input_row.chinese_customs_name,
            first_level_category=input_row.first_level_category,
            development_note=sales_unit_note,
            process_batch_id=process_batch_id,
        )
        affected_mapping_target_skus = {mapping_target_sku}
        existing_mapping = db.find_platform_mapping(conn, input_row.platform_sku)
        if existing_mapping:
            existing_target = str(existing_mapping["mapping_target_sku"])
            existing_type = str(existing_mapping["mapping_target_type"])
            if existing_type != mapping_target_type or existing_target != mapping_target_sku:
                affected_mapping_target_skus.add(existing_target)

        created_mapping = db.upsert_platform_mapping(
            conn,
            platform_sku=input_row.platform_sku,
            shop_name=input_row.shop_name,
            sales_unit_id=sales_unit_id,
            mapping_target_type=mapping_target_type,
            mapping_target_sku=mapping_target_sku,
            note=sales_unit_note,
            allow_rebind=allow_mapping_rebind,
        )
        db.insert_mapping_snapshot(
            conn,
            process_batch_id=process_batch_id,
            platform_sku=input_row.platform_sku,
            shop_name=input_row.shop_name,
            mapping_target_type=mapping_target_type,
            mapping_target_sku=mapping_target_sku,
            sales_unit_id=sales_unit_id,
        )

    sales_unit_result = SalesUnitResult(
        sales_unit_id=sales_unit_id,
        platform_sku=input_row.platform_sku,
        shop_name=input_row.shop_name,
        sales_unit_type=decision.sales_unit_type,
        mapping_target_type=mapping_target_type,
        mapping_target_sku=mapping_target_sku,
        product_skus=tuple(record.product_sku for record in product_records),
        bundle_sku=bundle_record.bundle_sku if bundle_record else None,
    )
    row_log = RowLog(
        row_no=input_row.row_no,
        business_key=input_row.platform_sku,
        sales_unit_type=decision.sales_unit_type,
        mapping_target_type=mapping_target_type,
        mapping_target_sku=mapping_target_sku,
        product_skus=sales_unit_result.product_skus,
        bundle_sku=sales_unit_result.bundle_sku,
        branch_name=branch_name,
        result="success",
        message="更新模式处理成功" if allow_mapping_rebind else "处理成功",
    )
    return RowProcessResult(
        product_records=product_records,
        bundle_record=bundle_record,
        sales_unit_result=sales_unit_result,
        row_log=row_log,
        created_sales_unit=created_sales_unit,
        created_mapping=created_mapping,
        affected_mapping_target_skus=tuple(sorted(affected_mapping_target_skus)),
    )


def process_one_row_dry_run(
    db: ProductSkuDatabase,
    conn: Any,
    context: DryRunContext,
    process_batch_id: str,
    input_row: PlatformListingInputRow,
    *,
    allow_mapping_rebind: bool = False,
) -> RowProcessResult:
    """试运行处理单行输入，不写入数据库。

    Args:
        db: 商品SKU数据库仓储。
        conn: 当前只读数据库连接。
        context: 试运行上下文。
        process_batch_id: 当前试运行批次ID。
        input_row: 已解析的Excel输入行。
        allow_mapping_rebind: 是否允许平台SKU从旧目标改绑到本行新目标。

    Returns:
        RowProcessResult: 本行预期商品SKU、组合SKU、销售单元、日志和创建标记。

    Raises:
        ValueError: 必填字段、类目、货源、规格或映射冲突不合法时抛出。
    """
    validate_required_row_fields(input_row)
    category_code = context.get_category_code(db, conn, input_row.first_level_category)
    if not category_code:
        raise ValueError("一级类目无法匹配类目代号")

    parsed_items, parsed_details = parse_source_groups(input_row.source_groups)
    decision = decide_bundle(parsed_items)
    total_purchase_price_rmb = sum(item.group_purchase_price_rmb for item in dedupe_group_totals(parsed_items))
    total_weight_g = sum(item.group_weight_g for item in dedupe_group_totals(parsed_items))

    product_records: list[ProductSkuRecord] = []
    product_items: list[tuple[str, int]] = []

    if decision.sales_unit_type == SALES_UNIT_TYPE_FORCED_PRODUCT_SKU:
        package_details = package_details_from_items(parsed_items, parsed_details)
        package_fingerprint = package_fingerprint_from_details(package_details)
        product_name = build_forced_package_name(tuple(parsed_details))
        note = forced_package_note(input_row.development_note, package_details)
        product_record = context.forced_packages_by_fingerprint.get(package_fingerprint)
        if product_record is not None:
            product_record = replace(
                product_record,
                length_cm=input_row.length_cm,
                width_cm=input_row.width_cm,
                height_cm=input_row.height_cm,
                is_direct_sales_unit=True,
                note=note,
                created=False,
            )
        else:
            existing = db.find_forced_package_product_sku(conn, package_fingerprint)
            if existing:
                product_record = product_record_from_row(existing, None, product_name, created=False)
                product_record = replace(
                    product_record,
                    main_image_url=input_row.main_image_url,
                    chinese_customs_name=product_record.chinese_customs_name or input_row.chinese_customs_name,
                    logistics_attribute=input_row.logistics_attribute,
                    length_cm=input_row.length_cm,
                    width_cm=input_row.width_cm,
                    height_cm=input_row.height_cm,
                    is_direct_sales_unit=True,
                    note=note,
                )
            else:
                primary_detail = package_details[0]
                product_record = ProductSkuRecord(
                    product_sku=context.next_product_sku_code(category_code),
                    source_url=str(primary_detail["source_url"]),
                    source_platform=str(primary_detail["source_platform"]),
                    spec=str(primary_detail["spec"]),
                    quantity=1,
                    product_sku_type=PRODUCT_SKU_TYPE_FORCED_PACKAGE,
                    package_fingerprint=package_fingerprint,
                    package_details=package_details,
                    product_name=product_name,
                    main_image_url=input_row.main_image_url,
                    first_level_category=input_row.first_level_category,
                    category_code=category_code,
                    reference_purchase_price_rmb=total_purchase_price_rmb,
                    reference_weight_g=total_weight_g,
                    chinese_customs_name=input_row.chinese_customs_name,
                    logistics_attribute=input_row.logistics_attribute,
                    note=note,
                    length_cm=input_row.length_cm,
                    width_cm=input_row.width_cm,
                    height_cm=input_row.height_cm,
                    is_direct_sales_unit=True,
                    created=True,
                )
            context.forced_packages_by_fingerprint[package_fingerprint] = product_record

        product_records.append(product_record)
        product_items.append((product_record.product_sku, 1))
    else:
        for item, detail in zip(parsed_items, parsed_details, strict=True):
            product_name = build_product_name(detail.display_spec_params, detail.quantity)
            product_key = (item.source_url, item.spec, item.quantity)
            product_record = context.products_by_source.get(product_key)
            if product_record is not None:
                product_record = replace(
                    product_record,
                    length_cm=input_row.length_cm if not decision.needs_bundle else product_record.length_cm,
                    width_cm=input_row.width_cm if not decision.needs_bundle else product_record.width_cm,
                    height_cm=input_row.height_cm if not decision.needs_bundle else product_record.height_cm,
                    is_direct_sales_unit=product_record.is_direct_sales_unit or not decision.needs_bundle,
                    created=False,
                )
            else:
                existing = db.find_product_sku_by_source(conn, item.source_url, item.spec, item.quantity)
                if existing:
                    product_record = product_record_from_row(existing, item, product_name, created=False)
                    product_record = replace(
                        product_record,
                        main_image_url=input_row.main_image_url,
                        chinese_customs_name=product_record.chinese_customs_name or input_row.chinese_customs_name,
                        logistics_attribute=input_row.logistics_attribute,
                        length_cm=input_row.length_cm if not decision.needs_bundle else product_record.length_cm,
                        width_cm=input_row.width_cm if not decision.needs_bundle else product_record.width_cm,
                        height_cm=input_row.height_cm if not decision.needs_bundle else product_record.height_cm,
                        is_direct_sales_unit=product_record.is_direct_sales_unit or not decision.needs_bundle,
                    )
                else:
                    product_record = ProductSkuRecord(
                        product_sku=context.next_product_sku_code(category_code),
                        source_url=item.source_url,
                        source_platform=item.source_platform,
                        spec=item.spec,
                        quantity=item.quantity,
                        product_sku_type=PRODUCT_SKU_TYPE_NORMAL,
                        package_fingerprint=None,
                        package_details=(),
                        product_name=product_name,
                        main_image_url=input_row.main_image_url,
                        first_level_category=input_row.first_level_category,
                        category_code=category_code,
                        reference_purchase_price_rmb=item.reference_purchase_price_rmb,
                        reference_weight_g=item.reference_weight_g,
                        chinese_customs_name=input_row.chinese_customs_name,
                        logistics_attribute=input_row.logistics_attribute,
                        note=item.source_note,
                        length_cm=input_row.length_cm if not decision.needs_bundle else None,
                        width_cm=input_row.width_cm if not decision.needs_bundle else None,
                        height_cm=input_row.height_cm if not decision.needs_bundle else None,
                        is_direct_sales_unit=not decision.needs_bundle,
                        created=True,
                    )
                context.products_by_source[product_key] = product_record

            product_records.append(product_record)
            product_items.append((product_record.product_sku, 1))

    bundle_record: BundleSkuRecord | None = None
    if decision.needs_bundle:
        bundle_source_urls = unique_ordered_source_urls(record.source_url for record in product_records)
        fingerprint = bundle_fingerprint(tuple(product_items))
        bundle_record = context.bundles_by_fingerprint.get(fingerprint)
        if bundle_record is not None:
            bundle_record = replace(bundle_record, created=False)
        else:
            existing_bundle = db.find_bundle_by_fingerprint(conn, fingerprint)
            if existing_bundle:
                bundle_record = bundle_record_from_row(
                    existing_bundle,
                    db.list_bundle_items(conn, str(existing_bundle["bundle_sku"])),
                    created=False,
                    source_urls=db.list_bundle_source_urls(conn, str(existing_bundle["bundle_sku"])),
                )
                bundle_record = replace(bundle_record, logistics_attribute=input_row.logistics_attribute)
            else:
                distinct_count = len({product_sku for product_sku, _ in product_items})
                total_count = sum(quantity for _, quantity in product_items)
                bundle_record = BundleSkuRecord(
                    bundle_sku=context.next_bundle_sku_code(distinct_count, total_count),
                    bundle_name=build_bundle_name(tuple(parsed_details)),
                    total_product_count=total_count,
                    distinct_product_sku_count=distinct_count,
                    items=tuple(product_items),
                    main_image_url=input_row.main_image_url,
                    chinese_customs_name=input_row.chinese_customs_name,
                    reference_total_purchase_price_rmb=total_purchase_price_rmb,
                    reference_total_weight_g=total_weight_g,
                    logistics_attribute=input_row.logistics_attribute,
                    note=input_row.development_note,
                    source_urls=bundle_source_urls,
                    created=True,
                )
            context.bundles_by_fingerprint[fingerprint] = bundle_record

        bundle_record = replace(
            bundle_record,
            length_cm=input_row.length_cm,
            width_cm=input_row.width_cm,
            height_cm=input_row.height_cm,
        )
        mapping_target_type = MAPPING_TARGET_BUNDLE_SKU
        mapping_target_sku = bundle_record.bundle_sku
        branch_name = "bundle_sku_dry_run"
    else:
        mapping_target_type = MAPPING_TARGET_PRODUCT_SKU
        mapping_target_sku = product_records[0].product_sku
        branch_name = (
            "forced_product_sku_dry_run"
            if decision.sales_unit_type == SALES_UNIT_TYPE_FORCED_PRODUCT_SKU
            else "product_sku_dry_run"
        )

    existing_sales_unit = db.find_sales_unit(
        conn,
        platform_sku=input_row.platform_sku,
        mapping_target_type=mapping_target_type,
        mapping_target_sku=mapping_target_sku,
    )
    created_sales_unit = False if existing_sales_unit else context.remember_sales_unit(
        input_row.platform_sku,
        mapping_target_type,
        mapping_target_sku,
    )

    existing_mapping = db.find_platform_mapping(conn, input_row.platform_sku)
    affected_mapping_target_skus = {mapping_target_sku}
    if existing_mapping:
        existing_target = str(existing_mapping["mapping_target_sku"])
        existing_type = str(existing_mapping["mapping_target_type"])
        if existing_type != mapping_target_type or existing_target != mapping_target_sku:
            if not allow_mapping_rebind:
                raise ValueError("平台SKU已绑定不同映射目标")
            affected_mapping_target_skus.add(existing_target)
            context.remember_platform_rebind(
                input_row.platform_sku,
                existing_target,
                mapping_target_type,
                mapping_target_sku,
            )
            created_mapping = True
        else:
            created_mapping = False
    else:
        created_mapping = context.remember_platform_mapping(
            input_row.platform_sku,
            mapping_target_type,
            mapping_target_sku,
        )

    sales_unit_result = SalesUnitResult(
        sales_unit_id=int(existing_sales_unit["id"]) if existing_sales_unit else None,
        platform_sku=input_row.platform_sku,
        shop_name=input_row.shop_name,
        sales_unit_type=decision.sales_unit_type,
        mapping_target_type=mapping_target_type,
        mapping_target_sku=mapping_target_sku,
        product_skus=tuple(record.product_sku for record in product_records),
        bundle_sku=bundle_record.bundle_sku if bundle_record else None,
    )
    row_log = RowLog(
        row_no=input_row.row_no,
        business_key=input_row.platform_sku,
        sales_unit_type=decision.sales_unit_type,
        mapping_target_type=mapping_target_type,
        mapping_target_sku=mapping_target_sku,
        product_skus=sales_unit_result.product_skus,
        bundle_sku=sales_unit_result.bundle_sku,
        branch_name=branch_name,
        result="success",
        message="更新模式试运行处理成功，未写入数据库" if allow_mapping_rebind else "试运行处理成功，未写入数据库",
    )
    return RowProcessResult(
        product_records=product_records,
        bundle_record=bundle_record,
        sales_unit_result=sales_unit_result,
        row_log=row_log,
        created_sales_unit=created_sales_unit,
        created_mapping=created_mapping,
        affected_mapping_target_skus=tuple(sorted(affected_mapping_target_skus)),
    )


def validate_required_row_fields(input_row: PlatformListingInputRow) -> None:
    """校验平台SKU补充第一版必填字段。

    Args:
        input_row: 已解析的Excel输入行。

    Returns:
        None: 校验通过不返回值。

    Raises:
        ValueError: 平台SKU、一级类目或货源组缺失时抛出。
    """
    if not input_row.platform_sku:
        raise ValueError("平台SKU不能为空")
    if not input_row.first_level_category:
        raise ValueError("一级类目不能为空")
    if not input_row.logistics_attribute:
        raise ValueError("属性不能为空")
    if not input_row.source_groups:
        raise ValueError("至少需要一组货源链接和规格")
    dianxiaomi_dangerous_transport_code(input_row.logistics_attribute)


def parse_source_groups(
    source_groups: tuple[SourceGroupInput, ...],
) -> tuple[list[ParsedSourceItem], list[ParsedSpecDetail]]:
    """清洗货源链接、解析规格并计算参考价格重量。

    Args:
        source_groups: 输入行中的货源组。

    Returns:
        tuple: 依次为展开后的货源商品明细和规格解析明细。

    Raises:
        ValueError: 货源组必填项、链接、规格或数量不合法时抛出。
    """
    parsed_items: list[ParsedSourceItem] = []
    parsed_details: list[ParsedSpecDetail] = []
    for group in source_groups:
        validate_source_group(group)
        cleaned = clean_source_url(group.source_url)
        spec_details = parse_spec(group.spec)
        group_product_count = sum(detail.quantity for detail in spec_details)
        purchase_price_rmb = group.purchase_price_rmb or Decimal("0")
        group_weight_g = kg_to_g(group.weight_kg or Decimal("0"))
        reference_purchase_price_rmb = calculate_reference_value(
            purchase_price_rmb,
            group_product_count,
            f"货源{group.group_no}采购价",
        )
        reference_weight_g = calculate_reference_value(
            group_weight_g,
            group_product_count,
            f"货源{group.group_no}重量",
        )
        for detail in spec_details:
            parsed_items.append(
                ParsedSourceItem(
                    source_group_no=group.group_no,
                    source_url=cleaned.source_url,
                    source_platform=cleaned.source_platform,
                    raw_spec=detail.raw_spec,
                    spec=detail.spec,
                    display_spec_params=detail.display_spec_params,
                    quantity=detail.quantity,
                    source_note=group.note,
                    group_purchase_price_rmb=purchase_price_rmb,
                    group_weight_g=group_weight_g,
                    reference_purchase_price_rmb=reference_purchase_price_rmb,
                    reference_weight_g=reference_weight_g,
                )
            )
            parsed_details.append(detail)
    return parsed_items, parsed_details


def validate_source_group(group: SourceGroupInput) -> None:
    """校验单个货源组。

    Args:
        group: 单个货源组输入。

    Returns:
        None: 校验通过不返回值。

    Raises:
        ValueError: 链接、规格、采购价或重量缺失或非法时抛出。
    """
    if not group.source_url:
        raise ValueError(f"货源链接{group.group_no}不能为空")
    if not group.spec:
        raise ValueError(f"货源{group.group_no}规格不能为空")
    if group.purchase_price_rmb is None:
        raise ValueError(f"货源{group.group_no}采购价不能为空")
    if group.purchase_price_rmb < 0:
        raise ValueError(f"货源{group.group_no}采购价不能小于 0")
    if group.weight_kg is None:
        raise ValueError(f"货源{group.group_no}重量/kg不能为空")
    if group.weight_kg < 0:
        raise ValueError(f"货源{group.group_no}重量/kg不能小于 0")


def dedupe_group_totals(items: list[ParsedSourceItem]) -> list[ParsedSourceItem]:
    """按货源组去重以计算销售单元总值。

    Args:
        items: 展开后的货源商品明细。

    Returns:
        list[ParsedSourceItem]: 每个货源组保留一条记录，用于避免组总价和组总重重复累加。
    """
    seen: set[int] = set()
    result: list[ParsedSourceItem] = []
    for item in items:
        if item.source_group_no in seen:
            continue
        seen.add(item.source_group_no)
        result.append(item)
    return result


def unique_ordered_source_urls(source_urls: Iterable[str]) -> tuple[str, ...]:
    """按出现顺序去重货源链接。

    Args:
        source_urls: 原始货源链接序列。

    Returns:
        tuple[str, ...]: 去重后的非空货源链接。
    """
    seen: set[str] = set()
    result: list[str] = []
    for source_url in source_urls:
        if not source_url or source_url in seen:
            continue
        seen.add(source_url)
        result.append(source_url)
    return tuple(result)


def package_details_from_items(
    items: list[ParsedSourceItem],
    details: list[ParsedSpecDetail],
) -> tuple[dict[str, Any], ...]:
    """构建强制合包商品SKU采购辨识明细。

    Args:
        items: 展开后的货源商品明细。
        details: 规格解析明细。

    Returns:
        tuple[dict[str, Any], ...]: 可写入JSON的结构化明细。
    """
    package_details: list[dict[str, Any]] = []
    for item, detail in zip(items, details, strict=True):
        package_details.append(
            {
                "source_group_no": item.source_group_no,
                "source_platform": item.source_platform,
                "source_url": item.source_url,
                "raw_spec": item.raw_spec,
                "spec": item.spec,
                "display_spec_params": list(detail.display_spec_params),
                "quantity": item.quantity,
                "source_note": item.source_note,
            }
        )
    return tuple(package_details)


def package_fingerprint_from_details(package_details: tuple[dict[str, Any], ...]) -> str:
    """生成强制合包商品SKU结构化明细指纹。

    Args:
        package_details: 强制合包采购辨识明细。

    Returns:
        str: 排序后稳定序列化得到的SHA256指纹。
    """
    identity_tuples = sorted(
        (
            str(detail["source_url"]),
            str(detail["spec"]),
            int(detail["quantity"]),
        )
        for detail in package_details
    )
    identities = [
        {"source_url": source_url, "spec": spec, "quantity": quantity}
        for source_url, spec, quantity in identity_tuples
    ]
    text = json.dumps(identities, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def forced_package_note(development_note: str, package_details: tuple[dict[str, Any], ...]) -> str:
    """生成强制合包商品SKU采购辨识备注。

    Args:
        development_note: 输入表开发备注。
        package_details: 强制合包采购辨识明细。

    Returns:
        str: 合并原备注和强制合并标记后的备注文本。
    """
    forced_note = "强制合并"
    if not development_note:
        return forced_note
    return f"{development_note}\n{forced_note}"
