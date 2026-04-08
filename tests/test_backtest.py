"""Test cases for backtest system."""

from __future__ import annotations

import random
import unittest

import pandas as pd

from backtest import run_backtest
from config import Config



def make_data(n: int, seed: int = 42, trend: float = 0.1, vol: float = 5.0) -> pd.DataFrame:
    """Generate synthetic OHLCV data for testing without numpy dependency."""
    rng = random.Random(seed)
    dt = pd.date_range("2020-01-01", periods=n, freq="D")

    prices: list[float] = []
    price = 10000.0
    for _ in range(n):
        price += rng.gauss(trend, vol)
        prices.append(price)

    open_, close, high, low, volume = [], [], [], [], []
    for p in prices:
        o = p + rng.gauss(0, 2)
        c = p + rng.gauss(0, 2)
        h = max(o, c) + rng.uniform(1, 5)
        l = min(o, c) - rng.uniform(1, 5)
        v = rng.randint(1000, 10000)
        open_.append(o)
        close.append(c)
        high.append(h)
        low.append(l)
        volume.append(v)

    return pd.DataFrame(
        {
            "datetime": dt,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )


class BacktestTestCase(unittest.TestCase):
    """Backtest coverage for required scenarios."""

    def setUp(self) -> None:
        self.config = Config()

    def test_normal_data(self) -> None:
        df = make_data(600)
        curve, trades, _ = run_backtest(df, self.config)
        self.assertFalse(curve.empty)
        self.assertIsInstance(trades, list)

    def test_empty_data(self) -> None:
        df = pd.DataFrame(columns=["datetime", "open", "high", "low", "close", "volume"])
        curve, trades, _ = run_backtest(df, self.config)
        self.assertTrue(curve.empty)
        self.assertEqual(len(trades), 0)

    def test_extreme_market(self) -> None:
        df = make_data(500, vol=80.0)
        curve, trades, _ = run_backtest(df, self.config)
        self.assertFalse(curve.empty)
        self.assertGreaterEqual(len(trades), 0)

    def test_small_sample(self) -> None:
        df = make_data(30)
        curve, trades, _ = run_backtest(df, self.config)
        self.assertIsNotNone(curve)
        self.assertIsNotNone(trades)

    def test_large_sample(self) -> None:
        df = make_data(5000)
        curve, trades, _ = run_backtest(df, self.config)
        self.assertFalse(curve.empty)


if __name__ == "__main__":
    unittest.main()
