"""SKU 映射核心业务处理。"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from .matcher import match_product_sku
from .models import (
    AppSettings,
    DailyFirstOrderRow,
    ErpRow,
    ExceptionRow,
    FirstCategoryCode,
    HistoricalOrderedPlatformSku,
    ProcessLogRow,
    ProcessOutput,
    ProductSkuMaster,
    RunSummary,
    SkuPlatformMapping,
    UploadedProductSku,
)
from .normalizer import build_source_key
from .sku_generator import generate_product_sku
from .validator import find_ambiguous_source_keys, find_duplicate_mapping_platform_skus, validate_daily_required


def new_batch_id(settings: AppSettings) -> str:
    """生成批次号。"""
    return datetime.now(ZoneInfo(settings.batch_timezone)).strftime("%Y%m%d_%H%M%S")


def process_sku_mapping(
    *,
    settings: AppSettings,
    batch_id: str,
    daily_rows: list[DailyFirstOrderRow],
    product_master_rows: list[ProductSkuMaster],
    uploaded_rows: list[UploadedProductSku],
    historical_rows: list[HistoricalOrderedPlatformSku],
    mapping_rows: list[SkuPlatformMapping],
    first_category_code_rows: list[FirstCategoryCode] | None = None,
) -> ProcessOutput:
    """执行 SKU 映射处理。"""
    run_time = _batch_time(settings)
    summary = RunSummary(batch_id=batch_id, input_rows=len(daily_rows))
    exceptions: list[ExceptionRow] = []
    logs: list[ProcessLogRow] = []

    uploaded_by_sku = {row.product_sku: row for row in uploaded_rows if row.product_sku}
    initial_uploaded_skus = set(uploaded_by_sku)
    historical_platform_skus = {row.platform_sku for row in historical_rows if row.platform_sku}
    ambiguous_source_keys = find_ambiguous_source_keys(product_master_rows)
    duplicate_mapping_platforms = find_duplicate_mapping_platform_skus(mapping_rows)
    category_code_by_first_category = _build_category_code_index(first_category_code_rows or [])

    product_by_sku = {row.product_sku: row for row in product_master_rows if row.product_sku}
    source_key_to_skus = _build_source_index(list(product_by_sku.values()))
    runtime_mapping = _build_runtime_mapping(mapping_rows)
    platform_to_product = _build_platform_to_product(mapping_rows)
    batch_generated_skus: set[str] = set()
    changed_product_skus: set[str] = set()

    for row in _deduplicate_daily_rows(daily_rows):
        if not row.platform_sku:
            message = "平台SKU为空"
            exceptions.append(_exception(batch_id, row, "platform_sku_missing", message, "补充每日出单平台SKU输入表中的平台SKU"))
            logs.append(_exception_log(batch_id, row, "platform_sku_missing", message))
            continue

        if row.platform_sku in duplicate_mapping_platforms:
            message = "映射表中同一平台SKU存在多个商品SKU"
            exceptions.append(_exception(batch_id, row, "duplicate_mapping_platform_sku", message, "修正商品SKU-平台SKU映射关系表后重跑"))
            logs.append(_exception_log(batch_id, row, "duplicate_mapping_platform_sku", message))
            continue

        if row.platform_sku in historical_platform_skus:
            summary.historical_skipped += 1
            continue

        required_errors = validate_daily_required(row)
        if required_errors:
            for code, message, suggestion in required_errors:
                exceptions.append(_exception(batch_id, row, code, message, suggestion))
                logs.append(_exception_log(batch_id, row, code, message))
            continue

        corrected_key = build_source_key(row.corrected_source_url, row.corrected_spec)
        if corrected_key in ambiguous_source_keys:
            message = "校正后货源信息匹配到多个商品SKU"
            exceptions.append(_exception(batch_id, row, "ambiguous_source_key", message, "修正product_source中的重复货源信息后重跑"))
            logs.append(_exception_log(batch_id, row, "ambiguous_source_key", message))
            continue

        initial_product = product_by_sku.get(row.initial_product_sku) if row.initial_product_sku else None
        match = match_product_sku(row, initial_product, source_key_to_skus)
        if match.match_type == "initial_consistent":
            correct_product_sku = row.initial_product_sku
            branch = _branch(row.initial_product_sku, correct_product_sku, initial_uploaded_skus, True, "matched")
        elif match.match_type == "source_key_matched" and match.correct_product_sku:
            correct_product_sku = match.correct_product_sku
            branch = _branch(row.initial_product_sku, correct_product_sku, initial_uploaded_skus, False, "matched")
        elif match.match_type == "source_key_missing":
            category_code = _resolve_category_code(row, category_code_by_first_category)
            if not category_code:
                message = "生成新商品SKU缺少一级类目编码"
                exceptions.append(_exception(batch_id, row, "missing_first_category_code", message, "补充一级类目或维护first_category_code类目编码表后重跑"))
                logs.append(_exception_log(batch_id, row, "missing_first_category_code", message))
                continue
            generated = generate_product_sku(
                set(product_by_sku) | set(uploaded_by_sku),
                batch_generated_skus,
                category_code=category_code,
                sku_date=_sku_date(batch_id, settings),
            )
            correct_product_sku = generated.product_sku
            product_by_sku[correct_product_sku] = _product_from_daily(correct_product_sku, row, category_code)
            source_key_to_skus[corrected_key].append(correct_product_sku)
            batch_generated_skus.add(correct_product_sku)
            summary.generated_product_skus += 1
            branch = _branch(row.initial_product_sku, correct_product_sku, initial_uploaded_skus, False, "generated")
        elif match.match_type == "ambiguous":
            message = "校正后货源信息匹配到多个商品SKU"
            exceptions.append(_exception(batch_id, row, "ambiguous_source_key", message, "修正product_source中的重复货源信息后重跑"))
            logs.append(_exception_log(batch_id, row, "ambiguous_source_key", message))
            continue
        else:
            message = match.message or "商品SKU匹配失败"
            exceptions.append(_exception(batch_id, row, match.match_type, message, "检查product_source和每日输入表后重跑"))
            logs.append(_exception_log(batch_id, row, match.match_type, message))
            continue

        old_product_sku = platform_to_product.get(row.platform_sku)
        if old_product_sku and old_product_sku != correct_product_sku:
            runtime_mapping[old_product_sku].discard(row.platform_sku)
            changed_product_skus.add(old_product_sku)

        runtime_mapping[correct_product_sku].add(row.platform_sku)
        platform_to_product[row.platform_sku] = correct_product_sku
        changed_product_skus.add(correct_product_sku)
        historical_platform_skus.add(row.platform_sku)
        historical_rows.append(HistoricalOrderedPlatformSku(row.platform_sku, row.order_no, row.platform_channel, row.shop_account, row.order_time, run_time, batch_id, row.remark))
        summary.first_order_processed += 1
        logs.append(_success_log(batch_id, row, correct_product_sku, match.source_consistent, branch, initial_uploaded_skus))

    erp_new_rows, erp_update_rows = _build_erp_rows(changed_product_skus, runtime_mapping, product_by_sku, initial_uploaded_skus)
    summary.erp_new_product_skus = len(erp_new_rows)
    summary.erp_update_product_skus = len(erp_update_rows)
    summary.exceptions = len(exceptions)

    latest_uploaded = _build_latest_uploaded(uploaded_by_sku, erp_new_rows, run_time)
    latest_mapping = _build_latest_mapping(runtime_mapping, mapping_rows, batch_id, run_time)

    return ProcessOutput(
        erp_new_rows=erp_new_rows,
        erp_update_rows=erp_update_rows,
        latest_product_sku_master=sorted(product_by_sku.values(), key=lambda item: item.product_sku),
        latest_uploaded_product_skus=latest_uploaded,
        latest_historical_ordered_platform_skus=sorted(historical_rows, key=lambda item: item.platform_sku),
        latest_sku_platform_mapping=latest_mapping,
        exception_rows=exceptions,
        log_rows=logs,
        summary=summary,
    )


def _deduplicate_daily_rows(rows: list[DailyFirstOrderRow]) -> list[DailyFirstOrderRow]:
    """今日订单数据按平台 SKU 去重，保留最早出单记录。"""
    selected: dict[str, DailyFirstOrderRow] = {}
    for row in sorted(rows, key=_daily_sort_key):
        if row.platform_sku and row.platform_sku not in selected:
            selected[row.platform_sku] = row
        elif not row.platform_sku:
            selected[f"__row_{row.row_number}"] = row
    return list(selected.values())


def _daily_sort_key(row: DailyFirstOrderRow) -> tuple[str, int]:
    return row.order_time, row.row_number

def _batch_time(settings: AppSettings) -> str:
    return datetime.now(ZoneInfo(settings.batch_timezone)).strftime("%Y-%m-%d %H:%M:%S")


def _build_category_code_index(rows: list[FirstCategoryCode]) -> dict[str, str]:
    index: dict[str, str] = {}
    for row in rows:
        if row.first_category and row.code:
            index[row.first_category] = row.code
        if row.first_category_chinese and row.code:
            index[row.first_category_chinese] = row.code
    return index


def _resolve_category_code(row: DailyFirstOrderRow, category_code_by_first_category: dict[str, str]) -> str:
    if row.category_code:
        return row.category_code
    if row.first_level_category:
        return category_code_by_first_category.get(row.first_level_category, "")
    return ""


def _sku_date(batch_id: str, settings: AppSettings) -> str:
    if len(batch_id) >= 8 and batch_id[:8].isdigit():
        return batch_id[2:8]
    return datetime.now(ZoneInfo(settings.batch_timezone)).strftime("%y%m%d")


def _product_from_daily(product_sku: str, row: DailyFirstOrderRow, category_code: str | None = None) -> ProductSkuMaster:
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
        category_code=category_code or row.category_code,
        temp_sku=row.temp_sku,
        supplier=row.supplier,
        note=row.remark,
    )


def _build_source_index(rows: list[ProductSkuMaster]) -> dict[tuple[str, str], list[str]]:
    index: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in rows:
        if row.source_url and row.spec and row.product_sku:
            index[build_source_key(row.source_url, row.spec)].append(row.product_sku)
    return index


def _build_runtime_mapping(rows: list[SkuPlatformMapping]) -> dict[str, set[str]]:
    mapping: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if row.product_sku and row.platform_sku:
            mapping[row.product_sku].add(row.platform_sku)
    return mapping


def _build_platform_to_product(rows: list[SkuPlatformMapping]) -> dict[str, str]:
    return {row.platform_sku: row.product_sku for row in rows if row.platform_sku and row.product_sku}


def _branch(
    initial_product_sku: str,
    correct_product_sku: str,
    initial_uploaded_skus: set[str],
    source_consistent: bool,
    match_result: str,
) -> str:
    initial_status = "初始已上传" if initial_product_sku in initial_uploaded_skus else "初始未上传"
    source_status = "货源无误" if source_consistent else "货源有误"
    correct_status = "正确SKU已上传" if correct_product_sku in initial_uploaded_skus else "正确SKU未上传"
    return f"{initial_status}/{source_status}/{match_result}/{correct_status}"


def _build_erp_rows(
    changed_product_skus: set[str],
    runtime_mapping: dict[str, set[str]],
    product_by_sku: dict[str, ProductSkuMaster],
    initial_uploaded_skus: set[str],
) -> tuple[list[ErpRow], list[ErpRow]]:
    new_rows: list[ErpRow] = []
    update_rows: list[ErpRow] = []
    for product_sku in sorted(changed_product_skus):
        platform_skus = sorted(runtime_mapping.get(product_sku, set()))
        product = product_by_sku.get(product_sku)
        if not product:
            continue
        if not platform_skus and product_sku not in initial_uploaded_skus:
            continue
        row = ErpRow(
            product_sku=product_sku,
            platform_skus=platform_skus,
            source_url=product.source_url,
            spec=product.spec,
            length=product.length,
            width=product.width,
            height=product.height,
            source_image_url=product.source_image_url,
            purchase_price=product.purchase_price,
            weight_g=product.weight_g,
            chinese_customs_name=product.chinese_customs_name,
            note=product.note,
        )
        if product_sku in initial_uploaded_skus:
            update_rows.append(row)
        else:
            new_rows.append(row)
    return new_rows, update_rows


def _build_latest_uploaded(
    uploaded_by_sku: dict[str, UploadedProductSku],
    erp_new_rows: list[ErpRow],
    run_time: str,
) -> list[UploadedProductSku]:
    latest = dict(uploaded_by_sku)
    for row in erp_new_rows:
        if row.product_sku not in latest:
            latest[row.product_sku] = UploadedProductSku(
                product_sku=row.product_sku,
                first_uploaded_at=run_time,
                last_updated_at=run_time,
                remark="本批次ERP新增后视为已上传",
            )
    return sorted(latest.values(), key=lambda item: item.product_sku)


def _build_latest_mapping(
    runtime_mapping: dict[str, set[str]],
    existing_rows: list[SkuPlatformMapping],
    batch_id: str,
    run_time: str,
) -> list[SkuPlatformMapping]:
    existing_meta = {row.platform_sku: row for row in existing_rows if row.platform_sku}
    latest: list[SkuPlatformMapping] = []
    for product_sku in sorted(runtime_mapping):
        for platform_sku in sorted(runtime_mapping[product_sku]):
            old = existing_meta.get(platform_sku)
            unchanged = old is not None and old.product_sku == product_sku
            latest.append(
                SkuPlatformMapping(
                    product_sku=product_sku,
                    platform_sku=platform_sku,
                    bound_at=old.bound_at if unchanged else run_time,
                    last_updated_at=run_time,
                    source=old.source if unchanged else f"首单校正:{batch_id}",
                    remark=old.remark if unchanged else "",
                )
            )
    return latest


def _exception(
    batch_id: str,
    row: DailyFirstOrderRow,
    exception_type: str,
    message: str,
    suggestion: str,
) -> ExceptionRow:
    return ExceptionRow(
        batch_id=batch_id,
        row_number=row.row_number,
        platform_sku=row.platform_sku,
        initial_product_sku=row.initial_product_sku,
        order_no=row.order_no,
        platform_channel=row.platform_channel,
        shop_account=row.shop_account,
        order_time=row.order_time,
        corrected_source_url=row.corrected_source_url,
        corrected_spec=row.corrected_spec,
        exception_type=exception_type,
        exception_message=message,
        suggestion=suggestion,
        remark=row.remark,
    )


def _exception_log(batch_id: str, row: DailyFirstOrderRow, branch: str, message: str) -> ProcessLogRow:
    return ProcessLogRow(
        batch_id=batch_id,
        row_number=row.row_number,
        platform_sku=row.platform_sku,
        initial_product_sku=row.initial_product_sku,
        correct_product_sku="",
        order_no=row.order_no,
        platform_channel=row.platform_channel,
        shop_account=row.shop_account,
        order_time=row.order_time,
        source_check_result="",
        branch=branch,
        process_result="异常",
        erp_table_type="",
        message=message,
        remark=row.remark,
    )


def _success_log(
    batch_id: str,
    row: DailyFirstOrderRow,
    correct_product_sku: str,
    source_consistent: bool,
    branch: str,
    initial_uploaded_skus: set[str],
) -> ProcessLogRow:
    return ProcessLogRow(
        batch_id=batch_id,
        row_number=row.row_number,
        platform_sku=row.platform_sku,
        initial_product_sku=row.initial_product_sku,
        correct_product_sku=correct_product_sku,
        order_no=row.order_no,
        platform_channel=row.platform_channel,
        shop_account=row.shop_account,
        order_time=row.order_time,
        source_check_result="无误" if source_consistent else "有误",
        branch=branch,
        process_result="成功",
        erp_table_type="ERP更新表" if correct_product_sku in initial_uploaded_skus else "ERP新增表",
        message="处理成功",
        remark=row.remark,
    )



