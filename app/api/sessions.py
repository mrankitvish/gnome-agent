"""Sessions history API — list sessions and message history."""

import logging
from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("")
async def list_sessions(request: Request, agent_id: str | None = None) -> list[dict]:
    """List all chat sessions, optionally filtered by agent.

    Query params:
        agent_id: Optional, filter sessions by this agent.
    """
    session_manager = request.app.state.session_manager
    return await session_manager.list_sessions(agent_id=agent_id)


@router.get("/{session_id}")
async def get_session(session_id: str, request: Request) -> dict:
    """Get a single session record."""
    session_manager = request.app.state.session_manager
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return session


@router.get("/{session_id}/messages")
async def get_session_messages(session_id: str, request: Request) -> list[dict]:
    """Get all messages in a session, ordered chronologically."""
    session_manager = request.app.state.session_manager
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return await session_manager.get_messages(session_id)


@router.delete("/{session_id}", status_code=204)
async def delete_session(session_id: str, request: Request) -> None:
    """Delete a session and all its messages (CASCADE)."""
    db_get = request.app.state.db_get
    async with db_get() as db:
        result = await db.execute(
            "DELETE FROM sessions WHERE id = ?", (session_id,)
        )
        await db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    logger.info("Deleted session %s", session_id)
