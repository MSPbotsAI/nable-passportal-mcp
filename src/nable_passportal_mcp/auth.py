"""Passportal client-credentials token exchange (HMAC-SHA256 signed).

Passportal does not accept a long-lived static token. Instead it issues a
short-lived (~55 minute) bearer access token from a long-lived Access Key /
Secret Access Key pair via `POST {base_url}/api/v2/auth/client_token`:

  - `x-key`  header carries the Access Key (public identifier).
  - `x-hash` header carries HMAC-SHA256(secret_access_key, content), hex-encoded.
  - the JSON body repeats `content` (the exact plaintext that was hashed) plus
    a fixed `scope`.
  - the response carries `access_token` and `expiry_time` (Unix seconds).

That `access_token` is then sent as the `x-access-token` header on real
Documents API calls (see api_client.py) — this module never talks to the
Documents API itself, only to the auth endpoint.

Docs:
  https://documentation.n-able.com/passportal/userguide/Content/api/api_authorization.htm
  https://documentation.n-able.com/passportal/userguide/Content/api/api_create_hmac.htm
"""

import asyncio
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

import httpx

TOKEN_PATH = "/api/v2/auth/client_token"
DEFAULT_SCOPE = "docs_api"
DEFAULT_TOKEN_TTL_SECONDS = 55 * 60  # fallback if the response omits expiry_time
_CONTENT_NBYTES = 16  # length of the random plaintext signed per exchange


class PassportalAuthError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"Passportal auth error {status_code}: {message}")


def compute_x_hash(secret_access_key: str, content: str) -> str:
    """HMAC-SHA256(secret_access_key, content), lowercase hex — Passportal's `x-hash`."""
    digest = hmac.new(
        secret_access_key.encode("utf-8"),
        content.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return digest.hex()


@dataclass
class _CachedToken:
    access_token: str
    expires_at: float  # wall-clock (time.time()) seconds


# In-process token cache, keyed by a fingerprint of (base_url, access_key,
# secret_key) — never by tenant identity, and the secret itself is never used
# as a dict key verbatim. This holds only the short-lived derived access
# token, not the long-lived secret, and exists purely so that the ~dozens of
# tool calls an MCP session makes inside a ~55 minute window don't each pay
# for a fresh HMAC exchange round trip.
_cache: dict[str, _CachedToken] = {}
_cache_lock = asyncio.Lock()


def _cache_key(base_url: str, access_key: str, secret_key: str) -> str:
    fingerprint = f"{base_url}|{access_key}|{secret_key}".encode()
    return hashlib.sha256(fingerprint).hexdigest()


async def _fetch_token(base_url: str, access_key: str, secret_key: str, scope: str) -> _CachedToken:
    content = secrets.token_hex(_CONTENT_NBYTES)
    x_hash = compute_x_hash(secret_key, content)
    url = f"{base_url.rstrip('/')}{TOKEN_PATH}"
    headers = {
        "Content-Type": "application/json",
        "x-key": access_key,
        "x-hash": x_hash,
    }
    body = {"scope": scope, "content": content}
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, headers=headers, json=body)
    if resp.status_code >= 400:
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text
        raise PassportalAuthError(resp.status_code, str(detail))
    try:
        payload = resp.json()
    except ValueError as e:
        raise PassportalAuthError(resp.status_code, f"non-JSON response: {resp.text}") from e
    access_token = payload.get("access_token")
    if not access_token:
        raise PassportalAuthError(resp.status_code, f"no access_token in response: {payload}")
    expiry_time = payload.get("expiry_time")
    expires_at = float(expiry_time) if expiry_time else time.time() + DEFAULT_TOKEN_TTL_SECONDS
    return _CachedToken(access_token=access_token, expires_at=expires_at)


async def get_access_token(
    base_url: str,
    access_key: str,
    secret_key: str,
    scope: str = DEFAULT_SCOPE,
    skew_seconds: int = 60,
) -> str:
    """Return a valid Passportal access token for (base_url, access_key, secret_key),
    reusing a cached one until it's within `skew_seconds` of expiry, otherwise
    performing a fresh HMAC-signed client_token exchange."""
    key = _cache_key(base_url, access_key, secret_key)
    now = time.time()

    async with _cache_lock:
        cached = _cache.get(key)
        if cached and cached.expires_at - now > skew_seconds:
            return cached.access_token

    fresh = await _fetch_token(base_url, access_key, secret_key, scope)

    async with _cache_lock:
        _cache[key] = fresh
    return fresh.access_token
