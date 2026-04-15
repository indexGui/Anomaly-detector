"""Tests for alerts.py"""

import csv
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from engine import Alert
from alerts import (
    CSVAlertLogger,
    TelegramAlerter,
    format_alert,
    send_telegram,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_alert(**overrides) -> Alert:
    defaults = dict(
        symbol="CL=F",
        timestamp="2024-06-15 14:30:00+00:00",
        pct_return=0.025,
        log_return=0.024,
        volume=12000,
        dollar_volume=960000,
        candle_range_pct=0.018,
        return_zscore=3.5,
        volume_zscore=2.9,
        range_zscore=1.2,
        anomaly_signals=2,
        reasons=["return_zscore=3.50", "volume_zscore=2.90"],
    )
    defaults.update(overrides)
    return Alert(**defaults)


# ---------------------------------------------------------------------------
# format_alert
# ---------------------------------------------------------------------------


class TestFormatAlert:
    def test_contains_symbol(self):
        msg = format_alert(_make_alert())
        assert "CL=F" in msg

    def test_direction_up(self):
        msg = format_alert(_make_alert(pct_return=0.02))
        assert "UP" in msg

    def test_direction_down(self):
        msg = format_alert(_make_alert(pct_return=-0.02))
        assert "DOWN" in msg

    def test_benchmark_included(self):
        msg = format_alert(_make_alert(), benchmark_return=-0.005)
        assert "Benchmark" in msg
        assert "-0.50" in msg

    def test_benchmark_absent_by_default(self):
        msg = format_alert(_make_alert())
        assert "Benchmark" not in msg

    def test_contains_zscores(self):
        msg = format_alert(_make_alert())
        assert "3.50" in msg  # return_zscore
        assert "2.90" in msg  # volume_zscore

    def test_contains_reasons(self):
        msg = format_alert(_make_alert())
        assert "return_zscore=3.50" in msg


# ---------------------------------------------------------------------------
# send_telegram
# ---------------------------------------------------------------------------


class TestSendTelegram:
    @patch("alerts.requests.post")
    def test_success(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        assert send_telegram("hi", "tok", "123") is True
        mock_post.assert_called_once()

    @patch("alerts.requests.post")
    def test_retries_on_failure(self, mock_post):
        mock_post.return_value = MagicMock(status_code=500, text="err")
        result = send_telegram("hi", "tok", "123", max_retries=2, retry_backoff=0)
        assert result is False
        assert mock_post.call_count == 2

    @patch("alerts.requests.post")
    def test_retries_on_exception(self, mock_post):
        import requests as req

        mock_post.side_effect = req.ConnectionError("offline")
        result = send_telegram("hi", "tok", "123", max_retries=2, retry_backoff=0)
        assert result is False
        assert mock_post.call_count == 2

    @patch("alerts.requests.post")
    def test_succeeds_after_retry(self, mock_post):
        fail = MagicMock(status_code=500, text="err")
        ok = MagicMock(status_code=200)
        mock_post.side_effect = [fail, ok]
        result = send_telegram("hi", "tok", "123", max_retries=3, retry_backoff=0)
        assert result is True
        assert mock_post.call_count == 2


# ---------------------------------------------------------------------------
# TelegramAlerter
# ---------------------------------------------------------------------------


class TestTelegramAlerter:
    @patch("alerts.send_telegram", return_value=True)
    def test_call_sends_when_enabled(self, mock_send):
        alerter = TelegramAlerter(token="tok", chat_id="123", enabled=True)
        result = alerter(_make_alert())
        assert result is True
        mock_send.assert_called_once()

    def test_call_noop_when_disabled(self):
        alerter = TelegramAlerter(token="tok", chat_id="123", enabled=False)
        result = alerter(_make_alert())
        assert result is False

    def test_call_warns_missing_credentials(self):
        alerter = TelegramAlerter(token="", chat_id="", enabled=True)
        result = alerter(_make_alert())
        assert result is False

    @patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "envtok", "TELEGRAM_CHAT_ID": "999"})
    def test_reads_env_vars(self):
        alerter = TelegramAlerter()
        assert alerter.token == "envtok"
        assert alerter.chat_id == "999"


# ---------------------------------------------------------------------------
# CSVAlertLogger
# ---------------------------------------------------------------------------


class TestCSVAlertLogger:
    def test_creates_file_with_header(self, tmp_path):
        path = tmp_path / "test_alerts.csv"
        CSVAlertLogger(path=str(path))
        assert path.exists()
        with path.open() as fh:
            reader = csv.reader(fh)
            header = next(reader)
        assert "symbol" in header

    def test_appends_alert_row(self, tmp_path):
        path = tmp_path / "test_alerts.csv"
        logger_cb = CSVAlertLogger(path=str(path))
        logger_cb(_make_alert())
        with path.open() as fh:
            rows = list(csv.reader(fh))
        assert len(rows) == 2  # header + 1 data row
        # data row contains the symbol
        assert "CL=F" in rows[1]

    def test_multiple_alerts_append(self, tmp_path):
        path = tmp_path / "test_alerts.csv"
        logger_cb = CSVAlertLogger(path=str(path))
        logger_cb(_make_alert(symbol="AAA"))
        logger_cb(_make_alert(symbol="BBB"))
        with path.open() as fh:
            rows = list(csv.reader(fh))
        assert len(rows) == 3  # header + 2 data rows
