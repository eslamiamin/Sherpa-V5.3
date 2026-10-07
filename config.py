"""
Configuration module for the crypto trading bot.
Centralizes environment variables and application constants.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ============================================================
# LOGGING
# ============================================================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ============================================================
# TRADING / ANALYSIS CONFIGURATION
# ============================================================
# Target symbols to analyze and trade
SYMBOLS: list[str] = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "AVAXUSDT",
    "NEARUSDT",
]

# Timeframes configuration
TIMEFRAME_PRIMARY = os.getenv("TIMEFRAME_PRIMARY", "1h")
TIMEFRAME_SECONDARY = os.getenv("TIMEFRAME_SECONDARY", "15m")
TIMEFRAME_HIGHER = os.getenv("TIMEFRAME_HIGHER", "4h")

# Strategy Parameters
MIN_CONFLUENCE_SCORE = int(os.getenv("MIN_CONFLUENCE_SCORE", "70"))
RISK_REWARD_RATIO_MIN = float(os.getenv("RISK_REWARD_RATIO_MIN", "1.5"))

# ============================================================
# EXCHANGE CONFIGURATION
# ============================================================
API_KEY = os.getenv("API_KEY", "")
API_SECRET = os.getenv("API_SECRET", "")
USE_TESTNET = os.getenv("USE_TESTNET", "False").lower() in ("true", "1", "t")

# ============================================================
# TELEGRAM NOTIFICATIONS
# ============================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "")
TELEGRAM_PERSONAL_CHAT_ID = os.getenv("TELEGRAM_PERSONAL_CHAT_ID", "")

# ============================================================
# SCHEDULING & INTERVALS
# ============================================================
SCAN_INTERVAL_MINUTES = int(os.getenv("SCAN_INTERVAL_MINUTES", "5"))
