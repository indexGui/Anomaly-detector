"""Feature engineering for the anomaly detection engine."""

import numpy as np
import pandas as pd


def compute_features(df: pd.DataFrame, ema_fast: int = 10, ema_slow: int = 30) -> pd.DataFrame:
    """Add derived features to an OHLCV DataFrame.

    Columns added
    -------------
    pct_return : percent change of Close
    log_return : log return of Close
    candle_range_pct : (High - Low) / Close
    dollar_volume : Close * Volume
    ema_fast : EMA of Close with *ema_fast* span
    ema_slow : EMA of Close with *ema_slow* span

    Parameters
    ----------
    df : DataFrame
        Must contain at least ``Close`` and ``Volume`` columns.
        ``High`` and ``Low`` are used when available.
    ema_fast, ema_slow : int
        Spans for the fast / slow EMA.

    Returns
    -------
    DataFrame
        Original data with feature columns appended (copy).
    """
    out = df.copy()

    # Returns
    out["pct_return"] = out["Close"].pct_change()
    out["log_return"] = np.log(out["Close"] / out["Close"].shift(1))

    # Candle range
    if "High" in out.columns and "Low" in out.columns:
        out["candle_range_pct"] = (out["High"] - out["Low"]) / out["Close"]
    else:
        out["candle_range_pct"] = np.nan

    # Volume & dollar volume
    if "Volume" in out.columns:
        out["dollar_volume"] = out["Close"] * out["Volume"]
    else:
        out["dollar_volume"] = np.nan

    # EMA trends
    out["ema_fast"] = out["Close"].ewm(span=ema_fast, adjust=False).mean()
    out["ema_slow"] = out["Close"].ewm(span=ema_slow, adjust=False).mean()

    return out


def robust_zscore(series: pd.Series, window: int = 50) -> pd.Series:
    """Compute a rolling MAD-based (robust) z-score.

    Z = (x - rolling_median) / (1.4826 * rolling_MAD)

    The constant 1.4826 makes the MAD consistent with the standard
    deviation for normally distributed data.

    Parameters
    ----------
    series : Series
        Input values.
    window : int
        Rolling window size.

    Returns
    -------
    Series
        Robust z-scores (NaN where insufficient data).
    """
    rolling_median = series.rolling(window, min_periods=max(1, window // 2)).median()
    rolling_mad = (
        series.rolling(window, min_periods=max(1, window // 2))
        .apply(lambda x: np.median(np.abs(x - np.median(x))), raw=True)
    )
    # Scale MAD to be consistent with std-dev
    scaled_mad = 1.4826 * rolling_mad
    # Avoid division by zero
    scaled_mad = scaled_mad.replace(0, np.nan)
    return (series - rolling_median) / scaled_mad


def compute_zscores(
    df: pd.DataFrame, window: int = 50
) -> pd.DataFrame:
    """Add z-score columns for key features.

    Columns added
    -------------
    return_zscore : robust z-score of ``pct_return``
    volume_zscore : robust z-score of ``Volume``
    range_zscore  : robust z-score of ``candle_range_pct``

    Parameters
    ----------
    df : DataFrame
        Must already contain the feature columns produced by
        :func:`compute_features`.
    window : int
        Rolling window for z-score calculation.

    Returns
    -------
    DataFrame
        Copy with z-score columns appended.
    """
    out = df.copy()

    if "pct_return" in out.columns:
        out["return_zscore"] = robust_zscore(out["pct_return"], window)

    if "Volume" in out.columns:
        out["volume_zscore"] = robust_zscore(out["Volume"], window)

    if "candle_range_pct" in out.columns:
        out["range_zscore"] = robust_zscore(out["candle_range_pct"], window)

    return out
