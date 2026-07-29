"""飞书录入节点 runner 命令行入口。

当前阶段先提供节点发现和配置校验能力。
后续正式同步流程会在这个入口上继续扩展。
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .config_loader import (
    list_node_codes,
    load_all_node_bundles,
    load_node_bundle,
    summarize_node,
    validate_node_bundle,
)


DEFAULT_CONFIG_ROOT = Path("configs") / "feishu_nodes"


def main() -> None:
    """命令行入口。"""
    args = parse_args()
    config_root = Path(args.config_root)

    if args.list:
        print_node_list(config_root, enabled_only=args.enabled_only)
        return

    if not args.node:
        raise SystemExit("请指定 --node，或使用 --list 查看节点")

    bundle = load_node_bundle(config_root, args.node)
    errors = validate_node_bundle(bundle)
    print_node_summary(summarize_node(bundle))

    if errors:
        print("配置校验失败:")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)

    print("配置校验通过")
    if args.dry_run:
        print("dry-run 完成：当前只验证节点配置，不访问飞书和数据库")


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="Feishu intake node runner")
    parser.add_argument("--config-root", default=str(DEFAULT_CONFIG_ROOT), help="飞书节点配置根目录")
    parser.add_argument("--list", action="store_true", help="列出节点")
    parser.add_argument("--enabled-only", action="store_true", help="列出节点时只显示启用节点")
    parser.add_argument("--node", help="要检查或运行的节点编码")
    parser.add_argument("--dry-run", action="store_true", help="只做配置校验，不访问外部系统")
    return parser.parse_args()


def print_node_list(config_root: Path, *, enabled_only: bool) -> None:
    """打印节点列表。"""
    node_codes = list_node_codes(config_root)
    if not node_codes:
        print(f"未发现节点配置: {config_root}")
        return

    bundles = load_all_node_bundles(config_root, enabled_only=enabled_only)
    for bundle in bundles:
        status = "enabled" if bundle.enabled else "disabled"
        print(f"{bundle.node_code}\t{bundle.node_name}\t{status}")


def print_node_summary(summary: dict[str, Any]) -> None:
    """打印单个节点摘要。"""
    print(f"节点编码: {summary['node_code']}")
    print(f"节点名称: {summary['node_name']}")
    print(f"是否启用: {summary['enabled']}")
    print(f"来源表 app_token 前缀: {summary['source_app_token_prefix']}")
    print(f"来源表 table_id: {summary['source_table_id']}")
    print(f"标准业务表: {summary['biz_table']}")
    print(f"ODS原始表: {summary['ods_table']}")
    print(f"任务数: {summary['task_count']}")
    print(f"映射字段数: {summary['mapping_field_count']}")
    print(f"回写字段数: {summary['writeback_field_count']}")
    print(f"启用分发目标数: {summary['distribution_target_count']}")


if __name__ == "__main__":
    main()
