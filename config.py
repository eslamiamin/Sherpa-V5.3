import os
from datetime import timezone

# ============================================================
# BOT
# ============================================================

BOT_VERSION = "SHERPA_V5.3"
STRATEGY_VERSION = "EMA50-CROSS-V1"

# ============================================================
# MARKET
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

MAIN_TIMEFRAME = "1h"
REGIME_TIMEFRAME = "1d"

# ============================================================
# CAPITAL & RISK
# ============================================================

INITIAL_CAPITAL = 1000.0

# Maximum notional value of one position
MAX_POSITION_NOTIONAL_PCT = 0.25

# Maximum number of simultaneous open positions
MAX_CONCURRENT_POSITIONS = 5

# Risk per trade
STRONG_REGIME_RISK_PCT = 0.025   # 2.5%
NORMAL_REGIME_RISK_PCT = 0.01    # 1%

# ============================================================
# ATR / TRADE MANAGEMENT
# ============================================================

TP_ATR_MULTIPLIER = 2.0
SL_ATR_MULTIPLIER = 1.2

# Move SL to entry after reaching 50% of TP distance
BREAK_EVEN_TRIGGER_RATIO = 0.50

# Lock 25% of original TP distance after reaching 80% of TP
PROFIT_LOCK_TRIGGER_RATIO = 0.80
PROFIT_LOCK_SL_RATIO = 0.25

# ============================================================
# INDICATORS
# ============================================================

EMA_FAST_PERIOD = 5
EMA_SIGNAL_PERIOD = 15
EMA_50_PERIOD = 50
EMA_200_PERIOD = 200

RSI_PERIOD = 14
ATR_PERIOD = 14
ADX_PERIOD = 14
MFI_PERIOD = 14
BB_PERIOD = 20
BB_STD = 2.0
VOLUME_SMA_PERIOD = 20

# ============================================================
# REGIME THRESHOLDS
# ============================================================

ADX_DEAD_CHOP = 18.0
ADX_STRONG_TREND = 30.0

BB_WIDTH_DEAD_CHOP = 0.02

# ============================================================
# SIGNAL THRESHOLDS
# ============================================================

# Trend entries
BULL_RSI_MIN = 55.0
BEAR_RSI_MAX = 45.0

# Range entries
RANGE_RSI_LONG_MAX = 35.0
RANGE_RSI_SHORT_MIN = 65.0

RANGE_MFI_LONG_MAX = 30.0
RANGE_MFI_SHORT_MIN = 70.0

# ============================================================
# TIMING / LOOP
# ============================================================

# Main loop runs every 5 minutes.
LOOP_DELAY_SECONDS = 300.0

# Small delay between symbol requests.
SYMBOL_DELAY_SECONDS = 2.0

# Daily market data refresh interval.
DAILY_DATA_REFRESH_HOURS = 4

# MEXC HTTP timeout
MEXC_REQUEST_TIMEOUT = 10

# Telegram HTTP timeout
TELEGRAM_REQUEST_TIMEOUT = 10

# ============================================================
# TELEGRAM
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Optional separate channel.
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "")

# ============================================================
# TIMEZONES
# ============================================================

TIMEZONE_UTC = timezone.utc

# Tehran timezone.
# Using a fixed offset avoids requiring an external timezone package.
from datetime import timedelta

TIMEZONE_TEHRAN = timezone(timedelta(hours=3, minutes=30))

# ============================================================
# REPORTING
# ============================================================

# Daily journal hour in UTC.
DAILY_REPORT_UTC_HOUR = 23

# 4-hour report schedule.
REPORT_INTERVAL_HOURS = 4

# ============================================================
# NEWS
# ============================================================

NEWS_ENABLED = False

# ============================================================
# VALIDATION
# ============================================================

if INITIAL_CAPITAL <= 0:
    raise ValueError("INITIAL_CAPITAL must be greater than zero")

if not 0 < MAX_POSITION_NOTIONAL_PCT <= 1:
    raise ValueError("MAX_POSITION_NOTIONAL_PCT must be between 0 and 1")

if not 0 < STRONG_REGIME_RISK_PCT <= 1:
    raise ValueError("STRONG_REGIME_RISK_PCT must be between 0 and 1")

if not 0 < NORMAL_REGIME_RISK_PCT <= 1:
    raise ValueError("NORMAL_REGIME_RISK_PCT must be between 0 and 1")

if TP_ATR_MULTIPLIER <= 0:
    raise ValueError("TP_ATR_MULTIPLIER must be greater than zero")

if SL_ATR_MULTIPLIER <= 0:
    raise ValueError("SL_ATR_MULTIPLIER must be greater than zero")
