import os

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = structlog.get_logger(__name__)

INTERNAL_API_SECRET = os.environ.get("INTERNAL_API_SECRET", "")


class InternalTokenMiddleware(BaseHTTPMiddleware):
    """Validate that requests come from an authorized internal service.

    Checks the X-Internal-Token header against a shared secret.
    This replaces the enterprise-only @auth.authenticate handler
    for self-hosted lite deployments.
    """

    async def dispatch(self, request: Request, call_next):
        # Allow health check without token
        if request.url.path == "/ok":
            return await call_next(request)

        token = request.headers.get("X-Internal-Token", "")
        if not INTERNAL_API_SECRET or token != INTERNAL_API_SECRET:
            logger.warning(
                "Request rejected: invalid or missing internal token",
                path=request.url.path,
            )
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing internal token"},
            )

        return await call_next(request)
