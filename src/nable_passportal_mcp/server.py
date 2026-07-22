import contextvars
import sys

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from . import auth
from .api_client import PassportalClient
from .config import Settings

# ─────────────────────────────────────────────────────────────────────────────
# Per-request contextvars for gateway mode.
# GatewayTokenMiddleware sets these before the MCP handler runs.
# Python asyncio copies context per task, so concurrent requests are isolated —
# credentials and instance base URLs never bleed across tenants.
# ─────────────────────────────────────────────────────────────────────────────
_gateway_access_key_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "passportal_gateway_access_key", default=None
)
_gateway_secret_key_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "passportal_gateway_secret_key", default=None
)
_gateway_base_url_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "passportal_gateway_base_url", default=None
)


async def get_client_from_context(settings: Settings) -> PassportalClient | None:
    """Resolve the active PassportalClient for the current request context.

    Performs the HMAC client-credentials token exchange (auth.get_access_token,
    cached ~55 minutes) and wraps the resulting short-lived access token in a
    PassportalClient. Raises auth.PassportalAuthError if the exchange fails
    (bad Access Key / Secret Access Key, unreachable instance, etc.) — callers
    should catch it alongside PassportalError.
    """
    if settings.auth_mode == "gateway":
        access_key = _gateway_access_key_var.get()
        secret_key = _gateway_secret_key_var.get()
        base_url = _gateway_base_url_var.get()
    else:
        access_key = settings.passportal_access_key
        secret_key = settings.passportal_secret_key
        base_url = settings.passportal_base_url

    if not access_key or not secret_key or not base_url:
        return None
    token = await auth.get_access_token(
        base_url, access_key, secret_key, settings.passportal_token_scope
    )
    return PassportalClient(token, base_url)


class GatewayTokenMiddleware:
    """ASGI middleware for gateway mode.

    Reads the configured Access Key, Secret Access Key, and base-URL headers
    from each request and stores them in contextvars for the duration of that
    request. Returns 401 if any header is missing on /mcp requests. The
    Secret Access Key never leaves the process — it is used in-process to
    compute the HMAC signature (auth.py) and is never logged or forwarded.
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
        access_key = request.headers.get(self.settings.passportal_access_key_header.lower())
        secret_key = request.headers.get(self.settings.passportal_secret_key_header.lower())
        base_url = request.headers.get(self.settings.passportal_base_url_header.lower())
        if not access_key or not secret_key or not base_url:
            required = [
                self.settings.passportal_access_key_header,
                self.settings.passportal_secret_key_header,
                self.settings.passportal_base_url_header,
            ]
            response = JSONResponse(
                {
                    "error": "Missing credentials",
                    "message": f"Gateway mode requires the {', '.join(required)} headers",
                    "required_headers": required,
                },
                status_code=401,
            )
            await response(scope, receive, send)
            return

        ctx_access_key = _gateway_access_key_var.set(access_key)
        ctx_secret_key = _gateway_secret_key_var.set(secret_key)
        ctx_base_url = _gateway_base_url_var.set(base_url)
        try:
            await self.app(scope, receive, send)
        finally:
            _gateway_access_key_var.reset(ctx_access_key)
            _gateway_secret_key_var.reset(ctx_secret_key)
            _gateway_base_url_var.reset(ctx_base_url)


def create_mcp_server(settings: Settings) -> FastMCP:
    """Build the FastMCP server instance and register all tools."""
    # DNS-rebinding protection is disabled because the container runs behind
    # mcp-gateway on an internal Docker network and is never publicly exposed.
    mcp = FastMCP(
        name="nable-passportal-mcp",
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    async def client_factory() -> PassportalClient | None:
        return await get_client_from_context(settings)

    if not settings.has_credentials:
        # Graceful degradation: register only a diagnostic tool when no credentials are available.
        @mcp.tool()
        async def passportal_test_connection() -> str:
            """Test Passportal API connection; shows config requirements if creds are missing."""
            return (
                "Error: Missing Passportal credentials.\n\n"
                "Set the required environment variables (env mode):\n"
                "  PASSPORTAL_ACCESS_KEY=your_access_key\n"
                "  PASSPORTAL_SECRET_KEY=your_secret_access_key\n"
                "  PASSPORTAL_BASE_URL=https://instance.passportalmsp.com\n\n"
                "Or use gateway mode (per-request headers):\n"
                f"  AUTH_MODE=gateway\n"
                f"  Send headers: {settings.passportal_access_key_header}: your_access_key\n"
                f"                {settings.passportal_secret_key_header}: your_secret_access_key\n"
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
