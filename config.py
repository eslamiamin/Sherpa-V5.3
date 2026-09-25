"""
Configuration module for SHERPA V5.3.

Loads environment variables and defines:
- Runtime settings
- Market data settings
- Telegram settings
- Risk management
- Trade management
- Versioning
"""

import logging
import os

from dotenv import load_dotenv
from zoneinfo import ZoneInfo


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()


# ============================================================
# LOGGING
# ============================================================

LOGGING_LEVEL = logging.INFO

LOGGING_FORMAT = (
    "%(asctime)s - "
    "%(levelname)s - "
    "%(name)s - "
    "%(message)s"
)


# ============================================================
# TIMEZONES
# ============================================================

TIMEZONE_UTC = ZoneInfo("UTC")
TIMEZONE_TEHRAN = ZoneInfo("Asia/Tehran")


# ============================================================
# BOT RUNTIME
# ============================================================

SYMBOL_DELAY_SECONDS = 2.0

LOOP_DELAY_SECONDS = 60.0

MAX_CONCURRENT_POSITIONS = 5


# ============================================================
# MARKET DATA
# ============================================================

HOURLY_CANDLE_LIMIT = 300

DAILY_CANDLE_LIMIT = 250

MEXC_API_URL = (
    "https://api.mexc.com/api/v3/klines"
)


SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "AVAXUSDT",
    "NEARUSDT",
]


# ============================================================
# TELEGRAM
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN"
)

TELEGRAM_PERSONAL_CHAT_ID = os.getenv(
    "TELEGRAM_PERSONAL_CHAT_ID"
)

TELEGRAM_CHANNEL_CHAT_ID = os.getenv(
    "TELEGRAM_CHANNEL_CHAT_ID"
)

TELEGRAM_API_URL = (
    "https://api.telegram.org/"
    "bot{token}/sendMessage"
)

# HTTP timeout for Telegram requests.
TELEGRAM_REQUEST_TIMEOUT = 10


# ============================================================
# PAPER TRADING
# ============================================================

INITIAL_CAPITAL = 1000.0


# Maximum notional allocation per position.
# Example:
# $1000 capital × 25% = maximum $250 position.
MAX_POSITION_NOTIONAL_PCT = 0.25


# ============================================================
# RISK MANAGEMENT
# ============================================================

# Strong market regime:
# 2.5% of capital at risk per trade.
STRONG_REGIME_RISK_PCT = 0.025


# Normal market regime:
# 1% of capital at risk per trade.
NORMAL_REGIME_RISK_PCT = 0.01


# ============================================================
# TP / SL
# ============================================================

TP_ATR_MULTIPLIER = 2.0

SL_ATR_MULTIPLIER = 1.2


# ============================================================
# POSITION MANAGEMENT
# ============================================================

# When price reaches 50% of the original TP distance:
# move SL to entry.
BREAK_EVEN_TRIGGER_RATIO = 0.50


# When price reaches 80% of the original TP distance:
# lock 25% of the original TP distance.
PROFIT_LOCK_TRIGGER_RATIO = 0.80


# Example:
# Entry = 100
# TP = 110
# Original TP distance = 10
# Profit lock SL = 102.5
PROFIT_LOCK_SL_RATIO = 0.25


# ============================================================
# VERSIONING
# ============================================================

BOT_VERSION = "SHERPA_V5.3"

STRATEGY_VERSION = "EMA50-CROSS-V1"


# ============================================================
# HELPERS
# ============================================================

def get_env_variable(
    var_name: str,
    default: str | None = None,
) -> str | None:

    value = os.getenv(
        var_name,
        default,
    )

    if not value and default is None:

        logging.warning(
            "Environment variable '%s' is not set.",
            var_name,
        )

    return value


def configure_logging():

    logging.basicConfig(
        level=LOGGING_LEVEL,
        format=LOGGING_FORMAT,
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logging.getLogger(
        "urllib3"
    ).setLevel(
        logging.WARNING
    )


# ============================================================
# INITIALIZATION
# ============================================================

configure_logging()


# ============================================================
# ENVIRONMENT VALIDATION
# ============================================================

missing_telegram_vars = []

if not TELEGRAM_BOT_TOKEN:
    missing_telegram_vars.append(
        "TELEGRAM_BOT_TOKEN"
    )

if not TELEGRAM_PERSONAL_CHAT_ID:
    missing_telegram_vars.append(
        "TELEGRAM_PERSONAL_CHAT_ID"
    )

if not TELEGRAM_CHANNEL_CHAT_ID:
    missing_telegram_vars.append(
        "TELEGRAM_CHANNEL_CHAT_ID"
    )


if missing_telegram_vars:

    logging.warning(
        "Missing Telegram environment variables: %s. "
        "Telegram notifications may not work.",
        ", ".join(missing_telegram_vars),
    )
