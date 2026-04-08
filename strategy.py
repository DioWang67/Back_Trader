"""SMC strategy logic: Liquidity Sweep + BOS + FVG Pullback."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(slots=True)
class SetupState:
    """Pending setup state waiting for pullback into FVG."""

    direction: str
    fvg_low: float
    fvg_high: float
    stop: float
    created_idx: int


class SMCStrategy:
    """Strict rule-based SMC strategy state machine."""

    def __init__(self, fvg_valid_bars: int) -> None:
        self.fvg_valid_bars = fvg_valid_bars
        self.pending: list[SetupState] = []

    def _clean_expired(self, i: int) -> None:
        self.pending = [s for s in self.pending if i - s.created_idx <= self.fvg_valid_bars]

    def on_bar(self, df: pd.DataFrame, i: int) -> list[dict]:
        """Evaluate strategy on a single bar and return entry signals."""
        self._clean_expired(i)
        row = df.iloc[i]
        prev = df.iloc[i - 1]

        bullish_trend = row["ema_fast"] > row["ema_slow"]
        bearish_trend = row["ema_fast"] < row["ema_slow"]

        sweep_high = row["high"] > prev["high"] and row["close"] < prev["high"]
        sweep_low = row["low"] < prev["low"] and row["close"] > prev["low"]

        bos_bull = row["close"] > row["swing_high"] if pd.notna(row["swing_high"]) else False
        bos_bear = row["close"] < row["swing_low"] if pd.notna(row["swing_low"]) else False

        if bullish_trend and sweep_low and bos_bull and row["bull_fvg"]:
            self.pending.append(
                SetupState(
                    direction="long",
                    fvg_low=float(row["bull_fvg_low"]),
                    fvg_high=float(row["bull_fvg_high"]),
                    stop=float(row["low"]),
                    created_idx=i,
                )
            )

        if bearish_trend and sweep_high and bos_bear and row["bear_fvg"]:
            self.pending.append(
                SetupState(
                    direction="short",
                    fvg_low=float(row["bear_fvg_low"]),
                    fvg_high=float(row["bear_fvg_high"]),
                    stop=float(row["high"]),
                    created_idx=i,
                )
            )

        signals: list[dict] = []
        still_pending: list[SetupState] = []
        for setup in self.pending:
            touched = row["low"] <= setup.fvg_high and row["high"] >= setup.fvg_low
            if touched:
                signals.append(
                    {
                        "direction": setup.direction,
                        "entry": float(row["close"]),
                        "stop": setup.stop,
                        "fvg_low": setup.fvg_low,
                        "fvg_high": setup.fvg_high,
                    }
                )
            else:
                still_pending.append(setup)
        self.pending = still_pending
        return signals
