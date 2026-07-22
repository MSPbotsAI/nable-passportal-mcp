from typing import Any

import httpx

# Fixed by Passportal's own API contract (not user-configurable, unlike the
# gateway-mode credential headers this container itself exposes): the bearer
# access token obtained via auth.get_access_token is sent as x-access-token.
ACCESS_TOKEN_HEADER = "x-access-token"


class PassportalError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"Passportal API error {status_code}: {message}")


class PassportalClient:
    """Async httpx client wrapping the N-able Passportal REST API (v2).

    Authentication uses the ``x-access-token`` header, carrying a short-lived
    access token obtained via the HMAC client-credentials exchange in
    ``auth.py`` (never the long-lived Access Key / Secret Access Key). The
    base URL is the customer instance root (e.g.
    ``https://instance.passportalmsp.com``); the ``/api/v2`` version prefix is
    included in the paths passed to the request methods.
    """

    def __init__(self, access_token: str, base_url: str):
        self._token = access_token
        self._base_url = base_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        return {
            ACCESS_TOKEN_HEADER: self._token,
            "Content-Type": "application/json",
        }

    def _clean_params(self, params: dict | None) -> dict:
        if not params:
            return {}
        return {k: v for k, v in params.items() if v is not None}

    async def get(self, path: str, params: dict | None = None) -> Any:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base_url}{path}",
                headers=self._headers(),
                params=self._clean_params(params),
            )
            self._raise_for_status(resp)
            return resp.json() if resp.status_code != 204 else None

    def _raise_for_status(self, resp: httpx.Response) -> None:
        if resp.status_code >= 400:
            try:
                detail = resp.json()
            except Exception:
                detail = resp.text
            raise PassportalError(resp.status_code, str(detail))
