"""飞书录入节点配置加载与校验。

正式阶段，一个飞书录入节点由一个目录管理：

configs/feishu_nodes/{node_code}/
  node.yaml
  table_mapping.yaml
  writeback.yaml
  distribution.yaml

node.yaml 物理上是一个文件，但逻辑上分为 node/source/storage/runtime/tasks。
这个模块只负责“配置发现、读取、基础校验”，不直接访问飞书或数据库。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


REQUIRED_NODE_FILES = (
    "node.yaml",
    "table_mapping.yaml",
    "writeback.yaml",
    "distribution.yaml",
)


@dataclass(frozen=True)
class NodePaths:
    """一个录入节点目录下的配置文件路径。"""

    node_dir: Path
    node: Path
    table_mapping: Path
    writeback: Path
    distribution: Path


@dataclass(frozen=True)
class NodeConfigBundle:
    """一个录入节点加载后的完整配置。"""

    node_code: str
    paths: NodePaths
    node: dict[str, Any]
    table_mapping: dict[str, Any]
    writeback: dict[str, Any]
    distribution: dict[str, Any]

    @property
    def meta(self) -> dict[str, Any]:
        """节点基础信息块。"""
        meta = self.node.get("node") or {}
        if not isinstance(meta, dict):
            return {}
        return meta

    @property
    def source(self) -> dict[str, Any]:
        """来源配置块。"""
        source = self.node.get("source") or {}
        if not isinstance(source, dict):
            return {}
        return source

    @property
    def storage(self) -> dict[str, Any]:
        """存储目标配置块。"""
        storage = self.node.get("storage") or {}
        if not isinstance(storage, dict):
            return {}
        return storage

    @property
    def runtime(self) -> dict[str, Any]:
        """运行开关配置块。"""
        runtime = self.node.get("runtime") or {}
        if not isinstance(runtime, dict):
            return {}
        return runtime

    @property
    def tasks(self) -> list[dict[str, Any]]:
        """节点任务列表。"""
        tasks = self.node.get("tasks") or []
        if not isinstance(tasks, list):
            return []
        return [task for task in tasks if isinstance(task, dict)]

    @property
    def enabled(self) -> bool:
        """节点是否启用。"""
        return bool(self.meta.get("enabled", True))

    @property
    def node_name(self) -> str:
        """节点中文名称，缺失时退回 node_code。"""
        return str(self.meta.get("node_name") or self.node_code)


def list_node_codes(config_root: str | Path) -> list[str]:
    """列出配置根目录下所有节点编码。"""
    root = Path(config_root)
    if not root.exists():
        return []
    return sorted(path.name for path in root.iterdir() if path.is_dir())


def build_node_paths(config_root: str | Path, node_code: str) -> NodePaths:
    """根据配置根目录和节点编码生成配置文件路径。"""
    node_dir = Path(config_root) / node_code
    return NodePaths(
        node_dir=node_dir,
        node=node_dir / "node.yaml",
        table_mapping=node_dir / "table_mapping.yaml",
        writeback=node_dir / "writeback.yaml",
        distribution=node_dir / "distribution.yaml",
    )


def load_node_bundle(config_root: str | Path, node_code: str) -> NodeConfigBundle:
    """读取一个节点的 node.yaml 和三件套配置。"""
    paths = build_node_paths(config_root, node_code)
    missing = [name for name in REQUIRED_NODE_FILES if not (paths.node_dir / name).exists()]
    if missing:
        joined = ", ".join(missing)
        raise FileNotFoundError(f"节点 {node_code} 缺少配置文件: {joined}")

    node = load_yaml_file(paths.node)
    meta = node.get("node") or {}
    if not isinstance(meta, dict):
        meta = {}
    actual_node_code = str(meta.get("node_code") or node_code)
    return NodeConfigBundle(
        node_code=actual_node_code,
        paths=paths,
        node=node,
        table_mapping=load_yaml_file(paths.table_mapping),
        writeback=load_yaml_file(paths.writeback),
        distribution=load_yaml_file(paths.distribution),
    )


def load_all_node_bundles(config_root: str | Path, *, enabled_only: bool = False) -> list[NodeConfigBundle]:
    """读取配置根目录下所有节点。"""
    bundles = [load_node_bundle(config_root, node_code) for node_code in list_node_codes(config_root)]
    if enabled_only:
        return [bundle for bundle in bundles if bundle.enabled]
    return bundles


def select_node_task(bundle: NodeConfigBundle, task_code: str | None = None) -> dict[str, Any]:
    """选择要执行的节点任务。

    如果传入 task_code，则必须匹配对应任务；如果未传入，则选择第一个启用任务。
    POC 目前使用这个规则来保持命令行轻量，正式调度器可以显式传 task_code。
    """
    tasks = bundle.tasks
    if not tasks:
        raise ValueError(f"节点 {bundle.node_code} 未配置 tasks")

    if task_code:
        for task in tasks:
            if str(task.get("task_code") or "") == task_code:
                return task
        raise ValueError(f"节点 {bundle.node_code} 未找到任务: {task_code}")

    for task in tasks:
        if task.get("enabled", True):
            return task
    raise ValueError(f"节点 {bundle.node_code} 没有启用的任务")


def load_yaml_file(path: str | Path) -> dict[str, Any]:
    """读取 YAML 配置文件，并要求顶层必须是对象。"""
    with Path(path).open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML 文件顶层必须是对象: {path}")
    return data


def validate_node_bundle(bundle: NodeConfigBundle) -> list[str]:
    """校验一个节点配置的一致性。

    返回错误列表。列表为空表示配置通过基础校验。
    """
    errors: list[str] = []
    errors.extend(validate_node_yaml(bundle))
    errors.extend(validate_mapping_yaml(bundle))
    errors.extend(validate_writeback_yaml(bundle))
    errors.extend(validate_distribution_yaml(bundle))
    return errors


def validate_node_yaml(bundle: NodeConfigBundle) -> list[str]:
    """校验 node.yaml 基础字段。"""
    errors: list[str] = []
    meta = bundle.meta
    source = bundle.source
    storage = bundle.storage

    if bundle.node.get("version") != 1:
        errors.append("node.yaml version 必须为 1")
    if meta.get("node_code") != bundle.node_code:
        errors.append("node.yaml node.node_code 与加载后的节点编码不一致")
    if not meta.get("node_name"):
        errors.append("node.yaml node.node_name 不能为空")
    if not source.get("app_token"):
        errors.append("node.yaml source.app_token 不能为空")
    if not source.get("table_id"):
        errors.append("node.yaml source.table_id 不能为空")
    if not storage.get("biz_table"):
        errors.append("node.yaml storage.biz_table 不能为空")
    if not storage.get("ods_table"):
        errors.append("node.yaml storage.ods_table 不能为空")

    task_codes: set[str] = set()
    if not bundle.tasks:
        errors.append("node.yaml tasks 至少需要配置一个任务")
    for index, task in enumerate(bundle.tasks, start=1):
        task_code = str(task.get("task_code") or "")
        if not task_code:
            errors.append(f"node.yaml 第 {index} 个任务缺少 task_code")
        elif task_code in task_codes:
            errors.append(f"node.yaml task_code 重复: {task_code}")
        else:
            task_codes.add(task_code)
        if not task.get("task_type"):
            errors.append(f"node.yaml 任务 {task_code or index} 缺少 task_type")
        schedule = task.get("schedule") or {}
        if not isinstance(schedule, dict) or not schedule.get("expression"):
            errors.append(f"node.yaml 任务 {task_code or index} 缺少 schedule.expression")
        read_filter = task.get("read_filter")
        if not isinstance(read_filter, dict) or not read_filter:
            errors.append(f"node.yaml 任务 {task_code or index} 缺少 read_filter")
    return errors


def validate_mapping_yaml(bundle: NodeConfigBundle) -> list[str]:
    """校验 table_mapping.yaml 与节点配置的一致性。"""
    mapping = bundle.table_mapping
    errors: list[str] = []
    if mapping.get("table_code") != bundle.node_code:
        errors.append("table_mapping.yaml 的 table_code 必须等于 node.yaml 的 node.node_code")
    if "read_filter" in mapping:
        errors.append("table_mapping.yaml 不再配置 read_filter，请放到 node.yaml 的 tasks[].read_filter")

    fields = mapping.get("fields")
    if not isinstance(fields, dict) or not fields:
        errors.append("table_mapping.yaml fields 不能为空")
        return errors

    for field_name, rule in fields.items():
        if not isinstance(rule, dict):
            errors.append(f"字段 {field_name} 配置必须是对象")
            continue
        if not rule.get("feishu_field"):
            errors.append(f"字段 {field_name} 缺少 feishu_field")
        target = rule.get("target", "column")
        if target not in {"column", "dynamic_attributes"}:
            errors.append(f"字段 {field_name} target 不支持: {target}")
        if target == "column" and not rule.get("type"):
            errors.append(f"字段 {field_name} target=column 时建议配置 type")
    return errors


def validate_writeback_yaml(bundle: NodeConfigBundle) -> list[str]:
    """校验 writeback.yaml 与节点配置的一致性。"""
    writeback = bundle.writeback
    errors: list[str] = []
    if writeback.get("source_table_code") != bundle.node_code:
        errors.append("writeback.yaml 的 source_table_code 必须等于 node.yaml 的 node.node_code")

    fields = writeback.get("fields")
    if not isinstance(fields, dict):
        errors.append("writeback.yaml fields 必须是对象")
        return errors
    for field_name, rule in fields.items():
        if not isinstance(rule, dict):
            errors.append(f"回写字段 {field_name} 配置必须是对象")
            continue
        if not rule.get("feishu_field"):
            errors.append(f"回写字段 {field_name} 缺少 feishu_field")
        if not rule.get("value_from"):
            errors.append(f"回写字段 {field_name} 缺少 value_from")
    return errors


def validate_distribution_yaml(bundle: NodeConfigBundle) -> list[str]:
    """校验 distribution.yaml 与节点配置的一致性。"""
    distribution = bundle.distribution
    errors: list[str] = []
    if distribution.get("source_table_code") != bundle.node_code:
        errors.append("distribution.yaml 的 source_table_code 必须等于 node.yaml 的 node.node_code")

    targets = distribution.get("targets") or []
    if not isinstance(targets, list):
        errors.append("distribution.yaml targets 必须是列表")
        return errors

    seen_target_codes: set[str] = set()
    for index, target in enumerate(targets, start=1):
        if not isinstance(target, dict):
            errors.append(f"第 {index} 个分发目标配置必须是对象")
            continue
        target_code = target.get("target_table_code")
        if not target_code:
            errors.append(f"第 {index} 个分发目标缺少 target_table_code")
        elif target_code in seen_target_codes:
            errors.append(f"分发目标 target_table_code 重复: {target_code}")
        else:
            seen_target_codes.add(str(target_code))

        if not target.get("enabled", True):
            continue

        target_table = target.get("target") or {}
        if not target_table.get("app_token"):
            errors.append(f"分发目标 {target_code} 缺少 target.app_token")
        if not target_table.get("table_id"):
            errors.append(f"分发目标 {target_code} 缺少 target.table_id")
        if target.get("action_type", "create") not in {"create", "update", "upsert"}:
            errors.append(f"分发目标 {target_code} action_type 不支持: {target.get('action_type')}")

        fields = target.get("fields")
        if not isinstance(fields, dict) or not fields:
            errors.append(f"分发目标 {target_code} fields 不能为空")
    return errors


def summarize_node(bundle: NodeConfigBundle) -> dict[str, Any]:
    """生成节点摘要，供命令行和文档检查使用。"""
    source = bundle.source
    storage = bundle.storage
    targets = bundle.distribution.get("targets") or []
    enabled_targets = [target for target in targets if target.get("enabled", True)]
    enabled_tasks = [task for task in bundle.tasks if task.get("enabled", True)]
    return {
        "node_code": bundle.node_code,
        "node_name": bundle.node_name,
        "enabled": bundle.enabled,
        "source_app_token_prefix": mask_config_value(source.get("app_token")),
        "source_table_id": source.get("table_id"),
        "biz_table": storage.get("biz_table"),
        "ods_table": storage.get("ods_table"),
        "task_count": len(enabled_tasks),
        "mapping_field_count": len(bundle.table_mapping.get("fields") or {}),
        "writeback_field_count": len(bundle.writeback.get("fields") or {}),
        "distribution_target_count": len(enabled_targets),
    }


def mask_config_value(value: Any, *, visible_prefix: int = 8) -> str | None:
    """隐藏配置值主体，只展示前缀，避免命令行输出完整 token。"""
    if value is None:
        return None
    text = str(value)
    if len(text) <= visible_prefix:
        return "***"
    return f"{text[:visible_prefix]}..."