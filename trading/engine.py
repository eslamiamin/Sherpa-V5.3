"""
Trading Engine Module.

This module orchestrates the management of open trading positions.
It handles:
- Tracking current positions.
- Monitoring trade lifecycle events (Entry, Break-even, Profit Lock, Exit).
- Detecting Take Profit (TP) and Stop Loss (SL) hits based on intra-bar price action (High/Low).
- Implementing risk management rules like Break-even and Profit Lock.
- Calculating PnL for closed trades.
- Recording completed trades for journaling and reporting.
- Managing state to prevent repeated actions within the same candle.

This engine acts as the 'Single Source of Truth' for trade decisions.
"""

import logging
import pandas as pd
from datetime import datetime, timezone
from typing import Dict, Any, Tuple

import config
from trading.risk import calculate_position_size
from strategy.strategy import REGIME_GOOD_RANGE # Import specific regimes if needed for logic
from telegram.personal import (
    send_to_personal_chat,
    format_entry_message,
    format_break_even_message,
    format_profit_lock_message,
    format_trade_closed_message
)

logger = logging.getLogger(__name__)

# Global state for open positions, trade IDs, and lifecycle flags
# Format: {symbol: {position_data}}
# position_data structure:
# {
#   "type": "LONG" | "SHORT",
#   "entry": float,
#   "tp": float,
#   "sl": float,
#   "initial_sl": float,
#   "size_usd": float,
#   "risk_pct": float,
#   "regime": str,
#   "strategy_version": str,
#   "entry_candle_time": pd.Timestamp,
#   "trade_id": str,
#   "break_even_triggered": bool,
#   "profit_lock_triggered": bool
# }
open_positions: Dict[str, Dict[str, Any]] = {}

# Track the last processed candle time for each symbol to avoid re-evaluating
last_processed_candle_time: Dict[str, pd.Timestamp] = {}

# Store completed trades for the current day's journal
daily_completed_trades: List[Dict[str, Any]] = []

# --- Helper Functions ---

def get_position_pnl(
    position: Dict[str, Any],
    current_price: float,
    current_time_utc: datetime
) -> Tuple[float, float, float]:
    """
    Calculate PnL (USD and Percentage) for an open position at the current price.

    Args:
        position (Dict): The dictionary representing the open position.
        current_price (float): The current market price.
        current_time_utc (datetime): The current time in UTC.

    Returns:
        Tuple[float, float, float]: A tuple containing:
            - current_pnl_usd: Profit or loss in USD.
            - current_pnl_pct: Profit or loss as a percentage.
            - current_stop_loss: The current stop loss price (after potential adjustments).
    """
    entry = position["entry"]
    entry_dt = position["entry_candle_time"]
    pos_type = position["type"]
    
    # Recalculate current SL based on BE/PL triggers if they occurred
    current_sl = position["sl"] # Start with the potentially adjusted SL
    
    # PnL calculation
    if pos_type == "LONG":
        pnl_usd = (current_price - entry) * position["size_usd"] / entry
        pnl_pct = (current_price - entry) / entry * 100
    else: # SHORT
        pnl_usd = (entry - current_price) * position["size_usd"] / entry
        pnl_pct = (entry - current_price) / entry * 100

    return pnl_usd, pnl_pct, current_sl


def record_trade_completion(
    symbol: str,
    position: Dict[str, Any],
    exit_price: float,
    exit_reason: str,
    exit_candle_time: pd.Timestamp
) -> Dict[str, Any]:
    """
    Records a completed trade, calculating final PnL and preparing data for the journal.

    Args:
        symbol (str): The trading symbol.
        position (Dict): The closed position data.
        exit_price (float): The price at which the trade was closed.
        exit_reason (str): The reason for closure (e.g., "TP", "SL").
        exit_candle_time (pd.Timestamp): The timestamp of the candle where exit occurred.

    Returns:
        Dict: A dictionary containing all relevant information about the completed trade,
              including the formatted trade line.
    """
    entry = position["entry"]
    entry_dt_utc = position["entry_candle_time"]
    pos_type = position["type"]
    
    # Calculate PnL based on exit price
    if pos_type == "LONG":
        pnl_usd = (exit_price - entry) * position["size_usd"] / entry
        pnl_pct = (exit_price - entry) / entry * 100
    else: # SHORT
        pnl_usd = (entry - exit_price) * position["size_usd"] / entry
        pnl_pct = (entry - exit_price) / entry * 100

    # Create the structured trade line string
    trade_line = format_trade_line(
        bot_version=config.BOT_VERSION,
        trade_id=position["trade_id"],
        symbol=symbol,
        entry_dt_utc=entry_dt_utc,
        exit_dt_utc=exit_candle_time,
        side=pos_type,
        strategy_version=position["strategy_version"],
        regime=position["regime"],
        risk_pct=position["risk_pct"],
        initial_sl=position["initial_sl"],
        entry_price=entry,
        tp=position["tp"],
        position_size_usd=position["size_usd"],
        exit_price=exit_price,
        final_sl=position["sl"], # Use the final SL value after potential adjustments
        exit_reason=exit_reason,
        pnl_usd=pnl_usd,
        pnl_pct=pnl_pct,
        break_even_triggered=position["break_even_triggered"],
        profit_lock_triggered=position["profit_lock_triggered"]
    )

    completed_trade_data = {
        "trade_id": position["trade_id"],
        "symbol": symbol,
        "type": pos_type,
        "entry": entry,
        "exit": exit_price,
        "tp": position["tp"],
        "initial_sl": position["initial_sl"],
        "final_sl": position["sl"],
        "size_usd": position["size_usd"],
        "pnl_usd": pnl_usd,
        "pnl_pct": pnl_pct,
        "exit_reason": exit_reason,
        "regime": position["regime"],
        "strategy_version": position["strategy_version"],
        "entry_candle_time": entry_dt_utc,
        "exit_candle_time": exit_candle_time,
        "break_even_triggered": position["break_even_triggered"],
        "profit_lock_triggered": position["profit_lock_triggered"],
        "trade_line": trade_line # Include the formatted line
    }
    
    daily_completed_trades.append(completed_trade_data)
    logger.info(f"Trade {position['trade_id']} ({symbol} {pos_type}) closed. Reason: {exit_reason}. PnL: ${pnl_usd:+.2f}")
    
    return completed_trade_data


# --- Core Engine Logic ---

def manage_open_positions(
    current_market_data: Dict[str, Dict[str, Any]] # Dict mapping symbol to its latest candle data
) -> Dict[str, Dict[str, Any]]:
    """
    Manages all currently open positions.

    Iterates through open positions, checks for TP/SL hits, manages Break-even and
    Profit Lock triggers, and updates position state.

    Args:
        current_market_data (Dict): Dictionary containing the latest market data for each symbol.

    Returns:
        Dict: A dictionary summarizing the state of open positions after management.
    """
    closed_trades_info = {} # To store info about trades closed in this cycle

    for symbol, position in list(open_positions.items()): # Use list() for safe iteration while modifying dict
        market_info = current_market_data.get(symbol)
        if not market_info:
            logger.warning(f"Market data not found for open position {symbol}. Skipping.")
            continue

        current_price = market_info["price"]
        current_candle_time = market_info["candle_time"] # Assumes candle_time is in the market data
        current_time_utc = market_info["timestamp_utc"] # Assumes timestamp_utc is in the market data
        
        entry = position["entry"]
        tp = position["tp"]
        pos_type = position["type"]
        
        # --- Recalculate current TP/SL if BE/PL were triggered ---
        # This ensures we use the latest adjusted SL for exit checks
        current_sl = position["sl"]
        
        # Calculate progress towards TP
        tp_distance = abs(tp - entry)
        
        # Favorable move calculation depends on position type
        if pos_type == "LONG":
            favorable_move = max(0, current_price - entry) # Price above entry
            # Check intra-candle highs for TP/SL hits
            high_price = market_info["high"]
            low_price = market_info["low"]
        else: # SHORT
            favorable_move = max(0, entry - current_price) # Price below entry
            # Check intra-candle lows for TP/SL hits
            high_price = market_info["high"]
            low_price = market_info["low"]
            
        progress_ratio = (favorable_move / tp_distance) if tp_distance > 0 else 0

        # --- 1. Break-Even Trigger ---
        if (not position["break_even_triggered"]
                and progress_ratio >= config.BREAK_EVEN_TRIGGER_RATIO):
            
            old_sl = current_sl
            position["sl"] = entry # Move SL to entry price
            position["break_even_triggered"] = True
            
            send_to_personal_chat(format_break_even_message(
                trade_id=position["trade_id"],
                symbol=symbol,
                entry_price=entry,
                old_sl=old_sl,
                new_sl=position["sl"],
                current_price=current_price,
                timestamp_utc=current_time_utc
            ))
            logger.debug(f"Break-even triggered for {symbol} ({position['trade_id']}). SL moved to {position['sl']:.6g}.")

        # --- 2. Profit Lock Trigger ---
        # This check should happen after Break-even, as it might adjust SL further
        if (not position["profit_lock_triggered"]
                and progress_ratio >= config.PROFIT_LOCK_TRIGGER_RATIO):
            
            # Calculate new SL based on Profit Lock ratio
            locked_sl_price = entry + (tp_distance * config.PROFIT_LOCK_SL_RATIO) if pos_type == "LONG" else entry - (tp_distance * config.PROFIT_LOCK_SL_RATIO)
            
            old_sl_for_pl = position["sl"] # SL before Profit Lock adjustment
            position["sl"] = locked_sl_price # Update SL to the locked level
            position["profit_lock_triggered"] = True
            
            send_to_personal_chat(format_profit_lock_message(
                trade_id=position["trade_id"],
                symbol=symbol,
                old_sl=old_sl_for_pl, # Report the SL before this adjustment
                new_sl=position["sl"],
                current_price=current_price,
                timestamp_utc=current_time_utc
            ))
            logger.debug(f"Profit Lock triggered for {symbol} ({position['trade_id']}). SL moved to {position['sl']:.6g}.")

        # --- 3. TP / SL Hit Detection (using intra-bar High/Low) ---
        hit_tp = False
        hit_sl = False
        exit_price = current_price # Default exit price if only SL hit

        if pos_type == "LONG":
            # Check if TP was hit (high price reached TP)
            if high_price >= tp:
                hit_tp = True
            # Check if SL was hit (low price reached SL)
            if low_price <= current_sl:
                hit_sl = True
                exit_price = current_sl # Use SL price if hit
                
        else: # SHORT
            # Check if TP was hit (low price reached TP)
            if low_price <= tp:
                hit_tp = True
            # Check if SL was hit (high price reached SL)
            if high_price >= current_sl:
                hit_sl = True
                exit_price = current_sl # Use SL price if hit

        # Determine exit reason, prioritizing SL (conservative assumption)
        exit_reason = None
        if hit_tp and hit_sl:
            # Both hit in the same candle: assume SL first (conservative)
            exit_reason = "SL (Simultaneous TP/SL)"
            exit_price = current_sl # Exit at SL price
        elif hit_sl:
            exit_reason = "BREAK-EVEN SL" if position["break_even_triggered"] and not position["profit_lock_triggered"] else "SL"
            exit_price = current_sl
        elif hit_tp:
            exit_reason = "TP"
            exit_price = tp # Exit at TP price
            
        # --- 4. Close Trade if Exit Condition Met ---
        if exit_reason:
            closed_trade = record_trade_completion(
                symbol=symbol,
                position=position,
                exit_price=exit_price,
                exit_reason=exit_reason,
                exit_candle_time=current_candle_time # Use candle close time for journal
            )
            
            # Send notification to personal chat
            send_to_personal_chat(format_trade_closed_message(
                symbol=symbol,
                position_type=pos_type,
                entry=position["entry"],
                exit_price=exit_price,
                initial_sl=position["initial_sl"],
                final_sl=position["sl"], # Final SL after adjustments
                tp=position["tp"],
                exit_reason=exit_reason,
                pnl_usd=closed_trade["pnl_usd"],
                pnl_pct=closed_trade["pnl_pct"],
                trade_id=position["trade_id"],
                risk_pct=position["risk_pct"],
                regime=position["regime"],
                strategy_version=position["strategy_version"],
                entry_dt_utc=position["entry_candle_time"],
                exit_dt_utc=current_candle_time, # Use candle time for exit timestamp
                break_even_triggered=position["break_even_triggered"],
                profit_lock_triggered=position["profit_lock_triggered"]
            ))
            
            # Remove the position from open positions
            closed_trades_info[symbol] = closed_trade
            del open_positions[symbol]

    return closed_trades_info # Return info about trades that were just closed


def process_new_entry_signal(
    symbol: str,
    signal: Dict[str, Any],
    market_data: Dict[str, Any], # Latest market data for this symbol
    current_capital: float
) -> Tuple[bool, Dict[str, Any] | None]:
    """
    Processes a new trading signal to potentially open a new position.

    Args:
        symbol (str): The trading symbol.
        signal (Dict): The trading signal generated by the strategy module.
                       Contains action, risk_pct, entry_price, stop_price, etc.
        market_data (Dict): Latest market data including current price, ATR, regime, etc.
        current_capital (float): The current available trading capital.

    Returns:
        Tuple[bool, Dict | None]: A tuple where:
            - The first element is True if a new position was opened, False otherwise.
            - The second element is the new position dictionary if opened, None otherwise.
    """
    action = signal.get("action")
    if action in ["HOLD", "ERROR"]: # Do not process HOLD or error signals for new entries
        return False, None
        
    if len(open_positions) >= config.MAX_CONCURRENT_POSITIONS:
        logger.warning(f"Cannot open new {action} for {symbol}: Maximum concurrent positions ({config.MAX_CONCURRENT_POSITIONS}) reached.")
        return False, None
        
    # Validate essential signal data
    required_keys = ["entry_price", "stop_price", "take_profit_price", "risk_pct"]
    if not all(key in signal and signal[key] is not None for key in required_keys):
        logger.error(f"Signal for {symbol} is missing required data: {signal}. Cannot open position.")
        return False, None

    entry_price = signal["entry_price"]
    stop_price = signal["stop_price"]
    tp_price = signal["take_profit_price"]
    risk_pct = signal["risk_pct"]
    
    # Ensure entry price and stop price are valid for calculation
    if entry_price <= 0 or stop_price <= 0:
        logger.error(f"Invalid entry or stop price for {symbol}: Entry={entry_price}, Stop={stop_price}. Cannot open position.")
        return False, None

    # Calculate position size using the risk management module
    position_size_usd = calculate_position_size(
        capital=current_capital,
        risk_pct=risk_pct,
        entry_price=entry_price,
        stop_price=stop_price
    )
    
    if position_size_usd <= 0:
        logger.warning(f"Calculated position size for {symbol} is zero or negative. Cannot open position.")
        return False, None

    # Generate a unique Trade ID
    timestamp_str = market_data["candle_time"].strftime("%Y%m%d-%H%M%S")
    trade_id = f"{config.BOT_VERSION}-{symbol}-{timestamp_str}-{len(open_positions):04d}" # Example format

    # Create the new position dictionary
    new_position = {
        "type": action, # "BUY_LONG" or "SELL_SHORT"
        "entry": entry_price,
        "tp": tp_price,
        "sl": stop_price, # This is the initial SL
        "initial_sl": stop_price, # Store initial SL for reference
        "size_usd": position_size_usd,
        "risk_pct": risk_pct,
        "regime": market_data["regime"],
        "strategy_version": signal["strategy_version"], # Get from signal
        "entry_candle_time": market_data["candle_time"],
        "trade_id": trade_id,
        "break_even_triggered": False,
        "profit_lock_triggered": False
    }
    
    # Add the new position to the global state
    open_positions[symbol] = new_position
    logger.info(f"Opened new position: {trade_id} ({symbol} {action}). Entry: {entry_price:.6g}, Size: ${position_size_usd:.2f}")

    # Send entry notification to personal chat
    send_to_personal_chat(format_entry_message(
        symbol=symbol,
        entry_price=entry_price,
        sl=stop_price,
        tp=tp_price,
        position_size_usd=position_size_usd,
        regime=market_data["regime"],
        strategy_version=signal["strategy_version"],
        trade_id=trade_id,
        entry_dt_utc=market_data["candle_time"], # Use candle time as entry time
        risk_pct=risk_pct
    ))
    
    return True, new_position


def process_symbol_state(
    symbol: str,
    signal: Dict[str, Any],
    market_data: Dict[str, Any], # Latest market data for this symbol
    current_capital: float
) -> Tuple[bool, Dict[str, Any] | None]:
    """
    Processes the state for a single symbol: either manages an existing position
    or attempts to open a new one based on the signal.

    Args:
        symbol (str): The trading symbol.
        signal (Dict): The trading signal for this symbol.
        market_data (Dict): Latest market data for this symbol.
        current_capital (float): The current trading capital.

    Returns:
        Tuple[bool, Dict | None]: Returns (True, position_dict) if a new position was opened,
                                  (False, None) otherwise. Handles both existing and new trades.
    """
    candle_time = market_data.get("candle_time")
    if not candle_time:
        logger.warning(f"Candle time missing in market data for {symbol}. Skipping processing.")
        return False, None

    # --- Check if a position already exists for this symbol ---
    if symbol in open_positions:
        # Manage existing position (TP/SL checks, BE/PL triggers)
        # Note: manage_open_positions is called globally for all positions,
        # so this part is implicitly handled there. We just need to ensure
        # the signal doesn't try to open a *new* trade if one exists.
        logger.debug(f"Position already exists for {symbol}. Managing in global loop.")
        # This function's primary role here is to handle NEW entries.
        # If a position exists, we don't process a new entry signal.
        return False, None
        
    # --- Process potential new entry ---
    # Check if the signal indicates a trade action (not HOLD)
    if signal.get("action") != "HOLD":
        # Attempt to open a new position
        opened, new_pos = process_new_entry_signal(
            symbol=symbol,
            signal=signal,
            market_data=market_data,
            current_capital=current_capital
        )
        if opened:
            # Store the candle time that generated this entry signal
            last_processed_candle_time[symbol] = candle_time
            return True, new_pos
    
    # If no new position was opened (either HOLD signal, or no signal, or position exists)
    return False, None


# --- Global State Management & Initialization ---

def initialize_trading_state():
    """Clears global trading state variables."""
    global open_positions, last_processed_candle_time, daily_completed_trades
    open_positions = {}
    last_processed_candle_time = {}
    daily_completed_trades = []
    logger.info("Trading state initialized.")

def get_current_open_positions_summary() -> list[dict]:
    """Provides a summary of open positions for reporting."""
    summary = []
    for symbol, pos in open_positions.items():
        # NOTE: This summary needs current prices, which are not directly available here.
        # It should ideally be called after market data is fetched and prices are known.
        # For now, returning basic details.
        summary.append({
            "symbol": symbol,
            "type": pos["type"],
            "entry_price": pos["entry"],
            "sl": pos["sl"],
            "tp": pos["tp"],
            # Placeholder values, real-time PnL needs live price
            "current_price": pos["entry"], # Placeholder
            "current_pnl_pct": 0.0 # Placeholder
        })
    return summary

def get_daily_journal_data() -> Tuple[list, dict]:
    """
    Returns the daily completed trades list and relevant stats.
    Used for generating the daily report.
    """
    # Calculate stats from the completed trades list
    num_trades = len(daily_completed_trades)
    wins = sum(1 for t in daily_completed_trades if t.get("pnl_usd", 0) >= 0)
    losses = num_trades - wins
    daily_pnl_total = sum(t.get("pnl_usd", 0.0) for t in daily_completed_trades)
    
    stats = {
        "trades": num_trades,
        "wins": wins,
        "losses": losses,
        "pnl_usd": daily_pnl_total,
        "win_rate": (wins / num_trades * 100) if num_trades > 0 else 0.0
    }
    return daily_completed_trades, stats

# --- Example Usage ---
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format=config.LOGGING_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")
    
    print("--- Testing Trading Engine ---")
    
    # Mock current capital
    mock_capital = config.INITIAL_CAPITAL
    
    # Initialize engine state
    initialize_trading_state()

    # Mock market data (simulate a few candles for testing)
    # Candle 1: Generate a BULLISH signal
    signal_bullish = {
        "action": "BUY_LONG", "risk_pct": 0.01, "entry_price": 100.0,
        "stop_price": 98.8, "take_profit_price": 102.4, "strategy_version": "EMA50-CROSS-V1"
    }
    market_data_candle1 = {
        "symbol": "BTCUSDT", "price": 100.0, "high": 100.5, "low": 99.8, "volume": 1000,
        "candle_time": datetime(2023, 10, 27, 10, 0, 0, tzinfo=timezone.utc),
        "timestamp_utc": datetime(2023, 10, 27, 10, 0, 0, tzinfo=timezone.utc),
        "regime": "WEAK_BULLISH", "atr": 1.0
    }
    
    print("\nSimulating Candle 1: Generating BUY_LONG signal...")
    opened, new_pos = process_symbol_state("BTCUSDT", signal_bullish, market_data_candle1, mock_capital)
    if opened:
        print(f"New position opened: {new_pos['trade_id']} for BTCUSDT")

    # Candle 2: Price moves favorably, but not enough for BE/PL, no TP/SL hit
    market_data_candle2 = {
        "symbol": "BTCUSDT", "price": 100.5, "high": 101.0, "low": 100.2, "volume": 1200,
        "candle_time": datetime(2023, 10, 27, 11, 0, 0, tzinfo=timezone.utc),
        "timestamp_utc": datetime(2023, 10, 27, 11, 0, 0, tzinfo=timezone.utc),
        "regime": "WEAK_BULLISH", "atr": 1.0 # Assume ATR is stable for simplicity
    }
    print("\nSimulating Candle 2: Price moves slightly, no exit...")
    # No signal generated, just managing existing position
    closed_trades_cycle2 = manage_open_positions( {market_data_candle2["symbol"]: market_data_candle2} )
    print(f"Open positions after Candle 2: {len(open_positions)}")

    # Candle 3: Price hits 50% TP distance, triggering Break-even
    # Entry: 100, TP: 102.4 (dist 2.4), SL: 98.8 (dist 1.2)
    # BE trigger at 50% TP dist = 100 + 0.5 * 2.4 = 101.2
    market_data_candle3 = {
        "symbol": "BTCUSDT", "price": 101.5, "high": 101.8, "low": 100.8, "volume": 1500, # High hits BE
        "candle_time": datetime(2023, 10, 27, 12, 0, 0, tzinfo=timezone.utc),
        "timestamp_utc": datetime(2023, 10, 27, 12, 0, 0, tzinfo=timezone.utc),
        "regime": "WEAK_BULLISH", "atr": 1.0
    }
    print("\nSimulating Candle 3: Price reaches Break-even level...")
    closed_trades_cycle3 = manage_open_positions( {market_data_candle3["symbol"]: market_data_candle3} )
    print(f"Open positions after Candle 3: {len(open_positions)}")
    print(f"Position SL after BE: {open_positions['BTCUSDT']['sl']:.6g} (should be entry price 100.0)")

    # Candle 4: Price hits 80% TP distance, triggering Profit Lock
    # PL trigger at 80% TP dist = 100 + 0.8 * 2.4 = 101.92
    # New SL at 25% of TP dist from entry = 100 + 0.25 * 2.4 = 100.6
    market_data_candle4 = {
        "symbol": "BTCUSDT", "price": 102.0, "high": 102.2, "low": 101.0, "volume": 1800, # High hits PL
        "candle_time": datetime(2023, 10, 27, 13, 0, 0, tzinfo=timezone.utc),
        "timestamp_utc": datetime(2023, 10, 27, 13, 0, 0, tzinfo=timezone.utc),
        "regime": "WEAK_BULLISH", "atr": 1.0
    }
    print("\nSimulating Candle 4: Price reaches Profit Lock level...")
    closed_trades_cycle4 = manage_open_positions( {market_data_candle4["symbol"]: market_data_candle4} )
    print(f"Open positions after Candle 4: {len(open_positions)}")
    print(f"Position SL after PL: {open_positions['BTCUSDT']['sl']:.6g} (should be around 100.6)")

    # Candle 5: Price hits TP
    market_data_candle5 = {
        "symbol": "BTCUSDT", "price": 102.4, "high": 102.5, "low": 101.5, "volume": 2000, # High hits TP
        "candle_time": datetime(2023, 10, 27, 14, 0, 0, tzinfo=timezone.utc),
        "timestamp_utc": datetime(2023, 10, 27, 14, 0, 0, tzinfo=timezone.utc),
        "regime": "WEAK_BULLISH", "atr": 1.0
    }
    print("\nSimulating Candle 5: Price hits Take Profit...")
    closed_trades_cycle5 = manage_open_positions( {market_data_candle5["symbol"]: market_data_candle5} )
    print(f"Open positions after Candle 5: {len(open_positions)}")
    print(f"Closed trades today: {len(daily_completed_trades)}")
    if daily_completed_trades:
        print(f"Last closed trade PnL: ${daily_completed_trades[-1]['pnl_usd']:.2f}")
        print(f"Trade Line: {daily_completed_trades[-1]['trade_line']}")

    # Candle 6: Simulate SL hit after break-even but before profit lock
    # Reset state for this simulation
    initialize_trading_state()
    open_positions["ETHUSDT"] = {
        "type": "LONG", "entry": 1800.0, "tp": 1836.0, "sl": 1776.0, "initial_sl": 1776.0,
        "size_usd": 1800.0 * 0.01 / ((1800.0-1776.0)/1800.0), # Approx 1470 USD size
        "risk_pct": 0.01, "regime": "GOOD_RANGE", "strategy_version": "RSI-BB-V1",
        "entry_candle_time": datetime(2023, 10, 27, 10, 0, 0, tzinfo=timezone.utc),
        "trade_id": "SHERPA_V5.3-ETHUSDT-20231027-000002", "break_even_triggered": True, # Assume BE already triggered
        "profit_lock_triggered": False
    }
    # Price moves to trigger BE (already triggered), then hits SL
    # Entry 1800, SL 1800 (after BE), TP 1836
    market_data_candle6 = {
        "symbol": "ETHUSDT", "price": 1805.0, "high": 1810.0, "low": 1795.0, "volume": 1000, # Low hits SL (which is at 1800)
        "candle_time": datetime(2023, 10, 27, 11, 0, 0, tzinfo=timezone.utc),
        "timestamp_utc": datetime(2023, 10, 27, 11, 0, 0, tzinfo=timezone.utc),
        "regime": "GOOD_RANGE", "atr": 1.0
    }
    print("\nSimulating Candle 6: SL hit after Break-even...")
    closed_trades_cycle6 = manage_open_positions( {market_data_candle6["symbol"]: market_data_candle6} )
    print(f"Open positions after Candle 6: {len(open_positions)}")
    if daily_completed_trades:
        print(f"Last closed trade PnL: ${daily_completed_trades[-1]['pnl_usd']:.2f}")
        print(f"Exit Reason: {daily_completed_trades[-1]['exit_reason']}")
        print(f"Trade Line: {daily_completed_trades[-1]['trade_line']}")
