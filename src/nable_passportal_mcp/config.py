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
    # "gateway" — production/SOP-compliant: credentials + instance base URL from HTTP
    #             headers per request (no global state).
    # "env"     — local dev only: shared credentials/base URL from environment
    #             variables (not SOP-compliant).
    auth_mode: Literal["env", "gateway"] = "gateway"

    # Passportal API is OAuth2 client-credentials, HMAC-signed: a long-lived
    # Access Key / Secret Access Key pair is exchanged for a short-lived (~55
    # minute) bearer access token per auth.py. These three fields are the
    # long-lived credentials (only required in env mode); in gateway mode they
    # come from per-request headers instead. The server performs the exchange
    # itself — callers never handle the access token or the HMAC directly.
    passportal_access_key: str | None = None
    passportal_secret_key: str | None = None
    # Per-customer instance base URL, e.g. https://instance.passportalmsp.com
    passportal_base_url: str | None = None

    # Header names used to pass the credentials and instance base URL in
    # gateway mode. The client must include ALL THREE headers on every /mcp
    # request.
    passportal_access_key_header: str = "x-passportal-access-key"
    passportal_secret_key_header: str = "x-passportal-secret-key"
    passportal_base_url_header: str = "x-passportal-base-url"

    # Scope requested at token-exchange time — fixed by Passportal's Documents
    # API, not user-configurable in practice, but kept as a setting in case a
    # future tool set needs a different scope.
    passportal_token_scope: str = "docs_api"

    @property
    def has_credentials(self) -> bool:
        """Returns True if the server can serve API calls.

        Gateway mode always returns True — each request carries its own
        credentials and instance base URL via headers.
        Env mode requires PASSPORTAL_ACCESS_KEY, PASSPORTAL_SECRET_KEY, and
        PASSPORTAL_BASE_URL.
        """
        if self.auth_mode == "gateway":
            return True
        return bool(
            self.passportal_access_key and self.passportal_secret_key and self.passportal_base_url
        )


def get_settings() -> Settings:
    return Settings()
