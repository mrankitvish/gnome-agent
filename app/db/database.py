"""Async SQLite database connection manager."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import aiosqlite

from app.config import settings
from app.db.models import SCHEMA_SQL, DEFAULT_AGENT_SQL

logger = logging.getLogger(__name__)

_db_path: str = settings.database_path


async def init_db() -> None:
    """Create all tables and seed defaults."""
    async with aiosqlite.connect(_db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.executescript(SCHEMA_SQL)
        seed_sql = DEFAULT_AGENT_SQL.format(
            provider=settings.default_llm_provider,
            model=settings.default_llm_model,
        )
        await db.executescript(seed_sql)
        await db.commit()
    logger.info("Database initialized at %s", _db_path)


@asynccontextmanager
async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Async context manager for a SQLite connection.

    Usage:
        async with get_db() as db:
            await db.execute(...)
    """
    async with aiosqlite.connect(_db_path) as db:
        db.row_factory = aiosqlite.Row
        yield db
