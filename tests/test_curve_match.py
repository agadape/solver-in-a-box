"""Unit tests for quote curve construction + order evaluation."""
from __future__ import annotations

import time

from solver.config import Config, Route
from solver.main import build_curve, evaluate


def _cfg(spread: int = 10) -> Config:
    return Config(
        mode="mock", api_key="", server_url="", server_ws="",
        solver_pk="0x" + "01" * 32,
        solver_address="0x" + "ab" * 20,
        src_rpc="", dst_rpc="",
        input_settler_src="", output_settler_dst="", input_oracle_src="",
        spread_bps=spread, refresh_seconds=60, expiry_seconds=3600,
        range_min_units=1, range_max_units=10_000,
        min_buffer_seconds=30, max_fill_gas_gwei=50, log_level="INFO",
        mock_interval=15, mock_size_units=50,
        route=Route(
            src_chain_id=84532, dst_chain_id=421614,
            src_token="0x" + "11" * 20, dst_token="0x" + "22" * 20,
            src_decimals=6, dst_decimals=6,
        ),
    )


def test_curve_has_two_ranges():
    curve = build_curve(_cfg())
    assert len(curve["ranges"]) == 2
    assert curve["fromChainId"] == 84532
    assert curve["toChainId"] == 421614


def test_curve_spread_applied():
    curve = build_curve(_cfg(spread=100))  # 1% spread
    small = float(curve["ranges"][0]["quote"])
    assert 0.989 < small < 0.991


def test_evaluate_skips_close_deadline():
    cfg = _cfg()
    order = {
        "fillDeadline": int(time.time()) + 5,
        "originChainId": 84532,
        "outputs": [{}],
    }
    ok, reason = evaluate(order, cfg)
    assert not ok
    assert "deadline" in reason


def test_evaluate_accepts_valid():
    cfg = _cfg()
    order = {
        "fillDeadline": int(time.time()) + 300,
        "originChainId": 84532,
        "outputs": [{"chainId": 421614}],
    }
    ok, reason = evaluate(order, cfg)
    assert ok, reason
