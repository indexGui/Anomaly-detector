"""Data ingestion module — fetches intraday data via yfinance."""

import logging
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


def fetch_intraday(
    symbols: List[str],
    interval: str = "5m",
    period: str = "1d",
) -> Dict[str, pd.DataFrame]:
    """Download intraday OHLCV data for a list of symbols.

    Parameters
    ----------
    symbols : list[str]
        Ticker symbols to fetch.
    interval : str
        Bar interval (e.g. ``"5m"``, ``"1m"``).
    period : str
        Lookback period (e.g. ``"1d"``, ``"5d"``).

    Returns
    -------
    dict[str, DataFrame]
        Mapping of symbol → OHLCV DataFrame.  Symbols that fail to
        download are omitted from the result.
    """
    result: Dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        try:
            df = _download_symbol(symbol, interval=interval, period=period)
            if df is not None and not df.empty:
                result[symbol] = df
            else:
                logger.warning("No data returned for %s", symbol)
        except Exception:
            logger.exception("Failed to fetch data for %s", symbol)
    return result


def _download_symbol(
    symbol: str,
    interval: str = "5m",
    period: str = "1d",
) -> Optional[pd.DataFrame]:
    """Download data for a single symbol and normalise columns."""
    ticker = yf.Ticker(symbol)
    df: pd.DataFrame = ticker.history(interval=interval, period=period)
    if df.empty:
        return None

    # Ensure standard column names
    df.columns = [c.strip().title() for c in df.columns]

    # Keep only OHLCV columns that exist
    keep = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
    df = df[keep].copy()
    return df
