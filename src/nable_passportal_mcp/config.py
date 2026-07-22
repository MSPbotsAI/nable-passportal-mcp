from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Transport
    mcp_transport: Literal["stdio", "http"] = "http"
    mcp_http_port: int = 8080
    mcp_http_host: str = "0.0.0.0"

    # Auth mode:
    # "gateway" — production/SOP-compliant: token + instance base URL from HTTP headers
    #             per request (no global state).
    # "env"     — local dev only: shared token/base URL from environment variables
    #             (not SOP-compliant).
    auth_mode: Literal["env", "gateway"] = "gateway"

    # Passportal credentials / instance (only required in env mode).
    # In gateway mode these come from per-request headers instead.
    passportal_api_token: str | None = None
    # Per-customer instance base URL, e.g. https://instance.passportalmsp.com
    passportal_base_url: str | None = None

    # Header names used to pass the token and instance base URL in gateway mode.
    # The client must include BOTH headers on every /mcp request.
    passportal_auth_header: str = "x-api-token"
    passportal_base_url_header: str = "x-passportal-base-url"

    @property
    def has_credentials(self) -> bool:
        """Returns True if the server can serve API calls.

        Gateway mode always returns True — each request carries its own token
        and instance base URL via headers.
        Env mode requires both PASSPORTAL_API_TOKEN and PASSPORTAL_BASE_URL.
        """
        if self.auth_mode == "gateway":
            return True
        return bool(self.passportal_api_token and self.passportal_base_url)


def get_settings() -> Settings:
    return Settings()
