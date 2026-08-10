"""
charon/gateway/middleware.py
System Version: v0.1.0 | File Revision: 1.2.0

Module: Local Network & Peripheral Node Authentication Boundary.

Enforces API key verification across HTTP connections for external clients, CLI tools,
and LAN network nodes communicating with charond.
Exempts dashboard assets, health checks, CORS preflight requests, and OpenAPI documentation routes.
"""

import logging
import secrets
from typing import List, Optional
from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from charon.config import API_KEY_HEADER_NAME, CHARON_API_KEY

logger = logging.getLogger("Charon.Gateway.Middleware")


class APIKeyMiddleware(BaseHTTPMiddleware):
    """HTTP Middleware inspecting incoming REST requests for valid authentication."""

    def __init__(self, app, public_paths: Optional[List[str]] = None):
        super().__init__(app)
        self.public_paths = public_paths or [
            "/v1/health",
            "/dashboard",
            "/favicon.ico",
            "/docs",
            "/openapi.json",
            "/redoc",
        ]

    async def dispatch(self, request: Request, call_next):
        # 1. CORS Preflight Bypass (OPTIONS requests do not carry Auth headers)
        if request.method == "OPTIONS":
            return await call_next(request)

        # 2. WebSocket Protocol Scope Pass-Through
        # (WebSocket authentication is handled directly in routes.py websocket_endpoint)
        if request.scope.get("type") == "websocket":
            return await call_next(request)

        # 3. Public Path Prefix Bypass
        path = request.url.path
        if any(
            path == p or path.startswith(f"{p.rstrip('/')}/")
            for p in self.public_paths
        ):
            return await call_next(request)

        # 4. Key Configuration Fail-Safe Check
        api_key_str = str(CHARON_API_KEY).strip() if CHARON_API_KEY else ""
        if not api_key_str:
            logger.critical("CHARON_API_KEY is unconfigured or empty! Rejecting request for safety.")
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": "Server security error: CHARON_API_KEY is unconfigured on host daemon."},
            )

        # 5. Multi-Channel Key Extraction (Header, Bearer Token, or Query Parameter)
        provided_key = None
        if API_KEY_HEADER_NAME:
            provided_key = request.headers.get(API_KEY_HEADER_NAME) or request.headers.get(API_KEY_HEADER_NAME.lower())

        # Fallback A: Authorization header ("Bearer <token>")
        if not provided_key and "authorization" in request.headers:
            auth_header = request.headers.get("authorization", "")
            if auth_header.lower().startswith("bearer "):
                provided_key = auth_header[7:].strip()

        # Fallback B: Query parameter (Required for constrained local nodes)
        if not provided_key:
            provided_key = request.query_params.get("api_key")

        # 6. Constant-Time Key Validation
        if not provided_key or not secrets.compare_digest(provided_key.strip(), api_key_str):
            client_ip = request.client.host if request.client else "Unknown"
            logger.warning(f"Unauthorized HTTP request to '{path}' blocked from IP: {client_ip}")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Invalid or missing API key token for HTTP access."},
            )

        return await call_next(request)