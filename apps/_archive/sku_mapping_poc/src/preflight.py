"""运行前检查。"""

from __future__ import annotations

from collections.abc import Callable

from .db import DatabaseSettings, SkuDatabase
from .loader import (
    load_daily_input,
    load_first_category_codes,
    load_historical_ordered_platform_skus,
    load_product_sku_master,
    load_sku_platform_mapping,
    load_uploaded_product_skus,
)
from .models import AppSettings
from .settings import check_input_files
from .validator import find_ambiguous_source_keys, find_duplicate_mapping_platform_skus, find_duplicate_product_skus, find_invalid_product_source_rows


def run_preflight_checks(settings: AppSettings, logger: Callable[[str], None] | None = None) -> list[str]:
    """检查入参、状态表和数据库连接，返回问题列表。"""
    _log(logger, "检查配置中的输入文件路径")
    problems = check_input_files(settings)
    if problems:
        return problems

    checks = [
        ("每日出单平台SKU输入表", lambda: load_daily_input(settings.daily_input, settings.default_sheet_name)),
    ]
    if settings.product_source_mode == "excel":
        if settings.product_sku_master is not None:
            checks.append(("商品基础库Excel兼容表", lambda: load_product_sku_master(settings.product_sku_master, settings.default_sheet_name)))
        if settings.first_category_codes and settings.first_category_codes.exists():
            checks.append(("一级类目编码表", lambda: load_first_category_codes(settings.first_category_codes, settings.default_sheet_name)))

    optional_state_checks = [
        ("已上传商品SKU产品表", settings.uploaded_product_skus, load_uploaded_product_skus),
        ("历史出单平台SKU表", settings.historical_ordered_platform_skus, load_historical_ordered_platform_skus),
        ("商品SKU-平台SKU映射关系表", settings.product_sku_platform_sku_mapping, load_sku_platform_mapping),
    ]
    for name, path, loader in optional_state_checks:
        if path.exists():
            checks.append((name, lambda path=path, loader=loader: loader(path, settings.default_sheet_name)))

    for name, check in checks:
        try:
            _log(logger, f"检查{name}")
            check()
        except Exception as exc:  # noqa: BLE001 - preflight needs to report all user-facing input failures
            problems.append(f"{name} 不符合规范: {exc}")

    if settings.product_sku_platform_sku_mapping.exists():
        _log(logger, "检查商品SKU-平台SKU映射关系表重复绑定")
        mapping_rows = load_sku_platform_mapping(settings.product_sku_platform_sku_mapping, settings.default_sheet_name)
        duplicate_mapping = find_duplicate_mapping_platform_skus(mapping_rows)
        if duplicate_mapping:
            examples = "; ".join(
                f"{platform_sku} -> {', '.join(product_skus)}"
                for platform_sku, product_skus in sorted(duplicate_mapping.items())[:5]
            )
            problems.append(f"商品SKU-平台SKU映射关系表存在同一平台SKU绑定多个商品SKU: {examples}")

    if settings.product_source_mode == "db":
        problems.extend(_check_database(settings, logger))

    return problems


def _check_database(settings: AppSettings, logger: Callable[[str], None] | None = None) -> list[str]:
    problems: list[str] = []
    try:
        _log(logger, "检查数据库连接")
        db = SkuDatabase(DatabaseSettings(settings.database_url, settings.database_schema))
        db.health_check()
    except Exception as exc:  # noqa: BLE001
        return [f"数据库连接失败: {exc}"]

    try:
        _log(logger, f"读取并校验数据库表 {settings.database_schema}.product_source")
        product_source_rows = db.load_product_source()
    except Exception as exc:  # noqa: BLE001
        problems.append(f"数据库表 {settings.database_schema}.product_source 查询失败: {exc}")
    else:
        problems.extend(_check_product_source_rows(product_source_rows))

    try:
        _log(logger, f"检查数据库表 {settings.database_schema}.first_category_code")
        db.load_first_category_codes()
    except Exception as exc:  # noqa: BLE001
        problems.append(f"数据库表 {settings.database_schema}.first_category_code 查询失败: {exc}")
    return problems


def _check_product_source_rows(product_source_rows):
    problems: list[str] = []
    invalid_rows = find_invalid_product_source_rows(product_source_rows)
    if invalid_rows:
        examples = ", ".join(invalid_rows[:5])
        problems.append(f"数据库表 product_source 存在商品SKU、货源链接或规格为空的数据: {examples}")

    duplicate_product_skus = find_duplicate_product_skus(product_source_rows)
    if duplicate_product_skus:
        examples = ", ".join(sorted(duplicate_product_skus)[:5])
        problems.append(f"数据库表 product_source 存在重复商品SKU: {examples}")

    ambiguous_source_keys = find_ambiguous_source_keys(product_source_rows)
    if ambiguous_source_keys:
        examples = "; ".join(
            f"{source_url} + {spec} -> {', '.join(product_skus)}"
            for (source_url, spec), product_skus in list(sorted(ambiguous_source_keys.items()))[:5]
        )
        problems.append(f"数据库表 product_source 存在重复货源链接+规格: {examples}")
    return problems


def _log(logger: Callable[[str], None] | None, message: str) -> None:
    if logger:
        logger(message)
