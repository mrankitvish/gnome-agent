"""Auth and rate-limiting middleware for Gnome Agent Runtime.

Auth:   Simple Bearer token check via GNOME_AGENT_API_KEY env var.
        If the env var is unset or empty, auth is DISABLED (local dev default).

Rate:   Sliding-window in-memory rate limiter per IP.
        Configurable via GNOME_AGENT_RATE_LIMIT_RPM (0 = disabled).
"""

import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings


# ── Bearer Token Auth ─────────────────────────────────────────────────────────

class AuthMiddleware(BaseHTTPMiddleware):
    """Check Authorization: Bearer <token> on every request.

    Skips /health and /docs* so the runtime is still inspectable
    without a token in dev mode.

    When GNOME_AGENT_API_KEY is empty, middleware is a no-op.
    """

    _SKIP_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}

    async def dispatch(self, request: Request, call_next):
        if not settings.api_key:
            # Auth disabled — pass through
            return await call_next(request)

        path = request.url.path
        if any(path.startswith(skip) for skip in self._SKIP_PATHS):
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                {"detail": "Missing or malformed Authorization header. Expected: Bearer <token>"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = auth_header.removeprefix("Bearer ").strip()
        if token != settings.api_key:
            return JSONResponse(
                {"detail": "Invalid API key"},
                status_code=403,
            )

        return await call_next(request)


# ── Sliding-Window Rate Limiter ───────────────────────────────────────────────

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP sliding-window rate limiter.

    Window: 60 seconds.
    Limit:  GNOME_AGENT_RATE_LIMIT_RPM requests per window.
    When RPM is 0, middleware is a no-op.

    Adds X-RateLimit-Limit / X-RateLimit-Remaining / X-RateLimit-Reset headers.
    """

    def __init__(self, app, rpm: int = 0):
        super().__init__(app)
        self._rpm = rpm
        self._windows: dict[str, deque] = defaultdict(deque)  # ip → timestamps

    async def dispatch(self, request: Request, call_next):
        if self._rpm == 0:
            return await call_next(request)

        ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        window_start = now - 60.0

        q = self._windows[ip]
        # Evict old timestamps outside the window
        while q and q[0] < window_start:
            q.popleft()

        remaining = self._rpm - len(q)
        reset_in = int(60 - (now - q[0])) if q else 60

        if remaining <= 0:
            return JSONResponse(
                {"detail": f"Rate limit exceeded. Max {self._rpm} requests/minute."},
                status_code=429,
                headers={
                    "X-RateLimit-Limit": str(self._rpm),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_in),
                    "Retry-After": str(reset_in),
                },
            )

        q.append(now)
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self._rpm)
        response.headers["X-RateLimit-Remaining"] = str(remaining - 1)
        response.headers["X-RateLimit-Reset"] = str(reset_in)
        return response
