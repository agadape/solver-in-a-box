"""Thin async wrapper around the LI.FI Intents order server.

Mirrors the endpoints documented at
https://docs.li.fi/lifi-intents/for-solvers/api-overview
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)


class OrderServerClient:
    def __init__(self, base_url: str, api_key: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["api-key"] = api_key
        self._client = httpx.AsyncClient(
            base_url=self.base_url, headers=headers, timeout=10.0
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _post(self, path: str, payload: Any) -> dict:
        r = await self._client.post(path, json=payload)
        log.debug("POST %s -> %s", path, r.status_code)
        r.raise_for_status()
        return r.json() if r.content else {}

    async def _get(self, path: str, params: dict | None = None) -> dict:
        r = await self._client.get(path, params=params)
        log.debug("GET %s -> %s", path, r.status_code)
        r.raise_for_status()
        return r.json() if r.content else {}

    # --- Solver-side endpoints ---

    async def register_account(self, address: str, signed_message: str) -> dict:
        return await self._post(
            "/solver-api/account/register",
            {"address": address, "signature": signed_message},
        )

    async def submit_quotes(self, quotes: list[dict]) -> dict:
        return await self._post("/quotes/submit", quotes)

    async def get_my_quotes(self) -> dict:
        return await self._get("/solver-api/quotes")

    async def submit_trust_components(self, components: list[dict]) -> dict:
        return await self._post("/quotes/trustComponents", components)

    # --- Integrator-side (used by mock/orderflow fallback) ---

    async def get_chains(self) -> dict:
        return await self._get("/chains/supported")

    async def get_orders(self, **filters: Any) -> dict:
        return await self._get("/orders", params=filters)

    async def get_order_status(self, order_id: str) -> dict:
        return await self._get("/orders/status", params={"onChainOrderId": order_id})
