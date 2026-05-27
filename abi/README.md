# ABIs

Drop the JSON ABIs for the OIF reference contracts here. The daemon
loads them lazily in testnet mode (see `solver/chain.py`).

## Where to get them

Source: https://github.com/openintentsframework/oif-contracts

Pin a known-good commit hash in your fork. Suggested files:

- `OutputSettler.json`
- `OutputSettlerSimple.json`
- `InputSettlerEscrow.json`
- `InputSettlerCompact.json`

## How to extract

```bash
git clone https://github.com/openintentsframework/oif-contracts
cd oif-contracts
forge build
cp out/OutputSettler.sol/OutputSettler.json /path/to/solver-in-a-box/abi/
# repeat for each contract
```

Mock mode does not need any ABI files.
