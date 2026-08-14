"""Platform listing Dianxiaomi export split tests."""

from openpyxl import Workbook

from apps.product_sku_management.src.constants import EXPORT_ACTION_CREATE, EXPORT_ACTION_SKIP, EXPORT_ACTION_UPDATE
from apps.product_sku_management.src.models.output_models import PlatformPairExportRecord
from apps.product_sku_management.src.models.output_models import DianxiaomiExportPlan
from apps.product_sku_management.src.settings import ProductSkuSettings
from apps.product_sku_management.src.workflows.platform_listing_supplement import (
    DianxiaomiExportResult,
    platform_pair_record_with_changes,
    platform_listing_file_for_mode,
    dianxiaomi_template_path,
    empty_export_buckets,
    export_dianxiaomi_templates,
    plan_with_action_export_file,
)


def test_dianxiaomi_template_path_splits_create_and_update(tmp_path) -> None:
    assert dianxiaomi_template_path(tmp_path, "product_sku", EXPORT_ACTION_CREATE).name == "dianxiaomi_product_sku_create.xlsx"
    assert dianxiaomi_template_path(tmp_path, "bundle_sku", EXPORT_ACTION_UPDATE).name == "dianxiaomi_bundle_sku_update.xlsx"
    assert dianxiaomi_template_path(tmp_path, "platform_pair", EXPORT_ACTION_CREATE).name == "dianxiaomi_platform_pair_create.xlsx"


def test_plan_with_action_export_file_keeps_skip_empty_and_routes_update(tmp_path) -> None:
    skipped = DianxiaomiExportPlan(
        process_batch_id="batch_1",
        object_type="product_sku",
        object_key="YS_1",
        action_type=EXPORT_ACTION_SKIP,
        reason="unchanged",
        current_hash="hash_1",
        previous_hash="hash_1",
        payload_json={},
        export_file="",
    )
    updated = DianxiaomiExportPlan(
        process_batch_id="batch_1",
        object_type="product_sku",
        object_key="YS_2",
        action_type=EXPORT_ACTION_UPDATE,
        reason="changed",
        current_hash="hash_2",
        previous_hash="hash_1",
        payload_json={},
        export_file="old.xlsx",
    )

    assert plan_with_action_export_file(skipped, tmp_path, "product_sku").export_file == ""
    assert plan_with_action_export_file(updated, tmp_path, "product_sku").export_file.endswith(
        "dianxiaomi_product_sku_update.xlsx",
    )


def test_empty_export_buckets_has_create_and_update_only() -> None:
    buckets = empty_export_buckets()

    assert set(buckets) == {EXPORT_ACTION_CREATE, EXPORT_ACTION_UPDATE}
    assert buckets[EXPORT_ACTION_CREATE] == []
    assert buckets[EXPORT_ACTION_UPDATE] == []


def test_platform_pair_record_with_changes_adds_and_removes_platform_skus() -> None:
    record = platform_pair_record_with_changes(
        FakePairDb(("OLD_A", "MOVE_ME")),
        "YS_1",
        additional_platform_skus={"NEW_A"},
        removed_platform_skus={"MOVE_ME"},
    )

    assert record.platform_skus == ("NEW_A", "OLD_A")


def test_export_dianxiaomi_templates_skips_empty_files(tmp_path) -> None:
    template = tmp_path / "template.xlsx"
    workbook = Workbook()
    workbook.save(template)
    workbook.close()

    settings = ProductSkuSettings(
        database_url="postgresql://example",
        schema_name="sku_mgmt",
        sql_path=tmp_path / "schema.sql",
        platform_listing_supplement_file=tmp_path / "supplement.xlsx",
        platform_listing_update_file=tmp_path / "update.xlsx",
        output_dir=tmp_path,
        product_sku_template=template,
        bundle_sku_template=template,
        platform_pair_template=template,
        exchange_rate_usd=7,
    )
    export_result = DianxiaomiExportResult(
        plans=[],
        product_exports_by_action=empty_export_buckets(),
        bundle_exports_by_action=empty_export_buckets(),
        platform_pair_exports_by_action={
            EXPORT_ACTION_CREATE: [PlatformPairExportRecord("YS_1", ("PLAT_1",))],
            EXPORT_ACTION_UPDATE: [],
        },
    )

    export_dianxiaomi_templates(settings, tmp_path, export_result)

    assert not dianxiaomi_template_path(tmp_path, "product_sku", EXPORT_ACTION_CREATE).exists()
    assert not dianxiaomi_template_path(tmp_path, "bundle_sku", EXPORT_ACTION_CREATE).exists()
    assert dianxiaomi_template_path(tmp_path, "platform_pair", EXPORT_ACTION_CREATE).exists()


def test_platform_listing_file_for_mode_uses_separate_input_files(tmp_path) -> None:
    settings = ProductSkuSettings(
        database_url="postgresql://example",
        schema_name="sku_mgmt",
        sql_path=tmp_path / "schema.sql",
        platform_listing_supplement_file=tmp_path / "supplement.xlsx",
        platform_listing_update_file=tmp_path / "update.xlsx",
        output_dir=tmp_path,
        product_sku_template=tmp_path / "template.xlsx",
        bundle_sku_template=tmp_path / "template.xlsx",
        platform_pair_template=tmp_path / "template.xlsx",
        exchange_rate_usd=7,
    )

    assert platform_listing_file_for_mode(settings, "supplement").name == "supplement.xlsx"
    assert platform_listing_file_for_mode(settings, "update").name == "update.xlsx"


class FakePairDb:
    """Fake database for platform pair export planning tests."""

    def __init__(self, platform_skus: tuple[str, ...]) -> None:
        self.platform_skus = platform_skus

    def get_platform_pair_export_record(self, mapping_target_sku: str) -> PlatformPairExportRecord:
        """Return a fixed platform pair export record."""
        return PlatformPairExportRecord(mapping_target_sku, self.platform_skus)
