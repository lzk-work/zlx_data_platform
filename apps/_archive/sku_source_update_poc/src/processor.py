"""平台 SKU 货源预校正核心处理。"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from apps.sku_mapping_poc.src.normalizer import build_source_key
from apps.sku_mapping_poc.src.sku_generator import generate_product_sku
from apps.sku_mapping_poc.src.validator import find_ambiguous_source_keys

from .models import (
    AppSettings,
    ExceptionRow,
    FirstCategoryCode,
    PlatformSkuMappingRow,
    ProcessLogRow,
    ProcessOutput,
    ProductSkuMaster,
    RunSummary,
    SourceUpdateInputRow,
)


def new_batch_id(settings: AppSettings) -> str:
    return datetime.now(ZoneInfo(settings.batch_timezone)).strftime("%Y%m%d_%H%M%S")


def process_source_update(
    *,
    settings: AppSettings,
    batch_id: str,
    input_rows: list[SourceUpdateInputRow],
    product_source_rows: list[ProductSkuMaster],
    first_category_code_rows: list[FirstCategoryCode],
) -> ProcessOutput:
    summary = RunSummary(batch_id=batch_id, input_rows=len(input_rows))
    source_key_to_skus = _build_source_index(product_source_rows)
    ambiguous_source_keys = find_ambiguous_source_keys(product_source_rows)
    product_skus = {row.product_sku for row in product_source_rows if row.product_sku}
    generated_skus: set[str] = set()
    category_code_index = _build_category_code_index(first_category_code_rows)
    seen_platform_skus: set[str] = set()

    new_products: list[ProductSkuMaster] = []
    mappings: list[PlatformSkuMappingRow] = []
    exceptions: list[ExceptionRow] = []
    logs: list[ProcessLogRow] = []

    for row in input_rows:
        required_errors = _validate_required(row, settings.run_mode)
        if settings.run_mode == "platform" and row.platform_sku in seen_platform_skus:
            required_errors.append(("duplicate_platform_sku", "同一输入表中平台SKU重复", "删除重复平台SKU后重跑"))
        if required_errors:
            for code, message, suggestion in required_errors:
                exceptions.append(_exception(batch_id, row, code, message, suggestion))
                logs.append(_log(batch_id, row, "", "", "异常", message))
            continue
        if settings.run_mode == "platform":
            seen_platform_skus.add(row.platform_sku)

        source_key = build_source_key(row.corrected_source_url, row.corrected_spec)
        if source_key in ambiguous_source_keys:
            message = "校正后货源信息匹配到多个商品SKU"
            exceptions.append(_exception(batch_id, row, "ambiguous_source_key", message, "修正product_source中的重复货源信息后重跑"))
            logs.append(_log(batch_id, row, "", "ambiguous", "异常", message))
            continue

        matches = sorted(set(source_key_to_skus.get(source_key, [])))
        if len(matches) == 1:
            correct_sku = matches[0]
            match_result = "matched_existing"
            summary.matched_existing_skus += 1
            if settings.run_mode == "source-only":
                summary.source_only_skipped += 1
                summary.processed_rows += 1
                logs.append(_log(batch_id, row, correct_sku, "source_only_existing_skipped", "成功", "货源已存在，跳过新增"))
                continue
        elif not matches:
            category_code = _resolve_category_code(row, category_code_index)
            if not category_code:
                message = "生成新商品SKU缺少一级类目编码"
                exceptions.append(_exception(batch_id, row, "missing_first_category_code", message, "补充类目代号或维护first_category_code后重跑"))
                logs.append(_log(batch_id, row, "", "missing_category_code", "异常", message))
                continue
            generated = generate_product_sku(product_skus, generated_skus, category_code=category_code, sku_date=_sku_date(batch_id, settings))
            correct_sku = generated.product_sku
            generated_skus.add(correct_sku)
            product_skus.add(correct_sku)
            product = _product_from_input(correct_sku, row, category_code)
            new_products.append(product)
            source_key_to_skus[source_key].append(correct_sku)
            summary.generated_product_skus += 1
            match_result = "generated_new"
        else:
            message = "校正后货源信息匹配到多个商品SKU"
            exceptions.append(_exception(batch_id, row, "ambiguous_source_key", message, "修正product_source中的重复货源信息后重跑"))
            logs.append(_log(batch_id, row, "", "ambiguous", "异常", message))
            continue

        if settings.run_mode == "platform":
            mappings.append(
                PlatformSkuMappingRow(
                    platform_sku=row.platform_sku,
                    initial_product_sku=row.initial_product_sku,
                    correct_product_sku=correct_sku,
                    corrected_source_url=row.corrected_source_url,
                    corrected_spec=row.corrected_spec,
                    match_result=match_result,
                    remark=row.remark,
                )
            )
        summary.processed_rows += 1
        logs.append(_log(batch_id, row, correct_sku, match_result, "成功", "处理成功"))

    summary.exceptions = len(exceptions)
    return ProcessOutput(
        new_product_source_rows=sorted(new_products, key=lambda item: item.product_sku),
        platform_mapping_rows=mappings,
        exception_rows=exceptions,
        log_rows=logs,
        summary=summary,
    )


def _validate_required(row: SourceUpdateInputRow, run_mode: str) -> list[tuple[str, str, str]]:
    checks = [
        ("corrected_source_url_missing", row.corrected_source_url, "校正后货源链接为空或清洗失败"),
        ("corrected_spec_missing", row.corrected_spec, "校正后规格为空"),
    ]
    if run_mode == "platform":
        checks.insert(0, ("platform_sku_missing", row.platform_sku, "平台SKU为空"))
    return [(code, message, "补充平台SKU货源预校正输入表中的必填字段") for code, value, message in checks if not value]


def _build_source_index(rows: list[ProductSkuMaster]) -> dict[tuple[str, str], list[str]]:
    index: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in rows:
        if row.source_url and row.spec and row.product_sku:
            index[build_source_key(row.source_url, row.spec)].append(row.product_sku)
    return index


def _build_category_code_index(rows: list[FirstCategoryCode]) -> dict[str, str]:
    index: dict[str, str] = {}
    for row in rows:
        if row.first_category and row.code:
            index[row.first_category] = row.code
        if row.first_category_chinese and row.code:
            index[row.first_category_chinese] = row.code
    return index


def _resolve_category_code(row: SourceUpdateInputRow, category_code_index: dict[str, str]) -> str:
    if row.category_code:
        return row.category_code
    if row.first_level_category:
        return category_code_index.get(row.first_level_category, "")
    return ""


def _sku_date(batch_id: str, settings: AppSettings) -> str:
    if len(batch_id) >= 8 and batch_id[:8].isdigit():
        return batch_id[2:8]
    return datetime.now(ZoneInfo(settings.batch_timezone)).strftime("%y%m%d")


def _product_from_input(product_sku: str, row: SourceUpdateInputRow, category_code: str) -> ProductSkuMaster:
    return ProductSkuMaster(
        product_sku=product_sku,
        source_url=row.corrected_source_url,
        spec=row.corrected_spec,
        length=row.length_cm,
        width=row.width_cm,
        height=row.height_cm,
        source_image_url=row.source_image_url,
        purchase_price=row.purchase_price,
        weight_g=row.weight_g,
        color=row.color,
        material=row.material,
        quantity=row.quantity,
        chinese_customs_name=row.chinese_customs_name,
        first_level_category=row.first_level_category,
        category_code=category_code,
        supplier=row.supplier,
        note=row.remark,
    )


def _exception(batch_id: str, row: SourceUpdateInputRow, exception_type: str, message: str, suggestion: str) -> ExceptionRow:
    return ExceptionRow(batch_id, row.row_number, row.platform_sku, row.initial_product_sku, row.corrected_source_url, row.corrected_spec, exception_type, message, suggestion, row.remark)


def _log(batch_id: str, row: SourceUpdateInputRow, correct_sku: str, match_result: str, process_result: str, message: str) -> ProcessLogRow:
    return ProcessLogRow(batch_id, row.row_number, row.platform_sku, row.initial_product_sku, correct_sku, row.corrected_source_url, row.corrected_spec, match_result, process_result, message, row.remark)
