# Solver economics

Before you run this daemon for real, you should be able to answer:
*how does a solver make money, and where does that money go when
things go wrong?* This doc walks through the math on one worked example.

---

## The mental model

A solver is a **principal market maker** for cross-chain transfers.

The user signs an intent: *"I will give 100 USDC on Base. I want 99.9
USDC on Arbitrum within 5 minutes."* The solver decides whether to
fill. If yes, the solver:

1. **Pays the user** 99.9 USDC on Arbitrum from its own inventory.
2. **Collects** 100 USDC on Base when the source escrow releases.
3. **Pockets the difference** (0.1 USDC) minus all costs.

There is no loan, no AMM pool, no LP token. The solver fronts the
liquidity, accepts the price + delivery risk, and earns the spread.

---

## One worked example

**Setup.** Solver quotes USDC Base → USDC Arbitrum at a 10 bp spread.
A user sends a 10,000 USDC intent.

| Item | Value | Notes |
|---|---|---|
| Notional | 10,000 USDC | The user's intent size |
| Spread quoted | 10 bps | From `QUOTE_SPREAD_BPS` |
| Gross spread captured | **10.00 USDC** | 10,000 × 0.0010 |
| Destination gas (`fillOrderOutputs` on Arbitrum) | ~0.05 USD | ~150k gas × 0.1 gwei × $ETH/1e9 |
| Source gas (`finalise` on Base) | ~0.10 USD | ~200k gas × 0.001 gwei × $ETH/1e9 |
| Token transfer cost (approval + ERC-20) | ~0.05 USD | One-time approval amortised |
| Inventory cost-of-capital (5 min lockup) | ~0.001 USDC | 5%/yr × 10k × 5/525600 |
| **Net PnL per intent** | **~9.80 USDC** | Most of the gross |

On stablecoin → stablecoin same-asset routes, gas is rounding error.
Real costs hit on:

- Inventory **rebalancing** — every so often you'll have too much USDC
  on Arbitrum and not enough on Base. You bridge back, paying real fees.
- Inventory **funding** — capital tied up earns no interest while
  parked. A solver running $1M of inventory at a 5%/yr opportunity
  cost burns ~$137/day even if it does zero volume.
- **Misquotes** — see risks below.

---

## Where the money goes wrong

### Risk 1: price moves between quote and fill

The standing curve says "I'll buy at 0.999." If USDC briefly
de-pegs to 0.997 on the source chain while you owe 0.999 on the
destination, you ate a 20 bp loss. Mitigation:

- Set `QUOTE_EXPIRY_SECONDS` short (60–300s).
- Don't quote during high-volatility windows (around CPI, FOMC, etc.).
- For non-stable pairs, anchor each range to a fresh oracle mid-price.

### Risk 2: oracle delay or failure

You filled on the destination. The oracle is slow / down / disagrees.
Your input stays escrowed until `expires`, at which point the user can
take it back. You ate the destination payment without recovering input.
Mitigation:

- Track per-oracle reliability stats.
- Pause the route if the oracle hasn't attested any order in N minutes.

### Risk 3: gas spike on destination

You priced assuming 0.1 gwei on Arbitrum. A spike to 50 gwei makes the
fill cost more than your spread. Mitigation:

- Pre-fill check: abort if `dst_gas_gwei > MAX_FILL_GAS_GWEI` (default 50).
- For large notionals, that ceiling is generous; for small ones, drop it.

### Risk 4: MEV sandwich on destination calldata

If the order has post-delivery calldata (e.g., auto-swap into a vault),
a searcher can sandwich your fill tx. Mitigation:

- Send fill via private mempool (Flashbots-style or builder bundle).
- Set tight `minOut` on any downstream swap.

### Risk 5: solver gets exclusivity but doesn't fill in time

If you quoted with `exclusiveFor = <your-address>` and missed the
window, the order goes to open market and you lose nothing — but you've
also wasted the user's time. Repeatedly missing exclusive fills hurts
your reputation score (see `/solver-api/solver/identities`). Mitigation:

- Set `MIN_BUFFER_SECONDS` conservatively.
- Don't quote exclusively unless you can guarantee fill.

---

## Sizing your inventory

A simple sizing rule that works for stable-pair solvers:

```
required_inventory_per_chain = expected_daily_volume / rebalance_frequency_per_day
```

For 1M/day USDC volume, rebalancing 4× a day:

```
inventory_per_chain = 1,000,000 / 4 = 250,000 USDC per chain × 2 chains = 500,000 USDC total
```

At 10 bps gross, daily gross = $1,000. After ~$140/day funding cost +
~$200/day rebalance bridging fees → **~$660/day net** on $500K
inventory ≈ **48% APY** (back-of-envelope, before competition).

That's why intent solvers exist as a business. Whether you can capture
that yield depends on whether your curve beats five other solvers'
curves — competition compresses spreads fast.

---

## Reputation matters more than spread

The LI.FI order server tracks fill rate, latency, and revert rate per
solver identity. A solver that quotes tight but reverts 5% of fills
loses to a solver that quotes 1 bp wider but never reverts. Most of
your engineering effort, after the daemon works, should go into
**not breaking** — not into pricing.

---

## TL;DR

| Question | Answer |
|---|---|
| How does a solver make money? | Spread × volume |
| What kills profit? | Misquotes, oracle delay, gas spikes, idle inventory |
| What can you control? | Spread, expiry, route selection, gas ceiling, MEV protection |
| What can you not control? | Other solvers' curves, user behaviour, oracle outages |
| Where does the edge come from? | Cheaper inventory funding, faster rebalancing, better risk pricing |

Run this daemon in mock mode until the numbers above stop being
abstract. Then you're ready for testnet.
