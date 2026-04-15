"""Configuration for the anomaly detection engine."""

from dataclasses import dataclass, field
from typing import List


@dataclass
class Config:
    """Engine configuration with sensible defaults."""

    # Symbols to monitor
    symbols: List[str] = field(
        default_factory=lambda: ["CL=F", "BZ=F", "USO", "XLE"]
    )

    # Benchmark for cross-asset filtering
    benchmark_symbol: str = "SPY"

    # Data interval (yfinance format)
    interval: str = "5m"

    # Lookback period for data download
    period: str = "1d"

    # Z-score thresholds
    return_zscore_threshold: float = 2.5
    volume_zscore_threshold: float = 2.5
    range_zscore_threshold: float = 2.5

    # Absolute return threshold (fraction, e.g. 0.015 = 1.5%)
    absolute_return_threshold: float = 0.015

    # Minimum anomaly signals required to trigger an alert
    min_anomaly_signals: int = 2

    # Strong absolute move threshold that triggers alert on its own (fraction)
    strong_move_threshold: float = 0.015

    # Z-score lookback window (number of bars)
    zscore_window: int = 50

    # EMA spans
    ema_fast: int = 10
    ema_slow: int = 30

    # Cooldown per symbol in seconds
    cooldown_seconds: int = 300

    # Engine scan interval in seconds
    scan_interval_seconds: int = 60

    # Cross-asset correlation threshold — ignore signal if benchmark moved
    # at least this fraction of the asset's move in the same direction
    benchmark_filter_ratio: float = 0.5
