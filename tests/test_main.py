"""Tests for main.py"""

import os
from unittest.mock import MagicMock, patch

from main import _bool_env, build_engine


# ---------------------------------------------------------------------------
# _bool_env
# ---------------------------------------------------------------------------


class TestBoolEnv:
    @patch.dict(os.environ, {"MY_FLAG": "true"})
    def test_true(self):
        assert _bool_env("MY_FLAG") is True

    @patch.dict(os.environ, {"MY_FLAG": "1"})
    def test_one(self):
        assert _bool_env("MY_FLAG") is True

    @patch.dict(os.environ, {"MY_FLAG": "yes"})
    def test_yes(self):
        assert _bool_env("MY_FLAG") is True

    @patch.dict(os.environ, {"MY_FLAG": "false"})
    def test_false(self):
        assert _bool_env("MY_FLAG") is False

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_uses_default(self):
        assert _bool_env("NONEXISTENT", default=True) is True
        assert _bool_env("NONEXISTENT", default=False) is False


# ---------------------------------------------------------------------------
# build_engine
# ---------------------------------------------------------------------------


class TestBuildEngine:
    @patch.dict(
        os.environ,
        {
            "TELEGRAM_BOT_TOKEN": "tok",
            "TELEGRAM_CHAT_ID": "123",
            "TELEGRAM_ENABLED": "true",
            "SCAN_INTERVAL_SECONDS": "30",
            "COOLDOWN_SECONDS": "120",
        },
    )
    def test_builds_with_env(self):
        engine = build_engine()
        assert engine.cfg.scan_interval_seconds == 30
        assert engine.cfg.cooldown_seconds == 120
        # At least one callback registered (TelegramAlerter)
        assert len(engine._alert_callbacks) >= 1

    @patch.dict(
        os.environ,
        {
            "TELEGRAM_ENABLED": "false",
            "CSV_LOG_ENABLED": "false",
        },
    )
    def test_disabled_telegram(self):
        engine = build_engine()
        # Callback is still registered but disabled internally
        assert len(engine._alert_callbacks) >= 1

    @patch.dict(
        os.environ,
        {
            "TELEGRAM_ENABLED": "false",
            "CSV_LOG_ENABLED": "true",
            "CSV_LOG_PATH": "/tmp/test_build_alerts.csv",
        },
    )
    def test_csv_logger_registered(self):
        engine = build_engine()
        # TelegramAlerter + CSVAlertLogger
        assert len(engine._alert_callbacks) >= 2
