"""Environment + route configuration. Single source of truth."""
from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _int(key: str, default: int) -> int:
    return int(os.getenv(key, str(default)))


@dataclass(frozen=True)
class Route:
    src_chain_id: int
    dst_chain_id: int
    src_token: str
    dst_token: str
    src_decimals: int
    dst_decimals: int


@dataclass(frozen=True)
class Config:
    mode: str
    api_key: str
    server_url: str
    server_ws: str
    solver_pk: str
    solver_address: str
    src_rpc: str
    dst_rpc: str
    input_settler_src: str
    output_settler_dst: str
    input_oracle_src: str
    spread_bps: int
    refresh_seconds: int
    expiry_seconds: int
    range_min_units: int
    range_max_units: int
    min_buffer_seconds: int
    max_fill_gas_gwei: int
    log_level: str
    mock_interval: int
    mock_size_units: int
    route: Route


def load() -> Config:
    mode = _env("MODE", "mock").lower()
    if mode == "mock":
        server_url = _env("MOCK_SERVER_URL", "http://127.0.0.1:8000")
        server_ws = _env("MOCK_SERVER_WS", "ws://127.0.0.1:8000/ws/orders")
    else:
        server_url = _env("ORDER_SERVER_URL", "https://order-dev.li.fi")
        server_ws = _env("ORDER_SERVER_WS", "wss://order-dev.li.fi/ws/orders")

    route = Route(
        src_chain_id=_int("SRC_CHAIN_ID", 84532),
        dst_chain_id=_int("DST_CHAIN_ID", 421614),
        src_token=_env("SRC_TOKEN_ADDRESS"),
        dst_token=_env("DST_TOKEN_ADDRESS"),
        src_decimals=_int("SRC_TOKEN_DECIMALS", 6),
        dst_decimals=_int("DST_TOKEN_DECIMALS", 6),
    )

    return Config(
        mode=mode,
        api_key=_env("LIFI_API_KEY"),
        server_url=server_url,
        server_ws=server_ws,
        solver_pk=_env("SOLVER_PRIVATE_KEY"),
        solver_address=_env("SOLVER_ADDRESS"),
        src_rpc=_env("SRC_CHAIN_RPC", "https://sepolia.base.org"),
        dst_rpc=_env("DST_CHAIN_RPC", "https://sepolia-rollup.arbitrum.io/rpc"),
        input_settler_src=_env("INPUT_SETTLER_ESCROW_SRC"),
        output_settler_dst=_env("OUTPUT_SETTLER_DST"),
        input_oracle_src=_env("INPUT_ORACLE_SRC"),
        spread_bps=_int("QUOTE_SPREAD_BPS", 10),
        refresh_seconds=_int("QUOTE_REFRESH_SECONDS", 60),
        expiry_seconds=_int("QUOTE_EXPIRY_SECONDS", 3600),
        range_min_units=_int("QUOTE_RANGE_MIN_USDC", 1),
        range_max_units=_int("QUOTE_RANGE_MAX_USDC", 10000),
        min_buffer_seconds=_int("MIN_BUFFER_SECONDS", 30),
        max_fill_gas_gwei=_int("MAX_FILL_GAS_GWEI", 50),
        log_level=_env("LOG_LEVEL", "INFO"),
        mock_interval=_int("MOCK_INTERVAL_SECONDS", 15),
        mock_size_units=_int("MOCK_ORDER_SIZE_USDC", 50),
        route=route,
    )
