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


def _try_read_csv(content: bytes) -> pd.DataFrame:
    """Try multiple common encodings used by TAIFEX datasets."""
    for enc in ("utf-8-sig", "cp950", "big5", "latin1"):
        try:
            return pd.read_csv(BytesIO(content), encoding=enc)
        except UnicodeDecodeError:
            continue
        except pd.errors.ParserError:
            continue
    raise DataLoaderError("Unable to decode CSV with known encodings.")


def _decode_zip_first_csv(content: bytes) -> pd.DataFrame:
    """Extract first CSV from ZIP and decode with encoding fallbacks."""
    with ZipFile(BytesIO(content)) as zf:
        csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not csv_names:
            raise DataLoaderError("No CSV found in downloaded ZIP")
        raw = zf.read(csv_names[0])
    return _try_read_csv(raw)


def download_txf_data(config: Config = DEFAULT_CONFIG) -> pd.DataFrame:
    """Download TXF daily futures data from TAIFEX public endpoint.

    Returns a normalized DataFrame with columns:
    datetime, open, high, low, close, volume.
    """
    resp = requests.get(config.taifex_url, timeout=config.timeout)
    resp.raise_for_status()

    ctype = resp.headers.get("Content-Type", "").lower()
    if "text/html" in ctype:
        raise DataLoaderError(
            "TAIFEX endpoint returned HTML page instead of CSV/ZIP. "
            "Please check URL or use local CSV via load_csv()."
        )

    # TAIFEX may return ZIP or CSV in various encodings.
    if resp.content[:2] == b"PK":
        raw_df = _decode_zip_first_csv(resp.content)
    else:
        raw_df = _try_read_csv(resp.content)

    # Filter TXF if product column exists.
    if "商品代號" in raw_df.columns:
        raw_df = raw_df[raw_df["商品代號"].isin(["TX", "TXF"])]

    return _normalize_columns(raw_df)


def load_csv(path: str) -> pd.DataFrame:
    """Load local CSV and normalize schema."""
    for enc in ("utf-8-sig", "cp950", "big5", "latin1"):
        try:
            raw_df = pd.read_csv(path, encoding=enc)
            return _normalize_columns(raw_df)
        except UnicodeDecodeError:
            continue
    raise DataLoaderError(f"Unable to decode local CSV: {path}")
