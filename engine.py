"""Core anomaly detection engine."""

import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

import pandas as pd

from config import Config
from data import fetch_intraday
from features import compute_features, compute_zscores

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Alert data structure
# ---------------------------------------------------------------------------

@dataclass
class Alert:
    """Structured alert object emitted by the engine."""

    symbol: str
    timestamp: str
    pct_return: float
    log_return: float
    volume: float
    dollar_volume: float
    candle_range_pct: float
    return_zscore: float
    volume_zscore: float
    range_zscore: float
    anomaly_signals: int
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------

class StateManager:
    """Tracks per-symbol cooldown to avoid alert spam."""

    def __init__(self, cooldown_seconds: int = 300) -> None:
        self._cooldown = cooldown_seconds
        self._last_alert: Dict[str, datetime] = {}

    def can_alert(self, symbol: str) -> bool:
        last = self._last_alert.get(symbol)
        if last is None:
            return True
        elapsed = (datetime.now(timezone.utc) - last).total_seconds()
        return elapsed >= self._cooldown

    def record_alert(self, symbol: str) -> None:
        self._last_alert[symbol] = datetime.now(timezone.utc)

    def last_alert_time(self, symbol: str) -> Optional[datetime]:
        return self._last_alert.get(symbol)


# ---------------------------------------------------------------------------
# Anomaly detection helpers
# ---------------------------------------------------------------------------

def _detect_anomalies(row: pd.Series, cfg: Config) -> Optional[Alert]:
    """Evaluate a single bar for anomaly conditions.

    Returns an :class:`Alert` if the bar is anomalous, else ``None``.
    """
    reasons: List[str] = []

    return_z = abs(row.get("return_zscore", 0) or 0)
    volume_z = abs(row.get("volume_zscore", 0) or 0)
    range_z = abs(row.get("range_zscore", 0) or 0)
    abs_ret = abs(row.get("pct_return", 0) or 0)

    if return_z > cfg.return_zscore_threshold:
        reasons.append(f"return_zscore={return_z:.2f}")
    if volume_z > cfg.volume_zscore_threshold:
        reasons.append(f"volume_zscore={volume_z:.2f}")
    if range_z > cfg.range_zscore_threshold:
        reasons.append(f"range_zscore={range_z:.2f}")
    if abs_ret > cfg.absolute_return_threshold:
        reasons.append(f"abs_return={abs_ret:.4f}")

    anomaly_count = len(reasons)

    # Alert rules
    is_anomaly = (
        anomaly_count >= cfg.min_anomaly_signals
        or abs_ret > cfg.strong_move_threshold
    )

    if not is_anomaly:
        return None

    return Alert(
        symbol=row.get("_symbol", ""),
        timestamp=str(row.name) if hasattr(row, "name") else "",
        pct_return=float(row.get("pct_return", 0) or 0),
        log_return=float(row.get("log_return", 0) or 0),
        volume=float(row.get("Volume", 0) or 0),
        dollar_volume=float(row.get("dollar_volume", 0) or 0),
        candle_range_pct=float(row.get("candle_range_pct", 0) or 0),
        return_zscore=float(row.get("return_zscore", 0) or 0),
        volume_zscore=float(row.get("volume_zscore", 0) or 0),
        range_zscore=float(row.get("range_zscore", 0) or 0),
        anomaly_signals=anomaly_count,
        reasons=reasons,
    )


# ---------------------------------------------------------------------------
# Cross-asset filter
# ---------------------------------------------------------------------------

def _passes_cross_asset_filter(
    symbol_return: float,
    benchmark_return: float,
    ratio: float,
) -> bool:
    """Return ``True`` if the signal is NOT just a broad market move.

    If the benchmark (SPY) moved in the same direction by at least
    ``ratio`` of the asset's move, we consider the signal to be a
    market-wide move and filter it out.
    """
    if symbol_return == 0:
        return True
    if benchmark_return == 0:
        return True
    # Same direction check
    same_direction = (symbol_return > 0) == (benchmark_return > 0)
    if not same_direction:
        return True  # opposite moves → likely asset-specific
    # If benchmark accounts for a large fraction of the move, filter out
    return abs(benchmark_return / symbol_return) < ratio


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class AnomalyEngine:
    """Main engine that ties data, features, and detection together."""

    def __init__(self, config: Optional[Config] = None) -> None:
        self.cfg = config or Config()
        self.state = StateManager(cooldown_seconds=self.cfg.cooldown_seconds)
        self._alert_callbacks: list = []

    def on_alert(self, callback) -> None:
        """Register a callback that receives each :class:`Alert`."""
        self._alert_callbacks.append(callback)

    # ----- public API -----

    def scan_once(self) -> List[Alert]:
        """Run a single scan cycle and return any alerts."""
        all_symbols = self.cfg.symbols + [self.cfg.benchmark_symbol]
        data = fetch_intraday(
            all_symbols,
            interval=self.cfg.interval,
            period=self.cfg.period,
        )
        if not data:
            logger.warning("No data returned for any symbol")
            return []

        # Get benchmark latest return
        benchmark_return = self._latest_return(data.get(self.cfg.benchmark_symbol))

        alerts: List[Alert] = []
        for symbol in self.cfg.symbols:
            df = data.get(symbol)
            if df is None or df.empty:
                continue

            alert = self._process_symbol(symbol, df, benchmark_return)
            if alert is not None:
                alerts.append(alert)

        return alerts

    def run(self) -> None:
        """Run the engine in a continuous loop.

        The loop catches all exceptions so the engine never crashes.
        """
        logger.info("Engine started — scanning every %ds", self.cfg.scan_interval_seconds)
        while True:
            try:
                alerts = self.scan_once()
                for alert in alerts:
                    logger.info("ALERT: %s", alert.to_dict())
                    for cb in self._alert_callbacks:
                        try:
                            cb(alert)
                        except Exception:
                            logger.exception("Alert callback error")
            except KeyboardInterrupt:
                logger.info("Engine stopped by user")
                break
            except Exception:
                logger.exception("Error during scan cycle")

            time.sleep(self.cfg.scan_interval_seconds)

    # ----- internal helpers -----

    def _process_symbol(
        self,
        symbol: str,
        df: pd.DataFrame,
        benchmark_return: float,
    ) -> Optional[Alert]:
        """Feature-engineer, detect, filter, and emit for one symbol."""
        df = compute_features(df, ema_fast=self.cfg.ema_fast, ema_slow=self.cfg.ema_slow)
        df = compute_zscores(df, window=self.cfg.zscore_window)

        if df.empty:
            return None

        latest = df.iloc[-1].copy()
        latest["_symbol"] = symbol

        alert = _detect_anomalies(latest, self.cfg)
        if alert is None:
            return None

        # Cross-asset filter
        if not _passes_cross_asset_filter(
            alert.pct_return, benchmark_return, self.cfg.benchmark_filter_ratio
        ):
            logger.debug(
                "Filtered %s — appears to be broad market move", symbol
            )
            return None

        # Cooldown check
        if not self.state.can_alert(symbol):
            logger.debug("Cooldown active for %s — skipping alert", symbol)
            return None

        self.state.record_alert(symbol)
        return alert

    @staticmethod
    def _latest_return(df: Optional[pd.DataFrame]) -> float:
        """Return the latest bar pct return from a raw OHLCV frame."""
        if df is None or df.empty or len(df) < 2:
            return 0.0
        closes = df["Close"] if "Close" in df.columns else None
        if closes is None:
            return 0.0
        return float(closes.iloc[-1] / closes.iloc[-2] - 1)


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    engine = AnomalyEngine()
    engine.run()
