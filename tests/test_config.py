"""Tests for config.py"""

from config import Config


def test_default_config():
    cfg = Config()
    assert cfg.symbols == ["CL=F", "BZ=F", "USO", "XLE"]
    assert cfg.benchmark_symbol == "SPY"
    assert cfg.interval == "5m"
    assert cfg.return_zscore_threshold == 2.5
    assert cfg.volume_zscore_threshold == 2.5
    assert cfg.range_zscore_threshold == 2.5
    assert cfg.absolute_return_threshold == 0.015
    assert cfg.min_anomaly_signals == 2
    assert cfg.strong_move_threshold == 0.015
    assert cfg.cooldown_seconds == 300


def test_custom_config():
    cfg = Config(symbols=["AAPL"], interval="1m", cooldown_seconds=60)
    assert cfg.symbols == ["AAPL"]
    assert cfg.interval == "1m"
    assert cfg.cooldown_seconds == 60
    # Defaults still apply for unset fields
    assert cfg.benchmark_symbol == "SPY"
