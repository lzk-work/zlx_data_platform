"""Command line interface for product SKU management."""

from __future__ import annotations

import argparse

from .repositories.db import ProductSkuDatabase
from .settings import load_settings
from .workflows.platform_listing_supplement import run_platform_listing_supplement


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

    if args.init_db:
        ProductSkuDatabase.from_settings(settings).ensure_schema(settings.sql_path)
        if args.init_db_only:
            print("sku_mgmt schema initialized")
            return

    summary = run_platform_listing_supplement(settings, init_db=False, dry_run=args.dry_run)
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
    return parser.parse_args()
