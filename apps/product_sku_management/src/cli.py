"""Command line interface for product SKU management."""

from __future__ import annotations

import argparse
from typing import Any

from .repositories.db import ProductSkuDatabase
from .settings import load_settings
from .workflows.platform_listing_supplement import run_platform_listing_supplement
from .constants import WORKFLOW_MODE_SUPPLEMENT, WORKFLOW_MODE_UPDATE


def main() -> None:
    """运行商品SKU管理命令行入口。

    Args:
        None: 从命令行参数读取配置。

    Returns:
        None: 处理结果直接打印到控制台。
    """
    args = parse_args()
    settings = load_settings(args.config)

    if args.dry_run and args.init_db:
        raise ValueError("试运行模式不允许同时执行 --init-db，避免产生数据库写入")

    db = ProductSkuDatabase.from_settings(settings)

    if args.init_db:
        db.ensure_schema(settings.sql_path)
        if args.init_db_only:
            print("sku_mgmt schema initialized")
            return

    enforce_pending_confirmation_policy(db, dry_run=args.dry_run)

    summary = run_platform_listing_supplement(settings, init_db=False, dry_run=args.dry_run, mode=args.mode)
    print(f"{'试运行完成' if args.dry_run else '处理完成'}: {summary.process_batch_id}")
    print(f"成功: {summary.success_rows}")
    print(f"异常: {summary.exception_rows}")
    print(f"输出目录: {summary.output_dir}")


def parse_args() -> argparse.Namespace:
    """解析命令行参数。

    Args:
        None: 使用argparse读取当前进程参数。

    Returns:
        argparse.Namespace: 包含配置路径和初始化开关的参数对象。
    """
    parser = argparse.ArgumentParser(description="Run product SKU management workflows")
    parser.add_argument("--config", help="Path to settings YAML")
    parser.add_argument("--init-db", action="store_true", help="Initialize sku_mgmt schema before running")
    parser.add_argument("--init-db-only", action="store_true", help="Initialize schema and exit")
    parser.add_argument("--dry-run", action="store_true", help="Generate expected outputs without writing database tables")
    parser.add_argument(
        "--mode",
        choices=(WORKFLOW_MODE_SUPPLEMENT, WORKFLOW_MODE_UPDATE),
        default=WORKFLOW_MODE_SUPPLEMENT,
        help="supplement keeps existing platform SKU bindings; update allows explicit rebinding",
    )
    return parser.parse_args()


def enforce_pending_confirmation_policy(db: ProductSkuDatabase, *, dry_run: bool) -> None:
    """检查店小秘未确认状态，并按运行模式决定是否停止。

    Args:
        db: 商品SKU数据库仓储。
        dry_run: 是否为试运行模式。

    Returns:
        None: 无未确认记录或试运行模式时返回。

    Raises:
        SystemExit: 正式运行且存在未确认create/update导出记录时停止。
    """
    rows = db.list_pending_dianxiaomi_confirmations()
    print(format_pending_confirmation_warning(rows))
    if rows and not dry_run:
        raise SystemExit("正式运行已停止：请先确认已上传店小秘的历史批次，或处理未确认记录后再运行。")


def format_pending_confirmation_warning(rows: list[dict[str, Any]]) -> str:
    """格式化店小秘未确认提醒。

    Args:
        rows: 未确认记录聚合结果。

    Returns:
        str: 可直接打印到控制台的提醒文本。
    """
    if not rows:
        return "店小秘确认检查: 当前没有未确认的 create/update 导出记录。"

    total = sum(int(row["pending_count"]) for row in rows)
    lines = [
        "店小秘确认提醒: 当前存在未确认的 create/update 导出记录。",
        f"未确认对象总数: {total}",
        "未确认批次明细:",
    ]
    for row in rows:
        exported_at = row.get("last_exported_at") or ""
        lines.append(
            "  "
            f"批次={row.get('process_batch_id') or '<无批次>'} "
            f"对象={row.get('object_type')} "
            f"动作={row.get('action_type')} "
            f"数量={row.get('pending_count')} "
            f"最近导出={exported_at}"
        )
    lines.append("请确认已上传店小秘的批次并执行确认SQL；继续运行会按当前确认状态生成导出结果。")
    return "\n".join(lines)
