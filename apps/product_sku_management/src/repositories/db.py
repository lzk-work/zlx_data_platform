"""Database access for product SKU management."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from psycopg import Connection
from psycopg.types.json import Jsonb

from connectors.database import PostgresClient, PostgresConfig

from ..constants import (
    PRODUCT_SKU_TYPE_FORCED_PACKAGE,
    PRODUCT_SKU_TYPE_NORMAL,
    SCHEMA_NAME,
    SOURCE_STATUS_ACTIVE,
    WORKFLOW_PLATFORM_LISTING_SUPPLEMENT,
)
from ..domain.bundle_service import bundle_fingerprint
from ..models.domain_models import BundleSkuRecord, ParsedSourceItem, ProductSkuRecord
from ..models.output_models import BatchSummary, DianxiaomiExportPlan, ExceptionRecord, PlatformPairExportRecord, RowLog
from ..settings import ProductSkuSettings


class ProductSkuDatabase(PostgresClient):
    """商品SKU管理数据库仓储，封装sku_mgmt schema下的读写操作。"""

    def __init__(self, config: PostgresConfig, schema_name: str = SCHEMA_NAME) -> None:
        """初始化数据库仓储。

        Args:
            config: PostgreSQL连接配置。
            schema_name: 目标schema名称，默认sku_mgmt。

        Returns:
            None: 初始化连接配置和schema名称。
        """
        super().__init__(config)
        self.schema_name = schema_name

    @classmethod
    def from_settings(cls, settings: ProductSkuSettings) -> "ProductSkuDatabase":
        """从运行配置创建数据库仓储。

        Args:
            settings: 商品SKU管理运行配置。

        Returns:
            ProductSkuDatabase: 可用于本模块读写的数据库仓储。
        """
        return cls(PostgresConfig(settings.database_url), schema_name=settings.schema_name)

    def ensure_schema(self, sql_path: str | Path) -> None:
        """执行建表SQL。

        Args:
            sql_path: DDL SQL文件路径。

        Returns:
            None: SQL执行完成即完成schema初始化。
        """
        self.execute_sql_file(sql_path)

    def create_process_batch(
        self,
        process_batch_id: str,
        input_file: str,
        output_dir: str,
        workflow_type: str = WORKFLOW_PLATFORM_LISTING_SUPPLEMENT,
    ) -> None:
        """创建运行中的处理批次。

        Args:
            process_batch_id: 批次ID。
            input_file: 输入文件路径。
            output_dir: 输出目录路径。
            workflow_type: 工作流类型。

        Returns:
            None: 写入process_batch初始记录。
        """
        self.execute(
            f"""
            insert into {self.schema_name}.process_batch (
                process_batch_id, workflow_type, input_file, output_dir, status
            ) values (%s, %s, %s, %s, 'running')
            """,
            (process_batch_id, workflow_type, input_file, output_dir),
        )

    def finish_process_batch(self, summary: BatchSummary, status: str) -> None:
        """更新处理批次最终结果。

        Args:
            summary: 批次汇总数据。
            status: 最终状态，success、partial_success或failed。

        Returns:
            None: 更新process_batch统计字段和完成时间。
        """
        self.execute(
            f"""
            update {self.schema_name}.process_batch
            set status = %s,
                input_rows = %s,
                success_rows = %s,
                exception_rows = %s,
                created_product_sku_count = %s,
                created_bundle_sku_count = %s,
                created_sales_unit_count = %s,
                created_mapping_count = %s,
                summary_json = %s,
                finished_at = now() at time zone 'Asia/Shanghai',
                updated_at = now() at time zone 'Asia/Shanghai'
            where process_batch_id = %s
            """,
            (
                status,
                summary.input_rows,
                summary.success_rows,
                summary.exception_rows,
                summary.created_product_sku_count,
                summary.created_bundle_sku_count,
                summary.created_sales_unit_count,
                summary.created_mapping_count,
                Jsonb(asdict(summary)),
                summary.process_batch_id,
            ),
        )

    def insert_row_log(
        self,
        process_batch_id: str,
        log: RowLog,
        workflow_type: str = WORKFLOW_PLATFORM_LISTING_SUPPLEMENT,
    ) -> None:
        """写入单行处理日志。

        Args:
            process_batch_id: 批次ID。
            log: 单行处理日志。
            workflow_type: 工作流类型。

        Returns:
            None: 写入process_row_log。
        """
        self.execute(
            f"""
            insert into {self.schema_name}.process_row_log (
                process_batch_id, workflow_type, row_no, business_key,
                sales_unit_type, mapping_target_type, mapping_target_sku,
                product_skus_json, bundle_sku, branch_name, result, message
            ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                process_batch_id,
                workflow_type,
                log.row_no,
                log.business_key,
                log.sales_unit_type,
                log.mapping_target_type,
                log.mapping_target_sku,
                Jsonb(list(log.product_skus)),
                log.bundle_sku,
                log.branch_name,
                log.result,
                log.message,
            ),
        )

    def insert_exception_record(
        self,
        process_batch_id: str,
        exception: ExceptionRecord,
        workflow_type: str = WORKFLOW_PLATFORM_LISTING_SUPPLEMENT,
    ) -> None:
        """写入异常记录。

        Args:
            process_batch_id: 批次ID。
            exception: 行级异常记录。
            workflow_type: 工作流类型。

        Returns:
            None: 写入exception_record。
        """
        self.execute(
            f"""
            insert into {self.schema_name}.exception_record (
                process_batch_id, workflow_type, row_no, business_key,
                raw_row_json, exception_type, exception_message, suggested_action
            ) values (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                process_batch_id,
                workflow_type,
                exception.row_no,
                exception.business_key,
                Jsonb(exception.raw_row),
                exception.exception_type,
                exception.exception_message,
                exception.suggested_action,
            ),
        )

    def get_category_code(self, first_level_category: str) -> str | None:
        """查询一级类目代号。

        Args:
            first_level_category: 一级类目英文名或中文名。

        Returns:
            str | None: 匹配到的类目代号；没有匹配时返回None。
        """
        row = self.fetch_one(
            f"""
            select code
            from {self.schema_name}.first_category_code
            where first_category = %s or first_category_chinese = %s
            limit 1
            """,
            (first_level_category, first_level_category),
        )
        return str(row["code"]) if row and row.get("code") else None

    def get_category_code_with_connection(self, conn: Connection[Any], first_level_category: str) -> str | None:
        """使用现有连接查询一级类目代号。

        Args:
            conn: 当前数据库连接。
            first_level_category: 一级类目英文名或中文名。

        Returns:
            str | None: 匹配到的类目代号；没有匹配时返回None。
        """
        row = conn.execute(
            f"""
            select code
            from {self.schema_name}.first_category_code
            where first_category = %s or first_category_chinese = %s
            limit 1
            """,
            (first_level_category, first_level_category),
        ).fetchone()
        return str(row["code"]) if row and row.get("code") else None

    def find_product_sku_by_source(
        self,
        conn: Connection[Any],
        source_url: str,
        spec: str,
        quantity: int,
    ) -> dict[str, Any] | None:
        """按清洗链接、去数量规格和数量查找普通商品SKU。

        Args:
            conn: 当前事务连接。
            source_url: 清洗后的货源链接。
            spec: 去掉数量后的规格文本。
            quantity: 商品SKU身份数量。

        Returns:
            dict[str, Any] | None: 商品SKU行；不存在时返回None。
        """
        row = conn.execute(
            f"""
            select *
            from {self.schema_name}.product_sku
            where source_url = %s
              and spec = %s
              and quantity = %s
              and product_sku_type = %s
            """,
            (source_url, spec, quantity, PRODUCT_SKU_TYPE_NORMAL),
        ).fetchone()
        return dict(row) if row else None

    def find_forced_package_product_sku(
        self,
        conn: Connection[Any],
        package_fingerprint: str,
    ) -> dict[str, Any] | None:
        """按强制合包指纹查找商品SKU。

        Args:
            conn: 当前事务连接。
            package_fingerprint: 强制合包结构化明细指纹。

        Returns:
            dict[str, Any] | None: 商品SKU行；不存在时返回None。
        """
        row = conn.execute(
            f"""
            select *
            from {self.schema_name}.product_sku
            where product_sku_type = %s
              and package_fingerprint = %s
            """,
            (PRODUCT_SKU_TYPE_FORCED_PACKAGE, package_fingerprint),
        ).fetchone()
        return dict(row) if row else None

    def create_product_sku(
        self,
        conn: Connection[Any],
        *,
        item: ParsedSourceItem,
        category_code: str,
        first_level_category: str,
        main_image_url: str,
        chinese_customs_name: str,
        logistics_attribute: str,
        product_name: str,
        length_cm: Decimal | None = None,
        width_cm: Decimal | None = None,
        height_cm: Decimal | None = None,
        is_direct_sales_unit: bool = False,
    ) -> ProductSkuRecord:
        """创建商品SKU和主货源记录。

        Args:
            conn: 当前事务连接。
            item: 已解析的货源商品明细。
            category_code: 一级类目代号。
            first_level_category: 一级类目英文名。
            main_image_url: 主图链接。
            chinese_customs_name: 中文报关名。
            logistics_attribute: 产品属性。
            product_name: 商品SKU中文名称。
            length_cm: 直接承接销售单元时的包装长。
            width_cm: 直接承接销售单元时的包装宽。
            height_cm: 直接承接销售单元时的包装高。
            is_direct_sales_unit: 是否直接承接平台SKU销售单元。

        Returns:
            ProductSkuRecord: 新建后的商品SKU领域记录。
        """
        product_sku = self.next_product_sku_code(conn, category_code)
        row = conn.execute(
            f"""
            insert into {self.schema_name}.product_sku (
                product_sku, source_url, spec, quantity, product_sku_type,
                main_image_url, first_level_category,
                category_code, reference_purchase_price_rmb, reference_weight_g,
                chinese_customs_name, logistics_attribute, note,
                length_cm, width_cm, height_cm, is_direct_sales_unit
            ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            returning *
            """,
            (
                product_sku,
                item.source_url,
                item.spec,
                item.quantity,
                PRODUCT_SKU_TYPE_NORMAL,
                main_image_url,
                first_level_category,
                category_code,
                item.reference_purchase_price_rmb,
                item.reference_weight_g,
                chinese_customs_name,
                logistics_attribute,
                item.source_note,
                length_cm,
                width_cm,
                height_cm,
                is_direct_sales_unit,
            ),
        ).fetchone()
        conn.execute(
            f"""
            insert into {self.schema_name}.product_sku_source (
                product_sku, source_platform, source_url, spec, quantity, reference_purchase_price_rmb,
                reference_weight_g, source_status, is_primary, note
            ) values (%s, %s, %s, %s, %s, %s, %s, %s, true, %s)
            on conflict (source_platform, source_url, spec, quantity) do nothing
            """,
            (
                product_sku,
                item.source_platform,
                item.source_url,
                item.spec,
                item.quantity,
                item.reference_purchase_price_rmb,
                item.reference_weight_g,
                SOURCE_STATUS_ACTIVE,
                item.source_note,
            ),
        )
        return product_record_from_row(dict(row), item, product_name, created=True)

    def create_forced_package_product_sku(
        self,
        conn: Connection[Any],
        *,
        package_fingerprint: str,
        package_details: tuple[dict[str, Any], ...],
        category_code: str,
        first_level_category: str,
        main_image_url: str,
        chinese_customs_name: str,
        logistics_attribute: str,
        product_name: str,
        total_purchase_price_rmb: Decimal,
        total_weight_g: Decimal,
        note: str,
        length_cm: Decimal | None = None,
        width_cm: Decimal | None = None,
        height_cm: Decimal | None = None,
    ) -> ProductSkuRecord:
        """创建强制合包商品SKU。

        Args:
            conn: 当前事务连接。
            package_fingerprint: 强制合包结构化明细指纹。
            package_details: 强制合包采购辨识明细。
            category_code: 一级类目代号。
            first_level_category: 一级类目英文名。
            main_image_url: 主图链接。
            chinese_customs_name: 中文报关名。
            logistics_attribute: 产品属性。
            product_name: 商品SKU中文名称。
            total_purchase_price_rmb: 整包参考采购价。
            total_weight_g: 整包参考重量，单位克。
            note: 商品SKU备注。
            length_cm: 直接承接销售单元时的包装长。
            width_cm: 直接承接销售单元时的包装宽。
            height_cm: 直接承接销售单元时的包装高。

        Returns:
            ProductSkuRecord: 新建后的强制合包商品SKU领域记录。
        """
        product_sku = self.next_product_sku_code(conn, category_code)
        primary_detail = package_details[0]
        row = conn.execute(
            f"""
            insert into {self.schema_name}.product_sku (
                product_sku, source_url, spec, quantity, product_sku_type,
                package_fingerprint, package_details_json, main_image_url,
                first_level_category, category_code, reference_purchase_price_rmb,
                reference_weight_g, chinese_customs_name, logistics_attribute, note,
                length_cm, width_cm, height_cm, is_direct_sales_unit
            ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true)
            returning *
            """,
            (
                product_sku,
                str(primary_detail["source_url"]),
                str(primary_detail["spec"]),
                1,
                PRODUCT_SKU_TYPE_FORCED_PACKAGE,
                package_fingerprint,
                Jsonb(list(package_details)),
                main_image_url,
                first_level_category,
                category_code,
                total_purchase_price_rmb,
                total_weight_g,
                chinese_customs_name,
                logistics_attribute,
                note,
                length_cm,
                width_cm,
                height_cm,
            ),
        ).fetchone()
        return product_record_from_row(dict(row), None, product_name, created=True)

    def update_product_sku_latest_fields(
        self,
        conn: Connection[Any],
        *,
        product_sku: str,
        logistics_attribute: str,
        reference_purchase_price_rmb: Decimal | None = None,
        reference_weight_g: Decimal | None = None,
        chinese_customs_name: str = "",
        note: str | None = None,
        length_cm: Decimal | None = None,
        width_cm: Decimal | None = None,
        height_cm: Decimal | None = None,
        is_direct_sales_unit: bool = False,
    ) -> dict[str, Any]:
        """用最新输入覆盖商品SKU平台属性字段。

        Args:
            conn: 当前事务连接。
            product_sku: 商品SKU编码。
            logistics_attribute: 最新输入的产品属性。
            reference_purchase_price_rmb: 最新参考采购价。
            reference_weight_g: 最新参考重量，单位克。
            chinese_customs_name: 最新中文报关名。
            note: 最新备注；None表示不覆盖。
            length_cm: 直接承接销售单元时的包装长。
            width_cm: 直接承接销售单元时的包装宽。
            height_cm: 直接承接销售单元时的包装高。
            is_direct_sales_unit: 是否按直接销售单元覆盖尺寸。

        Returns:
            dict[str, Any]: 更新后的product_sku行。
        """
        row = conn.execute(
            f"""
            update {self.schema_name}.product_sku
            set logistics_attribute = %s,
                reference_purchase_price_rmb = coalesce(%s, reference_purchase_price_rmb),
                reference_weight_g = coalesce(%s, reference_weight_g),
                chinese_customs_name = coalesce(nullif(%s, ''), chinese_customs_name),
                note = case when %s then %s else note end,
                length_cm = case when %s then %s else length_cm end,
                width_cm = case when %s then %s else width_cm end,
                height_cm = case when %s then %s else height_cm end,
                is_direct_sales_unit = is_direct_sales_unit or %s,
                updated_at = now() at time zone 'Asia/Shanghai'
            where product_sku = %s
            returning *
            """,
            (
                logistics_attribute,
                reference_purchase_price_rmb,
                reference_weight_g,
                chinese_customs_name,
                note is not None,
                note,
                is_direct_sales_unit,
                length_cm,
                is_direct_sales_unit,
                width_cm,
                is_direct_sales_unit,
                height_cm,
                is_direct_sales_unit,
                product_sku,
            ),
        ).fetchone()
        conn.execute(
            f"""
            update {self.schema_name}.product_sku_source
            set reference_purchase_price_rmb = coalesce(%s, reference_purchase_price_rmb),
                reference_weight_g = coalesce(%s, reference_weight_g),
                note = case when %s then %s else note end,
                updated_at = now() at time zone 'Asia/Shanghai'
            where product_sku = %s
              and is_primary = true
            """,
            (reference_purchase_price_rmb, reference_weight_g, note is not None, note, product_sku),
        )
        return dict(row)

    def next_product_sku_code(self, conn: Connection[Any], category_code: str) -> str:
        """分配商品SKU编码。

        Args:
            conn: 当前事务连接。
            category_code: 一级类目代号，仅作为编码前缀。

        Returns:
            str: 格式为类目代号_YYMMDD_日流水的商品SKU编码；日流水全局不分类目。
        """
        date_key = datetime.now().strftime("%y%m%d")
        current_value = self.next_code_counter_value(conn, "product_sku", date_key)
        return f"{category_code}_{date_key}_{current_value}"

    def next_bundle_sku_code(
        self,
        conn: Connection[Any],
        distinct_product_sku_count: int,
        total_product_count: int,
    ) -> str:
        """分配组合SKU编码。

        Args:
            conn: 当前事务连接。
            distinct_product_sku_count: 组合内不同商品SKU数量。
            total_product_count: 组合内商品总件数。

        Returns:
            str: 格式为ZH_YYMMDD_不同商品数_总件数_日流水的组合SKU编码。
        """
        date_key = datetime.now().strftime("%y%m%d")
        current_value = self.next_code_counter_value(conn, "bundle_sku", f"ZH_{date_key}")
        return f"ZH_{date_key}_{distinct_product_sku_count}_{total_product_count}_{current_value}"

    def next_code_counter_value(self, conn: Connection[Any], counter_type: str, counter_key: str) -> int:
        """获取并递增编码流水当前值。

        Args:
            conn: 当前事务连接。
            counter_type: 编码类型。
            counter_key: 取号维度键。

        Returns:
            int: 递增后的当前流水值。
        """
        row = conn.execute(
            f"""
            insert into {self.schema_name}.sku_code_counter (
                counter_type, counter_key, current_value
            ) values (%s, %s, 1)
            on conflict (counter_type, counter_key)
            do update set
                current_value = {self.schema_name}.sku_code_counter.current_value + 1,
                updated_at = now() at time zone 'Asia/Shanghai'
            returning current_value
            """,
            (counter_type, counter_key),
        ).fetchone()
        return int(row["current_value"])

    def get_current_code_counter_value(self, conn: Connection[Any], counter_type: str, counter_key: str) -> int:
        """读取编码流水当前值，不递增。

        Args:
            conn: 当前数据库连接。
            counter_type: 编码类型。
            counter_key: 取号维度键。

        Returns:
            int: 当前最大流水值；不存在时返回0。
        """
        row = conn.execute(
            f"""
            select current_value
            from {self.schema_name}.sku_code_counter
            where counter_type = %s and counter_key = %s
            """,
            (counter_type, counter_key),
        ).fetchone()
        return int(row["current_value"]) if row and row.get("current_value") is not None else 0

    def find_bundle_by_fingerprint(self, conn: Connection[Any], fingerprint: str) -> dict[str, Any] | None:
        """按明细指纹查找组合SKU。

        Args:
            conn: 当前事务连接。
            fingerprint: 组合明细指纹。

        Returns:
            dict[str, Any] | None: 组合SKU行；不存在时返回None。
        """
        row = conn.execute(
            f"select * from {self.schema_name}.bundle_sku where detail_fingerprint = %s",
            (fingerprint,),
        ).fetchone()
        return dict(row) if row else None

    def create_bundle_sku(
        self,
        conn: Connection[Any],
        *,
        bundle_name: str,
        items: tuple[tuple[str, int], ...],
        main_image_url: str,
        chinese_customs_name: str,
        total_purchase_price_rmb: Decimal,
        total_weight_g: Decimal,
        logistics_attribute: str,
        note: str,
        source_urls: tuple[str, ...],
        length_cm: Decimal | None = None,
        width_cm: Decimal | None = None,
        height_cm: Decimal | None = None,
    ) -> BundleSkuRecord:
        """创建组合SKU及其明细。

        Args:
            conn: 当前事务连接。
            bundle_name: 组合SKU名称。
            items: 商品SKU和数量明细。
            main_image_url: 主图链接。
            chinese_customs_name: 中文报关名。
            total_purchase_price_rmb: 组合参考采购总价。
            total_weight_g: 组合参考总重量，单位克。
            logistics_attribute: 产品属性。
            note: 备注。
            source_urls: 组合内商品SKU对应的货源链接。
            length_cm: 组合SKU销售包装长。
            width_cm: 组合SKU销售包装宽。
            height_cm: 组合SKU销售包装高。

        Returns:
            BundleSkuRecord: 新建后的组合SKU领域记录。
        """
        distinct_count = len({product_sku for product_sku, _ in items})
        total_count = sum(quantity for _, quantity in items)
        fingerprint = bundle_fingerprint(items)
        bundle_sku = self.next_bundle_sku_code(conn, distinct_count, total_count)
        row = conn.execute(
            f"""
            insert into {self.schema_name}.bundle_sku (
                bundle_sku, bundle_name, detail_fingerprint, total_product_count,
                distinct_product_sku_count, main_image_url, chinese_customs_name,
                reference_total_purchase_price_rmb, reference_total_weight_g, logistics_attribute, note,
                length_cm, width_cm, height_cm
            ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            returning *
            """,
            (
                bundle_sku,
                bundle_name,
                fingerprint,
                total_count,
                distinct_count,
                main_image_url,
                chinese_customs_name,
                total_purchase_price_rmb,
                total_weight_g,
                logistics_attribute,
                note,
                length_cm,
                width_cm,
                height_cm,
            ),
        ).fetchone()
        for product_sku, quantity in sorted(items, key=lambda item_pair: item_pair[0]):
            conn.execute(
                f"""
                insert into {self.schema_name}.bundle_sku_item (
                    bundle_sku, product_sku, quantity, source_detail_key
                ) values (%s, %s, %s, %s)
                """,
                (bundle_sku, product_sku, quantity, f"{product_sku}*{quantity}"),
        )
        return bundle_record_from_row(dict(row), items, created=True, source_urls=source_urls)

    def update_bundle_sku_latest_fields(
        self,
        conn: Connection[Any],
        *,
        bundle_sku: str,
        logistics_attribute: str,
        reference_total_purchase_price_rmb: Decimal,
        reference_total_weight_g: Decimal,
        chinese_customs_name: str,
        note: str,
        length_cm: Decimal | None,
        width_cm: Decimal | None,
        height_cm: Decimal | None,
    ) -> dict[str, Any]:
        """用最新输入覆盖组合SKU平台属性字段。

        Args:
            conn: 当前事务连接。
            bundle_sku: 组合SKU编码。
            logistics_attribute: 最新输入的产品属性。
            reference_total_purchase_price_rmb: 最新参考采购总价。
            reference_total_weight_g: 最新参考总重量，单位克。
            chinese_customs_name: 最新中文报关名。
            note: 最新备注。
            length_cm: 最新包装长。
            width_cm: 最新包装宽。
            height_cm: 最新包装高。

        Returns:
            dict[str, Any]: 更新后的bundle_sku行。
        """
        row = conn.execute(
            f"""
            update {self.schema_name}.bundle_sku
            set logistics_attribute = %s,
                reference_total_purchase_price_rmb = %s,
                reference_total_weight_g = %s,
                chinese_customs_name = coalesce(nullif(%s, ''), chinese_customs_name),
                note = %s,
                length_cm = %s,
                width_cm = %s,
                height_cm = %s,
                updated_at = now() at time zone 'Asia/Shanghai'
            where bundle_sku = %s
            returning *
            """,
            (
                logistics_attribute,
                reference_total_purchase_price_rmb,
                reference_total_weight_g,
                chinese_customs_name,
                note,
                length_cm,
                width_cm,
                height_cm,
                bundle_sku,
            ),
        ).fetchone()
        return dict(row)

    def list_bundle_items(self, conn: Connection[Any], bundle_sku: str) -> tuple[tuple[str, int], ...]:
        """读取组合SKU明细。

        Args:
            conn: 当前事务连接。
            bundle_sku: 组合SKU编码。

        Returns:
            tuple[tuple[str, int], ...]: 商品SKU和数量明细。
        """
        rows = conn.execute(
            f"""
            select product_sku, quantity
            from {self.schema_name}.bundle_sku_item
            where bundle_sku = %s
            order by product_sku
            """,
            (bundle_sku,),
        ).fetchall()
        return tuple((str(row["product_sku"]), int(row["quantity"])) for row in rows)

    def list_bundle_source_urls(self, conn: Connection[Any], bundle_sku: str) -> tuple[str, ...]:
        """读取组合SKU内商品SKU对应的货源链接。

        Args:
            conn: 当前事务连接。
            bundle_sku: 组合SKU编码。

        Returns:
            tuple[str, ...]: 按组合明细顺序去重后的货源链接。
        """
        rows = conn.execute(
            f"""
            select p.source_url
            from {self.schema_name}.bundle_sku_item i
            join {self.schema_name}.product_sku p on p.product_sku = i.product_sku
            where i.bundle_sku = %s
            order by i.product_sku
            """,
            (bundle_sku,),
        ).fetchall()
        seen: set[str] = set()
        source_urls: list[str] = []
        for row in rows:
            source_url = str(row.get("source_url") or "")
            if not source_url or source_url in seen:
                continue
            seen.add(source_url)
            source_urls.append(source_url)
        return tuple(source_urls)

    def create_sales_unit(
        self,
        conn: Connection[Any],
        *,
        platform_sku: str,
        shop_name: str,
        sales_unit_type: str,
        mapping_target_type: str,
        mapping_target_sku: str,
        main_image_url: str,
        total_purchase_price_rmb: Decimal,
        total_weight_g: Decimal,
        length_cm: Decimal | None,
        width_cm: Decimal | None,
        height_cm: Decimal | None,
        logistics_attribute: str,
        chinese_customs_name: str,
        first_level_category: str,
        development_note: str,
        process_batch_id: str,
    ) -> tuple[int, bool]:
        """创建或复用平台补充销售单元。

        Args:
            conn: 当前事务连接。
            platform_sku: 平台SKU。
            shop_name: 店铺名称。
            sales_unit_type: 销售单元类型。
            mapping_target_type: 映射目标类型。
            mapping_target_sku: 映射目标SKU编码。
            main_image_url: 主图链接。
            total_purchase_price_rmb: 销售单元参考采购总价。
            total_weight_g: 销售单元参考总重量，单位克。
            length_cm: 包装长，单位厘米。
            width_cm: 包装宽，单位厘米。
            height_cm: 包装高，单位厘米。
            logistics_attribute: 物流属性。
            chinese_customs_name: 中文报关名。
            first_level_category: 一级类目。
            development_note: 开发备注。
            process_batch_id: 当前处理批次ID。

        Returns:
            tuple[int, bool]: 销售单元ID，以及是否新建。
        """
        existing = conn.execute(
            f"""
            select id
            from {self.schema_name}.sales_unit
            where platform_sku = %s
              and mapping_target_type = %s
              and mapping_target_sku = %s
            """,
            (platform_sku, mapping_target_type, mapping_target_sku),
        ).fetchone()
        if existing:
            conn.execute(
                f"""
                update {self.schema_name}.sales_unit
                set sales_unit_type = %s,
                    main_image_url = %s,
                    total_purchase_price_rmb = %s,
                    total_weight_g = %s,
                    length_cm = %s,
                    width_cm = %s,
                    height_cm = %s,
                    logistics_attribute = %s,
                    chinese_customs_name = %s,
                    first_level_category = %s,
                    development_note = %s,
                    process_batch_id = %s,
                    updated_at = now() at time zone 'Asia/Shanghai'
                where id = %s
                """,
                (
                    sales_unit_type,
                    main_image_url,
                    total_purchase_price_rmb,
                    total_weight_g,
                    length_cm,
                    width_cm,
                    height_cm,
                    logistics_attribute,
                    chinese_customs_name,
                    first_level_category,
                    development_note,
                    process_batch_id,
                    int(existing["id"]),
                ),
            )
            return int(existing["id"]), False

        row = conn.execute(
            f"""
            insert into {self.schema_name}.sales_unit (
                sales_unit_source, platform_sku, sales_unit_type,
                mapping_target_type, mapping_target_sku, main_image_url,
                total_purchase_price_rmb, total_weight_g, length_cm, width_cm,
                height_cm, logistics_attribute, chinese_customs_name,
                first_level_category, development_note, process_batch_id
            ) values (
                'platform_listing', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            returning id
            """,
            (
                platform_sku,
                sales_unit_type,
                mapping_target_type,
                mapping_target_sku,
                main_image_url,
                total_purchase_price_rmb,
                total_weight_g,
                length_cm,
                width_cm,
                height_cm,
                logistics_attribute,
                chinese_customs_name,
                first_level_category,
                development_note,
                process_batch_id,
            ),
        ).fetchone()
        return int(row["id"]), True

    def find_sales_unit(
        self,
        conn: Connection[Any],
        *,
        platform_sku: str,
        mapping_target_type: str,
        mapping_target_sku: str,
    ) -> dict[str, Any] | None:
        """查找已存在的销售单元。

        Args:
            conn: 当前数据库连接。
            platform_sku: 平台SKU。
            mapping_target_type: 映射目标类型。
            mapping_target_sku: 映射目标SKU编码。

        Returns:
            dict[str, Any] | None: 已存在销售单元行；不存在时返回None。
        """
        row = conn.execute(
            f"""
            select *
            from {self.schema_name}.sales_unit
            where platform_sku = %s
              and mapping_target_type = %s
              and mapping_target_sku = %s
            """,
            (platform_sku, mapping_target_type, mapping_target_sku),
        ).fetchone()
        return dict(row) if row else None

    def upsert_platform_mapping(
        self,
        conn: Connection[Any],
        *,
        platform_sku: str,
        shop_name: str,
        sales_unit_id: int,
        mapping_target_type: str,
        mapping_target_sku: str,
        note: str,
        allow_rebind: bool = False,
    ) -> bool:
        """新建或幂等确认平台SKU映射。

        Args:
            conn: 当前事务连接。
            platform_sku: 平台SKU。
            shop_name: 店铺名称。
            sales_unit_id: 销售单元ID。
            mapping_target_type: 映射目标类型。
            mapping_target_sku: 映射目标SKU编码。
            note: 映射备注。
            allow_rebind: 是否允许平台SKU从旧目标改绑到当前目标。

        Returns:
            bool: 新建或改绑映射返回True；已有相同映射并更新辅助信息返回False。

        Raises:
            ValueError: 平台SKU已绑定到不同目标时抛出。
        """
        existing = conn.execute(
            f"select * from {self.schema_name}.platform_sku_mapping where platform_sku = %s",
            (platform_sku,),
        ).fetchone()
        if existing:
            existing_target = str(existing["mapping_target_sku"])
            existing_type = str(existing["mapping_target_type"])
            if existing_type != mapping_target_type or existing_target != mapping_target_sku:
                if not allow_rebind:
                    raise ValueError("平台SKU已绑定不同映射目标")
                conn.execute(
                    f"""
                    update {self.schema_name}.platform_sku_mapping
                    set shop_name = %s,
                        sales_unit_id = %s,
                        mapping_target_type = %s,
                        mapping_target_sku = %s,
                        note = %s,
                        updated_at = now() at time zone 'Asia/Shanghai'
                    where platform_sku = %s
                    """,
                    (shop_name, sales_unit_id, mapping_target_type, mapping_target_sku, note, platform_sku),
                )
                return True
            conn.execute(
                f"""
                update {self.schema_name}.platform_sku_mapping
                set shop_name = %s,
                    sales_unit_id = %s,
                    note = %s,
                    updated_at = now() at time zone 'Asia/Shanghai'
                where platform_sku = %s
                """,
                (shop_name, sales_unit_id, note, platform_sku),
            )
            return False

        conn.execute(
            f"""
            insert into {self.schema_name}.platform_sku_mapping (
                platform_sku, shop_name, sales_unit_id, mapping_target_type,
                mapping_target_sku, bind_source, note
            ) values (%s, %s, %s, %s, %s, 'platform_listing', %s)
            """,
            (platform_sku, shop_name, sales_unit_id, mapping_target_type, mapping_target_sku, note),
        )
        return True

    def find_platform_mapping(self, conn: Connection[Any], platform_sku: str) -> dict[str, Any] | None:
        """查找平台SKU当前映射。

        Args:
            conn: 当前数据库连接。
            platform_sku: 平台SKU。

        Returns:
            dict[str, Any] | None: 平台SKU映射行；不存在时返回None。
        """
        row = conn.execute(
            f"select * from {self.schema_name}.platform_sku_mapping where platform_sku = %s",
            (platform_sku,),
        ).fetchone()
        return dict(row) if row else None

    def insert_mapping_snapshot(
        self,
        conn: Connection[Any],
        *,
        process_batch_id: str,
        platform_sku: str,
        shop_name: str,
        mapping_target_type: str,
        mapping_target_sku: str,
        sales_unit_id: int,
    ) -> None:
        """记录本批次平台SKU映射快照。

        Args:
            conn: 当前事务连接。
            process_batch_id: 当前处理批次ID。
            platform_sku: 平台SKU。
            shop_name: 店铺名称。
            mapping_target_type: 映射目标类型。
            mapping_target_sku: 映射目标SKU编码。
            sales_unit_id: 销售单元ID。

        Returns:
            None: 写入platform_mapping_snapshot。
        """
        conn.execute(
            f"""
            insert into {self.schema_name}.platform_mapping_snapshot (
                process_batch_id, platform_sku, shop_name, mapping_target_type,
                mapping_target_sku, sales_unit_id
            ) values (%s, %s, %s, %s, %s, %s)
            """,
            (process_batch_id, platform_sku, shop_name, mapping_target_type, mapping_target_sku, sales_unit_id),
        )

    def get_dianxiaomi_confirmed_hash(self, object_type: str, object_key: str) -> str | None:
        """读取店小秘已确认状态哈希。

        Args:
            object_type: 店小秘对象类型。
            object_key: 对象唯一键。

        Returns:
            str | None: 最近确认哈希；未确认过返回None。
        """
        row = self.fetch_one(
            f"""
            select last_confirmed_hash
            from {self.schema_name}.dianxiaomi_sync_state
            where object_type = %s and object_key = %s
            """,
            (object_type, object_key),
        )
        if not row:
            return None
        return str(row["last_confirmed_hash"]) if row.get("last_confirmed_hash") else None

    def get_dianxiaomi_confirmed_payload(self, object_type: str, object_key: str) -> dict[str, Any] | None:
        """读取店小秘已确认哈希对应的历史导出状态。

        Args:
            object_type: 店小秘对象类型。
            object_key: 对象唯一键。

        Returns:
            dict[str, Any] | None: 上次确认哈希对应的payload_json；找不到时返回None。
        """
        row = self.fetch_one(
            f"""
            select p.payload_json
            from {self.schema_name}.dianxiaomi_sync_state s
            join {self.schema_name}.dianxiaomi_export_plan p
              on p.object_type = s.object_type
             and p.object_key = s.object_key
             and p.current_hash = s.last_confirmed_hash
            where s.object_type = %s
              and s.object_key = %s
              and s.last_confirmed_hash is not null
            order by p.created_at desc
            limit 1
            """,
            (object_type, object_key),
        )
        if not row:
            return None
        payload = row.get("payload_json")
        return payload if isinstance(payload, dict) else None

    def list_pending_dianxiaomi_confirmations(self) -> list[dict[str, Any]]:
        """统计尚未确认上传成功的店小秘导出记录。

        Args:
            None.

        Returns:
            list[dict[str, Any]]: 按批次、对象类型和导出动作聚合的未确认记录。
        """
        table_exists = self.fetch_one(
            "select to_regclass(%s) as table_name",
            (f"{self.schema_name}.dianxiaomi_sync_state",),
        )
        if not table_exists or not table_exists.get("table_name"):
            return []

        return self.fetch_all(
            f"""
            select
                last_export_batch_id as process_batch_id,
                object_type,
                last_export_action as action_type,
                count(*) as pending_count,
                max(last_exported_at) as last_exported_at
            from {self.schema_name}.dianxiaomi_sync_state
            where sync_status = 'exported'
              and last_export_action in ('create', 'update')
              and last_export_hash is not null
            group by last_export_batch_id, object_type, last_export_action
            order by max(last_exported_at) desc, last_export_batch_id, object_type, last_export_action
            """,
        )

    def insert_dianxiaomi_export_plan(self, plan: DianxiaomiExportPlan) -> None:
        """写入店小秘导出计划。

        Args:
            plan: 单个对象的导出计划。

        Returns:
            None: 写入或更新dianxiaomi_export_plan。
        """
        self.execute(
            f"""
            insert into {self.schema_name}.dianxiaomi_export_plan (
                process_batch_id, object_type, object_key, action_type, reason,
                current_hash, previous_hash, payload_json, export_file
            ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (process_batch_id, object_type, object_key)
            do update set
                action_type = excluded.action_type,
                reason = excluded.reason,
                current_hash = excluded.current_hash,
                previous_hash = excluded.previous_hash,
                payload_json = excluded.payload_json,
                export_file = excluded.export_file
            """,
            (
                plan.process_batch_id,
                plan.object_type,
                plan.object_key,
                plan.action_type,
                plan.reason,
                plan.current_hash,
                plan.previous_hash,
                Jsonb(plan.payload_json),
                plan.export_file,
            ),
        )

    def mark_dianxiaomi_exported(self, plan: DianxiaomiExportPlan) -> None:
        """记录店小秘导出动作已生成。

        Args:
            plan: 单个对象的导出计划。

        Returns:
            None: 更新dianxiaomi_sync_state的最近导出信息；不代表店小秘上传成功。
        """
        self.execute(
            f"""
            insert into {self.schema_name}.dianxiaomi_sync_state (
                object_type, object_key, sync_status, last_export_batch_id,
                last_export_action, last_export_hash, last_exported_at
            ) values (
                %s, %s, %s, %s, %s, %s, now() at time zone 'Asia/Shanghai'
            )
            on conflict (object_type, object_key)
            do update set
                sync_status = case
                    when excluded.last_export_action = 'skip'
                    then {self.schema_name}.dianxiaomi_sync_state.sync_status
                    else excluded.sync_status
                end,
                last_export_batch_id = excluded.last_export_batch_id,
                last_export_action = excluded.last_export_action,
                last_export_hash = excluded.last_export_hash,
                last_exported_at = excluded.last_exported_at,
                updated_at = now() at time zone 'Asia/Shanghai'
            """,
            (
                plan.object_type,
                plan.object_key,
                "exported",
                plan.process_batch_id,
                plan.action_type,
                plan.current_hash,
            ),
        )

    def get_platform_pair_export_record(self, mapping_target_sku: str) -> PlatformPairExportRecord:
        """读取某个映射目标的完整平台SKU集合。

        Args:
            mapping_target_sku: 商品SKU或组合SKU编码。

        Returns:
            PlatformPairExportRecord: 映射目标及其当前全部平台SKU。
        """
        rows = self.fetch_all(
            f"""
            select platform_sku
            from {self.schema_name}.platform_sku_mapping
            where mapping_target_sku = %s
            order by platform_sku
            """,
            (mapping_target_sku,),
        )
        return PlatformPairExportRecord(
            mapping_target_sku=mapping_target_sku,
            platform_skus=tuple(str(row["platform_sku"]) for row in rows),
        )


def new_process_batch_id(prefix: str = "sku_mgmt") -> str:
    """生成处理批次ID。

    Args:
        prefix: 批次ID前缀。

    Returns:
        str: 带时间和随机后缀的批次ID。
    """
    date_key = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{date_key}_{uuid4().hex[:8]}"


def product_record_from_row(
    row: dict[str, Any],
    item: ParsedSourceItem | None,
    product_name: str,
    *,
    created: bool,
) -> ProductSkuRecord:
    """从数据库行和解析上下文构建商品SKU领域记录。

    Args:
        row: product_sku表查询结果。
        item: 已解析货源商品明细；强制合包商品SKU可为空。
        product_name: 商品SKU中文名称。
        created: 是否为本次新建。

    Returns:
        ProductSkuRecord: 商品SKU领域记录。
    """
    return ProductSkuRecord(
        product_sku=str(row["product_sku"]),
        source_url=str(row["source_url"]),
        source_platform=item.source_platform if item else "",
        spec=str(row["spec"]),
        quantity=int(row.get("quantity") or 1),
        product_sku_type=str(row.get("product_sku_type") or PRODUCT_SKU_TYPE_NORMAL),
        package_fingerprint=str(row["package_fingerprint"]) if row.get("package_fingerprint") else None,
        package_details=tuple(row.get("package_details_json") or ()),
        product_name=product_name,
        main_image_url=str(row.get("main_image_url") or ""),
        first_level_category=str(row.get("first_level_category") or ""),
        category_code=str(row.get("category_code") or ""),
        reference_purchase_price_rmb=Decimal(str(row.get("reference_purchase_price_rmb") or "0")),
        reference_weight_g=Decimal(str(row.get("reference_weight_g") or "0")),
        chinese_customs_name=str(row.get("chinese_customs_name") or ""),
        logistics_attribute=str(row.get("logistics_attribute") or ""),
        note=str(row.get("note") or ""),
        length_cm=row.get("length_cm"),
        width_cm=row.get("width_cm"),
        height_cm=row.get("height_cm"),
        is_direct_sales_unit=bool(row.get("is_direct_sales_unit")),
        created=created,
    )


def bundle_record_from_row(
    row: dict[str, Any],
    items: tuple[tuple[str, int], ...],
    *,
    created: bool,
    source_urls: tuple[str, ...] = (),
) -> BundleSkuRecord:
    """从数据库行构建组合SKU领域记录。

    Args:
        row: bundle_sku表查询结果。
        items: 组合明细，包含商品SKU和数量。
        created: 是否为本次新建。
        source_urls: 组合内商品SKU对应的货源链接。

    Returns:
        BundleSkuRecord: 组合SKU领域记录。
    """
    return BundleSkuRecord(
        bundle_sku=str(row["bundle_sku"]),
        bundle_name=str(row["bundle_name"]),
        total_product_count=int(row["total_product_count"]),
        distinct_product_sku_count=int(row["distinct_product_sku_count"]),
        items=items,
        main_image_url=str(row.get("main_image_url") or ""),
        chinese_customs_name=str(row.get("chinese_customs_name") or ""),
        reference_total_purchase_price_rmb=Decimal(str(row.get("reference_total_purchase_price_rmb") or "0")),
        reference_total_weight_g=Decimal(str(row.get("reference_total_weight_g") or "0")),
        logistics_attribute=str(row.get("logistics_attribute") or ""),
        note=str(row.get("note") or ""),
        source_urls=source_urls,
        length_cm=row.get("length_cm"),
        width_cm=row.get("width_cm"),
        height_cm=row.get("height_cm"),
        created=created,
    )
