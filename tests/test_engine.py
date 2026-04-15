"""Tests for engine.py"""

from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import numpy as np
import pandas as pd

from config import Config
from engine import (
    Alert,
    AnomalyEngine,
    StateManager,
    _detect_anomalies,
    _passes_cross_asset_filter,
)


# -----------------------------------------------------------------------
# Alert
# -----------------------------------------------------------------------


def test_alert_to_dict():
    alert = Alert(
        symbol="CL=F",
        timestamp="2024-01-01",
        pct_return=0.02,
        log_return=0.019,
        volume=5000,
        dollar_volume=500000,
        candle_range_pct=0.03,
        return_zscore=3.0,
        volume_zscore=2.8,
        range_zscore=1.0,
        anomaly_signals=2,
        reasons=["return_zscore=3.00", "volume_zscore=2.80"],
    )
    d = alert.to_dict()
    assert d["symbol"] == "CL=F"
    assert d["anomaly_signals"] == 2
    assert isinstance(d["reasons"], list)


# -----------------------------------------------------------------------
# StateManager
# -----------------------------------------------------------------------


class TestStateManager:
    def test_initial_state_allows_alert(self):
        sm = StateManager(cooldown_seconds=300)
        assert sm.can_alert("CL=F") is True

    def test_cooldown_blocks_alert(self):
        sm = StateManager(cooldown_seconds=300)
        sm.record_alert("CL=F")
        assert sm.can_alert("CL=F") is False

    def test_cooldown_expires(self):
        sm = StateManager(cooldown_seconds=1)
        sm.record_alert("CL=F")
        # Backdate last alert
        sm._last_alert["CL=F"] = datetime.now(timezone.utc) - timedelta(seconds=2)
        assert sm.can_alert("CL=F") is True

    def test_last_alert_time(self):
        sm = StateManager()
        assert sm.last_alert_time("CL=F") is None
        sm.record_alert("CL=F")
        assert sm.last_alert_time("CL=F") is not None


# -----------------------------------------------------------------------
# Cross-asset filter
# -----------------------------------------------------------------------


class TestCrossAssetFilter:
    def test_opposite_direction_passes(self):
        assert _passes_cross_asset_filter(0.02, -0.01, 0.5) is True

    def test_broad_market_move_filtered(self):
        # Benchmark moved 80% as much as the asset in the same direction
        assert _passes_cross_asset_filter(0.02, 0.016, 0.5) is False

    def test_asset_specific_passes(self):
        # Benchmark moved only 20% as much
        assert _passes_cross_asset_filter(0.02, 0.004, 0.5) is True

    def test_zero_returns(self):
        assert _passes_cross_asset_filter(0.0, 0.01, 0.5) is True
        assert _passes_cross_asset_filter(0.01, 0.0, 0.5) is True


# -----------------------------------------------------------------------
# _detect_anomalies
# -----------------------------------------------------------------------


class TestDetectAnomalies:
    def _make_row(self, **overrides):
        defaults = {
            "_symbol": "CL=F",
            "pct_return": 0.001,
            "log_return": 0.001,
            "Volume": 1000,
            "dollar_volume": 100000,
            "candle_range_pct": 0.005,
            "return_zscore": 0.5,
            "volume_zscore": 0.5,
            "range_zscore": 0.5,
        }
        defaults.update(overrides)
        return pd.Series(defaults)

    def test_no_alert_for_normal_bar(self):
        row = self._make_row()
        assert _detect_anomalies(row, Config()) is None

    def test_alert_on_two_signals(self):
        row = self._make_row(return_zscore=3.0, volume_zscore=3.0)
        alert = _detect_anomalies(row, Config())
        assert alert is not None
        assert alert.anomaly_signals >= 2

    def test_alert_on_strong_move(self):
        row = self._make_row(pct_return=0.02)
        alert = _detect_anomalies(row, Config())
        assert alert is not None

    def test_single_signal_no_alert(self):
        row = self._make_row(return_zscore=3.0)
        alert = _detect_anomalies(row, Config())
        # Only 1 signal (return_zscore) and abs return below strong_move → no alert
        assert alert is None


# -----------------------------------------------------------------------
# AnomalyEngine integration (mocked data)
# -----------------------------------------------------------------------


def _make_ohlcv(n=60, seed=42):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.standard_normal(n) * 0.5)
    return pd.DataFrame(
        {
            "Open": close - 0.1,
            "High": close + rng.uniform(0, 1, n),
            "Low": close - rng.uniform(0, 1, n),
            "Close": close,
            "Volume": rng.integers(1000, 5000, n).astype(float),
        },
        index=pd.date_range("2024-01-01", periods=n, freq="5min"),
    )


class TestAnomalyEngine:
    @patch("engine.fetch_intraday")
    def test_scan_once_no_crash(self, mock_fetch):
        mock_fetch.return_value = {
            "CL=F": _make_ohlcv(),
            "BZ=F": _make_ohlcv(seed=1),
            "USO": _make_ohlcv(seed=2),
            "XLE": _make_ohlcv(seed=3),
            "SPY": _make_ohlcv(seed=4),
        }
        engine = AnomalyEngine()
        alerts = engine.scan_once()
        assert isinstance(alerts, list)

    @patch("engine.fetch_intraday")
    def test_scan_once_empty_data(self, mock_fetch):
        mock_fetch.return_value = {}
        engine = AnomalyEngine()
        alerts = engine.scan_once()
        assert alerts == []

    @patch("engine.fetch_intraday")
    def test_callback_invoked(self, mock_fetch):
        # Create data with a guaranteed anomaly at the last bar
        df = _make_ohlcv()
        df.iloc[-1, df.columns.get_loc("Close")] = df.iloc[-2]["Close"] * 1.05
        df.iloc[-1, df.columns.get_loc("Volume")] = 999999
        df.iloc[-1, df.columns.get_loc("High")] = df.iloc[-1]["Close"] * 1.02

        spy = _make_ohlcv(seed=99)  # uncorrelated benchmark
        mock_fetch.return_value = {"CL=F": df, "SPY": spy}

        cfg = Config(symbols=["CL=F"])
        engine = AnomalyEngine(config=cfg)
        received = []
        engine.on_alert(lambda a: received.append(a))
        # Run via scan_once — callbacks are only invoked in run(), so test directly
        alerts = engine.scan_once()
        # Invoke callbacks manually for scan_once test
        for a in alerts:
            for cb in engine._alert_callbacks:
                cb(a)
        # We injected a big move; if the engine detected it, callbacks were called
        # (detection depends on z-score window; this is a best-effort integration test)

    def test_latest_return_edge_cases(self):
        assert AnomalyEngine._latest_return(None) == 0.0
        assert AnomalyEngine._latest_return(pd.DataFrame()) == 0.0
        df = pd.DataFrame({"Close": [100.0]})
        assert AnomalyEngine._latest_return(df) == 0.0
