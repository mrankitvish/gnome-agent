"""Session manager — lifecycle of chat sessions and message persistence."""

import logging
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)


class SessionManager:
    """Creates, retrieves, and persists chat sessions and messages."""

    def __init__(self, db_get_fn) -> None:
        """
        Args:
            db_get_fn: Async callable that returns an aiosqlite.Connection.
        """
        self._get_db = db_get_fn

    async def create_session(self, agent_id: str) -> str:
        """Create a new session for an agent. Returns the new session_id."""
        session_id = str(uuid.uuid4())
        async with self._get_db() as db:
            await db.execute(
                "INSERT INTO sessions (id, agent_id) VALUES (?, ?)",
                (session_id, agent_id),
            )
            await db.commit()
        logger.info("Created session %s for agent %s", session_id, agent_id)
        return session_id

    async def get_session(self, session_id: str) -> dict | None:
        """Look up a session record."""
        async with self._get_db() as db:
            async with db.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ) as cursor:
                row = await cursor.fetchone()
        return dict(row) if row else None

    async def list_sessions(self, agent_id: str | None = None) -> list[dict]:
        """List sessions, optionally filtered by agent."""
        async with self._get_db() as db:
            if agent_id:
                async with db.execute(
                    "SELECT * FROM sessions WHERE agent_id = ? ORDER BY created_at DESC",
                    (agent_id,),
                ) as cursor:
                    rows = await cursor.fetchall()
            else:
                async with db.execute(
                    "SELECT * FROM sessions ORDER BY created_at DESC"
                ) as cursor:
                    rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def add_message(
        self, session_id: str, role: str, content: str
    ) -> str:
        """Persist a message in a session. Returns the message id."""
        msg_id = str(uuid.uuid4())
        async with self._get_db() as db:
            await db.execute(
                "INSERT INTO messages (id, session_id, role, content) VALUES (?, ?, ?, ?)",
                (msg_id, session_id, role, content),
            )
            await db.commit()
        return msg_id

    async def get_messages(self, session_id: str) -> list[dict]:
        """Return all messages in a session, ordered chronologically."""
        async with self._get_db() as db:
            async with db.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,),
            ) as cursor:
                rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def log_tool_call(
        self,
        session_id: str,
        tool_name: str,
        arguments: str,
        result: str | None,
        approved: bool | None,
        latency_ms: int | None,
    ) -> None:
        """Record a tool execution in the audit log."""
        async with self._get_db() as db:
            await db.execute(
                """INSERT INTO tool_logs
                   (id, session_id, tool_name, arguments, result, approved, latency_ms)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid.uuid4()),
                    session_id,
                    tool_name,
                    arguments,
                    result,
                    approved,
                    latency_ms,
                ),
            )
            await db.commit()
