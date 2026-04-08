"""Vector-prepared, bar-by-bar backtest engine."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from config import Config
from indicators import prepare_features
from risk import max_drawdown_reached, position_size
from strategy import SMCStrategy


@dataclass(slots=True)
class Position:
    """Open position state."""

    direction: str
    qty: int
    entry: float
    stop: float
    take_profit: float
    open_time: pd.Timestamp


@dataclass(slots=True)
class Trade:
    """Closed trade record."""

    direction: str
    qty: int
    entry: float
    exit: float
    pnl: float
    open_time: pd.Timestamp
    close_time: pd.Timestamp


def _exit_price_with_slippage(price: float, direction: str, tick: float, ticks: int) -> float:
    slip = tick * ticks
    if direction == "long":
        return price - slip
    return price + slip


def _entry_price_with_slippage(price: float, direction: str, tick: float, ticks: int) -> float:
    slip = tick * ticks
    if direction == "long":
        return price + slip
    return price - slip


def run_backtest(df: pd.DataFrame, config: Config) -> tuple[pd.DataFrame, list[Trade], dict]:
    """Run the complete backtest and return equity curve, trades, and summary."""
    if df.empty:
        return pd.DataFrame(columns=["datetime", "equity"]), [], {"stopped_by_dd": False}

    data = prepare_features(df, config.ema_fast, config.ema_slow, config.swing_lookback)
    strategy = SMCStrategy(fvg_valid_bars=config.fvg_valid_bars)

    equity = config.initial_capital
    peak = equity
    stopped_by_dd = False
    open_positions: list[Position] = []
    trades: list[Trade] = []
    curve: list[dict] = []

    for i in range(2, len(data)):
        row = data.iloc[i]
        dt = pd.Timestamp(row["datetime"])

        survivors: list[Position] = []
        for pos in open_positions:
            exit_price = None
            if pos.direction == "long":
                if row["low"] <= pos.stop:
                    exit_price = pos.stop
                elif row["high"] >= pos.take_profit:
                    exit_price = pos.take_profit
            else:
                if row["high"] >= pos.stop:
                    exit_price = pos.stop
                elif row["low"] <= pos.take_profit:
                    exit_price = pos.take_profit

            if exit_price is None:
                survivors.append(pos)
                continue

            fill = _exit_price_with_slippage(
                exit_price,
                pos.direction,
                config.tick_size,
                config.slippage_ticks,
            )
            gross = (
                (fill - pos.entry) * pos.qty * config.contract_multiplier
                if pos.direction == "long"
                else (pos.entry - fill) * pos.qty * config.contract_multiplier
            )
            net = gross - config.commission_per_order_ntd
            equity += net
            trades.append(
                Trade(
                    direction=pos.direction,
                    qty=pos.qty,
                    entry=pos.entry,
                    exit=fill,
                    pnl=net,
                    open_time=pos.open_time,
                    close_time=dt,
                )
            )
        open_positions = survivors

        peak = max(peak, equity)
        if max_drawdown_reached(equity, peak, config.max_drawdown):
            stopped_by_dd = True
            curve.append({"datetime": dt, "equity": equity})
            break

        if len(open_positions) < config.max_open_positions:
            signals = strategy.on_bar(data, i)
            for sig in signals:
                if len(open_positions) >= config.max_open_positions:
                    break
                entry = _entry_price_with_slippage(
                    sig["entry"],
                    sig["direction"],
                    config.tick_size,
                    config.slippage_ticks,
                )
                stop = sig["stop"]
                if sig["direction"] == "long":
                    tp = entry + (entry - stop) * config.reward_risk
                else:
                    tp = entry - (stop - entry) * config.reward_risk

                qty = position_size(
                    equity=equity,
                    entry_price=entry,
                    stop_price=stop,
                    risk_per_trade=config.risk_per_trade,
                    contract_multiplier=config.contract_multiplier,
                )
                if qty <= 0:
                    continue

                equity -= config.commission_per_order_ntd
                open_positions.append(
                    Position(
                        direction=sig["direction"],
                        qty=qty,
                        entry=entry,
                        stop=stop,
                        take_profit=tp,
                        open_time=dt,
                    )
                )

        curve.append({"datetime": dt, "equity": equity})

    equity_curve = pd.DataFrame(curve)
    return equity_curve, trades, {"stopped_by_dd": stopped_by_dd}
