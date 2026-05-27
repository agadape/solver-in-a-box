"""Solver-in-a-Box main daemon.

Lifecycle:
    register -> submit_quotes (loop) -> listen_orders (loop) ->
        evaluate -> fill -> wait_attest -> finalise

Each function maps 1:1 to a section of the LI.FI Intents solver docs.
Read top-to-bottom; no framework magic.
"""
from __future__ import annotations

import asyncio
import json
import logging
import signal
import time
from decimal import Decimal
from typing import Any

import websockets

from solver import config as cfg_mod
from solver.api_client import OrderServerClient
from solver.chain import ChainExecutor, sign_registration


# ---------- logging ----------

def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


log = logging.getLogger("solver")


# ---------- registration ----------

async def register(client: OrderServerClient, cfg: cfg_mod.Config) -> None:
    if cfg.mode == "mock":
        log.info("[mock] skipping registration")
        return
    ts = int(time.time())
    sig = sign_registration(cfg.solver_pk, cfg.solver_address, ts)
    log.info("registering solver %s ...", cfg.solver_address)
    await client.register_account(cfg.solver_address, sig)
    log.info("  ✓ registered")


# ---------- quote curve ----------

def build_curve(cfg: cfg_mod.Config) -> dict:
    """Construct one standing-quote payload.

    Spread is applied uniformly across two ranges (small + large). Real
    solvers vary spread by size; this is intentionally naive.
    """
    spread = Decimal(cfg.spread_bps) / Decimal(10_000)
    rate_small = Decimal(1) - spread
    rate_large = Decimal(1) - (spread / 2)

    unit = Decimal(10) ** cfg.route.src_decimals

    def to_wei(units: int) -> str:
        return str(int(Decimal(units) * unit))

    return {
        "expiry": int(time.time()) + cfg.expiry_seconds,
        "fromChainId": cfg.route.src_chain_id,
        "toChainId": cfg.route.dst_chain_id,
        "fromAsset": cfg.route.src_token,
        "toAsset": cfg.route.dst_token,
        "fromDecimals": cfg.route.src_decimals,
        "toDecimals": cfg.route.dst_decimals,
        "ranges": [
            {
                "minAmount": to_wei(cfg.range_min_units),
                "maxAmount": to_wei(cfg.range_min_units * 100),
                "quote": f"{rate_small:.6f}",
            },
            {
                "minAmount": to_wei(cfg.range_min_units * 100),
                "maxAmount": to_wei(cfg.range_max_units),
                "quote": f"{rate_large:.6f}",
            },
        ],
        "exclusiveFor": "0x0000000000000000000000000000000000000000",
    }


async def quote_loop(client: OrderServerClient, cfg: cfg_mod.Config) -> None:
    while True:
        curve = build_curve(cfg)
        log.info(
            "posting curve %s->%s spread=%dbps",
            cfg.route.src_chain_id,
            cfg.route.dst_chain_id,
            cfg.spread_bps,
        )
        try:
            await client.submit_quotes([curve])
            log.info("  ✓ curve accepted")
        except Exception as exc:  # noqa: BLE001
            log.warning("  ✗ submit_quotes failed: %s", exc)
        await asyncio.sleep(cfg.refresh_seconds)


# ---------- order evaluation ----------

def evaluate(order: dict, cfg: cfg_mod.Config) -> tuple[bool, str]:
    """Decide whether to fill. Return (decision, reason)."""
    deadline = int(order.get("fillDeadline", 0))
    now = int(time.time())
    if deadline - now < cfg.min_buffer_seconds:
        return False, f"deadline too close ({deadline - now}s)"

    src_chain = order.get("originChainId")
    if src_chain != cfg.route.src_chain_id:
        return False, f"src chain mismatch ({src_chain})"

    outs = order.get("outputs", [])
    if not outs:
        return False, "no outputs"

    return True, "match"


# ---------- order listener ----------

async def listen_orders(
    cfg: cfg_mod.Config,
    client: OrderServerClient,
    executor: ChainExecutor,
) -> None:
    backoff = 1
    while True:
        try:
            async with websockets.connect(cfg.server_ws) as ws:
                log.info("WS connected -> %s", cfg.server_ws)
                backoff = 1
                async for raw in ws:
                    asyncio.create_task(_handle_message(raw, cfg, executor))
        except Exception as exc:  # noqa: BLE001
            log.warning("WS dropped (%s); reconnect in %ds", exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)


async def _handle_message(
    raw: str, cfg: cfg_mod.Config, executor: ChainExecutor
) -> None:
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("malformed WS message, skipping")
        return

    order = msg.get("order", msg)
    order_id = order.get("orderId") or order.get("onChainOrderId", "?")
    log.info("◀ order %s", order_id)

    ok, reason = evaluate(order, cfg)
    if not ok:
        log.info("  skip: %s", reason)
        return

    log.info("  ✓ evaluate=fill, executing...")
    try:
        fill_tx = await executor.fill_order(
            output_settler=cfg.output_settler_dst,
            fill_deadline=int(order["fillDeadline"]),
            order_id=order_id,
            outputs=order.get("outputs", []),
        )
        log.info("  ✓ fill tx %s", fill_tx)

        fin_tx = await executor.finalise_source(
            input_settler=cfg.input_settler_src,
            order=order,
            attestation=b"",
        )
        log.info("[SETTLED] order=%s fill=%s finalise=%s", order_id, fill_tx, fin_tx)
    except Exception as exc:  # noqa: BLE001
        log.error("  ✗ execution failed: %s", exc)


# ---------- entry ----------

async def amain() -> None:
    cfg = cfg_mod.load()
    _setup_logging(cfg.log_level)
    log.info("solver-in-a-box starting (mode=%s)", cfg.mode)

    client = OrderServerClient(cfg.server_url, cfg.api_key)
    executor = ChainExecutor(
        cfg.src_rpc, cfg.dst_rpc, cfg.solver_pk, cfg.solver_address,
        mock=(cfg.mode == "mock"),
    )

    await register(client, cfg)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass  # Windows

    tasks = [
        asyncio.create_task(quote_loop(client, cfg)),
        asyncio.create_task(listen_orders(cfg, client, executor)),
        asyncio.create_task(stop.wait()),
    ]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()
    await client.close()
    log.info("shutdown clean")


def main() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    main()
