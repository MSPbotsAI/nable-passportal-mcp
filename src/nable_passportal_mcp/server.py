import contextvars
import sys

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .api_client import PassportalClient
from .config import Settings

# ─────────────────────────────────────────────────────────────────────────────
# Per-request contextvars for gateway mode.
# GatewayTokenMiddleware sets these before the MCP handler runs.
# Python asyncio copies context per task, so concurrent requests are isolated —
# tokens and instance base URLs never bleed across tenants.
# ─────────────────────────────────────────────────────────────────────────────
_gateway_token_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "passportal_gateway_token", default=None
)
_gateway_base_url_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "passportal_gateway_base_url", default=None
)


def get_client_from_context(settings: Settings) -> PassportalClient | None:
    """Resolve the active PassportalClient for the current request context."""
    if settings.auth_mode == "gateway":
        token = _gateway_token_var.get()
        base_url = _gateway_base_url_var.get()
    else:
        token = settings.passportal_api_token
        base_url = settings.passportal_base_url

    if not token or not base_url:
        return None
    return PassportalClient(token, base_url, settings.passportal_auth_header)


class GatewayTokenMiddleware:
    """ASGI middleware for gateway mode.

    Reads the configured token and base-URL headers from each request and stores
    them in contextvars for the duration of that request. Returns 401 if either
    header is missing on /mcp requests.
    """

    def __init__(self, app: ASGIApp, settings: Settings):
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if not path.startswith("/mcp"):
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        # Header lookup is case-insensitive in Starlette
        token = request.headers.get(self.settings.passportal_auth_header.lower())
        base_url = request.headers.get(self.settings.passportal_base_url_header.lower())
        if not token or not base_url:
            response = JSONResponse(
                {
                    "error": "Missing credentials",
                    "message": (
                        f"Gateway mode requires the "
                        f"{self.settings.passportal_auth_header} and "
                        f"{self.settings.passportal_base_url_header} headers"
                    ),
                    "required_headers": [
                        self.settings.passportal_auth_header,
                        self.settings.passportal_base_url_header,
                    ],
                },
                status_code=401,
            )
            await response(scope, receive, send)
            return

        ctx_token = _gateway_token_var.set(token)
        ctx_base_url = _gateway_base_url_var.set(base_url)
        try:
            await self.app(scope, receive, send)
        finally:
            _gateway_token_var.reset(ctx_token)
            _gateway_base_url_var.reset(ctx_base_url)


def create_mcp_server(settings: Settings) -> FastMCP:
    """Build the FastMCP server instance and register all tools."""
    # DNS-rebinding protection is disabled because the container runs behind
    # mcp-gateway on an internal Docker network and is never publicly exposed.
    mcp = FastMCP(
        name="nable-passportal-mcp",
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    def client_factory() -> PassportalClient | None:
        return get_client_from_context(settings)

    if not settings.has_credentials:
        # Graceful degradation: register only a diagnostic tool when no credentials are available.
        @mcp.tool()
        async def passportal_test_connection() -> str:
            """Test Passportal API connection; shows config requirements if creds are missing."""
            return (
                "Error: Missing Passportal credentials.\n\n"
                "Set the required environment variables (env mode):\n"
                "  PASSPORTAL_API_TOKEN=your_token_here\n"
                "  PASSPORTAL_BASE_URL=https://instance.passportalmsp.com\n\n"
                "Or use gateway mode (per-request headers):\n"
                f"  AUTH_MODE=gateway\n"
                f"  Send headers: {settings.passportal_auth_header}: your_token_here\n"
                f"                {settings.passportal_base_url_header}: https://instance.passportalmsp.com"
            )

        print(
            "Warning: No Passportal credentials found. Only the diagnostic tool is available.",
            file=sys.stderr,
        )
        return mcp

    # Register all tool modules here.
    from .tools import documents

    documents.register(mcp, client_factory)

    return mcp
