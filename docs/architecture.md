# Architecture

A LI.FI Intents solver is a small daemon that does five things in a loop:
**register, quote, listen, fill, finalise.** This document explains how
they fit together, what each touches, and why the split exists.

---

## Component diagram

```
                ┌──────────────────────────────────────────────┐
                │  LI.FI Order Server (order-dev.li.fi)        │
                │  Off-chain matching layer. Holds quote       │
                │  inventory and routes new orders to solvers. │
                └──┬───────────────┬───────────────┬────────────┘
                   │               │               │
        POST /quotes/submit        │     WS push: order.signed
                   │               │               │
                   ▼               ▼               ▼
       ┌──────────────────────────────────────────────────┐
       │                solver/main.py                    │
       │                                                  │
       │   register(once) ─► quote_loop  (every 60s)      │
       │                  ─► listen_orders (WS, forever)  │
       │                         │                        │
       │                         ▼                        │
       │                    evaluate(order)               │
       │                         │                        │
       │                  ┌──────┴──────┐                 │
       │                  │             │                 │
       │             skip │             │ fill            │
       │                  ▼             ▼                 │
       │                                                  │
       │           fill_order ────► chain.py ─┐           │
       │                                      │           │
       │           finalise_source ──► chain.py ─┐        │
       └────────────────────────────────────────│┴────────┘
                                                │
                                                ▼
                              ┌─────────────────────────────────────┐
                              │  Destination RPC (Arbitrum Sepolia) │
                              │  → OutputSettler.fillOrderOutputs   │
                              │                                     │
                              │  Source RPC (Base Sepolia)          │
                              │  → InputSettlerEscrow.finalise      │
                              └─────────────────────────────────────┘
```

---

## Why the split: off-chain matching, on-chain settlement

The order server is **off-chain** because quote matching needs latency
the chain can't offer. Solvers maintain standing curves that are
overwritten on every update. When a user signs an intent, the order
server picks the best curve in microseconds and routes the order to
that solver — no auction round, no per-order RPC.

Settlement is **on-chain** because the funds are. The source chain
escrows the user's input; the destination chain pays out. The oracle
bridges trust between the two: it attests that the destination payment
landed, which lets the source chain release the escrow.

---

## Order lifecycle

```
  user signs intent
        │
        ▼
   Signed          ── order broadcast to order server + solvers
        │
        ▼
   Delivered       ── solver called OutputSettler.fillOrderOutputs
        │
        ▼
   Settled         ── oracle attested, solver called InputSettlerEscrow.finalise
                      and claimed the source-chain input
```

Two timestamps gate the lifecycle:

- **`fillDeadline`** — solver must call `fillOrderOutputs` before this or
  lose the right to fill.
- **`expires`** — final cutoff. After this, the user can claim a refund.

Always leave a safety buffer (`MIN_BUFFER_SECONDS`, default 30s)
between `now` and `fillDeadline` so you don't broadcast a tx that mines
just after the deadline.

---

## Why one route in v1

`solver/main.py` posts one standing curve for one route (USDC Base
Sepolia → USDC Arbitrum Sepolia). That keeps the code readable and the
demo deterministic. The shape of the code is identical for N routes —
loop the curve builder over a config list. That's a 10-line change. It's
left to forks so the reference stays small.

---

## Mock mode vs testnet mode

| | Mock | Testnet |
|---|---|---|
| Internet | not needed | needed |
| API key | not needed | needed |
| Wallet funds | not needed | needed |
| Order source | `mock_server` emits synthetic orders | real users + Lintent UI |
| Fill execution | logged only | real `eth_sendRawTransaction` |
| Finalise execution | logged only | real `eth_sendRawTransaction` |
| Use case | iterate on solver logic, write tests, record demo | prove the integration |

Both share the **exact same code path** in `solver/main.py` — only the
URLs and the `mock=True` flag on `ChainExecutor` change. That's the
point: if it works in mock, the bugs that remain on testnet are
network/contract issues, not logic issues.

---

## What you'd add to make this production

Anything you'd lose sleep over:

1. **Inventory limits.** Cap notional per route, per hour, per chain.
2. **Hot-reload pricing.** Listen to a price feed; rebuild curve on tick.
3. **Private mempool.** Submit fills via a builder bundle to avoid
   sandwich attacks on the destination swap.
4. **Failure budgets.** If three fills revert in a row, pause and page
   on-call.
5. **Settlement bot separate from fill bot.** Different criticality.
6. **Observability.** Prometheus metrics on every API call + tx.
7. **Cold-storage signer** with delegated hot keys per chain.

None of these belong in a reference. All of them belong in a real solver.
