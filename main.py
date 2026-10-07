# Sherpa-V5.3-main/main.py
"""
Sherpa V5.3 - Main Entry Point
Orchestrates trading logic, risk management, and telegram reporting.
"""

import time
import schedule
import traceback
from datetime import datetime
from typing import Dict, Any

from config import (
    SYMBOLS,
    SLEEP_TIME_SECONDS,
    logger,
    MAX_CONCURRENT_TRADES,
)
from trading.engine import (
    get_historical_data,
    analyze_market_regime,
    generate_signals,
    evaluate_signal,
    open_paper_trade,
    close_paper_trade,
    update_trailing_stop,
)
from trading.risk import (
    calculate_position_size,
    calculate_stop_loss,
    can_open_new_trade,
    get_open_trades_count,
    PAPER_TRADES,
    ACTIVE_POSITIONS_VALUE,
    save_paper_trades,
)
from telegram.channel import (
    publish_trading_signal,
    check_and_publish_session_alerts,
)
from telegram.personal import (
    send_admin_alert,
    send_admin_startup_message,
)

# Global variables
LAST_HEARTBEAT: float = 0.0


def initialize_bot() -> None:
    """Initialize bot state and send startup notifications."""
    logger.info("Initializing Sherpa V5.3...")
    startup_msg = f"🚀 Sherpa V5.3 Started.\nTracking {len(SYMBOLS)} symbols."
    send_admin_startup_message(startup_msg)


def handle_scheduled_tasks() -> None:
    """Run pending scheduled tasks."""
    schedule.run_pending()
    check_and_publish_session_alerts()


def process_symbol(symbol: str) -> None:
    """Process market data and trading logic for a single symbol."""
    try:
        # 1. Fetch Data
        df = get_historical_data(symbol)
        if df is None or df.empty:
            logger.warning(f"No data for {symbol}, skipping.")
            return

        current_price = float(df['close'].iloc[-1])

        # 2. Update Active Trades
        if symbol in PAPER_TRADES:
            trade = PAPER_TRADES[symbol]
            updated_trade = update_trailing_stop(symbol, df)
            
            # Check exit conditions
            close_reason = None
            if updated_trade['direction'] == 'LONG':
                if current_price <= updated_trade['stop_loss']:
                    close_reason = "Stop Loss"
                elif 'take_profit' in updated_trade and current_price >= updated_trade['take_profit']:
                    close_reason = "Take Profit"
            else:  # SHORT
                if current_price >= updated_trade['stop_loss']:
                    close_reason = "Stop Loss"
                elif 'take_profit' in updated_trade and current_price <= updated_trade['take_profit']:
                    close_reason = "Take Profit"

            if close_reason:
                close_paper_trade(symbol, current_price, close_reason)
                publish_trading_signal(symbol, "CLOSE", current_price, trade, close_reason)
                return  # Move to next symbol after closing

        # 3. Analyze Market Regime
        regime = analyze_market_regime(df)
        
        # 4. Generate Signals
        raw_signals = generate_signals(df, regime)
        
        # 5. Evaluate Signal (Filtered)
        final_signal, score = evaluate_signal(raw_signals, regime)

        # 6. Execute Trade Logic
        if final_signal in ["STRONG_BUY", "STRONG_SELL"]:
            if symbol not in PAPER_TRADES:
                if can_open_new_trade(symbol):
                    direction = 'LONG' if final_signal == "STRONG_BUY" else 'SHORT'
                    
                    sl_price = calculate_stop_loss(df, direction)
                    if sl_price is None:
                        logger.warning(f"[{symbol}] Failed to calculate SL. Skipping.")
                        return

                    pos_size = calculate_position_size(
                        current_price=current_price,
                        stop_loss=sl_price,
                        regime=regime
                    )
                    
                    if pos_size > 0:
                        trade_record = open_paper_trade(
                            symbol=symbol,
                            direction=direction,
                            entry_price=current_price,
                            size=pos_size,
                            stop_loss=sl_price,
                            regime=regime
                        )
                        publish_trading_signal(symbol, "OPEN", current_price, trade_record)
                        logger.info(f"Opened {direction} on {symbol} at {current_price}")
                    else:
                        logger.info(f"[{symbol}] Position size 0, skipping trade.")
                else:
                    logger.debug(f"[{symbol}] Cannot open new trade (Risk/Limit reached).")
    
    except Exception as e:
        logger.error(f"Error processing {symbol}: {e}")
        send_admin_alert(f"Error processing {symbol}:\n{traceback.format_exc()}")


def main_loop() -> None:
    """Main execution loop for the bot."""
    global LAST_HEARTBEAT
    initialize_bot()

    while True:
        try:
            current_time = time.time()
            handle_scheduled_tasks()

            open_trades = get_open_trades_count()
            logger.info(f"--- Cycle Start | Open Trades: {open_trades}/{MAX_CONCURRENT_TRADES} ---")

            for symbol in SYMBOLS:
                process_symbol(symbol)

            # Save state
            save_paper_trades()

            # Heartbeat logic
            if current_time - LAST_HEARTBEAT >= 3600:
                LAST_HEARTBEAT = current_time
                logger.info("Heartbeat: Bot is running normally.")

            # Sleep until next cycle
            logger.info(f"Cycle Complete. Sleeping {SLEEP_TIME_SECONDS}s.")
            time.sleep(SLEEP_TIME_SECONDS)

        except KeyboardInterrupt:
            logger.info("Bot stopped by user.")
            break
        except Exception as e:
            logger.error(f"Critical error in main loop: {e}")
            send_admin_alert(f"Critical Bot Error:\n{traceback.format_exc()}")
            time.sleep(60)  # Sleep briefly before retrying


if __name__ == "__main__":
    main_loop()
