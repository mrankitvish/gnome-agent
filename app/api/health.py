"""Health check endpoint."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Return server health status."""
    return {"status": "ok", "version": "0.1.0"}
