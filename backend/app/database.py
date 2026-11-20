"""The DuckDB file, opened read-only once per process.

DuckDB connections are not safe to share between threads, but cursors made
from one are, so every query gets its own cursor and runs in a worker thread,
keeping the event loop free.
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb


@dataclass
class Rows:
    columns: list[str]
    rows: list[dict[str, Any]]


class Database:
    def __init__(self, path: Path):
        self.path = path
        self._conn = duckdb.connect(str(path), read_only=True)
        self.hex_columns: frozenset[str] = frozenset(
            name
            for (name,) in self._conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'hexes'"
            ).fetchall()
        )
        self.microzones: tuple[str, ...] = tuple(
            name
            for (name,) in self._conn.execute(
                "SELECT DISTINCT mz_id FROM hexes WHERE mz_id IS NOT NULL ORDER BY 1"
            ).fetchall()
        )

    def query_sync(self, sql: str, params: list[Any] | dict[str, Any] | None = None) -> Rows:
        cursor = self._conn.cursor()
        try:
            result = cursor.execute(sql, params or [])
            columns = [d[0] for d in result.description or []]
            return Rows(
                columns, [dict(zip(columns, row, strict=True)) for row in result.fetchall()]
            )
        finally:
            cursor.close()

    async def query(self, sql: str, params: list[Any] | dict[str, Any] | None = None) -> Rows:
        return await asyncio.to_thread(self.query_sync, sql, params)

    def close(self) -> None:
        self._conn.close()


_db: Database | None = None


def open_database(path: Path) -> Database:
    global _db
    if _db is not None:
        _db.close()
    _db = Database(path)
    return _db


def close_database() -> None:
    global _db
    if _db is not None:
        _db.close()
        _db = None


def get_db() -> Database:
    """FastAPI dependency."""
    if _db is None:
        raise RuntimeError("the database is not open")
    return _db
