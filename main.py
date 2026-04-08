"""Entry point for running the SMC backtest."""

from __future__ import annotations

from config import DEFAULT_CONFIG
from backtest import run_backtest
from data_loader import download_txf_data
from metrics import summarize


def main() -> None:
    """Run backtest from TXF downloaded data and print metrics."""
    config = DEFAULT_CONFIG
    df = download_txf_data(config)
    equity_curve, trades, extra = run_backtest(df, config)
    result = summarize(config.initial_capital, equity_curve, trades)

    print("=== SMC Backtest Report ===")
    print(f"Total Return (%): {result['total_return_pct']:.2f}")
    print(f"Max Drawdown (%): {result['max_drawdown_pct']:.2f}")
    print(f"Sharpe Ratio: {result['sharpe_ratio']:.2f}")
    print(f"Win Rate (%): {result['win_rate_pct']:.2f}")
    print(f"Profit Factor: {result['profit_factor']:.2f}")
    print(f"Trade Count: {result['trade_count']}")
    print(f"Stopped by Max DD: {extra['stopped_by_dd']}")


if __name__ == "__main__":
    main()
