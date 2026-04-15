"""Telegram alerting module for the anomaly detection engine."""

import csv
import logging
import os
import time
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Alert formatting
# ---------------------------------------------------------------------------

_TEMPLATE = """\
🚨 *Anomaly Detected*

*Symbol:* `{symbol}`
*Time (UTC):* `{timestamp}`
*Direction:* {direction}
*Return:* `{pct_return:+.4%}`
*Volume:* `{volume:,.0f}`

*Z-scores*
  Return: `{return_zscore:+.2f}`
  Volume: `{volume_zscore:+.2f}`
  Range:  `{range_zscore:+.2f}`

*Signals:* {anomaly_signals}  ({reasons})"""

_BENCHMARK_LINE = "\n*Benchmark comparison:* `{benchmark_return:+.4%}`"


def format_alert(alert, benchmark_return: Optional[float] = None) -> str:
    """Return a Telegram-friendly Markdown message for an alert.

    Parameters
    ----------
    alert
        An ``Alert`` dataclass instance (from ``engine.py``).
    benchmark_return
        Optional benchmark return to include for context.
    """
    direction = "⬆️ UP" if alert.pct_return >= 0 else "⬇️ DOWN"
    text = _TEMPLATE.format(
        symbol=alert.symbol,
        timestamp=alert.timestamp,
        direction=direction,
        pct_return=alert.pct_return,
        volume=alert.volume,
        return_zscore=alert.return_zscore,
        volume_zscore=alert.volume_zscore,
        range_zscore=alert.range_zscore,
        anomaly_signals=alert.anomaly_signals,
        reasons=", ".join(alert.reasons),
    )
    if benchmark_return is not None:
        text += _BENCHMARK_LINE.format(benchmark_return=benchmark_return)
    return text


# ---------------------------------------------------------------------------
# Telegram sender
# ---------------------------------------------------------------------------

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

# Retry settings
_MAX_RETRIES = 3
_RETRY_BACKOFF = 2  # seconds (doubles each attempt)


def send_telegram(
    text: str,
    token: str,
    chat_id: str,
    max_retries: int = _MAX_RETRIES,
    retry_backoff: float = _RETRY_BACKOFF,
) -> bool:
    """Send a message via the Telegram Bot API.

    Parameters
    ----------
    text
        Message body (Markdown).
    token
        Telegram bot token.
    chat_id
        Target chat / channel ID.
    max_retries
        Number of retry attempts on transient errors.
    retry_backoff
        Initial delay between retries (doubled each attempt).

    Returns
    -------
    bool
        ``True`` if the message was delivered, ``False`` otherwise.
    """
    url = _TELEGRAM_API.format(token=token)
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code == 200:
                return True
            logger.warning(
                "Telegram API returned %s on attempt %d: %s",
                resp.status_code,
                attempt,
                resp.text,
            )
        except requests.RequestException as exc:
            logger.warning(
                "Telegram request failed on attempt %d: %s", attempt, exc
            )

        if attempt < max_retries:
            delay = retry_backoff * (2 ** (attempt - 1))
            time.sleep(delay)

    logger.error("Failed to send Telegram message after %d attempts", max_retries)
    return False


# ---------------------------------------------------------------------------
# TelegramAlerter — callback-compatible class
# ---------------------------------------------------------------------------


class TelegramAlerter:
    """Wraps Telegram config and exposes a callback for :class:`AnomalyEngine`.

    Parameters
    ----------
    token
        Bot token.  Falls back to ``TELEGRAM_BOT_TOKEN`` env var.
    chat_id
        Chat ID.  Falls back to ``TELEGRAM_CHAT_ID`` env var.
    enabled
        Master on/off switch.  When ``False``, :meth:`__call__` is a no-op.
    """

    def __init__(
        self,
        token: Optional[str] = None,
        chat_id: Optional[str] = None,
        enabled: bool = True,
    ) -> None:
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")
        self.enabled = enabled

    # Make the instance usable as a callback via engine.on_alert(alerter)
    def __call__(self, alert, benchmark_return: Optional[float] = None) -> bool:
        """Format and send an alert.  Returns ``True`` on success."""
        if not self.enabled:
            logger.debug("Telegram alerting disabled — skipping")
            return False
        if not self.token or not self.chat_id:
            logger.warning("Telegram credentials missing — skipping alert")
            return False

        text = format_alert(alert, benchmark_return=benchmark_return)
        return send_telegram(text, self.token, self.chat_id)


# ---------------------------------------------------------------------------
# Optional CSV logger
# ---------------------------------------------------------------------------

_CSV_HEADER = [
    "timestamp_utc",
    "symbol",
    "direction",
    "pct_return",
    "volume",
    "return_zscore",
    "volume_zscore",
    "range_zscore",
    "anomaly_signals",
    "reasons",
]


class CSVAlertLogger:
    """Append each alert as a row in a CSV file.

    Parameters
    ----------
    path
        CSV file path.  Created with header if it does not exist.
    """

    def __init__(self, path: str = "alerts.csv") -> None:
        self.path = Path(path)
        self._ensure_header()

    def _ensure_header(self) -> None:
        if not self.path.exists():
            with self.path.open("w", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(_CSV_HEADER)

    def __call__(self, alert) -> None:
        """Append an alert row."""
        direction = "UP" if alert.pct_return >= 0 else "DOWN"
        row = [
            alert.timestamp,
            alert.symbol,
            direction,
            f"{alert.pct_return:.6f}",
            f"{alert.volume:.0f}",
            f"{alert.return_zscore:.4f}",
            f"{alert.volume_zscore:.4f}",
            f"{alert.range_zscore:.4f}",
            alert.anomaly_signals,
            "|".join(alert.reasons),
        ]
        with self.path.open("a", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(row)
        logger.debug("Alert logged to %s", self.path)
