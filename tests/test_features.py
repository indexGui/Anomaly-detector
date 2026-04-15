"""Tests for features.py"""

import numpy as np
import pandas as pd

from features import compute_features, compute_zscores, robust_zscore


def _make_ohlcv(n: int = 60) -> pd.DataFrame:
    """Create a simple synthetic OHLCV DataFrame."""
    rng = np.random.default_rng(42)
    close = 100 + np.cumsum(rng.standard_normal(n) * 0.5)
    high = close + rng.uniform(0, 1, n)
    low = close - rng.uniform(0, 1, n)
    volume = rng.integers(1000, 5000, n).astype(float)
    return pd.DataFrame(
        {"Open": close - 0.1, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=pd.date_range("2024-01-01", periods=n, freq="5min"),
    )


class TestComputeFeatures:
    def test_columns_added(self):
        df = _make_ohlcv()
        out = compute_features(df)
        for col in [
            "pct_return",
            "log_return",
            "candle_range_pct",
            "dollar_volume",
            "ema_fast",
            "ema_slow",
        ]:
            assert col in out.columns, f"Missing column {col}"

    def test_returns_not_all_nan(self):
        df = _make_ohlcv()
        out = compute_features(df)
        assert out["pct_return"].dropna().shape[0] > 0
        assert out["log_return"].dropna().shape[0] > 0

    def test_dollar_volume_positive(self):
        df = _make_ohlcv()
        out = compute_features(df)
        assert (out["dollar_volume"].dropna() >= 0).all()

    def test_original_not_mutated(self):
        df = _make_ohlcv()
        cols_before = set(df.columns)
        compute_features(df)
        assert set(df.columns) == cols_before

    def test_custom_ema_spans(self):
        df = _make_ohlcv()
        out = compute_features(df, ema_fast=5, ema_slow=20)
        assert "ema_fast" in out.columns
        assert "ema_slow" in out.columns


class TestRobustZscore:
    def test_output_length_matches(self):
        s = pd.Series(np.random.default_rng(0).standard_normal(100))
        z = robust_zscore(s, window=20)
        assert len(z) == len(s)

    def test_zero_when_constant(self):
        s = pd.Series([5.0] * 100)
        z = robust_zscore(s, window=20)
        # Constant series → MAD=0 → z-score = NaN (division by zero guard)
        assert z.dropna().empty or (z.dropna() == 0).all()

    def test_outlier_has_large_zscore(self):
        rng = np.random.default_rng(1)
        vals = rng.standard_normal(100)
        vals[99] = 20.0  # inject outlier
        s = pd.Series(vals)
        z = robust_zscore(s, window=50)
        assert abs(z.iloc[-1]) > 3


class TestComputeZscores:
    def test_zscore_columns_added(self):
        df = _make_ohlcv()
        df = compute_features(df)
        out = compute_zscores(df, window=20)
        for col in ["return_zscore", "volume_zscore", "range_zscore"]:
            assert col in out.columns
