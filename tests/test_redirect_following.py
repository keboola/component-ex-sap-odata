"""SAP OData 307 trailing-slash redirect handling (CFTL-681).

SAP redirects .../SERVICE -> .../SERVICE/ with a 307. httpx does not follow
redirects by default, so loadServices / loadEntities / metadata fetches failed
with a "307 Temporary Redirect" error while Postman/browsers worked. The async
clients must follow redirects.
"""

import asyncio

import httpx
import respx

from odata_client.async_v4_client import AsyncODataV4Client

BASE = "https://sap.example.com/sap/opu/odata/sap/ZZ1_BILL_DOC_ITEM_QUERY_CDS"


def _make_client():
    return AsyncODataV4Client.from_basic_auth(
        username="u", password="p", base_url=BASE, max_retries=0
    )


def test_both_httpx_clients_follow_redirects():
    client = _make_client()
    assert client._client.client.follow_redirects is True
    assert client._probe_client.client.follow_redirects is True


def test_async_client_follows_307_trailing_slash_redirect():
    client = _make_client()

    async def _run():
        async with client._client as c:
            return await c.get_raw("Entity")

    with respx.mock:
        respx.get(f"{BASE}/Entity").mock(
            return_value=httpx.Response(307, headers={"Location": f"{BASE}/Entity/"})
        )
        respx.get(f"{BASE}/Entity/").mock(return_value=httpx.Response(200, json={"ok": True}))
        resp = asyncio.run(_run())

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
