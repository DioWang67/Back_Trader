"""Data loading utilities for TXF futures."""

from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

import pandas as pd
import requests

from config import Config, DEFAULT_CONFIG


class DataLoaderError(RuntimeError):
    """Raised when data loading fails."""


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names to datetime/open/high/low/close/volume format."""
    rename_map = {
        "Date": "datetime",
        "日期": "datetime",
        "Open": "open",
        "開盤價": "open",
        "High": "high",
        "最高價": "high",
        "Low": "low",
        "最低價": "low",
        "Close": "close",
        "收盤價": "close",
        "Volume": "volume",
        "成交量": "volume",
    }

    out = df.rename(columns=rename_map).copy()
    needed = ["datetime", "open", "high", "low", "close", "volume"]
    missing = [c for c in needed if c not in out.columns]
    if missing:
        raise DataLoaderError(f"CSV missing required columns: {missing}")

    out = out[needed]
    out["datetime"] = pd.to_datetime(out["datetime"], errors="coerce")
    for c in ["open", "high", "low", "close", "volume"]:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out = out.dropna().sort_values("datetime").reset_index(drop=True)
    return out


def download_txf_data(config: Config = DEFAULT_CONFIG) -> pd.DataFrame:
    """Download TXF daily futures data from TAIFEX public endpoint.

    Returns a normalized DataFrame with columns:
    datetime, open, high, low, close, volume.
    """
    resp = requests.get(config.taifex_url, timeout=config.timeout)
    resp.raise_for_status()

    # TAIFEX endpoint commonly returns zip; fallback to CSV if not zipped.
    if resp.content[:2] == b"PK":
        with ZipFile(BytesIO(resp.content)) as zf:
            csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if not csv_names:
                raise DataLoaderError("No CSV found in downloaded ZIP")
            with zf.open(csv_names[0]) as fobj:
                raw_df = pd.read_csv(fobj, encoding="utf-8-sig")
    else:
        raw_df = pd.read_csv(BytesIO(resp.content), encoding="utf-8-sig")

    # Filter TXF if product column exists.
    if "商品代號" in raw_df.columns:
        raw_df = raw_df[raw_df["商品代號"] == "TX"]

    return _normalize_columns(raw_df)


def load_csv(path: str) -> pd.DataFrame:
    """Load local CSV and normalize schema."""
    raw_df = pd.read_csv(path, encoding="utf-8-sig")
    return _normalize_columns(raw_df)
