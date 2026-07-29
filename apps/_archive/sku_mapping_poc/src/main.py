"""商品 SKU 映射 POC 入口。"""

from __future__ import annotations

import argparse
from datetime import datetime

from .db import DatabaseSettings, SkuDatabase, diff_product_source_rows
from .exporter import export_process_output, publish_state_files
from .loader import load_daily_input, load_first_category_codes, load_historical_ordered_platform_skus, load_product_sku_master, load_sku_platform_mapping, load_uploaded_product_skus
from .preflight import run_preflight_checks
from .processor import new_batch_id, process_sku_mapping
from .report import build_summary_message, build_system_status_message, build_system_status_summary
from .settings import load_settings


def main() -> None:
    args = parse_args()
    _log_step("启动商品SKU出单管理工具")
    settings = load_settings(args.config)
    if args.source:
        settings.product_source_mode = args.source
    if args.apply_db and settings.product_source_mode != "db":
        raise SystemExit("--apply-db 只能在数据库商品基础库模式下使用")
    _log_step(f"加载配置完成: source={settings.product_source_mode}, dry_run={args.dry_run}, check={args.check}")

    _log_step("开始执行前检查")
    problems = run_preflight_checks(settings, logger=_log_step)
    if problems:
        raise SystemExit("\n".join(problems))
    _log_step("执行前检查通过")

    _log_step(f"读取每日输入表: {settings.daily_input}")
    daily_rows = load_daily_input(settings.daily_input, settings.default_sheet_name)
    _log_step(f"每日输入表读取完成: {len(daily_rows)} 行")
    if settings.product_source_mode == "db":
        _log_step("连接数据库商品基础库")
        db = SkuDatabase(DatabaseSettings(settings.database_url, settings.database_schema))
        _log_step("检查数据库连接")
        db_health = db.health_check()
        _log_step("读取数据库商品基础库 product_source")
        product_master_rows = db.load_product_source()
        _log_step(f"商品基础库读取完成: {len(product_master_rows)} 行")
        _log_step("读取数据库一级类目编码 first_category_code")
        first_category_code_rows = db.load_first_category_codes()
        _log_step(f"一级类目编码读取完成: {len(first_category_code_rows)} 行")
    else:
        db_health = None
        if settings.product_sku_master is None:
            raise SystemExit("Excel 商品基础库模式缺少 paths.product_sku_master")
        _log_step(f"读取 Excel 商品基础库: {settings.product_sku_master}")
        product_master_rows = load_product_sku_master(settings.product_sku_master, settings.default_sheet_name)
        _log_step(f"商品基础库读取完成: {len(product_master_rows)} 行")
        first_category_code_rows = (
            load_first_category_codes(settings.first_category_codes, settings.default_sheet_name)
            if settings.first_category_codes and settings.first_category_codes.exists()
            else []
        )
        _log_step(f"一级类目编码读取完成: {len(first_category_code_rows)} 行")
    _log_step("读取状态表")
    uploaded_rows = load_uploaded_product_skus(settings.uploaded_product_skus, settings.default_sheet_name) if settings.uploaded_product_skus.exists() else []
    historical_rows = (
        load_historical_ordered_platform_skus(settings.historical_ordered_platform_skus, settings.default_sheet_name)
        if settings.historical_ordered_platform_skus.exists()
        else []
    )
    mapping_rows = (
        load_sku_platform_mapping(settings.product_sku_platform_sku_mapping, settings.default_sheet_name)
        if settings.product_sku_platform_sku_mapping.exists()
        else []
    )
    _log_step(
        "状态表读取完成: "
        f"已上传={len(uploaded_rows)}, "
        f"历史出单={len(historical_rows)}, "
        f"映射关系={len(mapping_rows)}"
    )
    status = build_system_status_summary(
        daily_rows=daily_rows,
        product_master_rows=product_master_rows,
        first_category_code_rows=first_category_code_rows,
        uploaded_rows=uploaded_rows,
        historical_rows=historical_rows,
        mapping_rows=mapping_rows,
        product_source_mode=settings.product_source_mode,
    )

    if args.check:
        if db_health:
            print(f"数据库连接检查通过: {db_health.get('database_name')} / {db_health.get('user_name')}")
        print("SKU映射POC配置检查通过")
        print(f"每日输入: {settings.daily_input}")
        print(f"输出目录: {settings.output_dir}")
        print(build_system_status_message(status))
        return

    print(build_system_status_message(status))

    batch_id = new_batch_id(settings)
    _log_step(f"开始处理数据批次: {batch_id}")
    output = process_sku_mapping(
        settings=settings,
        batch_id=batch_id,
        daily_rows=daily_rows,
        product_master_rows=product_master_rows,
        uploaded_rows=uploaded_rows,
        historical_rows=historical_rows,
        mapping_rows=mapping_rows,
        first_category_code_rows=first_category_code_rows,
    )
    if output.summary:
        _log_step(
            "数据处理完成: "
            f"首单处理={output.summary.first_order_processed}, "
            f"历史跳过={output.summary.historical_skipped}, "
            f"ERP新增={output.summary.erp_new_product_skus}, "
            f"ERP更新={output.summary.erp_update_product_skus}, "
            f"异常={output.summary.exceptions}"
        )
    changed_product_source_rows = []
    if settings.product_source_mode == "db":
        _log_step("计算商品基础库变更")
        changed_product_source_rows = diff_product_source_rows(product_master_rows, output.latest_product_sku_master)
        output.latest_product_sku_master = changed_product_source_rows
        _log_step(f"商品基础库变更计算完成: {len(changed_product_source_rows)} 条")
    _log_step("开始导出结果文件")
    output_dir = export_process_output(settings, output, batch_id)
    _log_step(f"结果文件导出完成: {output_dir}")
    should_publish_state = bool(output.summary and not args.dry_run)
    if settings.product_source_mode == "db":
        changed_count = len(changed_product_source_rows)
        if args.dry_run:
            if changed_count:
                print(f"数据库 product_source 未写入: dry-run 模式，本次有 {changed_count} 条新增/更新")
        else:
            _log_step(f"开始写入数据库 product_source: {changed_count} 条新增/更新")
            written_count = db.upsert_product_source_rows(changed_product_source_rows)
            print(f"数据库 product_source 写入完成: {written_count} 条")
            if output.summary and output.summary.exceptions > 0:
                print(f"异常行已跳过: {output.summary.exceptions} 条异常未写入数据库，请按异常表修正后下批处理")
    if should_publish_state:
        _log_step("发布最新状态表到 data/state")
        publish_state_files(settings, output_dir, batch_id)
        print("最新状态表已发布为下一次运行入参")
        if output.summary and output.summary.exceptions > 0:
            print(f"异常行未进入最新状态表: {output.summary.exceptions} 条异常请按异常表修正后下批处理")
    elif args.dry_run:
        print("最新状态表未发布: dry-run 模式")
    if output.summary:
        print(build_summary_message(output.summary))


def _log_step(message: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the SKU mapping POC")
    parser.add_argument("--config", help="Path to settings YAML file")
    parser.add_argument("--source", choices=["excel", "db"], help="Product source backend")
    parser.add_argument("--check", action="store_true", help="Check configured input files")
    parser.add_argument("--dry-run", action="store_true", help="Generate output files without writing product_source")
    parser.add_argument("--apply-db", action="store_true", help="Deprecated: default db mode writes product_source when there are no exceptions")
    return parser.parse_args()


if __name__ == "__main__":
    main()
