# Solver-in-a-Box

A minimal, readable reference implementation of a **LI.FI Intents solver**. Spin up a working solver locally (mock mode) in under 5 minutes; testnet path scaffolded for forks. MIT licensed.

> Built for the [LI.FI Intents Mini Builder Challenge](https://lifi.notion.site/LI-FI-Intents-Mini-Builder-Challenge-366f0ff14ac78168a0cdd9f44a3c1f13) (May 2026).

> **Demo target:** mock mode — `make run-mock` runs the full lifecycle end-to-end against a local FastAPI mimic of `order-dev.li.fi`. No API key, no testnet faucet, no internet. Testnet wiring is scaffolded with explicit TODOs in [`solver/chain.py`](./solver/chain.py); see [§ "Why mock mode is the primary target"](#why-mock-mode-is-the-primary-target) below.

---

## What is a LI.FI Intents solver?

LI.FI Intents is an intent-based marketplace built on the [Open Intents Framework](https://github.com/openintentsframework/oif-contracts). Users express *what* they want — for example, "give me 100 USDC on Arbitrum, I'll pay with USDC on Base" — and **solvers** compete to fulfill it from their own inventory in exchange for a small spread.

A solver continuously:

1. Posts a **standing quote curve** to the off-chain order server.
2. Listens for new orders that match its curve.
3. Delivers the requested asset on the destination chain (`OutputSettler.fillOrderOutputs`).
4. After oracle attestation, claims the locked input on the source chain (`InputSettlerEscrow.finalise`).

That whole loop is what this repo implements — in ~400 lines of Python.

See [`docs/economics.md`](./docs/economics.md) for the *why* (PnL, risk, gas cost).
See [`docs/architecture.md`](./docs/architecture.md) for the *how* (component diagram).

---

## Quickstart (mock mode, 5 minutes)

No API key, no testnet faucet, no internet required.

**Linux / macOS:**
```bash
git clone <this-repo> solver-in-a-box
cd solver-in-a-box
cp .env.example .env
make install          # creates venv, installs deps
make run-mock         # starts mock server + solver
```

**Windows / PowerShell:**
```powershell
git clone <this-repo> solver-in-a-box
cd solver-in-a-box
copy .env.example .env
scripts\install.ps1
scripts\run-mock.ps1
```

Within 60 seconds you'll see:

```
[mock]   ▶ pushed order 0x1234... (USDC Base → USDC Arb, 50 USDC)
[solver] ◀ received order 0x1234...
[solver]   curve match: range 1-100 @ 0.999 → quote 49.95 USDC
[solver]   ✓ fill simulated on dst chain (mock)
[solver]   ✓ finalise simulated on src chain (mock)
[solver] [SETTLED] 0x1234... +0.05 USDC PnL
```

To stop: `Ctrl-C` in either pane (the Makefile cleans up the other).

---

## Testnet mode (scaffolded for forks — not the demo target)

> The two on-chain functions (`fill_order`, `finalise_source` in `solver/chain.py`) raise `NotImplementedError` in this v0.1. Wiring them is the [first good-first-issue](./CONTRIBUTING.md#1-wire-the-testnet-fill-path). Everything below describes the intended testnet flow once those are implemented.

### 1. Register as a solver

Go to [https://devintents.li.fi](https://devintents.li.fi), connect a fresh wallet, choose a solver name, and generate an API key. Copy it.

### 2. Fund the solver wallet on Base Sepolia + Arbitrum Sepolia

Faucets:
- Base Sepolia ETH: https://www.alchemy.com/faucets/base-sepolia
- Arbitrum Sepolia ETH: https://www.alchemy.com/faucets/arbitrum-sepolia
- USDC test tokens: bridge a small amount via the LI.FI Widget on testnet, or use Circle's faucet.

### 3. Configure `.env`

```bash
MODE=testnet
LIFI_API_KEY=<paste-from-step-1>
SOLVER_PRIVATE_KEY=0x<your-fresh-testnet-key>
SOLVER_ADDRESS=0x<derived-from-key>

BASE_SEPOLIA_RPC=https://sepolia.base.org
ARBITRUM_SEPOLIA_RPC=https://sepolia-rollup.arbitrum.io/rpc

QUOTE_SPREAD_BPS=10          # 10 bps = 0.10% spread
QUOTE_REFRESH_SECONDS=60
MIN_BUFFER_SECONDS=30
```

### 4. Run

```bash
make run-testnet
```

The solver will:

1. Sign a registration message and POST `/solver-api/account/register`.
2. Build a standing curve for the default route (USDC Base Sepolia → USDC Arbitrum Sepolia) and POST `/quotes/submit`.
3. Open a WebSocket to `wss://order-dev.li.fi/ws/orders` (with HTTP fallback if WS unavailable).
4. On match, broadcast `fillOrderOutputs` on Arbitrum Sepolia.
5. Wait for oracle attestation, then `finalise` on Base Sepolia.

### 5. Trigger a test order

Use the [Lintent UI](https://devintents.li.fi) to manually create an Escrow order, set `exclusiveFor` to your solver address, and submit. Your daemon picks it up within seconds.

---

## Repo layout

```
solver-in-a-box/
├── README.md                  ← you are here
├── Makefile                   ← all the run targets
├── .env.example               ← every env var documented
├── pyproject.toml             ← deps + pytest config
├── solver/
│   ├── main.py                ← entry point — the daemon (~400 LOC)
│   ├── api_client.py          ← thin httpx wrapper around order server
│   ├── chain.py               ← web3.py helpers (fill + finalise)
│   ├── eip7930.py             ← interoperable address encoder
│   └── config.py              ← env loader + route definitions
├── mock_server/
│   └── main.py                ← FastAPI mimic of order-dev.li.fi
├── abi/
│   ├── OutputSettler.json     ← from oif-contracts (pinned commit)
│   └── InputSettlerEscrow.json
├── docs/
│   ├── architecture.md        ← component diagram + lifecycle
│   └── economics.md           ← why a solver makes money (or doesn't)
├── tests/
│   └── test_curve_match.py    ← unit test for quote matching
├── CONTRIBUTING.md            ← good-first-issues for forks
└── .github/workflows/ci.yml   ← pytest + mock smoke test on every push
```

---

## Make targets

| Target | What it does |
|---|---|
| `make install` | Create venv, install deps from `pyproject.toml` |
| `make run-mock` | Start mock server + solver in mock mode |
| `make run-testnet` | Start solver against `order-dev.li.fi` |
| `make test` | Run pytest |
| `make demo` | Reproducible 60s mock-mode run for video recording |
| `make clean` | Remove caches + venv |

---

## Why mock mode is the primary target

Most "solver tutorials" hand you a single happy-path testnet recipe and walk away. This repo flips that: the **mock server is the canonical demo target**, and testnet wiring is left as deliberate, scaffolded forks.

Three reasons:

1. **Reproducibility for judges and forkers.** Anyone — including someone with zero testnet ETH, zero API key, zero RPC endpoint — can `git clone && make run-mock` and see the exact same `[SETTLED]` log line within 60 seconds. Mock mode is the demo I can guarantee works on your laptop.

2. **The solver loop, not the chain plumbing, is the lesson.** `OutputSettler.fillOrderOutputs` is a single contract call documented in the OIF repo. The thing worth understanding is the register → quote → listen → evaluate → fill → finalise daemon shape. Mock mode exercises every code path of that loop. Testnet only adds an `eth_sendRawTransaction`.

3. **Honest about what's hard.** Testnet faucets are gated by mainnet ETH balance, solver API keys take unknown turnaround time, and WebSocket URLs published in docs may not match production. None of these are technical achievements; they're operational hoops. Mock mode sidesteps them so the educational content stands on its own.

If you want to push to testnet, [`solver/chain.py`](./solver/chain.py) has two `NotImplementedError` blocks with inline comments listing exact next steps (load ABI from `abi/`, build EIP-1559 tx, sign, simulate via `eth_call`, broadcast, wait receipt). Estimated 2–3 hours of work for someone comfortable with `web3.py`.

---

## What this is NOT

Read this before forking for production use:

- **No inventory management.** The solver assumes pre-funded balances on both chains. A real solver rebalances continuously.
- **Naive pricing.** Spread is a flat bps over par. Real solvers price against an oracle and update on every block.
- **No MEV protection.** Fills broadcast through public mempool. A real solver uses private RPCs or builder bundles.
- **One route only.** Hardcoded to USDC Base Sepolia → USDC Arbitrum Sepolia in v1.
- **Testnet only.** Do not run on mainnet without adding inventory limits, alerts, and an audit pass.

These are *intentional gaps* — they're where your fork adds value.

---

## Fork this and add X

Suggested next steps for forks:

1. **Multi-route curves** — generate quotes for N routes from a YAML config.
2. **Oracle-driven pricing** — pull mid from Chainlink / Pyth, add dynamic spread.
3. **TypeScript port** — same architecture, `ethers` instead of `web3.py`.
4. **Compact mode** — implement `InputSettlerCompact` filling (resource-lock model).
5. **Dashboard UI** — Next.js dashboard subscribing to the same WS — pair it with [Intent Pulse](#) (separate project idea).

---

## Resources

- LI.FI Intents docs: https://docs.li.fi/lifi-intents/introduction
- Solver API: https://docs.li.fi/lifi-intents/for-solvers/api-overview
- OIF contracts: https://github.com/openintentsframework/oif-contracts
- Solver UI (testnet): https://devintents.li.fi
- Solver UI (mainnet): https://intents.li.fi
- LI.FI Builders TG: https://t.me/lifibuilders

---

## License

MIT. Go win.
