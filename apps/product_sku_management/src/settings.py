"""Settings for product SKU management workflows."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .constants import EXCHANGE_RATE_USD, SCHEMA_NAME


@dataclass(frozen=True)
class ProductSkuSettings:
    """Runtime settings for product SKU management."""

    database_url: str
    schema_name: str
    platform_listing_supplement_file: Path
    platform_listing_update_file: Path
    output_dir: Path
    product_sku_template: Path
    bundle_sku_template: Path
    platform_pair_template: Path
    sql_path: Path
    exchange_rate_usd: float = EXCHANGE_RATE_USD


def load_settings(config_path: str | Path | None = None) -> ProductSkuSettings:
    """加载运行配置。

    Args:
        config_path: 配置文件路径；为空时读取模块内置示例配置。

    Returns:
        ProductSkuSettings: 数据库、输入输出目录、模板路径和汇率配置。

    Raises:
        RuntimeError: 未提供数据库连接串时抛出。
    """
    app_root = Path(__file__).resolve().parents[1]
    default_config = app_root / "config" / "settings.example.yaml"
    raw_config = load_yaml_file(config_path or default_config)

    database_url = os.getenv("DATABASE_URL") or raw_config.get("database", {}).get("dsn")
    if not database_url:
        raise RuntimeError("Missing DATABASE_URL or database.dsn")

    input_config = raw_config.get("input", {})
    output_config = raw_config.get("output", {})
    template_config = raw_config.get("templates", {})
    export_config = raw_config.get("export", {})

    template_root = app_root / "data" / "input" / "dianxiaomi_templates"
    return ProductSkuSettings(
        database_url=str(database_url),
        schema_name=str(raw_config.get("database", {}).get("schema") or SCHEMA_NAME),
        platform_listing_supplement_file=resolve_path(
            app_root,
            input_config.get("platform_listing_supplement_file"),
            "data/input/platform_sku_supplement.xlsx",
        ),
        platform_listing_update_file=resolve_path(
            app_root,
            input_config.get("platform_listing_update_file"),
            "data/input/platform_sku_update.xlsx",
        ),
        output_dir=resolve_path(app_root, output_config.get("output_dir"), "data/output"),
        product_sku_template=resolve_path(
            app_root,
            template_config.get("product_sku"),
            str(template_root / "template_product_sku_sample.xlsx"),
        ),
        bundle_sku_template=resolve_path(
            app_root,
            template_config.get("bundle_sku"),
            str(template_root / "template_bundle_sku_sample.xlsx"),
        ),
        platform_pair_template=resolve_path(
            app_root,
            template_config.get("platform_pair"),
            str(template_root / "template_platform_sku_sample.xlsx"),
        ),
        sql_path=resolve_path(app_root, raw_config.get("database", {}).get("sql_path"), "src/sql/001_create_sku_mgmt_tables.sql"),
        exchange_rate_usd=float(export_config.get("exchange_rate_usd") or EXCHANGE_RATE_USD),
    )


def resolve_path(app_root: Path, value: Any, default: str) -> Path:
    """解析配置路径。

    Args:
        app_root: 子项目根目录。
        value: 配置中读取到的路径值。
        default: value为空时使用的默认相对路径。

    Returns:
        Path: 绝对路径；相对路径会按app_root补齐。
    """
    raw_path = Path(str(value or default))
    if raw_path.is_absolute():
        return raw_path
    return app_root / raw_path


def load_yaml_file(path: str | Path) -> dict[str, Any]:
    """读取YAML配置文件。

    Args:
        path: YAML文件路径。

    Returns:
        dict[str, Any]: YAML顶层对象。

    Raises:
        ValueError: YAML顶层不是对象时抛出。
    """
    with Path(path).open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML file must contain an object: {path}")
    return data
