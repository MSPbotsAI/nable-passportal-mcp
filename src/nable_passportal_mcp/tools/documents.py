"""Passportal Documents tools.

Tool naming convention: <vendor>_<action>_<resource>
"""

import json
from collections.abc import Callable

from mcp.server.fastmcp import FastMCP

from ..api_client import PassportalClient, PassportalError

_NO_TOKEN = (
    "Error: No Passportal credentials configured. Set PASSPORTAL_API_TOKEN + "
    "PASSPORTAL_BASE_URL, or use AUTH_MODE=gateway and pass the x-api-token and "
    "x-passportal-base-url headers per request."
)

# Valid values for the `type` (template type) filter, per Passportal API v2.
_DOCUMENT_TYPES = (
    "asset, active_directory, application, backup, email, file_sharing, contact, "
    "location, internet, lan, printing, remote_access, vendor, virtualization, "
    "voice, wireless, licencing, custom, ssl"
)


def register(mcp: FastMCP, client_factory: Callable[[], PassportalClient | None]) -> None:
    @mcp.tool()
    async def passportal_list_documents(
        resultsPerPage: int | None = None,
        pageNum: int | None = None,
        orderBy: str | None = None,
        orderDir: str | None = None,
        type: str | None = None,
        templateUid: str | None = None,
        clientId: int | None = None,
        searchTxt: str | None = None,
    ) -> str:
        """List documents from N-able Passportal (GET /api/v2/documents).

        Args:
            resultsPerPage: Positive integer — number of results returned per page.
            pageNum: Positive integer — the page number / index.
            orderBy: Attribute to order by. One of: label, id.
            orderDir: Sort direction. One of: asc, desc.
            type: Template type filter. One of: asset, active_directory,
                application, backup, email, file_sharing, contact, location,
                internet, lan, printing, remote_access, vendor, virtualization,
                voice, wireless, licencing, custom, ssl.
            templateUid: Filter by specific template. Accepts a UID or ID
                (e.g. "tpl-101" or "101").
            clientId: Client identifier filter.
            searchTxt: Free-text search across document attributes.
        """
        client = client_factory()
        if client is None:
            return _NO_TOKEN
        try:
            result = await client.get(
                "/api/v2/documents",
                params={
                    "resultsPerPage": resultsPerPage,
                    "pageNum": pageNum,
                    "orderBy": orderBy,
                    "orderDir": orderDir,
                    "type": type,
                    "templateUid": templateUid,
                    "clientId": clientId,
                    "searchTxt": searchTxt,
                },
            )
            return json.dumps(result, indent=2)
        except PassportalError as e:
            return f"Error: {e}"
