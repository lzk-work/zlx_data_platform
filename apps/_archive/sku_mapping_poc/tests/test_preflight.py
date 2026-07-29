from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from apps.sku_mapping_poc.src.models import AppSettings
from apps.sku_mapping_poc.src.models import ProductSkuMaster
from apps.sku_mapping_poc.src.preflight import run_preflight_checks


def settings(tmp_path: Path) -> AppSettings:
    return AppSettings(
        project_root=tmp_path,
        daily_input=tmp_path / "daily.xlsx",
        product_sku_master=tmp_path / "master.xlsx",
        uploaded_product_skus=tmp_path / "uploaded.xlsx",
        historical_ordered_platform_skus=tmp_path / "history.xlsx",
        product_sku_platform_sku_mapping=tmp_path / "mapping.xlsx",
        output_dir=tmp_path / "output",
    )


def write_xlsx(path: Path, headers: list[str], rows: list[list[str]] | None = None) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers)
    for row in rows or []:
        sheet.append(row)
    workbook.save(path)


def test_preflight_reports_bad_daily_input_schema(tmp_path: Path) -> None:
    config = settings(tmp_path)
    write_xlsx(config.daily_input, ["平台SKU"])
    write_xlsx(config.product_sku_master, ["商品SKU", "货源链接", "规格"])

    problems = run_preflight_checks(config)

    assert len(problems) == 1
    assert "每日出单平台SKU输入表 不符合规范" in problems[0]
    assert "缺少字段" in problems[0]


def test_preflight_checks_database_when_source_is_db(tmp_path: Path, monkeypatch) -> None:
    config = settings(tmp_path)
    config.product_source_mode = "db"
    config.database_url = "postgresql://user:pass@localhost:5432/db"
    write_xlsx(
        config.daily_input,
        ["平台SKU", "初始商品SKU", "订单号", "平台渠道", "店铺账号", "出单时间", "校正后货源链接", "校正后规格", "备注"],
    )
    calls: list[str] = []

    class FakeDatabase:
        def __init__(self, _settings) -> None:
            calls.append("init")

        def health_check(self):
            calls.append("health")
            return {"ok": True}

        def load_product_source(self):
            calls.append("product_source")
            return []

        def load_first_category_codes(self):
            calls.append("first_category_code")
            return []

    monkeypatch.setattr("apps.sku_mapping_poc.src.preflight.SkuDatabase", FakeDatabase)

    assert run_preflight_checks(config) == []
    assert calls == ["init", "health", "product_source", "first_category_code"]


def test_preflight_reports_database_product_source_quality_problems(tmp_path: Path, monkeypatch) -> None:
    config = settings(tmp_path)
    config.product_source_mode = "db"
    config.database_url = "postgresql://user:pass@localhost:5432/db"
    write_xlsx(
        config.daily_input,
        ["平台SKU", "初始商品SKU", "订单号", "平台渠道", "店铺账号", "出单时间", "校正后货源链接", "校正后规格", "备注"],
    )

    class FakeDatabase:
        def __init__(self, _settings) -> None:
            pass

        def health_check(self):
            return {"ok": True}

        def load_product_source(self):
            return [
                ProductSkuMaster("SKU_A", "https://detail.1688.com/offer/1.html", "spec-a"),
                ProductSkuMaster("SKU_B", "https://detail.1688.com/offer/1.html", "spec-a"),
                ProductSkuMaster("SKU_EMPTY", "", "spec-empty"),
            ]

        def load_first_category_codes(self):
            return []

    monkeypatch.setattr("apps.sku_mapping_poc.src.preflight.SkuDatabase", FakeDatabase)

    problems = run_preflight_checks(config)

    assert len(problems) == 2
    assert "商品SKU、货源链接或规格为空" in problems[0]
    assert "重复货源链接+规格" in problems[1]


def test_preflight_reports_duplicate_mapping_platform_sku(tmp_path: Path) -> None:
    config = settings(tmp_path)
    write_xlsx(
        config.daily_input,
        ["平台SKU", "初始商品SKU", "订单号", "平台渠道", "店铺账号", "出单时间", "校正后货源链接", "校正后规格", "备注"],
    )
    write_xlsx(config.product_sku_master, ["商品SKU", "货源链接", "规格"])
    write_xlsx(
        config.product_sku_platform_sku_mapping,
        ["商品SKU", "平台SKU", "绑定时间", "最后更新时间", "绑定来源", "备注"],
        [["S1", "P1", "", "", "", ""], ["S2", "P1", "", "", "", ""]],
    )

    problems = run_preflight_checks(config)

    assert len(problems) == 1
    assert "同一平台SKU绑定多个商品SKU" in problems[0]
    assert "P1 -> S1, S2" in problems[0]
