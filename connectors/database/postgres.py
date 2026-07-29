"""PostgreSQL 通用客户端工具。

这个模块只负责数据库连接和基础 SQL 执行，不绑定任何具体业务表。
业务表怎么写入、怎么 upsert，由各个 app/pipeline 自己封装。
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Sequence

import psycopg
from psycopg.rows import dict_row


@dataclass(frozen=True)
class PostgresConfig:
    """PostgreSQL 连接配置。"""

    database_url: str


class PostgresClient:
    """PostgreSQL 基础客户端。

    所有业务应用都可以复用它来执行 SQL、查询数据、执行迁移脚本。
    这里不写业务逻辑，保持工具层干净。
    """

    def __init__(self, config: PostgresConfig) -> None:
        self.config = config

    @contextmanager
    def connection(self) -> Iterator[psycopg.Connection[Any]]:
        """打开一个数据库连接。

        row_factory=dict_row 让查询结果以 dict 形式返回，便于上层按字段名读取。
        """
        with psycopg.connect(self.config.database_url, row_factory=dict_row) as conn:
            yield conn

    @contextmanager
    def transaction(self) -> Iterator[psycopg.Connection[Any]]:
        """打开一个事务。

        适合 SKU 分配、去重写入、状态变更这类必须保证原子性的操作。
        """
        with self.connection() as conn:
            with conn.transaction():
                yield conn

    def health_check(self) -> dict[str, Any]:
        """测试数据库连接是否可用，并返回当前数据库和用户。"""
        row = self.fetch_one("select current_database() as database_name, current_user as user_name")
        return {"ok": True, **(row or {})}

    def execute(self, sql: str, params: Sequence[Any] | dict[str, Any] | None = None) -> None:
        """执行不需要返回结果的 SQL。"""
        with self.connection() as conn:
            conn.execute(sql, params)
            conn.commit()

    def fetch_one(
        self,
        sql: str,
        params: Sequence[Any] | dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """执行查询并返回一行，没有结果时返回 None。"""
        with self.connection() as conn:
            row = conn.execute(sql, params).fetchone()
            return dict(row) if row else None

    def fetch_all(
        self,
        sql: str,
        params: Sequence[Any] | dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """执行查询并返回所有行。"""
        with self.connection() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

    def execute_sql_file(self, path: str | Path) -> None:
        """读取并执行一个 SQL 文件。

        POC 阶段用于初始化 schema/table，后续也可以用于简单迁移脚本。
        """
        sql = read_sql_file(path)
        with self.connection() as conn:
            conn.execute(sql)
            conn.commit()


def read_sql_file(path: str | Path) -> str:
    """读取 SQL 文件内容。

    使用 utf-8-sig 可以自动兼容带 BOM 的 SQL 文件，避免 PostgreSQL 把文件开头的
    不可见 BOM 字符当成 SQL 内容导致语法错误。
    """
    return Path(path).read_text(encoding="utf-8-sig")
