from __future__ import annotations

from pathlib import Path

from apps.sku_mapping_poc.src.models import (
    AppSettings,
    DailyFirstOrderRow,
    FirstCategoryCode,
    HistoricalOrderedPlatformSku,
    ProductSkuMaster,
    SkuPlatformMapping,
    UploadedProductSku,
)
from apps.sku_mapping_poc.src.processor import process_sku_mapping
from apps.sku_mapping_poc.src.sku_generator import generate_product_sku
from apps.sku_mapping_poc.src.settings import check_input_files


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


def daily(row: int, platform_sku: str, initial_sku: str, url: str, spec: str) -> DailyFirstOrderRow:
    return DailyFirstOrderRow(
        row_number=row,
        platform_sku=platform_sku,
        initial_product_sku=initial_sku,
        order_no=f"O{row}",
        platform_channel="Amazon-US",
        shop_account="shop-a",
        order_time="2026-07-22 10:00:00",
        corrected_source_url=url,
        corrected_spec=spec,
        first_level_category="Home",
        category_code="JT",
    )


def run_case(
    tmp_path: Path,
    *,
    row: DailyFirstOrderRow,
    master: list[ProductSkuMaster],
    uploaded: list[UploadedProductSku],
    mapping: list[SkuPlatformMapping] | None = None,
):
    return process_sku_mapping(
        settings=settings(tmp_path),
        batch_id="20260708_000000",
        daily_rows=[row],
        product_master_rows=master,
        uploaded_rows=uploaded,
        historical_rows=[],
        mapping_rows=mapping or [],
    )


def assert_single_update(output, product_sku: str, platform_skus: list[str]) -> None:
    assert [row.product_sku for row in output.erp_update_rows] == [product_sku]
    assert output.erp_update_rows[0].platform_skus == platform_skus
    assert not output.erp_new_rows


def assert_single_new(output, product_sku: str, platform_skus: list[str]) -> None:
    assert [row.product_sku for row in output.erp_new_rows] == [product_sku]
    assert output.erp_new_rows[0].platform_skus == platform_skus
    assert not output.erp_update_rows


def test_branch_1_uploaded_initial_consistent_goes_to_update(tmp_path: Path) -> None:
    output = run_case(
        tmp_path,
        row=daily(2, "PSKU1", "SKU000001", "https://detail.1688.com/offer/100001.html", "s1"),
        master=[ProductSkuMaster("SKU000001", "https://detail.1688.com/offer/100001.html", "s1")],
        uploaded=[UploadedProductSku("SKU000001")],
        mapping=[SkuPlatformMapping("SKU000001", "OLD")],
    )

    assert_single_update(output, "SKU000001", ["OLD", "PSKU1"])
    assert len(output.log_rows) == 1
    assert output.log_rows[0].branch == "初始已上传/货源无误/matched/正确SKU已上传"


def test_branch_2_uploaded_initial_wrong_matches_uploaded_goes_to_update(tmp_path: Path) -> None:
    output = run_case(
        tmp_path,
        row=daily(2, "PSKU1", "SKU000001", "https://detail.1688.com/offer/100002.html", "s2"),
        master=[ProductSkuMaster("SKU000001", "https://detail.1688.com/offer/100001.html", "s1"), ProductSkuMaster("SKU000002", "https://detail.1688.com/offer/100002.html", "s2")],
        uploaded=[UploadedProductSku("SKU000001"), UploadedProductSku("SKU000002")],
        mapping=[SkuPlatformMapping("SKU000002", "OLD2")],
    )

    assert_single_update(output, "SKU000002", ["OLD2", "PSKU1"])
    assert output.log_rows[0].branch == "初始已上传/货源有误/matched/正确SKU已上传"


def test_branch_3_uploaded_initial_wrong_matches_unuploaded_goes_to_new(tmp_path: Path) -> None:
    output = run_case(
        tmp_path,
        row=daily(2, "PSKU1", "SKU000001", "https://detail.1688.com/offer/100002.html", "s2"),
        master=[ProductSkuMaster("SKU000001", "https://detail.1688.com/offer/100001.html", "s1"), ProductSkuMaster("SKU000002", "https://detail.1688.com/offer/100002.html", "s2")],
        uploaded=[UploadedProductSku("SKU000001")],
    )

    assert_single_new(output, "SKU000002", ["PSKU1"])
    assert output.log_rows[0].branch == "初始已上传/货源有误/matched/正确SKU未上传"


def test_branch_4_uploaded_initial_wrong_missing_generates_new_sku(tmp_path: Path) -> None:
    output = run_case(
        tmp_path,
        row=daily(2, "PSKU1", "SKU000001", "https://detail.1688.com/offer/199999.html", "s-new"),
        master=[ProductSkuMaster("SKU000001", "https://detail.1688.com/offer/100001.html", "s1")],
        uploaded=[UploadedProductSku("SKU000001")],
    )

    assert_single_new(output, "JT_260708_1", ["PSKU1"])
    assert output.summary is not None
    assert output.summary.generated_product_skus == 1
    product_by_sku = {row.product_sku: row for row in output.latest_product_sku_master}
    assert product_by_sku["JT_260708_1"].source_url == "https://detail.1688.com/offer/199999.html"
    assert output.log_rows[0].branch == "初始已上传/货源有误/generated/正确SKU未上传"


def test_branch_5_unuploaded_initial_consistent_goes_to_new(tmp_path: Path) -> None:
    output = run_case(
        tmp_path,
        row=daily(2, "PSKU1", "SKU000001", "https://detail.1688.com/offer/100001.html", "s1"),
        master=[ProductSkuMaster("SKU000001", "https://detail.1688.com/offer/100001.html", "s1")],
        uploaded=[],
    )

    assert_single_new(output, "SKU000001", ["PSKU1"])
    assert output.log_rows[0].branch == "初始未上传/货源无误/matched/正确SKU未上传"


def test_branch_6_unuploaded_initial_wrong_matches_uploaded_goes_to_update(tmp_path: Path) -> None:
    output = run_case(
        tmp_path,
        row=daily(2, "PSKU1", "SKU000001", "https://detail.1688.com/offer/100002.html", "s2"),
        master=[ProductSkuMaster("SKU000001", "https://detail.1688.com/offer/100001.html", "s1"), ProductSkuMaster("SKU000002", "https://detail.1688.com/offer/100002.html", "s2")],
        uploaded=[UploadedProductSku("SKU000002")],
        mapping=[SkuPlatformMapping("SKU000002", "OLD2")],
    )

    assert_single_update(output, "SKU000002", ["OLD2", "PSKU1"])
    assert output.log_rows[0].branch == "初始未上传/货源有误/matched/正确SKU已上传"


def test_branch_7_unuploaded_initial_wrong_matches_unuploaded_goes_to_new(tmp_path: Path) -> None:
    output = run_case(
        tmp_path,
        row=daily(2, "PSKU1", "SKU000001", "https://detail.1688.com/offer/100002.html", "s2"),
        master=[ProductSkuMaster("SKU000001", "https://detail.1688.com/offer/100001.html", "s1"), ProductSkuMaster("SKU000002", "https://detail.1688.com/offer/100002.html", "s2")],
        uploaded=[],
    )

    assert_single_new(output, "SKU000002", ["PSKU1"])
    assert output.log_rows[0].branch == "初始未上传/货源有误/matched/正确SKU未上传"


def test_branch_8_unuploaded_initial_wrong_missing_generates_new_sku(tmp_path: Path) -> None:
    output = run_case(
        tmp_path,
        row=daily(2, "PSKU1", "SKU000001", "https://detail.1688.com/offer/199999.html", "s-new"),
        master=[ProductSkuMaster("SKU000001", "https://detail.1688.com/offer/100001.html", "s1")],
        uploaded=[],
    )

    assert_single_new(output, "JT_260708_1", ["PSKU1"])
    assert output.summary is not None
    assert output.summary.generated_product_skus == 1
    assert output.erp_new_rows[0].source_url == "https://detail.1688.com/offer/199999.html"
    assert output.erp_new_rows[0].spec == "s-new"
    product_by_sku = {row.product_sku: row for row in output.latest_product_sku_master}
    assert product_by_sku["SKU000001"].source_url == "https://detail.1688.com/offer/100001.html"
    assert product_by_sku["JT_260708_1"].source_url == "https://detail.1688.com/offer/199999.html"
    assert output.log_rows[0].branch == "初始未上传/货源有误/generated/正确SKU未上传"


def test_empty_initial_sku_matches_existing_product_source_before_generating(tmp_path: Path) -> None:
    output = run_case(
        tmp_path,
        row=daily(2, "PSKU1", "", "https://detail.1688.com/offer/100002.html", "s2"),
        master=[ProductSkuMaster("SKU000002", "https://detail.1688.com/offer/100002.html", "s2")],
        uploaded=[UploadedProductSku("SKU000002")],
        mapping=[SkuPlatformMapping("SKU000002", "OLD2")],
    )

    assert_single_update(output, "SKU000002", ["OLD2", "PSKU1"])
    assert output.log_rows[0].branch == "初始未上传/货源有误/matched/正确SKU已上传"


def test_empty_initial_sku_and_missing_source_generates_new_sku(tmp_path: Path) -> None:
    output = run_case(
        tmp_path,
        row=daily(2, "PSKU1", "", "https://detail.1688.com/offer/199999.html", "s-new"),
        master=[],
        uploaded=[],
    )

    assert_single_new(output, "JT_260708_1", ["PSKU1"])
    assert output.summary is not None
    assert output.summary.generated_product_skus == 1
    product_by_sku = {row.product_sku: row for row in output.latest_product_sku_master}
    assert product_by_sku["JT_260708_1"].source_url == "https://detail.1688.com/offer/199999.html"
    assert output.log_rows[0].branch == "初始未上传/货源有误/generated/正确SKU未上传"


def test_missing_corrected_source_for_unuploaded_initial_generates_one_sku_and_reuses_it(tmp_path: Path) -> None:
    output = process_sku_mapping(
        settings=settings(tmp_path),
        batch_id="20260708_000000",
        daily_rows=[
            daily(2, "PSKU1", "SKU000010", "https://detail.1688.com/offer/199998.html", "new-spec"),
            daily(3, "PSKU2", "SKU000010", "https://detail.1688.com/offer/199998.html", "new-spec"),
        ],
        product_master_rows=[ProductSkuMaster("SKU000010", "https://detail.1688.com/offer/100010.html", "old-spec")],
        uploaded_rows=[],
        historical_rows=[],
        mapping_rows=[],
    )

    assert output.summary is not None
    assert output.summary.generated_product_skus == 1
    assert_single_new(output, "JT_260708_1", ["PSKU1", "PSKU2"])
    assert output.erp_new_rows[0].source_url == "https://detail.1688.com/offer/199998.html"
    assert output.erp_new_rows[0].spec == "new-spec"


def test_missing_corrected_source_for_uploaded_initial_generates_one_sku_and_reuses_it(tmp_path: Path) -> None:
    output = process_sku_mapping(
        settings=settings(tmp_path),
        batch_id="20260708_000000",
        daily_rows=[
            daily(2, "PSKU1", "SKU000010", "https://detail.1688.com/offer/199998.html", "new-spec"),
            daily(3, "PSKU2", "SKU000010", "https://detail.1688.com/offer/199998.html", "new-spec"),
        ],
        product_master_rows=[ProductSkuMaster("SKU000010", "https://detail.1688.com/offer/100010.html", "old-spec")],
        uploaded_rows=[UploadedProductSku("SKU000010")],
        historical_rows=[],
        mapping_rows=[],
    )

    assert output.summary is not None
    assert output.summary.generated_product_skus == 1
    assert_single_new(output, "JT_260708_1", ["PSKU1", "PSKU2"])


def test_missing_category_code_when_generating_new_sku_goes_to_exception(tmp_path: Path) -> None:
    row = daily(2, "PSKU1", "SKU000010", "https://detail.1688.com/offer/199998.html", "new-spec")
    row.category_code = ""
    row.first_level_category = "Unknown"

    output = process_sku_mapping(
        settings=settings(tmp_path),
        batch_id="20260708_000000",
        daily_rows=[row],
        product_master_rows=[ProductSkuMaster("SKU000010", "https://detail.1688.com/offer/100010.html", "old-spec")],
        uploaded_rows=[UploadedProductSku("SKU000010")],
        historical_rows=[],
        mapping_rows=[],
        first_category_code_rows=[FirstCategoryCode(first_category="Home", code="JT")],
    )

    assert not output.erp_new_rows
    assert output.exception_rows[0].exception_type == "missing_first_category_code"


def test_historical_order_is_skipped_without_log(tmp_path: Path) -> None:
    output = process_sku_mapping(
        settings=settings(tmp_path),
        batch_id="B1",
        daily_rows=[daily(2, "PSKU1", "SKU000001", "https://detail.1688.com/offer/100002.html", "s2")],
        product_master_rows=[ProductSkuMaster("SKU000001", "https://detail.1688.com/offer/100001.html", "s1"), ProductSkuMaster("SKU000002", "https://detail.1688.com/offer/100002.html", "s2")],
        uploaded_rows=[UploadedProductSku("SKU000001")],
        historical_rows=[HistoricalOrderedPlatformSku("PSKU1")],
        mapping_rows=[],
    )

    assert output.summary is not None
    assert output.summary.historical_skipped == 1
    assert not output.erp_new_rows
    assert not output.erp_update_rows
    assert not output.log_rows


def test_duplicate_daily_platform_sku_keeps_earliest_order(tmp_path: Path) -> None:
    output = process_sku_mapping(
        settings=settings(tmp_path),
        batch_id="B1",
        daily_rows=[
            daily(3, "PSKU1", "SKU000001", "https://detail.1688.com/offer/100002.html", "s2"),
            daily(2, "PSKU1", "SKU000001", "https://detail.1688.com/offer/100001.html", "s1"),
        ],
        product_master_rows=[ProductSkuMaster("SKU000001", "https://detail.1688.com/offer/100001.html", "s1"), ProductSkuMaster("SKU000002", "https://detail.1688.com/offer/100002.html", "s2")],
        uploaded_rows=[],
        historical_rows=[],
        mapping_rows=[],
    )

    assert not output.exception_rows
    assert_single_new(output, "SKU000001", ["PSKU1"])
    assert len(output.log_rows) == 1
    assert output.log_rows[0].row_number == 2


def test_rebind_updates_old_uploaded_sku_with_remaining_platform_skus(tmp_path: Path) -> None:
    output = process_sku_mapping(
        settings=settings(tmp_path),
        batch_id="B1",
        daily_rows=[daily(2, "PSKU_MOVE", "SKU000001", "https://detail.1688.com/offer/100002.html", "s2")],
        product_master_rows=[ProductSkuMaster("SKU000001", "https://detail.1688.com/offer/100001.html", "s1"), ProductSkuMaster("SKU000002", "https://detail.1688.com/offer/100002.html", "s2")],
        uploaded_rows=[UploadedProductSku("SKU000001"), UploadedProductSku("SKU000002")],
        historical_rows=[],
        mapping_rows=[SkuPlatformMapping("SKU000001", "PSKU_KEEP"), SkuPlatformMapping("SKU000001", "PSKU_MOVE")],
    )

    by_sku = {row.product_sku: row.platform_skus for row in output.erp_update_rows}
    assert by_sku["SKU000001"] == ["PSKU_KEEP"]
    assert by_sku["SKU000002"] == ["PSKU_MOVE"]
    latest = {row.platform_sku: row.product_sku for row in output.latest_sku_platform_mapping}
    assert latest["PSKU_MOVE"] == "SKU000002"


def test_generator_uses_category_code_date_and_same_day_max_sequence() -> None:
    generated = generate_product_sku(
        {"ABC", "YS_260708_1", "JT_260708_3", "YS_260709_99"},
        set(),
        category_code="JK",
        sku_date="260708",
    )
    assert generated.product_sku == "JK_260708_4"


def test_generator_starts_from_one_when_only_other_dates_exist() -> None:
    generated = generate_product_sku(
        {"YS_260709_999999"},
        set(),
        category_code="YS",
        sku_date="260708",
    )
    assert generated.product_sku == "YS_260708_1"


def test_db_source_mode_does_not_require_product_master_excel(tmp_path: Path) -> None:
    config = settings(tmp_path)
    config.daily_input.touch()
    config.product_source_mode = "db"
    config.database_url = "postgresql://user:pass@localhost:5432/db"

    assert check_input_files(config) == []

