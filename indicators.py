"""Indicator calculations for SMC strategy."""

from __future__ import annotations

import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    """Compute exponential moving average."""
    return series.ewm(span=period, adjust=False).mean()


def compute_swings(df: pd.DataFrame, lookback: int) -> tuple[pd.Series, pd.Series]:
    """Compute confirmed swing highs and lows using symmetric pivot lookback."""
    highs = pd.Series(float("nan"), index=df.index, dtype=float)
    lows = pd.Series(float("nan"), index=df.index, dtype=float)

    for i in range(lookback, len(df) - lookback):
        window_high = df["high"].iloc[i - lookback : i + lookback + 1]
        window_low = df["low"].iloc[i - lookback : i + lookback + 1]
        if df["high"].iloc[i] == window_high.max():
            highs.iloc[i] = df["high"].iloc[i]
        if df["low"].iloc[i] == window_low.min():
            lows.iloc[i] = df["low"].iloc[i]
    return highs.ffill(), lows.ffill()


def compute_fvg(df: pd.DataFrame) -> pd.DataFrame:
    """Compute bullish and bearish FVG zones."""
    out = pd.DataFrame(index=df.index)
    out["bull_fvg"] = df["low"] > df["high"].shift(2)
    out["bear_fvg"] = df["high"] < df["low"].shift(2)
    out["bull_fvg_low"] = df["high"].shift(2)
    out["bull_fvg_high"] = df["low"]
    out["bear_fvg_low"] = df["high"]
    out["bear_fvg_high"] = df["low"].shift(2)
    return out


def prepare_features(
    df: pd.DataFrame,
    ema_fast: int,
    ema_slow: int,
    swing_lookback: int,
) -> pd.DataFrame:
    """Prepare all indicators required by the strategy."""
    out = df.copy()
    out["ema_fast"] = ema(out["close"], ema_fast)
    out["ema_slow"] = ema(out["close"], ema_slow)
    out["swing_high"], out["swing_low"] = compute_swings(out, swing_lookback)
    fvg = compute_fvg(out)
    out = pd.concat([out, fvg], axis=1)
    return out
