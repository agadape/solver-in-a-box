"""Solver-in-a-Box main daemon.

Lifecycle:
    register -> submit_quotes (loop) -> listen_orders (loop) ->
        evaluate -> fill -> wait_attest -> finalise

Each function maps 1:1 to a section of the LI.FI Intents solver docs.
Read top-to-bottom; no framework magic.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import signal
import time
from decimal import Decimal
from typing import Any

import websockets
from rich.align import Align
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel

from solver import config as cfg_mod
from solver.api_client import OrderServerClient
from solver.chain import ChainExecutor, sign_registration


console = Console(legacy_windows=False)

# ---------- stats ----------

@dataclasses.dataclass
class Stats:
    orders_seen: int = 0
    skipped: int = 0
    fills_ok: int = 0
    fills_failed: int = 0
    pnl_usdc: Decimal = dataclasses.field(default_factory=Decimal)


# ---------- logging ----------

def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%H:%M:%S]",
        handlers=[RichHandler(console=console, rich_tracebacks=True, markup=True)],
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
    log.info("  OK registered")


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
            "posting curve %s->%s spread=[magenta]%dbps[/magenta]",
            cfg.route.src_chain_id,
            cfg.route.dst_chain_id,
            cfg.spread_bps,
        )
        try:
            await client.submit_quotes([curve])
            log.info("  [green]OK curve accepted[/green]")
        except Exception as exc:  # noqa: BLE001
            log.warning("  [red]!! submit_quotes failed:[/red] %s", exc)
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


# ---------- order processing ----------

async def _process_order(
    order: dict,
    cfg: cfg_mod.Config,
    executor: ChainExecutor,
    stats: Stats,
) -> None:
    order_id = order.get("orderId") or order.get("onChainOrderId", "?")
    short_id = order_id[:20] + "..."
    stats.orders_seen += 1
    console.log(f"[cyan]<< order[/cyan] {short_id}")

    ok, reason = evaluate(order, cfg)
    if not ok:
        stats.skipped += 1
        console.log(f"  [dim]skip: {reason}[/dim]")
        return

    console.log("  [green]OK evaluate=fill[/green], executing...")
    try:
        fill_tx = await executor.fill_order(
            output_settler=cfg.output_settler_dst,
            fill_deadline=int(order["fillDeadline"]),
            order_id=order_id,
            outputs=order.get("outputs", []),
        )
        fin_tx = await executor.finalise_source(
            input_settler=cfg.input_settler_src,
            order=order,
            attestation=b"",
        )

        try:
            in_amt = Decimal(order["inputs"][0][1])
            out_amt = Decimal(order["outputs"][0]["amount"])
            pnl = (in_amt - out_amt) / Decimal(10 ** cfg.route.src_decimals)
            stats.pnl_usdc += pnl
        except Exception:
            pnl = Decimal(0)

        stats.fills_ok += 1
        console.print(
            f"[bold green][SETTLED][/bold green] {short_id} "
            f"fill={fill_tx} fin={fin_tx} "
            f"[yellow]+{pnl:.4f} USDC[/yellow]  |  "
            f"[bold]total PnL: {stats.pnl_usdc:.4f} USDC[/bold]  "
            f"fills={stats.fills_ok} skipped={stats.skipped}"
        )
    except Exception as exc:  # noqa: BLE001
        stats.fills_failed += 1
        console.log(f"  [red]!! execution failed:[/red] {exc}")


async def _handle_message(
    raw: str,
    cfg: cfg_mod.Config,
    executor: ChainExecutor,
    stats: Stats,
) -> None:
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("malformed WS message, skipping")
        return
    order = msg.get("order", msg)
    await _process_order(order, cfg, executor, stats)


# ---------- order listener (WS + HTTP fallback) ----------

_WS_FAIL_THRESHOLD = 3
_POLL_INTERVAL_SECONDS = 5


async def listen_orders(
    cfg: cfg_mod.Config,
    client: OrderServerClient,
    executor: ChainExecutor,
    stats: Stats,
) -> None:
    backoff = 1
    ws_failures = 0
    seen_ids: set[str] = set()

    while True:
        if ws_failures < _WS_FAIL_THRESHOLD:
            try:
                async with websockets.connect(cfg.server_ws) as ws:
                    console.log(f"[green]WS connected[/green] -> {cfg.server_ws}")
                    backoff = 1
                    ws_failures = 0
                    async for raw in ws:
                        asyncio.create_task(
                            _handle_message(raw, cfg, executor, stats)
                        )
            except Exception as exc:  # noqa: BLE001
                ws_failures += 1
                console.log(
                    f"[yellow]WS dropped[/yellow] ({exc}); "
                    f"reconnect in {backoff}s [{ws_failures}/{_WS_FAIL_THRESHOLD}]"
                )
                if ws_failures >= _WS_FAIL_THRESHOLD:
                    console.log(
                        "[yellow]WS unavailable — switching to HTTP polling "
                        f"(every {_POLL_INTERVAL_SECONDS}s)[/yellow]"
                    )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)
        else:
            # HTTP polling fallback
            try:
                result = await client.get_orders()
                orders = result if isinstance(result, list) else result.get("orders", [])
                for order in orders:
                    oid = order.get("orderId") or order.get("onChainOrderId", "?")
                    if oid not in seen_ids:
                        seen_ids.add(oid)
                        asyncio.create_task(
                            _process_order(order, cfg, executor, stats)
                        )
            except Exception as exc:  # noqa: BLE001
                log.warning("HTTP poll failed: %s", exc)
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)


# ---------- entry ----------

async def amain() -> None:
    cfg = cfg_mod.load()
    _setup_logging(cfg.log_level)

    console.print(Panel(
        Align.center(
            f"[bold cyan]solver-in-a-box[/bold cyan]\n"
            f"mode=[green]{cfg.mode}[/green]  "
            f"route=[yellow]{cfg.route.src_chain_id} -> {cfg.route.dst_chain_id}[/yellow]  "
            f"spread=[magenta]{cfg.spread_bps} bps[/magenta]"
        ),
        title="[bold]LI.FI Intents Solver[/bold]",
        border_style="cyan",
    ))

    stats = Stats()
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
        asyncio.create_task(listen_orders(cfg, client, executor, stats)),
        asyncio.create_task(stop.wait()),
    ]
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
    except (asyncio.CancelledError, KeyboardInterrupt):
        for t in tasks:
            t.cancel()
    finally:
        console.print(
            f"\n[bold]Session summary[/bold]  orders={stats.orders_seen}  "
            f"filled=[green]{stats.fills_ok}[/green]  "
            f"skipped=[dim]{stats.skipped}[/dim]  "
            f"failed=[red]{stats.fills_failed}[/red]  "
            f"PnL=[yellow]{stats.pnl_usdc:.4f} USDC[/yellow]"
        )
        await client.close()
        log.info("shutdown clean")


def main() -> None:
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
