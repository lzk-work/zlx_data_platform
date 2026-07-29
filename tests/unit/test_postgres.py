"""PostgreSQL 工具类单元测试。"""

from pathlib import Path

from connectors.database.postgres import read_sql_file


def test_read_sql_file_strips_utf8_bom(tmp_path: Path) -> None:
    sql_path = tmp_path / "schema.sql"
    sql_path.write_text("\ufeff-- comment\nselect 1;\n", encoding="utf-8")

    sql = read_sql_file(sql_path)

    assert sql.startswith("-- comment")
    assert "\ufeff" not in sql
