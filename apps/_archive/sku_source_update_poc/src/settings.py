"""平台 SKU 货源预校正配置读取。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from .models import AppSettings

DEFAULT_CONFIG = Path("apps/sku_source_update_poc/config/settings.example.yaml")


def find_project_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for path in (current, *current.parents):
        if (path / "pyproject.toml").exists() and (path / "apps").exists():
            return path
    return current


def load_settings(config_path: str | None = None) -> AppSettings:
    project_root = find_project_root()
    path = _resolve_path(project_root, config_path) if config_path else project_root / DEFAULT_CONFIG
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    paths = data.get("paths") or {}
    database = data.get("database") or {}
    excel = data.get("excel") or {}
    app = data.get("app") or {}

    if not paths.get("input") or not paths.get("output_dir"):
        raise ValueError("配置缺少 paths.input 或 paths.output_dir")

    env_name = str(database.get("url_env") or "SKU_SOURCE_UPDATE_DATABASE_URL")
    database_url = os.getenv(env_name) or str(database.get("url") or "")

    run_mode = str(app.get("run_mode") or "platform")
    if run_mode not in {"platform", "source-only"}:
        raise ValueError("app.run_mode 只能是 platform 或 source-only")

    return AppSettings(
        project_root=project_root,
        input=_resolve_path(project_root, str(paths["input"])),
        output_dir=_resolve_path(project_root, str(paths["output_dir"])),
        database_url=database_url,
        database_schema=str(database.get("schema") or "zlx_1"),
        default_sheet_name=excel.get("default_sheet_name"),
        batch_timezone=str(app.get("batch_timezone") or "Asia/Shanghai"),
        run_mode=run_mode,  # type: ignore[arg-type]
    )


def _resolve_path(project_root: Path, raw_path: str | None) -> Path:
    path = Path(raw_path or "")
    if path.is_absolute():
        return path
    return project_root / path
