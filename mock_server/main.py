"""FastAPI mock of the LI.FI order server — local development only.

Implements just enough surface to run solver/main.py end-to-end without
touching order-dev.li.fi:
  POST /solver-api/account/register
  POST /quotes/submit
  GET  /solver-api/quotes
  WS   /ws/orders        (pushes a synthetic order every MOCK_INTERVAL)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import time
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect

log = logging.getLogger("mock")
logging.basicConfig(level=logging.INFO, format="[mock] %(message)s")

app = FastAPI(title="lifi-intents-mock")

_state: dict[str, Any] = {"quotes": [], "registered": False}
_ws_clients: set[WebSocket] = set()
_order_queue: list[dict] = []
_ORDER_QUEUE_MAX = 20

MOCK_INTERVAL = int(os.getenv("MOCK_INTERVAL_SECONDS", "15"))
MOCK_SIZE = int(os.getenv("MOCK_ORDER_SIZE_USDC", "50"))
SRC_CHAIN = int(os.getenv("SRC_CHAIN_ID", "84532"))
DST_CHAIN = int(os.getenv("DST_CHAIN_ID", "421614"))
SRC_TOKEN = os.getenv("SRC_TOKEN_ADDRESS", "0x" + "11" * 20)
DST_TOKEN = os.getenv("DST_TOKEN_ADDRESS", "0x" + "22" * 20)


@app.post("/solver-api/account/register")
async def register(req: Request) -> dict:
    body = await req.json()
    log.info("register %s", body.get("address"))
    _state["registered"] = True
    return {"ok": True}


@app.post("/quotes/submit")
async def submit_quotes(req: Request) -> dict:
    body = await req.json()
    if not isinstance(body, list):
        body = [body]
    _state["quotes"] = body
    log.info("accepted %d quote(s)", len(body))
    return {"accepted": len(body)}


@app.get("/solver-api/quotes")
async def get_quotes() -> list[dict]:
    return _state["quotes"]


@app.get("/orders")
async def get_orders() -> dict:
    """HTTP polling fallback — returns last N synthetic orders."""
    return {"orders": _order_queue}


@app.get("/chains/supported")
async def chains() -> dict:
    return {
        "chains": [
            {"id": SRC_CHAIN, "name": "Base Sepolia"},
            {"id": DST_CHAIN, "name": "Arbitrum Sepolia"},
        ]
    }


@app.websocket("/ws/orders")
async def ws_orders(ws: WebSocket) -> None:
    await ws.accept()
    _ws_clients.add(ws)
    log.info("ws client connected (total=%d)", len(_ws_clients))
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        _ws_clients.discard(ws)
        log.info("ws client gone (total=%d)", len(_ws_clients))


def _synthetic_order() -> dict:
    order_id = "0x" + secrets.token_hex(16)
    now = int(time.time())
    amount = MOCK_SIZE * (10 ** 6)
    return {
        "orderId": order_id,
        "originChainId": SRC_CHAIN,
        "fillDeadline": now + 300,
        "expires": now + 600,
        "user": "0x" + "ab" * 20,
        "nonce": now,
        "inputs": [[SRC_TOKEN, str(amount)]],
        "outputs": [{
            "chainId": DST_CHAIN,
            "token": DST_TOKEN,
            "amount": str(int(amount * 0.999)),
            "recipient": "0x" + "cd" * 20,
            "oracle": "0x" + "00" * 20,
            "settler": "0x" + "00" * 20,
            "call": "0x",
            "context": "0x",
        }],
    }


async def _push_loop() -> None:
    while True:
        await asyncio.sleep(MOCK_INTERVAL)
        order = _synthetic_order()

        _order_queue.append(order)
        if len(_order_queue) > _ORDER_QUEUE_MAX:
            _order_queue.pop(0)

        if not _ws_clients:
            log.info("▶ queued %s (%.2f USDC, no WS clients)",
                     order["orderId"][:18], MOCK_SIZE)
            continue

        msg = json.dumps({"event": "order.signed", "order": order})
        dead: list[WebSocket] = []
        for ws in _ws_clients:
            try:
                await ws.send_text(msg)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            _ws_clients.discard(ws)
        log.info("▶ pushed %s (%.2f USDC, %d WS clients)",
                 order["orderId"][:18], MOCK_SIZE, len(_ws_clients))


@app.on_event("startup")
async def _on_start() -> None:
    asyncio.create_task(_push_loop())
    log.info("mock server live, interval=%ds", MOCK_INTERVAL)
