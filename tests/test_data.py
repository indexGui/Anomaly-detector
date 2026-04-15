"""Tests for data.py (uses mocks to avoid real network calls)."""

from unittest.mock import MagicMock, patch

import pandas as pd

from data import fetch_intraday


def _fake_ohlcv() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": [100.0, 101.0],
            "High": [102.0, 103.0],
            "Low": [99.0, 100.0],
            "Close": [101.0, 102.0],
            "Volume": [1000, 2000],
        },
        index=pd.date_range("2024-01-01", periods=2, freq="5min"),
    )


@patch("data.yf.Ticker")
def test_fetch_intraday_returns_dict(mock_ticker_cls):
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = _fake_ohlcv()
    mock_ticker_cls.return_value = mock_ticker

    result = fetch_intraday(["CL=F", "USO"], interval="5m", period="1d")
    assert isinstance(result, dict)
    assert "CL=F" in result
    assert "USO" in result
    assert list(result["CL=F"].columns) == ["Open", "High", "Low", "Close", "Volume"]


@patch("data.yf.Ticker")
def test_fetch_intraday_handles_empty(mock_ticker_cls):
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = pd.DataFrame()
    mock_ticker_cls.return_value = mock_ticker

    result = fetch_intraday(["BAD"], interval="5m", period="1d")
    assert result == {}


@patch("data.yf.Ticker")
def test_fetch_intraday_handles_exception(mock_ticker_cls):
    mock_ticker_cls.side_effect = RuntimeError("network error")
    result = fetch_intraday(["CL=F"], interval="5m", period="1d")
    assert result == {}
