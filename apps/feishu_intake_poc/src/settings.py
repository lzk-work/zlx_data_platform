"""飞书录入 POC 配置读取工具。

这里负责把 .env、环境变量和 YAML 映射文件读进程序。
真实密钥只放在本地 env 文件，不写进代码。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml

from apps.feishu_node_runner.src.config_loader import load_node_bundle, select_node_task


@dataclass(frozen=True)
class IntakeSettings:
    """POC 运行所需配置。

    飞书应用凭证、节点来源表定位信息、当前任务、数据库连接和可选通知配置都集中在这里。
    """

    feishu_app_id: str
    feishu_app_secret: str
    feishu_app_token: str
    feishu_table_id: str
    database_url: str
    mapping_path: Path
    writeback_config_path: Path
    distribution_config_path: Path
    sql_path: Path
    feishu_view_id: str | None = None
    feishu_filter: str | None = None
    feishu_read_filter: dict[str, Any] | None = None
    source_updated_at_field: str | None = None
    allow_execute_distribution_immediately: bool = False
    task_code: str | None = None
    notification_receive_id: str | None = None
    notification_receive_id_type: str = "chat_id"
    node_code: str | None = None
    node_config_root: Path | None = None


def load_settings(
    env_path: str | Path | None = None,
    *,
    node_code: str | None = None,
    node_config_root: str | Path | None = None,
    task_code: str | None = None,
) -> IntakeSettings:
    """读取 POC 配置。

    优先读取传入的 env_path；如果没有传入，就尝试读取
    apps/feishu_intake_poc/config/.env。
    POC 按正式节点方式运行，必须配置 node_code 或 FEISHU_NODE_CODE。
    来源多维表、字段映射、回写、分发和任务过滤都从节点配置目录读取。
    """
    app_root = Path(__file__).resolve().parents[1]
    project_root = Path(__file__).resolve().parents[3]

    if env_path:
        load_env_file(Path(env_path))
    else:
        default_env = app_root / "config" / ".env"
        if default_env.exists():
            load_env_file(default_env)

    effective_node_code = node_code or os.getenv("FEISHU_NODE_CODE") or None
    effective_task_code = task_code or os.getenv("FEISHU_TASK_CODE") or None
    effective_node_config_root = Path(
        node_config_root
        or os.getenv("FEISHU_NODE_CONFIG_ROOT")
        or project_root / "configs" / "feishu_nodes"
    )

    if not effective_node_code:
        raise RuntimeError("Missing FEISHU_NODE_CODE: POC source table must be configured by node YAML")

    app_root_config = app_root / "config"
    settings = IntakeSettings(
        feishu_app_id=require_env("FEISHU_APP_ID"),
        feishu_app_secret=require_env("FEISHU_APP_SECRET"),
        feishu_app_token="",
        feishu_table_id="",
        database_url=require_env("DATABASE_URL"),
        mapping_path=app_root_config / "table_mapping.yaml",
        writeback_config_path=app_root_config / "writeback.yaml",
        distribution_config_path=app_root_config / "distribution.yaml",
        sql_path=Path(os.getenv("POC_SQL_PATH") or app_root / "sql" / "001_create_poc_tables.sql"),
        feishu_view_id=os.getenv("FEISHU_VIEW_ID") or None,
        feishu_filter=os.getenv("FEISHU_FILTER") or None,
        task_code=effective_task_code,
        notification_receive_id=os.getenv("FEISHU_NOTIFICATION_RECEIVE_ID") or None,
        notification_receive_id_type=os.getenv("FEISHU_NOTIFICATION_RECEIVE_ID_TYPE", "chat_id"),
        node_code=effective_node_code,
        node_config_root=effective_node_config_root,
    )
    settings = apply_node_config(settings, effective_node_config_root, effective_node_code, effective_task_code)

    if not settings.feishu_app_token:
        raise RuntimeError("Missing source Feishu app_token in node.yaml")
    if not settings.feishu_table_id:
        raise RuntimeError("Missing source Feishu table_id in node.yaml")
    return settings


def apply_node_config(
    settings: IntakeSettings,
    config_root: Path,
    node_code: str,
    task_code: str | None = None,
) -> IntakeSettings:
    """把正式节点配置应用到 POC settings。

    POC 的环境参数仍来自 .env，例如自建应用凭证和数据库连接；
    来源/目标多维表、字段映射、回写、分发和任务过滤来自节点目录。
    """
    bundle = load_node_bundle(config_root, node_code)
    task = select_node_task(bundle, task_code)
    source = bundle.source
    runtime = bundle.runtime
    return replace(
        settings,
        feishu_app_token=str(source.get("app_token") or ""),
        feishu_table_id=str(source.get("table_id") or ""),
        feishu_view_id=os.getenv("FEISHU_VIEW_ID") or source.get("view_id") or None,
        feishu_read_filter=task.get("read_filter"),
        source_updated_at_field=source.get("updated_at_field") or None,
        allow_execute_distribution_immediately=bool(runtime.get("allow_execute_distribution_immediately")),
        task_code=str(task.get("task_code") or ""),
        mapping_path=bundle.paths.table_mapping,
        writeback_config_path=bundle.paths.writeback,
        distribution_config_path=bundle.paths.distribution,
        node_code=bundle.node_code,
        node_config_root=config_root,
    )


def load_mapping(path: str | Path) -> dict[str, Any]:
    """读取飞书字段到内部字段的 YAML 映射配置。"""
    return load_yaml_file(path)


def load_yaml_file(path: str | Path) -> dict[str, Any]:
    """读取 YAML 配置文件。"""
    with Path(path).open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML file must contain an object: {path}")
    return data


def load_env_file(path: Path) -> None:
    """读取 KEY=VALUE 格式的 env 文件。

    显式读取 env 文件时，以文件内容为准，避免旧的系统环境变量污染本次 POC。
    """
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().lstrip("\ufeff")
        value = normalize_env_value(value)
        os.environ[key] = value


def normalize_env_value(value: str) -> str:
    """规范化 .env 中的值。

    只去掉首尾空白，以及完整包裹整个值的一对引号。
    不要用 strip('"') 这类写法，否则会误删过滤表达式内部需要保留的引号，
    例如 FEISHU_FILTER=CurrentValue.[开发状态]="已完成"。
    """
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def require_env(name: str) -> str:
    """读取必填环境变量，缺失时给出明确错误。"""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value
