"""Agents API — CRUD for agent profiles."""

import uuid
import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agents", tags=["agents"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    model_provider: str = Field(default="ollama")
    model_name: str = Field(default="llama3")
    system_prompt: str = Field(
        default="You are a helpful AI assistant with access to desktop and system tools."
    )
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_iterations: int = Field(default=6, ge=1, le=20)


class AgentResponse(BaseModel):
    id: str
    name: str
    model_provider: str
    model_name: str
    system_prompt: str
    temperature: float
    max_iterations: int
    created_at: str


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[AgentResponse])
async def list_agents(request: Request) -> list[dict]:
    """List all agent profiles."""
    db_get = request.app.state.db_get
    async with db_get() as db:
        async with db.execute("SELECT * FROM agents ORDER BY created_at DESC") as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: str, request: Request) -> dict:
    """Get a specific agent profile."""
    db_get = request.app.state.db_get
    async with db_get() as db:
        async with db.execute(
            "SELECT * FROM agents WHERE id = ?", (agent_id,)
        ) as cur:
            row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    return dict(row)


@router.post("", response_model=AgentResponse, status_code=201)
async def create_agent(body: AgentCreate, request: Request) -> dict:
    """Create a new agent profile."""
    db_get = request.app.state.db_get
    agent_id = str(uuid.uuid4())
    async with db_get() as db:
        await db.execute(
            """INSERT INTO agents
               (id, name, model_provider, model_name, system_prompt, temperature, max_iterations)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                agent_id,
                body.name,
                body.model_provider,
                body.model_name,
                body.system_prompt,
                body.temperature,
                body.max_iterations,
            ),
        )
        await db.commit()
        async with db.execute(
            "SELECT * FROM agents WHERE id = ?", (agent_id,)
        ) as cur:
            row = await cur.fetchone()
    logger.info("Created agent: %s (%s)", body.name, agent_id)
    # Invalidate cached agent if one exists
    request.app.state.agent_builder.invalidate(agent_id)
    return dict(row)


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(agent_id: str, request: Request) -> None:
    """Delete an agent profile."""
    if agent_id == "default":
        raise HTTPException(status_code=400, detail="Cannot delete the default agent")
    db_get = request.app.state.db_get
    async with db_get() as db:
        result = await db.execute(
            "DELETE FROM agents WHERE id = ?", (agent_id,)
        )
        await db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    request.app.state.agent_builder.invalidate(agent_id)
