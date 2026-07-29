"""SKU POC 内部 PostgreSQL 读取层。"""

from __future__ import annotations

import re
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row

from .models import FirstCategoryCode, ProductSkuMaster
from .normalizer import normalize_sku, normalize_text


@dataclass(frozen=True, slots=True)
class DatabaseSettings:
    database_url: str
    schema: str = "zlx_1"


class SkuDatabase:
    def __init__(self, settings: DatabaseSettings) -> None:
        if not settings.database_url:
            raise ValueError("数据库模式需要配置 database_url 或环境变量 SKU_MAPPING_DATABASE_URL")
        self.settings = settings
        self.schema = _safe_identifier(settings.schema)

    @contextmanager
    def connection(self) -> Iterator[psycopg.Connection[Any]]:
        with psycopg.connect(self.settings.database_url, row_factory=dict_row) as conn:
            yield conn

    def health_check(self) -> dict[str, Any]:
        with self.connection() as conn:
            row = conn.execute("select current_database() as database_name, current_user as user_name").fetchone()
            return {"ok": True, **dict(row or {})}

    def load_product_source(self) -> list[ProductSkuMaster]:
        sql = f"""
            select
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
              first_level_category,
              category_code,
              temp_sku,
              supplier,
              note
            from "{self.schema}"."product_source"
            order by product_sku
        """
        with self.connection() as conn:
            rows = conn.execute(sql).fetchall()
        return [_product_source_row(dict(row)) for row in rows]

    def load_first_category_codes(self) -> list[FirstCategoryCode]:
        sql = f"""
            select
              first_category,
              first_category_chinese,
              code
            from "{self.schema}"."first_category_code"
            order by code, first_category
        """
        with self.connection() as conn:
            rows = conn.execute(sql).fetchall()
        return [_first_category_code_row(dict(row)) for row in rows]

    def upsert_product_source_rows(self, rows: list[ProductSkuMaster]) -> int:
        """新增或更新 product_source 商品基础数据。"""
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
            on conflict (product_sku) do update set
              source_image_url = excluded.source_image_url,
              source_url = excluded.source_url,
              spec = excluded.spec,
              purchase_price = excluded.purchase_price,
              weight_g = excluded.weight_g,
              length_cm = excluded.length_cm,
              width_cm = excluded.width_cm,
              height_cm = excluded.height_cm,
              color = excluded.color,
              material = excluded.material,
              quantity = excluded.quantity,
              chinese_customs_name = excluded.chinese_customs_name,
              supplier = excluded.supplier,
              note = excluded.note,
              first_level_category = excluded.first_level_category,
              category_code = excluded.category_code,
              temp_sku = excluded.temp_sku
        """
        params = [_product_source_params(row) for row in rows]
        with self.connection() as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    cursor.executemany(sql, params)
        return len(params)


def diff_product_source_rows(
    before_rows: list[ProductSkuMaster],
    after_rows: list[ProductSkuMaster],
) -> list[ProductSkuMaster]:
    """找出需要写回 product_source 的新增或变更商品 SKU。"""
    before = {row.product_sku: _product_source_fingerprint(row) for row in before_rows if row.product_sku}
    changed: list[ProductSkuMaster] = []
    for row in after_rows:
        if not row.product_sku:
            continue
        fingerprint = _product_source_fingerprint(row)
        if before.get(row.product_sku) != fingerprint:
            changed.append(row)
    return sorted(changed, key=lambda item: item.product_sku)


def _product_source_row(row: dict[str, Any]) -> ProductSkuMaster:
    return ProductSkuMaster(
        product_sku=normalize_sku(row.get("product_sku")),
        source_url=normalize_text(row.get("source_url")),
        spec=normalize_text(row.get("spec")),
        length=normalize_text(row.get("length_cm")),
        width=normalize_text(row.get("width_cm")),
        height=normalize_text(row.get("height_cm")),
        source_image_url=normalize_text(row.get("source_image_url")),
        purchase_price=normalize_text(row.get("purchase_price")),
        weight_g=normalize_text(row.get("weight_g")),
        color=normalize_text(row.get("color")),
        material=normalize_text(row.get("material")),
        quantity=normalize_text(row.get("quantity")),
        chinese_customs_name=normalize_text(row.get("chinese_customs_name")),
        first_level_category=normalize_text(row.get("first_level_category")),
        category_code=normalize_text(row.get("category_code")),
        temp_sku=normalize_text(row.get("temp_sku")),
        supplier=normalize_text(row.get("supplier")),
        note=normalize_text(row.get("note")),
    )


def _product_source_params(row: ProductSkuMaster) -> dict[str, Any]:
    return {
        "product_sku": row.product_sku,
        "source_image_url": _none_if_blank(row.source_image_url),
        "source_url": row.source_url,
        "spec": row.spec,
        "purchase_price": _float_or_none(row.purchase_price),
        "weight_g": _float_or_none(row.weight_g),
        "length_cm": _float_or_none(row.length),
        "width_cm": _float_or_none(row.width),
        "height_cm": _float_or_none(row.height),
        "color": _none_if_blank(row.color),
        "material": _none_if_blank(row.material),
        "quantity": _int_or_none(row.quantity),
        "chinese_customs_name": _none_if_blank(row.chinese_customs_name),
        "supplier": _none_if_blank(row.supplier),
        "note": _none_if_blank(row.note),
        "first_level_category": _none_if_blank(row.first_level_category),
        "category_code": _none_if_blank(row.category_code),
        "temp_sku": _none_if_blank(row.temp_sku),
    }


def _product_source_fingerprint(row: ProductSkuMaster) -> tuple[str, ...]:
    return (
        row.product_sku,
        row.source_image_url,
        row.source_url,
        row.spec,
        row.purchase_price,
        row.weight_g,
        row.length,
        row.width,
        row.height,
        row.color,
        row.material,
        row.quantity,
        row.chinese_customs_name,
        row.supplier,
        row.note,
        row.first_level_category,
        row.category_code,
        row.temp_sku,
    )


def _none_if_blank(value: str) -> str | None:
    text = normalize_text(value)
    return text or None


def _float_or_none(value: str) -> float | None:
    text = normalize_text(value)
    if not text:
        return None
    return float(text)


def _int_or_none(value: str) -> int | None:
    text = normalize_text(value)
    if not text:
        return None
    return int(float(text))


def _first_category_code_row(row: dict[str, Any]) -> FirstCategoryCode:
    return FirstCategoryCode(
        first_category=normalize_text(row.get("first_category")),
        first_category_chinese=normalize_text(row.get("first_category_chinese")),
        code=normalize_text(row.get("code")),
    )


def _safe_identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"非法数据库标识符: {value}")
    return value
