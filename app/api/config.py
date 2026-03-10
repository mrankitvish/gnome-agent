import sqlite3
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/config", tags=["config"])


class AppConfigModel(BaseModel):
    provider: str
    model: str
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    system_prompt: str
    temperature: float
    max_iterations: int
    supports_tools: Optional[bool] = None
    supports_structured_output: Optional[bool] = None


@router.get("/providers")
async def list_providers():
    """List supported LLM providers."""
    providers = [
        {"id": "ollama", "name": "Ollama (Local)"},
        {"id": "openai", "name": "OpenAI"},
        {"id": "anthropic", "name": "Anthropic"},
        {"id": "google_genai", "name": "Google Gemini"},
        {"id": "mistralai", "name": "Mistral AI"},
        {"id": "openai_compatible", "name": "OpenAI Compatible (vLLM, LM Studio, etc.)"}
    ]
    return {"providers": providers}


@router.get("/llm", response_model=AppConfigModel)
async def get_config(request: Request):
    """Retrieve the global LLM configuration and check its capabilities."""
    async with request.app.state.db_get() as db:
        async with db.execute("SELECT * FROM app_config WHERE id = 1") as cur:
            row = await cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Configuration not found")
            
            config_dict = dict(row)
            
            # Check capabilities
            try:
                from app.core.llm_factory import get_llm
                from langchain_core.tools import tool
                from pydantic import BaseModel as PydanticBaseModel
                
                @tool
                def _dummy_tool(x: int) -> int:
                    """Dummy tool"""
                    return x
                    
                class _DummyModel(PydanticBaseModel):
                    name: str
                    
                llm = get_llm(
                    provider=config_dict["provider"],
                    model=config_dict["model"],
                    base_url=config_dict.get("base_url"),
                    api_key=config_dict.get("api_key")
                )
                
                try:
                    llm.bind_tools([_dummy_tool])
                    config_dict["supports_tools"] = True
                except Exception:
                    config_dict["supports_tools"] = False
                    
                try:
                    llm.with_structured_output(_DummyModel)
                    config_dict["supports_structured_output"] = True
                except Exception:
                    config_dict["supports_structured_output"] = False
                    
            except Exception as e:
                # If get_llm fails (e.g., missing API key or bad provider)
                config_dict["supports_tools"] = False
                config_dict["supports_structured_output"] = False
                
            return config_dict


@router.put("/llm", response_model=AppConfigModel)
async def update_config(request: Request, config: AppConfigModel):
    """Update the global LLM configuration."""
    async with request.app.state.db_get() as db:
        await db.execute(
            """
            UPDATE app_config 
            SET provider = ?, model = ?, base_url = ?, api_key = ?, 
                system_prompt = ?, temperature = ?, max_iterations = ?, 
                updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
            """,
            (
                config.provider,
                config.model,
                config.base_url,
                config.api_key,
                config.system_prompt,
                config.temperature,
                config.max_iterations,
            ),
        )
        await db.commit()
    
    # Return updated config without capabilities checked, 
    # the client can do a GET /config/llm to see the capabilities.
    return config
