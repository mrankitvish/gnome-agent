"""SQLite-backed LangGraph checkpointer for persistent conversation memory.

Replaces InMemorySaver so conversation threads survive server restarts.
"""

from __future__ import annotations

import logging
from typing import Any, Iterator

import aiosqlite
from langchain_core.load import dumps as lc_dumps, loads as lc_loads
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)

from app.config import settings

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS checkpoints (
    thread_id   TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    parent_checkpoint_id TEXT,
    checkpoint   TEXT NOT NULL,
    metadata     TEXT NOT NULL,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);

CREATE TABLE IF NOT EXISTS checkpoint_blobs (
    thread_id    TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    channel      TEXT NOT NULL,
    version      TEXT NOT NULL,
    type         TEXT NOT NULL,
    blob         BLOB,
    PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
);

CREATE TABLE IF NOT EXISTS checkpoint_writes (
    thread_id    TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    task_id      TEXT NOT NULL,
    idx          INTEGER NOT NULL,
    channel      TEXT NOT NULL,
    type         TEXT,
    blob         BLOB,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);
"""


class SQLiteCheckpointer(BaseCheckpointSaver):
    """Async SQLite checkpointer for LangGraph conversation threads.

    Each conversation session maps 1:1 to a LangGraph thread_id.
    All checkpoint data is stored in the main gnome_agent.db database.
    """

    def __init__(self, db_path: str | None = None) -> None:
        super().__init__()
        self._db_path = db_path or settings.database_path

    async def setup(self) -> None:
        """Create checkpoint tables if they don't exist."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(_SCHEMA)
            await db.commit()
        logger.debug("Checkpoint tables initialized")

    # ── Required BaseCheckpointSaver interface ────────────────────────────────

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        """Sync get — delegates to aiosqlite via run_until_complete."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.aget_tuple(config))
        except RuntimeError:
            return None

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        """Sync list — not heavily used; returns empty iterator as safe fallback."""
        return iter([])

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: dict[str, Any],
    ) -> RunnableConfig:
        """Sync put — delegates to async."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(
                self.aput(config, checkpoint, metadata, new_versions)
            )
        except RuntimeError:
            return config

    # ── Async interface (primary for FastAPI/LangGraph async usage) ───────────

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        """Load the latest (or specified) checkpoint for a thread."""
        thread_id = config["configurable"].get("thread_id", "")
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = config["configurable"].get("checkpoint_id")

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            if checkpoint_id:
                sql = """
                    SELECT * FROM checkpoints
                    WHERE thread_id=? AND checkpoint_ns=? AND checkpoint_id=?
                """
                params = (thread_id, checkpoint_ns, checkpoint_id)
            else:
                sql = """
                    SELECT * FROM checkpoints
                    WHERE thread_id=? AND checkpoint_ns=?
                    ORDER BY checkpoint_id DESC LIMIT 1
                """
                params = (thread_id, checkpoint_ns)

            async with db.execute(sql, params) as cur:
                row = await cur.fetchone()

        if not row:
            return None

        config_out: RunnableConfig = {
            "configurable": {
                "thread_id": row["thread_id"],
                "checkpoint_ns": row["checkpoint_ns"],
                "checkpoint_id": row["checkpoint_id"],
            }
        }
        parent_config: RunnableConfig | None = None
        if row["parent_checkpoint_id"]:
            parent_config = {
                "configurable": {
                    "thread_id": row["thread_id"],
                    "checkpoint_ns": row["checkpoint_ns"],
                    "checkpoint_id": row["parent_checkpoint_id"],
                }
            }

        return CheckpointTuple(
            config=config_out,
            checkpoint=lc_loads(row["checkpoint"]),
            metadata=lc_loads(row["metadata"]),
            parent_config=parent_config,
        )

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: dict[str, Any],
    ) -> RunnableConfig:
        """Persist a checkpoint to SQLite."""
        thread_id = config["configurable"].get("thread_id", "")
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = checkpoint["id"]
        parent_id = config["configurable"].get("checkpoint_id")

        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO checkpoints
                (thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, checkpoint, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    thread_id,
                    checkpoint_ns,
                    checkpoint_id,
                    parent_id,
                    lc_dumps(checkpoint),
                    lc_dumps(metadata),
                ),
            )
            await db.commit()

        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
        }

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: list[tuple[str, Any]],
        task_id: str,
    ) -> None:
        """Persist pending writes (intermediate channel values) for a checkpoint."""
        thread_id = config["configurable"].get("thread_id", "")
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = config["configurable"].get("checkpoint_id", "")

        async with aiosqlite.connect(self._db_path) as db:
            for idx, (channel, value) in enumerate(writes):
                try:
                    serialized = lc_dumps(value)
                    type_ = "lc"
                except Exception:
                    serialized = str(value)
                    type_ = "str"

                await db.execute(
                    """
                    INSERT OR REPLACE INTO checkpoint_writes
                    (thread_id, checkpoint_ns, checkpoint_id, task_id, idx, channel, type, blob)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (thread_id, checkpoint_ns, checkpoint_id, task_id, idx, channel, type_, serialized),
                )
            await db.commit()
