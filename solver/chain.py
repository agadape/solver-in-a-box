"""On-chain operations: fill on destination, finalise on source.

In mock mode all chain calls are simulated (no RPC required).
"""
from __future__ import annotations

import logging
from typing import Any

from eth_account import Account
from eth_account.messages import encode_defunct

log = logging.getLogger(__name__)


REGISTRATION_MESSAGE_TEMPLATE = (
    "LI.FI Intents Solver Registration\n"
    "Address: {address}\n"
    "Timestamp: {timestamp}"
)


def sign_registration(private_key: str, address: str, timestamp: int) -> str:
    msg = REGISTRATION_MESSAGE_TEMPLATE.format(
        address=address, timestamp=timestamp
    )
    signed = Account.sign_message(encode_defunct(text=msg), private_key=private_key)
    return signed.signature.hex()


class ChainExecutor:
    """Wraps web3.py for fill + finalise. Lazy-imports web3 so mock mode
    works with zero RPC dependency.
    """

    def __init__(
        self,
        src_rpc: str,
        dst_rpc: str,
        solver_pk: str,
        solver_address: str,
        mock: bool = False,
    ) -> None:
        self.solver_pk = solver_pk
        self.solver_address = solver_address
        self.mock = mock
        if not mock:
            from web3 import Web3  # noqa: WPS433

            self._w3_src = Web3(Web3.HTTPProvider(src_rpc))
            self._w3_dst = Web3(Web3.HTTPProvider(dst_rpc))
        else:
            self._w3_src = None
            self._w3_dst = None

    async def fill_order(
        self,
        output_settler: str,
        fill_deadline: int,
        order_id: str,
        outputs: list[dict],
    ) -> str:
        """Call OutputSettler.fillOrderOutputs on destination chain.

        Returns: tx hash (real) or a synthetic mock hash.
        """
        if self.mock:
            mock_hash = f"0xmock-fill-{order_id[:10]}"
            log.info("[mock] would fill on dst -> %s", mock_hash)
            return mock_hash

        # Real implementation outline:
        # 1. Load OutputSettler ABI from abi/OutputSettler.json
        # 2. Encode fillOrderOutputs(fillDeadline, orderId, outputs, proposedSolver)
        # 3. Approve token spend if not already
        # 4. eth_call simulate, abort on revert
        # 5. Build EIP-1559 tx, sign with solver_pk, broadcast
        # 6. Wait for receipt
        raise NotImplementedError(
            "Testnet fill path: load ABI from abi/OutputSettler.json and call "
            "fillOrderOutputs. See README testnet section."
        )

    async def finalise_source(
        self,
        input_settler: str,
        order: dict,
        attestation: bytes,
    ) -> str:
        """Call InputSettlerEscrow.finalise on source chain to claim input."""
        if self.mock:
            mock_hash = f"0xmock-fin-{order.get('orderId', '')[:10]}"
            log.info("[mock] would finalise on src -> %s", mock_hash)
            return mock_hash

        raise NotImplementedError(
            "Testnet finalise path: call InputSettlerEscrow.finalise(order, "
            "attestation, solverBytes32). See README testnet section."
        )
