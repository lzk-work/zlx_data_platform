"""平台 SKU 货源预校正数据库访问。"""

from __future__ import annotations

from apps.sku_mapping_poc.src.db import DatabaseSettings, SkuDatabase, _product_source_params

from .models import FirstCategoryCode, ProductSkuMaster


class SourceUpdateDatabase(SkuDatabase):
    """复用 SKU 映射 POC 数据库读取能力，写入时只允许 insert。"""

    def insert_product_source_rows(self, rows: list[ProductSkuMaster]) -> int:
        if not rows:
            return 0
        sql = f"""
            insert into "{self.schema}"."product_source" (
              product_sku,
              source_image_url,
              source_url,
              spec,
              purchase_price,
              weight_g,
              length_cm,
              width_cm,
              height_cm,
              color,
              material,
              quantity,
              chinese_customs_name,
              supplier,
              note,
              first_level_category,
              category_code,
              temp_sku
            )
            values (
              %(product_sku)s,
              %(source_image_url)s,
              %(source_url)s,
              %(spec)s,
              %(purchase_price)s,
              %(weight_g)s,
              %(length_cm)s,
              %(width_cm)s,
              %(height_cm)s,
              %(color)s,
              %(material)s,
              %(quantity)s,
              %(chinese_customs_name)s,
              %(supplier)s,
              %(note)s,
              %(first_level_category)s,
              %(category_code)s,
              %(temp_sku)s
            )
        """
        params = [_product_source_params(row) for row in rows]
        with self.connection() as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    cursor.executemany(sql, params)
        return len(params)


__all__ = ["DatabaseSettings", "FirstCategoryCode", "ProductSkuMaster", "SourceUpdateDatabase"]
