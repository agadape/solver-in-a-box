# Contributing

This repo is a **reference**, not a product. The shortest contribution is a fork that adds something this skeleton intentionally left out.

---

## Good first issues (fork-and-PR welcome)

### 1. Wire the testnet fill path
**File:** `solver/chain.py`
**Difficulty:** medium
**Time:** 2–3 hours

Two functions raise `NotImplementedError`: `fill_order` and `finalise_source`. Both have inline comments listing exact steps. You need:

- ABIs in `abi/OutputSettler.json` and `abi/InputSettlerEscrow.json` (extract from [openintentsframework/oif-contracts](https://github.com/openintentsframework/oif-contracts) via `forge build`)
- A funded testnet wallet on Base Sepolia + Arbitrum Sepolia
- A LI.FI solver API key from https://devintents.li.fi

Acceptance: a single successful `[SETTLED]` log line with **real** tx hashes on Sepolia explorers.

### 2. Multi-route curve generation
**File:** `solver/main.py:build_curve`
**Difficulty:** easy
**Time:** 1 hour

Today the curve is hardcoded to one route from env vars. Extend `Route` config to accept a list (YAML or JSON file), iterate `build_curve` over the list, submit all curves in one `/quotes/submit` call (server accepts up to 200K).

### 3. Oracle-anchored pricing
**File:** `solver/main.py:build_curve`
**Difficulty:** medium
**Time:** 2 hours

Spread is currently `1 − bps`. Replace with `oracle_mid × (1 − bps)`. Pull mid from Chainlink or Pyth at curve-refresh time. Cache for `QUOTE_REFRESH_SECONDS / 2` to avoid hammering the feed.

### 4. HTTP polling fallback for WebSocket
**File:** `solver/main.py:listen_orders`
**Difficulty:** easy
**Time:** 45 min

If WebSocket connect fails 3× in a row, fall back to `GET /orders?status=Signed&since=<ts>` polled every 3 seconds. Already sketched in the WS try/except — extract into a second coroutine.

### 5. Compact (resource-lock) order support
**File:** new — `solver/chain.py:fill_compact`
**Difficulty:** hard
**Time:** 4 hours

`InputSettlerCompact` uses Uniswap's [The Compact](https://github.com/Uniswap/the-compact) resource-lock model. Different deposit flow, different `finalise` calldata. See [LI.FI docs § Compact Orders](https://docs.li.fi/lifi-intents/intents-api/compact-orders).

### 6. TypeScript port
**Difficulty:** medium
**Time:** 4–6 hours

Same architecture, `ethers` + `ws` instead of `web3.py` + `websockets`. Goal: `pnpm install && pnpm run mock` reaches `[SETTLED]` in 60 seconds.

### 7. Dashboard UI
**Difficulty:** medium
**Time:** 4 hours

Next.js page subscribing to the same `/ws/orders` WebSocket plus `GET /solver-api/quotes`. Visualise active curves + recent fills. Companion to the daemon.

---

## How to submit

1. Fork the repo.
2. Branch: `git checkout -b feat/<short-name>`.
3. Make changes. Add or update tests in `tests/`.
4. `make test` green.
5. Update README if behaviour changed.
6. Open PR with: what changed, why, screenshot/log proof.

## Code style

- Python 3.11, type hints on public functions.
- No new dependencies unless justified in the PR description.
- Keep `solver/main.py` ≤ 500 LOC — readability is the headline feature.
- No emojis in comments. Logs may use `✓ ◀ ▶ [SETTLED]` (already established vocabulary).

## License

By contributing you agree your contribution is MIT licensed.
