"""Chat API — SSE streaming endpoint for agent interactions."""

import json
import logging
import time
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.core.toon_utils import toon_context, toon_safe

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class ChatContext(BaseModel):
    """Optional GNOME desktop context injected into the agent state."""
    active_app: str | None = None
    current_path: str | None = None
    clipboard: str | None = None


class ChatRequest(BaseModel):
    agent_id: str = Field(default="default")
    session_id: str | None = Field(
        default=None,
        description="Existing session ID. If None, a new session is created.",
    )
    message: str = Field(..., min_length=1)
    context: ChatContext = Field(default_factory=ChatContext)


# ── SSE Event helpers ─────────────────────────────────────────────────────────

def _event(event_type: str, data: dict) -> dict:
    return {"event": event_type, "data": json.dumps(data)}


# ── Route ─────────────────────────────────────────────────────────────────────

@router.post("/chat")
async def chat(body: ChatRequest, request: Request):
    """Stream an agent response as Server-Sent Events.

    Event types:
    - ``session``      — session_id for this conversation
    - ``message``      — incremental assistant text token (if model supports streaming)
    - ``tool_call``    — a tool is being invoked
    - ``tool_result``  — result of a tool invocation
    - ``final_answer`` — agent has finished; full response text
    - ``error``        — an error occurred
    """
    db_get = request.app.state.db_get
    session_manager = request.app.state.session_manager
    agent_builder = request.app.state.agent_builder

    # ── Resolve agent config ──────────────────────────────────────────────────
    async with db_get() as db:
        async with db.execute(
            "SELECT * FROM agents WHERE id = ?", (body.agent_id,)
        ) as cur:
            agent_row = await cur.fetchone()

    if not agent_row:
        raise HTTPException(
            status_code=404, detail=f"Agent '{body.agent_id}' not found"
        )
    agent_cfg = dict(agent_row)

    # ── Resolve or create session ─────────────────────────────────────────────
    session_id = body.session_id
    if session_id:
        session = await session_manager.get_session(session_id)
        if not session:
            raise HTTPException(
                status_code=404, detail=f"Session '{session_id}' not found"
            )
    else:
        session_id = await session_manager.create_session(body.agent_id)

    # ── Persist user message ──────────────────────────────────────────────────
    await session_manager.add_message(session_id, "user", body.message)

    # ── Build TOON-compressed context injection ────────────────────────────────
    ctx = body.context
    context_data = {
        k: v for k, v in {
            "active_app": ctx.active_app,
            "current_path": ctx.current_path,
            "clipboard": ctx.clipboard[:500] if ctx.clipboard else None,
        }.items() if v
    }

    # ── Get or build agent ────────────────────────────────────────────────────
    agent = agent_builder.build(
        body.agent_id,
        provider=agent_cfg["model_provider"],
        model=agent_cfg["model_name"],
        system_prompt=agent_cfg["system_prompt"],
        temperature=agent_cfg["temperature"],
        max_iterations=agent_cfg["max_iterations"],
    )

    # ── Prepare input messages ────────────────────────────────────────────────
    user_content = body.message
    if context_data:
        toon_ctx = toon_context(context_data)
        user_content = (
            "[Desktop Context — TOON]\n"
            + toon_ctx
            + "\n\n[User Message]\n"
            + body.message
        )

    input_messages = {"messages": [{"role": "user", "content": user_content}]}
    # thread_id maps session → LangGraph checkpointer thread
    config = {"configurable": {"thread_id": session_id}}

    async def event_generator() -> AsyncGenerator[dict, None]:
        # Send session info first
        yield _event("session", {"session_id": session_id})

        final_text = ""

        try:
            async for chunk in agent.astream(input_messages, config=config):
                # LangGraph streams chunks as dicts keyed by node name.
                # Some control chunks may have None values — skip those.
                if not isinstance(chunk, dict):
                    continue

                for node_name, node_output in chunk.items():
                    if node_output is None:
                        continue

                    # node_output is usually {"messages": [...]}
                    messages = (
                        node_output.get("messages", [])
                        if isinstance(node_output, dict)
                        else []
                    )

                    for msg in messages:
                        msg_type = type(msg).__name__

                        # AIMessage — text content or tool call request
                        if msg_type == "AIMessage":
                            if hasattr(msg, "tool_calls") and msg.tool_calls:
                                for tc in msg.tool_calls:
                                    tool_info = {
                                        "tool_name": tc["name"],
                                        "arguments": tc.get("args", {}),
                                        "call_id": tc.get("id", str(uuid.uuid4())),
                                    }
                                    yield _event("tool_call", tool_info)
                                    logger.debug(
                                        "Tool call: %s(%s)", tc["name"], tc.get("args")
                                    )
                            elif msg.content:
                                content = (
                                    msg.content
                                    if isinstance(msg.content, str)
                                    else str(msg.content)
                                )
                                final_text = content
                                yield _event("message", {"text": content})

                        # ToolMessage — result of a tool execution
                        elif msg_type == "ToolMessage":
                            t_start = time.monotonic()
                            result_content = (
                                msg.content
                                if isinstance(msg.content, str)
                                else json.dumps(msg.content)
                            )
                            latency = int((time.monotonic() - t_start) * 1000)
                            tool_result = {
                                "tool_name": getattr(msg, "name", "unknown"),
                                "result": result_content[:2000],
                                "call_id": getattr(msg, "tool_call_id", None),
                            }
                            yield _event("tool_result", tool_result)

                            # Audit log
                            await session_manager.log_tool_call(
                                session_id=session_id,
                                tool_name=getattr(msg, "name", "unknown"),
                                arguments=json.dumps({}),
                                result=result_content[:5000],
                                approved=True,
                                latency_ms=latency,
                            )

        except Exception as e:
            logger.exception("Agent error for session %s: %s", session_id, e)
            yield _event("error", {"message": str(e)})
            return

        # ── Persist assistant reply and send final_answer ─────────────────────
        if final_text:
            await session_manager.add_message(session_id, "assistant", final_text)
        yield _event("final_answer", {"text": final_text, "session_id": session_id})

    return EventSourceResponse(event_generator())
