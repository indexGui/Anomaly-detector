#!/usr/bin/env python
"""Entry-point for the anomaly detection alerting system.

Reads configuration from environment variables (or ``.env`` file),
wires up the :class:`AnomalyEngine` with Telegram and optional CSV
alert callbacks, and runs the continuous scan loop.
"""

import logging
import os
import sys

from alerts import CSVAlertLogger, TelegramAlerter
from config import Config
from engine import AnomalyEngine

logger = logging.getLogger(__name__)


def _bool_env(key: str, default: bool = False) -> bool:
    """Read a boolean from an env var (accepts ``true``/``1``/``yes``)."""
    val = os.environ.get(key, "").strip().lower()
    if not val:
        return default
    return val in ("true", "1", "yes")


def build_engine() -> AnomalyEngine:
    """Construct an :class:`AnomalyEngine` from environment variables.

    Environment variables
    ---------------------
    TELEGRAM_BOT_TOKEN : str
    TELEGRAM_CHAT_ID : str
    TELEGRAM_ENABLED : bool  (default ``true``)
    SCAN_INTERVAL_SECONDS : int  (default ``60``)
    COOLDOWN_SECONDS : int  (default ``300``)
    CSV_LOG_ENABLED : bool  (default ``false``)
    CSV_LOG_PATH : str  (default ``alerts.csv``)
    """
    scan_interval = int(os.environ.get("SCAN_INTERVAL_SECONDS", "60"))
    cooldown = int(os.environ.get("COOLDOWN_SECONDS", "300"))

    cfg = Config(
        scan_interval_seconds=scan_interval,
        cooldown_seconds=cooldown,
    )
    engine = AnomalyEngine(config=cfg)

    # --- Telegram ---
    telegram_enabled = _bool_env("TELEGRAM_ENABLED", default=True)
    alerter = TelegramAlerter(enabled=telegram_enabled)
    engine.on_alert(alerter)
    if telegram_enabled:
        logger.info("Telegram alerting enabled")
    else:
        logger.info("Telegram alerting disabled")

    # --- CSV logging ---
    if _bool_env("CSV_LOG_ENABLED"):
        csv_path = os.environ.get("CSV_LOG_PATH", "alerts.csv")
        csv_logger = CSVAlertLogger(path=csv_path)
        engine.on_alert(csv_logger)
        logger.info("CSV alert logging enabled → %s", csv_path)

    return engine


def main() -> None:
    """Configure logging, build engine, and start the scan loop."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("Starting anomaly detection alerting system")

    try:
        engine = build_engine()
    except Exception:
        logger.exception("Failed to initialize engine")
        sys.exit(1)

    engine.run()


if __name__ == "__main__":
    main()
