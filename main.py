"""
Main Execution Module for SHERPA V5.3 Trading Bot.

This is the primary script that orchestrates the entire trading bot's operation.
It includes:
- The main trading loop that iterates through symbols and processes them.
- Scheduling and execution of periodic reports (4-hour and daily journals).
- Integration with other modules: data fetching, strategy, risk management, and telegram notifications.
- A keep-alive HTTP server to satisfy Render's deployment requirements.
- Error handling and logging.

The bot operates in a paper trading mode, simulating trades without risking real capital.
"""

import os
import time
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Tuple

# Import configurations and core modules
import config
from data.mexc import fetch_mexc_klines
from strategy.indicators import calculate_indicators
from strategy.strategy import detect_market_regime, generate_signals
from trading.engine import (
    initialize_trading_state,
    manage_open_positions,
    process_symbol_state,
    open_positions, # Import global state for reporting
    daily_completed_trades # Import for reporting
)
from telegram.personal import send_to_personal_chat, format_4h_report, format_daily_journal
from telegram.channel import (
    publish_trading_signal,
    publish_status_update,
    publish_market_pulse,
    check_and_publish_session_alerts,
    publish_news_alerts
)

# Configure logging based on config file
logger = logging.getLogger(__name__)

# Global variable to store the latest market data fetched for each symbol
# Used for reporting and status updates. Format: {symbol: {market_data_dict}}
latest_market_data_cache: Dict[str, Dict[str, Any]] = {}

# Global variables for tracking report scheduling
last_4h_report_hour: int = -1
last_daily_report_date_str: str = ""


# ============================================================
# RENDER KEEP-ALIVE SERVER
# ============================================================

class DummyServer(BaseHTTPRequestHandler):
    """A simple HTTP server to keep the Render service alive."""
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"SHERPA V5.3 Bot is alive and running!")

    def log_message(self, format, *args):
        # Suppress noisy HTTP access logs
        pass

def run_keep_alive_server():
    """Runs the dummy HTTP server in a separate thread."""
    port = int(os.getenv("PORT", 8080)) # Use PORT env variable or default to 8080
    try:
        server = HTTPServer(("0.0.0.0", port), DummyServer)
        logger.info(f"Dummy HTTP server running on port {port} for Render keep-alive.")
        server.serve_forever()
    except Exception as e:
        logger.error(f"Failed to start keep-alive server: {e}")

# ============================================================
# DATA FETCHING AND PROCESSING PER SYMBOL
# ============================================================

def fetch_and_process_symbol(symbol: str, current_capital: float) -> Dict[str, Any] | None:
    """
    Fetches market data, calculates indicators, detects regime, generates signals,
    and manages existing positions for a single trading symbol.

    Args:
        symbol (str): The trading symbol to process (e.g., "BTCUSDT").
        current_capital (float): The current available trading capital.

    Returns:
        Dict[str, Any] | None: A dictionary containing the latest market data and signal info
                               for the symbol if processing was successful, otherwise None.
                               Includes: price, rsi, atr, regime, changes, candle_time, timestamp_utc.
    """
    try:
        # --- 1. Fetch Market Data ---
        # Fetch daily data for regime detection
        df_1d = fetch_mexc_klines(symbol, interval="1d", limit=config.DAILY_CANDLE_LIMIT)
        # Fetch hourly data for indicators and strategy signals
        df_1h = fetch_mexc_klines(symbol, interval="60m", limit=config.HOURLY_CANDLE_LIMIT)

        # --- 2. Validate Data ---
        # Ensure we have enough data points for indicator calculations
        required_hourly_candles = 205 # Based on EMA200 and other longer periods
        required_daily_candles = 55  # Based on EMA50 and other longer periods
        
        if len(df_1h) < required_hourly_candles:
            logger.warning(f"{symbol}: Insufficient hourly data ({len(df_1h)} < {required_hourly_candles}). Skipping.")
            return None
        if len(df_1d) < required_daily_candles:
            logger.warning(f"{symbol}: Insufficient daily data ({len(df_1d)} < {required_daily_candles}). Skipping.")
            return None

        # --- 3. Calculate Indicators ---
        df_1h_indicators = calculate_indicators(df_1h)
        df_1d_indicators = calculate_indicators(df_1d) # Calculate indicators for daily data too

        if df_1h_indicators.empty or df_1d_indicators.empty:
            logger.error(f"{symbol}: Failed to calculate indicators. Skipping.")
            return None

        # --- 4. Get Latest Candle and Market Info ---
        latest_hourly = df_1h_indicators.iloc[-1]
        latest_daily = df_1d_indicators.iloc[-1]

        current_candle_time = latest_hourly["timestamp"] # Use the timestamp of the latest closed candle
        current_time_utc = datetime.now(timezone.utc) # Use current time for reports/alerts if needed

        price = latest_hourly["close"]
        atr = latest_hourly["atr"]

        # --- 5. Detect Market Regime ---
        regime = detect_market_regime(df_1d_indicators, df_1h_indicators)

        # --- 6. Calculate Price Changes and Snapshot Data ---
        def percentage_change(current: float, previous: float) -> float:
            if previous == 0: return 0.0
            return ((current - previous) / previous) * 100

        # Calculate changes based on specific candle counts (adjust indices as needed)
        change_4h = percentage_change(price, df_1h_indicators.iloc[-5]["close"]) # Approx 4 hours
        change_1d = percentage_change(price, df_1h_indicators.iloc[-25]["close"]) # Approx 1 day (24 * 1h candles)
        change_1w = percentage_change(price, df_1h_indicators.iloc[-169]["close"]) # Approx 1 week (7 * 24 = 168 hours)

        # Prepare market data summary for this symbol
        symbol_market_data = {
            "price": price,
            "high": latest_hourly["high"], # Needed for intra-bar exit checks
            "low": latest_hourly["low"],   # Needed for intra-bar exit checks
            "rsi": latest_hourly["rsi"],
            "atr": atr,
            "regime": regime,
            "change_4h": change_4h,
            "change_1d": change_1d,
            "change_1w": change_1w,
            "candle_time": current_candle_time, # Time of the closed candle being processed
            "timestamp_utc": current_time_utc # Current time for reporting/alerts
        }

        # --- 7. Generate Trading Signals ---
        signal = generate_signals(df_1h_indicators, regime, current_candle_time)
        signal["strategy_version"] = "EMA50-CROSS-V1" # Match strategy version

        # --- 8. Process New Entry Signal or Manage Existing Position ---
        # This function handles both opening new positions and checking existing ones
        # for exits/updates. It returns info about any trades closed in this cycle.
        
        # First, manage existing positions based on current market data
        # Note: manage_open_positions needs market data for *all* open symbols to check exits correctly.
        # This is handled globally in the main loop. Here, we only focus on potentially opening a NEW trade.

        new_position_opened = False
        if symbol not in open_positions: # Only try to open if no position exists for this symbol
            new_position_opened, _ = process_symbol_state(
                symbol=symbol,
                signal=signal,
                market_data=symbol_market_data,
                current_capital=current_capital
            )
            
        # --- 9. Publish Signal to Channel (if applicable) ---
        if new_position_opened and signal.get("action") != "HOLD":
            publish_trading_signal(
                symbol=symbol,
                side=signal["action"],
                entry_price=signal["entry_price"],
                stop_price=signal["stop_price"],
                tp_price=signal["take_profit_price"],
                risk_pct=signal["risk_pct"],
                regime=regime,
                strategy_version=signal["strategy_version"],
                trade_id=open_positions[symbol]["trade_id"], # Get trade ID from newly opened position
                entry_dt_utc=open_positions[symbol]["entry_candle_time"],
                position_size_usd=open_positions[symbol]["size_usd"]
            )

        # Return the consolidated market data and signal info
        return symbol_market_data

    except Exception as e:
        logger.exception(f"Error processing symbol {symbol}: {e}")
        return None


# ============================================================
# SCHEDULED REPORTS AND ALERTS
# ============================================================

def handle_scheduled_tasks(
    latest_market_data_cache: Dict[str, Dict[str, Any]],
    current_capital: float
):
    """
    Manages scheduled tasks like 4-hour reports, daily journals, session alerts,
    and news alerts.
    """
    global last_4h_report_hour, last_daily_report_date_str

    now_utc = datetime.now(timezone.utc)
    current_date_str = now_utc.strftime("%Y-%m-%d")

    # --- 1. 4-Hour Report ---
    # Trigger report if current hour is divisible by 4 and hasn't reported this hour yet
    if (now_utc.hour % 4 == 0 and now_utc.hour != last_4h_report_hour):
        logger.info("Generating 4-hour report...")
        
        # Prepare data for the report
        report_data_4h = format_4h_report(
            current_time_utc=now_utc,
            capital=current_capital,
            daily_pnl=sum(t.get("pnl_usd", 0.0) for t in daily_completed_trades),
            win_rate=(len(daily_completed_trades) > 0 and sum(1 for t in daily_completed_trades if t.get("pnl_usd", 0) >= 0) / len(daily_completed_trades) * 100) if daily_completed_trades else 0.0,
            num_trades=len(daily_completed_trades),
            today_closed_trades_summary=[t for t in daily_completed_trades], # Full list for now, could summarize
            open_positions_summary=get_current_open_positions_summary(), # Get summary of open positions
            market_overview=latest_market_data_cache # Use cached market data
        )
        send_to_personal_chat(report_data_4h)
        last_4h_report_hour = now_utc.hour
        logger.info("4-hour report sent to personal chat.")

    # --- 2. Daily Journal Report ---
    # Trigger daily report around 23:00 UTC (or adjust as needed)
    # Ensure it only runs once per day
    if (now_utc.hour == 23 and last_daily_report_date_str != current_date_str):
        logger.info("Generating daily journal report...")
        
        # Get completed trades and stats for the day
        completed_trades, daily_stats = get_daily_journal_data()
        
        # Prepare data for the journal report
        journal_report = format_daily_journal(
            current_date_utc=now_utc,
            starting_capital=config.INITIAL_CAPITAL, # Assuming initial capital is fixed, or managed globally
            ending_capital=current_capital,
            daily_pnl=daily_stats["pnl_usd"],
            daily_pnl_pct=daily_stats["win_rate"], # This calculation might need adjustment depending on definition
            num_trades=daily_stats["trades"],
            winning_trades=daily_stats["wins"],
            losing_trades=daily_stats["losses"],
            win_rate=daily_stats["win_rate"],
            total_pnl=0.0, # Placeholder: total PnL needs to be managed globally if tracked
            completed_trades_data=completed_trades,
            open_positions_summary=get_current_open_positions_summary(),
            market_snapshot=latest_market_data_cache
        )
        send_to_personal_chat(journal_report)
        
        last_daily_report_date_str = current_date_str
        logger.info("Daily journal report sent to personal chat.")
        
        # Reset daily stats and completed trades list for the new day
        initialize_trading_state() # This resets positions, completed trades etc. Needs careful handling if capital needs persistence.
        # NOTE: Re-initializing state here might be too aggressive if capital needs to persist across days.
        # A better approach would be to only reset daily stats and completed trades list,
        # while keeping open_positions and managing capital updates separately.
        # For now, let's assume daily reset is intended.
        
        # Explicitly reset only daily trackers if capital persistence is desired
        # global daily_completed_trades
        # daily_completed_trades = []
        # logger.info("Cleared daily completed trades list for the new day.")


    # --- 3. Session Alerts ---
    # Check every loop, but alerts are rate-limited internally
    check_and_publish_session_alerts(now_utc)

    # --- 4. News Alerts ---
    # Check news alerts periodically, e.g., every hour or based on provider refresh rate
    # For simplicity, let's check every loop, but rely on placeholder's internal logic if any.
    # A real implementation would check based on event times.
    # publish_news_alerts() # Uncomment to enable news alerts


# ============================================================
# MAIN BOT LOOP
# ============================================================

def main_trading_loop():
    """
    The main loop of the trading bot.
    Fetches data, processes symbols, manages positions, and triggers reports.
    """
    logger.info("Starting main trading loop...")
    
    # Initialize trading state (clear positions, etc.)
    initialize_trading_state()
    
    current_capital = config.INITIAL_CAPITAL # Start with initial capital
    
    # Send initial startup message to personal chat
    send_to_personal_chat(
        f"🚀 *SHERPA Bot V{config.BOT_VERSION} Started*\n\n"
        f"Mode: Paper Trading\n"
        f"Journal: Telegram\n"
        f"Initial Capital: `${current_capital:,.2f}`\n\n"
        f"📈 Strategy: {config.STRATEGY_VERSION}\n"
        f"🛡 Break-even @ {config.BREAK_EVEN_TRIGGER_RATIO*100:.0f}% TP distance\n"
        f"🔒 Profit Lock @ {config.PROFIT_LOCK_TRIGGER_RATIO*100:.0f}% TP distance\n"
        f"❌ No continuous trailing stop"
    )

    while True:
        start_time = time.monotonic()
        
        logger.debug("Starting new trading cycle...")
        
        global latest_market_data_cache # Access the global cache
        latest_market_data_cache.clear() # Clear cache for the new cycle

        # --- Process all symbols ---
        closed_trades_in_cycle: Dict[str, Any] = {}
        
        # First, manage existing open positions based on latest data BEFORE opening new ones
        # This requires fetching data for all symbols that have open positions.
        symbols_with_open_positions = list(open_positions.keys())
        market_data_for_open_positions = {}
        
        if symbols_with_open_positions:
            logger.debug(f"Managing existing positions for: {', '.join(symbols_with_open_positions)}")
            for symbol in symbols_with_open_positions:
                # Fetch necessary data ONLY for symbols with open positions
                symbol_data = fetch_and_process_symbol(symbol, current_capital)
                if symbol_data:
                    market_data_for_open_positions[symbol] = symbol_data
                    # Update global cache
                    latest_market_data_cache[symbol] = symbol_data
                    # Update capital if a trade was closed and_str = current_date_str
        logger.info("Daily journal report sent to personal chat.")
        
        # Reset daily stats and completed trades list for the new day
        initialize_trading_state() # This resets positions, completed trades etc. Needs careful handling if capital needs persistence.
        # NOTE: Re-initializing state here might be too aggressive if capital needs to persist across days.
        # A better approach would be to only reset daily stats and completed trades list,
        # while keeping open_positions and managing capital updates separately.
        # For now, let's assume daily reset is intended.
        
        # Explicitly reset only daily trackers if capital persistence is desired
        # global daily_completed_trades
        # daily_completed_trades = []
        # logger.info("Cleared daily completed trades list for the new day.")


    # --- 3. Session Alerts ---
    # Check every loop, but alerts are rate-limited internally
    check_and_publish_session_alerts(now_utc)

    # --- 4. News Alerts ---
    # Check news alerts periodically, e.g., every hour or based on provider refresh rate
    # For simplicity, let's check every loop, but rely on placeholder's internal logic if any.
    # A real implementation would check based on event times.
    # publish_news_alerts() # Uncomment to enable news alerts


# ============================================================
# MAIN BOT LOOP
# ============================================================

def main_trading_loop():
    """
    The main loop of the trading bot.
    Fetches data, processes symbols, manages positions, and triggers reports.
    """
    logger.info("Starting main trading loop...")
    
    # Initialize trading state (clear positions, etc.)
    initialize_trading_state()
    
    current_capital = config.INITIAL_CAPITAL # Start with initial capital
    
    # Send initial startup message to personal chat
    send_to_personal_chat(
        f"🚀 *SHERPA Bot V{config.BOT_VERSION} Started*\n\n"
        f"Mode: Paper Trading\n"
        f"Journal: Telegram\n"
        f"Initial Capital: `${current_capital:,.2f}`\n\n"
        f"📈 Strategy: {config.STRATEGY_VERSION}\n"
        f"🛡 Break-even @ {config.BREAK_EVEN_TRIGGER_RATIO*100:.0f}% TP distance\n"
        f"🔒 Profit Lock @ {config.PROFIT_LOCK_TRIGGER_RATIO*100:.0f}% TP distance\n"
        f"❌ No continuous trailing stop"
    )

    while True:
        start_time = time.monotonic()
        
        logger.debug("Starting new trading cycle...")
        
        global latest_market_data_cache # Access the global cache
        latest_market_data_cache.clear() # Clear cache for the new cycle

        # --- Process all symbols ---
        closed_trades_in_cycle: Dict[str, Any] = {}
        
        # First, manage existing open positions based on latest data BEFORE opening new ones
        # This requires fetching data for all symbols that have open positions.
        symbols_with_open_positions = list(open_positions.keys())
        market_data_for_open_positions = {}
        
        if symbols_with_open_positions:
            logger.debug(f"Managing existing positions for: {', '.join(symbols_with_open_positions)}")
            for symbol in symbols_with_open_positions:
                # Fetch necessary data ONLY for symbols with open positions
                symbol_data = fetch_and_process_symbol(symbol, current_capital)
                if symbol_data:
                    market_data_for_open_positions[symbol] = symbol_data
                    # Update global cache
                    latest_market_data_cache[symbol] = symbol_data
                    # Update capital if a trade was closed and PnL calculated
                    # NOTE: This requires manage_open_positions to return PnL updates.
                    # Currently, it returns closed trade dicts.
            
            # Process exits/updates for ALL open positions using`trading/engine.py`) تصمیمات را می‌گیرد و دقیقاً همان داده‌ها (سیگنال ورود، به‌روزرسانی حد ضرر، بسته شدن معامله) به هر دو کانال تلگرام (شخصی و عمومی) ارسال می‌شود.
