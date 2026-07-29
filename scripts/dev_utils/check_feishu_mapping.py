"""检查飞书表头和 table_mapping.yaml 是否能对上。

这个工具只检查 mapping 中声明的字段是否存在于飞书表头。
飞书表里额外存在但没有映射的字段，只作为提示，不作为失败。

运行示例：

    python scripts/dev_utils/check_feishu_mapping.py --env apps/feishu_intake_poc/config/test.env
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from apps.feishu_intake_poc.src.settings import load_mapping, load_settings
from connectors.feishu import FeishuClient, FeishuConfig


@dataclass
class MappingCheckResult:
    """映射检查结果。"""

    mapped_ok: list[str]
    dynamic_ok: list[str]
    writeback_ok: list[str]
    missing: list[str]
    writeback_missing: list[str]
    unmapped_feishu_fields: list[str]

    @property
    def passed(self) -> bool:
        """只要 mapping 字段和回写字段没有缺失，就认为通过。"""
        return not self.missing and not self.writeback_missing


def main() -> None:
    args = parse_args()
    settings = load_settings(args.env)
    mapping = load_mapping(settings.mapping_path)

    with FeishuClient(FeishuConfig(settings.feishu_app_id, settings.feishu_app_secret)) as client:
        feishu_fields = client.list_bitable_fields(
            app_token=settings.feishu_app_token,
            table_id=settings.feishu_table_id,
        )

    result = check_mapping(mapping=mapping, feishu_fields=feishu_fields)
    print_report(result, show_unmapped=not args.hide_unmapped)

    if not result.passed:
        raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="Check Feishu table fields against table_mapping.yaml")
    parser.add_argument("--env", required=True, help="Path to env file, such as apps/feishu_intake_poc/config/test.env")
    parser.add_argument("--hide-unmapped", action="store_true", help="Do not print Feishu fields that are not in mapping")
    return parser.parse_args()


def check_mapping(mapping: dict[str, Any], feishu_fields: list[dict[str, Any]]) -> MappingCheckResult:
    """检查 mapping 中声明的字段是否存在于飞书字段列表。

    参数：
        mapping: table_mapping.yaml 读取后的配置。
        feishu_fields: list_bitable_fields 返回的飞书字段结构。

    返回：
        MappingCheckResult，包含通过字段、缺失字段和未映射字段提示。
    """
    feishu_field_names = {field.get("field_name") for field in feishu_fields if field.get("field_name")}
    mapped_feishu_names: set[str] = set()

    mapped_ok: list[str] = []
    dynamic_ok: list[str] = []
    missing: list[str] = []

    for internal_name, rule in (mapping.get("fields") or {}).items():
        feishu_field = rule.get("feishu_field")
        if not feishu_field:
            missing.append(f"{internal_name}: 未配置 feishu_field")
            continue

        mapped_feishu_names.add(feishu_field)
        if feishu_field not in feishu_field_names:
            missing.append(f"{internal_name}: 飞书字段不存在 -> {feishu_field}")
            continue

        target = rule.get("target", "column")
        if target == "dynamic_attributes":
            dynamic_ok.append(f"{feishu_field} -> dynamic_attributes.{internal_name}")
        else:
            mapped_ok.append(f"{feishu_field} -> {internal_name}")

    writeback_ok: list[str] = []
    writeback_missing: list[str] = []
    for internal_name, feishu_field in (mapping.get("system_writeback_fields") or {}).items():
        if not feishu_field:
            writeback_missing.append(f"{internal_name}: 未配置回写字段名")
            continue

        mapped_feishu_names.add(feishu_field)
        if feishu_field in feishu_field_names:
            writeback_ok.append(f"{feishu_field} <- {internal_name}")
        else:
            writeback_missing.append(f"{internal_name}: 回写字段不存在 -> {feishu_field}")

    unmapped_feishu_fields = sorted(feishu_field_names - mapped_feishu_names)

    return MappingCheckResult(
        mapped_ok=sorted(mapped_ok),
        dynamic_ok=sorted(dynamic_ok),
        writeback_ok=sorted(writeback_ok),
        missing=sorted(missing),
        writeback_missing=sorted(writeback_missing),
        unmapped_feishu_fields=unmapped_feishu_fields,
    )


def print_report(result: MappingCheckResult, *, show_unmapped: bool) -> None:
    """打印人能看懂的检查报告。"""
    print("Mapping Check Report")
    print("====================")
    print(f"Result: {'PASS' if result.passed else 'FAIL'}")
    print()

    print_section("Column OK", result.mapped_ok)
    print_section("Dynamic Attributes OK", result.dynamic_ok)
    print_section("Writeback OK", result.writeback_ok)
    print_section("Missing", result.missing)
    print_section("Writeback Missing", result.writeback_missing)

    if show_unmapped:
        print_section("Unmapped Feishu Fields (提示，不影响通过)", result.unmapped_feishu_fields)


def print_section(title: str, lines: list[str]) -> None:
    """打印报告分组。"""
    print(title)
    if not lines:
        print("- 无")
    else:
        for line in lines:
            print(f"- {line}")
    print()


if __name__ == "__main__":
    main()
