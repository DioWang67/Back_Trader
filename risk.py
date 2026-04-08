"""Risk and position sizing utilities."""

from __future__ import annotations

import math


def position_size(
    equity: float,
    entry_price: float,
    stop_price: float,
    risk_per_trade: float,
    contract_multiplier: float,
) -> int:
    """Calculate integer contract size based on fixed fractional risk."""
    risk_amount = equity * risk_per_trade
    stop_distance = abs(entry_price - stop_price)
    if stop_distance <= 0:
        return 0
    risk_per_contract = stop_distance * contract_multiplier
    if risk_per_contract <= 0:
        return 0
    return max(0, math.floor(risk_amount / risk_per_contract))


def max_drawdown_reached(equity: float, peak_equity: float, max_drawdown: float) -> bool:
    """Return True when drawdown threshold is reached."""
    if peak_equity <= 0:
        return False
    dd = (peak_equity - equity) / peak_equity
    return dd >= max_drawdown
