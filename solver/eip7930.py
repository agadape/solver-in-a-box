"""EIP-7930 interoperable address encoding.

Format (variable-length bytes):
  version (1 byte)  || chain_type (1 byte) || chain_ref_len (1 byte)
                    || chain_ref || addr_len (1 byte) || addr

This implementation hardcodes v1 + EVM chain type (0x00) and uses a
big-endian uint encoding for chain_ref. Keep it dead-simple; spec linked
in README.
"""
from __future__ import annotations


VERSION = 0x01
CHAIN_TYPE_EVM = 0x00


def encode_evm(chain_id: int, address: str) -> bytes:
    addr_bytes = bytes.fromhex(address.removeprefix("0x"))
    if len(addr_bytes) != 20:
        raise ValueError(f"EVM address must be 20 bytes, got {len(addr_bytes)}")

    chain_ref = chain_id.to_bytes((chain_id.bit_length() + 7) // 8 or 1, "big")

    return (
        bytes([VERSION, CHAIN_TYPE_EVM, len(chain_ref)])
        + chain_ref
        + bytes([len(addr_bytes)])
        + addr_bytes
    )


def encode_hex(chain_id: int, address: str) -> str:
    return "0x" + encode_evm(chain_id, address).hex()
