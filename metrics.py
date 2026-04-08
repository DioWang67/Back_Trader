"""Performance metrics for backtest results."""

from __future__ import annotations

import math

import pandas as pd

from backtest import Trade



def max_drawdown(equity_curve: pd.Series) -> float:
    """Compute maximum drawdown as ratio."""
    if equity_curve.empty:
        return 0.0
    peak = equity_curve.cummax()
    dd = (equity_curve - peak) / peak
    return float(abs(dd.min()))



def sharpe_ratio(equity_curve: pd.Series) -> float:
    """Compute daily-like Sharpe using bar-to-bar returns."""
    ret = equity_curve.pct_change().dropna()
    std = float(ret.std(ddof=0)) if not ret.empty else 0.0
    if ret.empty or std == 0.0:
        return 0.0
    return float((ret.mean() / std) * math.sqrt(252))



def summarize(
    initial_capital: float,
    equity_curve: pd.DataFrame,
    trades: list[Trade],
) -> dict:
    """Build summary metrics dictionary."""
    final_equity = (
        float(equity_curve["equity"].iloc[-1]) if not equity_curve.empty else initial_capital
    )
    total_return = (final_equity / initial_capital - 1) * 100
    mdd = max_drawdown(equity_curve["equity"] if not equity_curve.empty else pd.Series(dtype=float))
    shp = sharpe_ratio(equity_curve["equity"] if not equity_curve.empty else pd.Series(dtype=float))

    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl < 0]
    win_rate = (len(wins) / len(trades) * 100) if trades else 0.0
    gross_profit = sum(t.pnl for t in wins)
    gross_loss = abs(sum(t.pnl for t in losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0

    return {
        "total_return_pct": total_return,
        "max_drawdown_pct": mdd * 100,
        "sharpe_ratio": shp,
        "win_rate_pct": win_rate,
        "profit_factor": profit_factor,
        "trade_count": len(trades),
        "final_equity": final_equity,
    }
