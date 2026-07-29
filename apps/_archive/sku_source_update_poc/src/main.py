"""平台 SKU 货源预校正入口。"""

from __future__ import annotations

import argparse
from datetime import datetime

from .db import DatabaseSettings, SourceUpdateDatabase
from .exporter import export_output
from .loader import load_input_rows
from .processor import new_batch_id, process_source_update
from .settings import load_settings


def main() -> None:
    args = parse_args()
    _log_step("启动平台SKU货源预校正工具")
    settings = load_settings(args.config)
    if args.mode:
        settings.run_mode = args.mode
    _log_step(f"加载配置完成: mode={settings.run_mode}, dry_run={args.dry_run}, check={args.check}")
    db = SourceUpdateDatabase(DatabaseSettings(settings.database_url, settings.database_schema))

    _log_step("开始执行前检查")
    problems = _preflight(settings, db)
    if problems:
        raise SystemExit("\n".join(problems))
    _log_step("执行前检查通过")

    _log_step(f"读取输入表: {settings.input}")
    input_rows = load_input_rows(settings.input, settings.default_sheet_name)
    _log_step(f"输入表读取完成: {len(input_rows)} 行")
    _log_step("读取数据库商品基础库 product_source")
    product_rows = db.load_product_source()
    _log_step(f"商品基础库读取完成: {len(product_rows)} 行")
    _log_step("读取数据库一级类目编码 first_category_code")
    category_rows = db.load_first_category_codes()
    _log_step(f"一级类目编码读取完成: {len(category_rows)} 行")

    if args.check:
        health = db.health_check()
        print(f"数据库连接检查通过: {health.get('database_name')} / {health.get('user_name')}")
        print("平台SKU货源预校正配置检查通过")
        print(f"运行模式: {settings.run_mode}")
        print(f"输入行数: {len(input_rows)}")
        print(f"商品基础库商品SKU数: {len({row.product_sku for row in product_rows if row.product_sku})}")
        print(f"一级类目编码数: {len({row.code for row in category_rows if row.code})}")
        return

    batch_id = new_batch_id(settings)
    _log_step(f"开始处理数据批次: {batch_id}")
    output = process_source_update(
        settings=settings,
        batch_id=batch_id,
        input_rows=input_rows,
        product_source_rows=product_rows,
        first_category_code_rows=category_rows,
    )
    if output.summary:
        _log_step(
            "数据处理完成: "
            f"成功={output.summary.processed_rows}, "
            f"匹配已有={output.summary.matched_existing_skus}, "
            f"生成新SKU={output.summary.generated_product_skus}, "
            f"异常={output.summary.exceptions}"
        )
    _log_step("开始导出结果文件")
    export_output(settings, output, batch_id)
    _log_step(f"结果文件导出完成: {output.summary.output_dir}" if output.summary else "结果文件导出完成")

    if args.dry_run:
        print(f"数据库 product_source 未写入: dry-run 模式，本次有 {len(output.new_product_source_rows)} 条新增")
    else:
        _log_step(f"开始写入数据库 product_source: {len(output.new_product_source_rows)} 条新增")
        count = db.insert_product_source_rows(output.new_product_source_rows)
        print(f"数据库 product_source 新增完成: {count} 条")
        if output.summary and output.summary.exceptions > 0:
            print(f"异常行已跳过: {output.summary.exceptions} 条异常未写入数据库，请按异常表修正后下批处理")

    if output.summary:
        print(
            "平台SKU货源预校正处理完成\n"
            f"批次: {output.summary.batch_id}\n"
            f"输入行数: {output.summary.input_rows}\n"
            f"运行模式: {settings.run_mode}\n"
            f"成功处理: {output.summary.processed_rows}\n"
            f"匹配已有商品SKU: {output.summary.matched_existing_skus}\n"
            f"直接添加货源已存在跳过: {output.summary.source_only_skipped}\n"
            f"生成新商品SKU: {output.summary.generated_product_skus}\n"
            f"异常: {output.summary.exceptions}\n"
            f"输出目录: {output.summary.output_dir}"
        )


def _log_step(message: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)


def _preflight(settings, db: SourceUpdateDatabase) -> list[str]:
    problems: list[str] = []
    if not settings.input.exists():
        problems.append(f"输入文件不存在: {settings.input}")
        return problems
    try:
        _log_step("检查输入表字段")
        load_input_rows(settings.input, settings.default_sheet_name)
    except Exception as exc:  # noqa: BLE001
        problems.append(f"输入表不符合规范: {exc}")
    try:
        _log_step("检查数据库连接")
        db.health_check()
    except Exception as exc:  # noqa: BLE001
        problems.append(f"数据库检查失败: {exc}")
    return problems


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run platform SKU source update POC")
    parser.add_argument("--config", help="Path to settings YAML file")
    parser.add_argument("--check", action="store_true", help="Check configured input and database")
    parser.add_argument("--dry-run", action="store_true", help="Generate output files without writing product_source")
    parser.add_argument("--mode", choices=["platform", "source-only"], help="Run mode")
    return parser.parse_args()


if __name__ == "__main__":
    main()
