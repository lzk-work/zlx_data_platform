from __future__ import annotations

from pathlib import Path

from apps.sku_mapping_poc.src.models import FirstCategoryCode, ProductSkuMaster
from apps.sku_source_update_poc.src.models import AppSettings, SourceUpdateInputRow
from apps.sku_source_update_poc.src.processor import process_source_update


def settings(tmp_path: Path) -> AppSettings:
    return AppSettings(
        project_root=tmp_path,
        input=tmp_path / "input.xlsx",
        output_dir=tmp_path / "output",
        database_url="postgresql://user:pass@localhost:5432/db",
    )


def source_only_settings(tmp_path: Path) -> AppSettings:
    config = settings(tmp_path)
    config.run_mode = "source-only"
    return config


def row(row_number: int, platform_sku: str, initial_sku: str, url: str, spec: str, category_code: str = "JT") -> SourceUpdateInputRow:
    return SourceUpdateInputRow(
        row_number=row_number,
        platform_sku=platform_sku,
        initial_product_sku=initial_sku,
        corrected_source_url=url,
        corrected_spec=spec,
        first_level_category="Home",
        category_code=category_code,
        purchase_price="12",
        weight_g="100",
        remark="remark",
    )


def test_matches_existing_source_without_new_product(tmp_path: Path) -> None:
    output = process_source_update(
        settings=settings(tmp_path),
        batch_id="20260725_120000",
        input_rows=[row(2, "PSKU1", "INIT1", "url-1", "spec-1")],
        product_source_rows=[ProductSkuMaster("SKU_EXIST", "url-1", "spec-1")],
        first_category_code_rows=[],
    )

    assert output.summary is not None
    assert output.summary.processed_rows == 1
    assert output.summary.matched_existing_skus == 1
    assert not output.new_product_source_rows
    assert output.platform_mapping_rows[0].correct_product_sku == "SKU_EXIST"


def test_missing_source_generates_new_product_sku(tmp_path: Path) -> None:
    output = process_source_update(
        settings=settings(tmp_path),
        batch_id="20260725_120000",
        input_rows=[row(2, "PSKU1", "INIT1", "url-new", "spec-new", "JT")],
        product_source_rows=[ProductSkuMaster("JT_260725_3", "url-1", "spec-1")],
        first_category_code_rows=[],
    )

    assert output.summary is not None
    assert output.summary.generated_product_skus == 1
    assert output.new_product_source_rows[0].product_sku == "JT_260725_4"
    assert output.new_product_source_rows[0].source_url == "url-new"
    assert output.platform_mapping_rows[0].correct_product_sku == "JT_260725_4"


def test_missing_category_code_goes_to_exception(tmp_path: Path) -> None:
    input_row = row(2, "PSKU1", "INIT1", "url-new", "spec-new", "")
    input_row.first_level_category = "Unknown"

    output = process_source_update(
        settings=settings(tmp_path),
        batch_id="20260725_120000",
        input_rows=[input_row],
        product_source_rows=[],
        first_category_code_rows=[FirstCategoryCode(first_category="Home", code="JT")],
    )

    assert output.exception_rows[0].exception_type == "missing_first_category_code"
    assert not output.new_product_source_rows
    assert not output.platform_mapping_rows


def test_duplicate_source_key_goes_to_exception(tmp_path: Path) -> None:
    output = process_source_update(
        settings=settings(tmp_path),
        batch_id="20260725_120000",
        input_rows=[row(2, "PSKU1", "INIT1", "url-dup", "spec-dup")],
        product_source_rows=[ProductSkuMaster("SKU_A", "url-dup", "spec-dup"), ProductSkuMaster("SKU_B", "url-dup", "spec-dup")],
        first_category_code_rows=[],
    )

    assert output.exception_rows[0].exception_type == "ambiguous_source_key"
    assert not output.platform_mapping_rows


def test_duplicate_platform_sku_goes_to_exception_for_second_row(tmp_path: Path) -> None:
    output = process_source_update(
        settings=settings(tmp_path),
        batch_id="20260725_120000",
        input_rows=[row(2, "PSKU1", "INIT1", "url-1", "spec-1"), row(3, "PSKU1", "INIT2", "url-2", "spec-2")],
        product_source_rows=[ProductSkuMaster("SKU_EXIST", "url-1", "spec-1")],
        first_category_code_rows=[],
    )

    assert output.summary is not None
    assert output.summary.processed_rows == 1
    assert output.exception_rows[0].exception_type == "duplicate_platform_sku"


def test_source_only_existing_source_skips_without_mapping(tmp_path: Path) -> None:
    output = process_source_update(
        settings=source_only_settings(tmp_path),
        batch_id="20260725_120000",
        input_rows=[row(2, "", "", "url-1", "spec-1")],
        product_source_rows=[ProductSkuMaster("SKU_EXIST", "url-1", "spec-1")],
        first_category_code_rows=[],
    )

    assert output.summary is not None
    assert output.summary.processed_rows == 1
    assert output.summary.source_only_skipped == 1
    assert not output.new_product_source_rows
    assert not output.platform_mapping_rows
    assert output.log_rows[0].match_result == "source_only_existing_skipped"


def test_source_only_missing_source_generates_new_product_without_mapping(tmp_path: Path) -> None:
    output = process_source_update(
        settings=source_only_settings(tmp_path),
        batch_id="20260725_120000",
        input_rows=[row(2, "", "", "url-new", "spec-new", "JT")],
        product_source_rows=[ProductSkuMaster("JT_260725_3", "url-1", "spec-1")],
        first_category_code_rows=[],
    )

    assert output.summary is not None
    assert output.summary.generated_product_skus == 1
    assert output.new_product_source_rows[0].product_sku == "JT_260725_4"
    assert not output.platform_mapping_rows
