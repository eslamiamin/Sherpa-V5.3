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

# Main loop:
# One market cycle every 5 minutes.
LOOP_DELAY_SECONDS = 300.0

# Maximum number of simultaneous paper positions.
MAX_CONCURRENT_POSITIONS = 5


# ============================================================
# MARKET DATA
# ============================================================

HOURLY_CANDLE_LIMIT = 300
DAILY_CANDLE_LIMIT = 250

MEXC_API_URL = (
    "https://api.mexc.com/api/v3/klines"
)

MEXC_REQUEST_TIMEOUT = 10

# Daily regime data is refreshed every 4 hours.
DAILY_DATA_REFRESH_HOURS = 4


# ============================================================
# SYMBOLS
# ============================================================

SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "AVAXUSDT",
    "NEARUSDT",
    "PAXGUSDT",
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

PROFIT_LOCK_SL_RATIO = 0.25


# ============================================================
# VERSIONING
# ============================================================

BOT_VERSION = "SHERPA_V5.3"

STRATEGY_VERSION = "EMA50-CROSS-V1"


# ============================================================
# NEWS
# ============================================================

# News provider is currently only a placeholder.
# Keep disabled until a real provider is integrated.
NEWS_ENABLED = False


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


# ============================================================
# BASIC VALIDATION
# ============================================================

if INITIAL_CAPITAL <= 0:
    raise ValueError(
        "INITIAL_CAPITAL must be greater than zero."
    )

if not 0 < MAX_POSITION_NOTIONAL_PCT <= 1:
    raise ValueError(
        "MAX_POSITION_NOTIONAL_PCT must be between 0 and 1."
    )

if not 0 < STRONG_REGIME_RISK_PCT <= 1:
    raise ValueError(
        "STRONG_REGIME_RISK_PCT must be between 0 and 1."
    )

if not 0 < NORMAL_REGIME_RISK_PCT <= 1:
    raise ValueError(
        "NORMAL_REGIME_RISK_PCT must be between 0 and 1."
    )

if TP_ATR_MULTIPLIER <= 0:
    raise ValueError(
        "TP_ATR_MULTIPLIER must be greater than zero."
    )

if SL_ATR_MULTIPLIER <= 0:
    raise ValueError(
        "SL_ATR_MULTIPLIER must be greater than zero."
    )

if MAX_CONCURRENT_POSITIONS <= 0:
    raise ValueError(
        "MAX_CONCURRENT_POSITIONS must be greater than zero."
    )
