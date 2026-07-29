"""SKU 映射 POC 配置读取。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from .models import AppSettings

DEFAULT_CONFIG = Path("apps/sku_mapping_poc/config/settings.example.yaml")


def find_project_root(start: Path | None = None) -> Path:
    """向上查找项目根目录。"""
    current = (start or Path.cwd()).resolve()
    for path in (current, *current.parents):
        if (path / "pyproject.toml").exists() and (path / "apps").exists():
            return path
    return current


def load_yaml(path: Path) -> dict[str, Any]:
    """读取 YAML 文件。"""
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    if not isinstance(data, dict):
        raise ValueError(f"配置文件必须是 YAML 对象: {path}")
    return data


def resolve_path(project_root: Path, raw_path: str) -> Path:
    """把配置路径解析为绝对路径。"""
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return project_root / path


def load_settings(config_path: str | None = None) -> AppSettings:
    """加载运行配置。"""
    project_root = find_project_root()
    path = resolve_path(project_root, config_path) if config_path else project_root / DEFAULT_CONFIG
    data = load_yaml(path)

    paths = data.get("paths") or {}
    excel = data.get("excel") or {}
    rules = data.get("rules") or {}
    app = data.get("app") or {}
    database = data.get("database") or {}
    product_source_mode = str(app.get("product_source_mode", "excel"))
    if product_source_mode not in {"excel", "db"}:
        raise ValueError("app.product_source_mode 只能是 excel 或 db")
    database_url = _database_url(database)

    required_paths = [
        "daily_input",
        "uploaded_product_skus",
        "historical_ordered_platform_skus",
        "product_sku_platform_sku_mapping",
        "output_dir",
    ]
    if product_source_mode == "excel":
        required_paths.append("product_sku_master")
    missing = [name for name in required_paths if not paths.get(name)]
    if missing:
        raise ValueError(f"配置缺少 paths 字段: {', '.join(missing)}")

    return AppSettings(
        project_root=project_root,
        daily_input=resolve_path(project_root, str(paths["daily_input"])),
        product_sku_master=resolve_path(project_root, str(paths["product_sku_master"])) if paths.get("product_sku_master") else None,
        first_category_codes=resolve_path(project_root, str(paths["first_category_codes"])) if paths.get("first_category_codes") else None,
        uploaded_product_skus=resolve_path(project_root, str(paths["uploaded_product_skus"])),
        historical_ordered_platform_skus=resolve_path(project_root, str(paths["historical_ordered_platform_skus"])),
        product_sku_platform_sku_mapping=resolve_path(project_root, str(paths["product_sku_platform_sku_mapping"])),
        output_dir=resolve_path(project_root, str(paths["output_dir"])),
        default_sheet_name=excel.get("default_sheet_name"),
        erp_platform_sku_separator=str(excel.get("erp_platform_sku_separator", "\n")),
        product_source_mode=product_source_mode,  # type: ignore[arg-type]
        database_url=database_url,
        database_schema=str(database.get("schema", "zlx_1")),
        allow_initialize_empty_state=bool(rules.get("allow_initialize_empty_state", True)),
        write_failed_rows_to_history=bool(rules.get("write_failed_rows_to_history", False)),
        batch_timezone=str(app.get("batch_timezone", "Asia/Shanghai")),
    )


def check_input_files(settings: AppSettings) -> list[str]:
    """检查配置指向的输入文件是否存在。"""
    problems: list[str] = []
    required_paths = [settings.daily_input]
    if settings.product_source_mode == "excel":
        if settings.product_sku_master is None:
            problems.append("Excel 商品基础库模式缺少 paths.product_sku_master")
        else:
            required_paths.append(settings.product_sku_master)
    for path in required_paths:
        if not path.exists():
            problems.append(f"必需入参文件不存在: {path}")

    if not settings.allow_initialize_empty_state:
        state_paths = [
            settings.uploaded_product_skus,
            settings.historical_ordered_platform_skus,
            settings.product_sku_platform_sku_mapping,
        ]
        for path in state_paths:
            if not path.exists():
                problems.append(f"状态表文件不存在: {path}")
    return problems


def _database_url(database: dict[str, Any]) -> str:
    env_name = str(database.get("url_env") or "SKU_MAPPING_DATABASE_URL")
    return os.getenv(env_name) or str(database.get("url") or "")
