"""
Configuration module for SHERPA V5.3 trading bot.

This module loads environment variables, defines constants,
and sets up initial bot configurations.
"""

import os
import logging
from dotenv import load_dotenv
from zoneinfo import ZoneInfo

# Load environment variables from a .env file
load_dotenv()

# ============================================================
# GENERAL SETTINGS
# ============================================================
LOGGING_LEVEL = logging.INFO
LOGGING_FORMAT = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"

# Timezones for logging and reporting
TIMEZONE_UTC = ZoneInfo("UTC")
TIMEZONE_TEHRAN = ZoneInfo("Asia/Tehran")

# Bot behavior
SYMBOL_DELAY_SECONDS = 2.0  # Delay between processing each symbol in the main loop
LOOP_DELAY_SECONDS = 60.0   # Delay between full bot cycles
MAX_CONCURRENT_POSITIONS = 5 # Maximum number of open trades allowed simultaneously

# ============================================================
# MARKET DATA SETTINGS
# ============================================================
# Number of candles to fetch for each timeframe
HOURLY_CANDLE_LIMIT = 300
DAILY_CANDLE_LIMIT = 250

# Exchange API endpoints (MEXC assumed for now)
# In future, this could be abstracted for different providers
MEXC_API_URL = "https://api.mexc.com/api/v3/klines"

# Symbols to trade
SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "AVAXUSDT",
    "NEARUSDT",
    # Additional assets to consider for future expansion:
    # "PAXGUSDT", # Gold - if data provider supports
    # "OILUSDT",  # Oil - if data provider supports
]

# ============================================================
# TELEGRAM SETTINGS
# ============================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_PERSONAL_CHAT_ID = os.getenv("TELEGRAM_PERSONAL_CHAT_ID")
TELEGRAM_CHANNEL_CHAT_ID = os.getenv("TELEGRAM_CHANNEL_CHAT_ID")

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"

# ============================================================
# TRADING STRATEGY SETTINGS
# ============================================================
# Risk Management
INITIAL_CAPITAL = 1000.0
MAX_POSITION_NOTIONAL_PCT = 0.25 # Max capital allocated to a single position

# Risk percentage based on market regime
STRONG_REGIME_RISK_PCT = 0.025 # 2.5%
NORMAL_REGIME_RISK_PCT = 0.01  # 1.0%

# Take Profit and Stop Loss multipliers (based on ATR)
TP_ATR_MULTIPLIER = 2.0
SL_ATR_MULTIPLIER = 1.2

# Profit Management Triggers
BREAK_EVEN_TRIGGER_RATIO = 0.50     # Trigger break-even when 50% of TP distance is reached
PROFIT_LOCK_TRIGGER_RATIO = 0.80    # Trigger profit lock when 80% of TP distance is reached
PROFIT_LOCK_SL_RATIO = 0.25         # Lock SL at 25% of the original TP distance from entry


# ============================================================
# VERSIONING
# ============================================================
BOT_VERSION = "SHERPA_V5.3"
# Strategy version should be defined and managed within the strategy module
# For example: STRATEGY_VERSION = "EMA50-CROSS-V1"


# ============================================================
# HELPER FUNCTIONS
# ============================================================
def get_env_variable(var_name: str, default: str | None = None) -> str:
    """Safely get an environment variable."""
    value = os.getenv(var_name, default)
    if not value and default is None:
        logging.warning(f"Environment variable '{var_name}' not set.")
    return value

def configure_logging():
    """Configures the basic logging setup."""
    logging.basicConfig(
        level=LOGGING_LEVEL,
        format=LOGGING_FORMAT,
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING) # Reduce noisy logs from requests


# ============================================================
# INITIALIZATION
# ============================================================
configure_logging()

# Check for essential Telegram credentials early
if not TELEGRAM_BOT_TOKEN or not TELEGRAM_PERSONAL_CHAT_ID or not TELEGRAM_CHANNEL_CHAT_ID:
    logging.warning(
        "One or more essential Telegram environment variables are missing. "
        "Telegram notifications will not function. "
        "Ensure TELEGRAM_BOT_TOKEN, TELEGRAM_PERSONAL_CHAT_ID, and TELEGRAM_CHANNEL_CHAT_ID are set."
    )
