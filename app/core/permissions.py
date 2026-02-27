"""Permission system — controls which tools require user approval."""

import logging
from enum import Enum

logger = logging.getLogger(__name__)


class PermissionPolicy(str, Enum):
    ALWAYS_ALLOW = "always_allow"
    ASK_EVERY_TIME = "ask_every_time"
    DENY = "deny"


# Default policies for built-in tool namespaces
_DEFAULT_POLICIES: dict[str, PermissionPolicy] = {
    # System reads are always allowed
    "system_list_processes": PermissionPolicy.ALWAYS_ALLOW,
    "system_disk_usage": PermissionPolicy.ALWAYS_ALLOW,
    "system_system_info": PermissionPolicy.ALWAYS_ALLOW,
    # Journal reads require user confirmation (could expose sensitive logs)
    "system_journal_logs": PermissionPolicy.ASK_EVERY_TIME,
}


class PermissionManager:
    """Manages tool execution permissions backed by SQLite, with in-memory cache."""

    def __init__(self, db_get_fn) -> None:
        """
        Args:
            db_get_fn: Async callable that returns an aiosqlite.Connection.
        """
        self._get_db = db_get_fn
        self._cache: dict[str, PermissionPolicy] = dict(_DEFAULT_POLICIES)

    async def get_policy(self, tool_name: str) -> PermissionPolicy:
        """Look up permission policy for a tool.

        Priority: in-memory cache → SQLite DB → default (ask_every_time).
        """
        if tool_name in self._cache:
            return self._cache[tool_name]

        async with self._get_db() as db:
            async with db.execute(
                "SELECT policy FROM permissions WHERE tool_name = ?", (tool_name,)
            ) as cursor:
                row = await cursor.fetchone()

        if row:
            policy = PermissionPolicy(row["policy"])
            self._cache[tool_name] = policy
            return policy

        # Unknown tool → ask every time (safe default)
        return PermissionPolicy.ASK_EVERY_TIME

    async def set_policy(self, tool_name: str, policy: PermissionPolicy) -> None:
        """Persist a permission policy for a tool."""
        async with self._get_db() as db:
            await db.execute(
                "INSERT OR REPLACE INTO permissions (tool_name, policy) VALUES (?, ?)",
                (tool_name, policy.value),
            )
            await db.commit()
        self._cache[tool_name] = policy
        logger.info("Permission policy set: %s → %s", tool_name, policy.value)

    async def list_policies(self) -> list[dict[str, str]]:
        """List all stored permission policies."""
        async with self._get_db() as db:
            async with db.execute("SELECT tool_name, policy FROM permissions") as cursor:
                rows = await cursor.fetchall()
        stored = {row["tool_name"]: row["policy"] for row in rows}
        # Merge defaults + stored
        merged = {k: v.value for k, v in _DEFAULT_POLICIES.items()}
        merged.update(stored)
        return [{"tool_name": k, "policy": v} for k, v in merged.items()]
