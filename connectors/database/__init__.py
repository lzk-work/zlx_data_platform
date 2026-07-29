"""Database connector package."""

from .postgres import PostgresClient, PostgresConfig

__all__ = ["PostgresClient", "PostgresConfig"]
