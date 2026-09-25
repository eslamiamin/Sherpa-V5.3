"""
Personal Telegram Messaging Module.

This module handles sending various types of messages to the user's personal Telegram chat.
It includes notifications for trade entries, exits, status updates (Break-even, Profit Lock),
and periodic reports (Daily Journal, 4-Hour Report).

Crucially, it formats trade-related messages with a structured 'TRADE|...' line at the end,
suitable for direct import into Excel or Power Query for performance analysis.
"""

import logging
import requests
from datetime import datetime
from typing import List, Dict, Any

import config

logger = logging.getLogger(__name__)

def format_timestamp_message(timestamp_utc: datetime) -> str:
    """
    Formats a UTC datetime object into a string showing both UTC and Tehran times.

    Args:
        timestamp_utc (datetime): The datetime object in UTC.

    Returns:
        str: A formatted string like "[UTC: YYYY-MM-DD HH:MM:SS | Tehran: YYYY-MM-DD HH:MM:SS]".
    """
    # Ensure the input is timezone-aware UTC
    if timestamp_utc.tzinfo is None or timestamp_utc.tzinfo.utcoffset(timestamp_utc) != timezone.utc.utcoffset(None):
         logger.warning(f"Timestamp {timestamp_utc} is not UTC. Attempting to convert or assume UTC.")
         # Attempt to make it UTC if naive, or just use it if it's already timezone-aware
         if timestamp_utc.tzinfo is None:
              timestamp_utc = timestamp_utc.replace(tzinfo=config.TIMEZONE_UTC)
         else: # If it's timezone aware but not UTC, convert it
              timestamp_utc = timestamp_utc.astimezone(config.TIMEZONE_UTC)
              
    tehran_time = timestamp_utc.astimezone(config.TIMEZONE_TEHRAN)
    
    utc_str = timestamp_utc.strftime("%Y-%m-%d %H:%M:%S")
    tehran_str = tehran_time.strftime("%Y-%m-%d %H:%M:%S")
    
    return f"UTC: {utc_str} | Tehran: {tehran_str}"

def format_trade_line(
    bot_version: str,
    trade_id: str,
    symbol: str,
    entry_dt_utc: datetime,
    exit_dt_utc: datetime | None,
    side: str,
    strategy_version: str,
    regime: str,
    risk_pct: float,
    initial_sl: float,
    entry_price: float,
    tp: float | None,
    position_size_usd: float,
    exit_price: float | None,
    final_sl: float | None,
    exit_reason: str,
    pnl_usd: float | None,
    pnl_pct: float | None,
    break_even_triggered: bool | None,
    profit_lock_triggered: bool | None
) -> str:
    """
    Formats a structured trade line string compatible with Excel/Power Query.

    Args:
        bot_version (str): The current version of the trading bot.
        trade_id (str): Unique identifier for the trade.
        symbol (str): Trading symbol (e.g., "BTCUSDT").
        entry_dt_utc (datetime): Timestamp of trade entry in UTC.
        exit_dt_utc (datetime | None): Timestamp of trade exit in UTC (if applicable).
        side (str): Trade direction ("LONG" or "SHORT").
        strategy_version (str): Version of the trading strategy used.
        regime (str): Market regime at the time of entry.
        risk_pct (float): Risk percentage allocated to this trade.
        initial_sl (float): The initial stop loss price.
        entry_price (float): The entry price of the trade.
        tp (float | None): The take profit price (if set).
        position_size_usd (float): The notional value of the position in USD.
        exit_price (float | None): The exit price of the trade (if applicable).
        final_sl (float | None): The final stop loss price (if different from initial).
        exit_reason (str): Reason for trade closure (e.g., "TP", "SL", "BREAK-EVEN", "OPEN").
        pnl_usd (float | None): Profit or loss in USD (if applicable).
        pnl_pct (float | None): Profit or loss as a percentage (if applicable).
        break_even_triggered (bool | None): Whether break-even was triggered.
        profit_lock_triggered (bool | None): Whether profit lock was triggered.

    Returns:
        str: A pipe-delimited string representing the trade data.
    """
    
    # Format timestamps (handle None for exit_dt_utc)
    entry_ts_str = entry_dt_utc.strftime("%Y-%m-%d %H:%M:%S")
    exit_ts_str = exit_dt_utc.strftime("%Y-%m-%d %H:%M:%S") if exit_dt_utc else "NA"
    
    # Format numerical values, using "NA" for None or undefined
    tp_str = f"{tp:.6g}" if tp is not None else "NA"
    exit_price_str = f"{exit_price:.6g}" if exit_price is not None else "NA"
    final_sl_str = f"{final_sl:.6g}" if final_sl is not None else "NA"
    pnl_usd_str = f"{pnl_usd:+.2f}" if pnl_usd is not None else "NA"
    pnl_pct_str = f"{pnl_pct:+.2f}" if pnl_pct is not None else "NA"
    
    # Boolean flags formatted as strings
    break_even_str = "YES" if break_even_triggered else "NO"
    profit_lock_str = "YES" if profit_lock_triggered else "NO"

    # Construct the line, ensuring all fields are present even if NA
    trade_line_parts = [
        "TRADE",
        bot_version,
        trade_id,
        symbol,
        entry_ts_str,
        exit_ts_str,
        side,
        strategy_version,
        regime,
        f"{risk_pct:.4f}", # Format risk percentage precisely
        f"{initial_sl:.6g}",
        f"{entry_price:.6g}",
        tp_str,
        f"{position_size_usd:.2f}", # Position size in USD
        exit_price_str,
        final_sl_str,
        exit_reason,
        pnl_usd_str,
        pnl_pct_str,
        break_even_str,
        profit_lock_str
    ]
    
    return "|".join(trade_line_parts)


def send_telegram_message(msg: str, chat_id: str, bot_token: str):
    """
    Sends a formatted message to a specified Telegram chat ID using the bot token.

    Args:
        msg (str): The message content to send.
        chat_id (str): The target chat ID.
        bot_token (str): The Telegram Bot API token.
    """
    if not bot_token or not chat_id:
        logger.warning("Telegram Bot Token or Chat ID is not configured. Cannot send message.")
        return

    url = config.TELEGRAM_API_URL.format(token=bot_token)
    payload = {
        "chat_id": chat_id,
        "text": msg,
        "parse_mode": "Markdown" # Use Markdown for formatting
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status() # Raise an exception for bad status codes
        logger.debug(f"Message sent to Telegram chat {chat_id}.")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send Telegram message to {chat_id}: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred while sending Telegram message: {e}")


def send_to_personal_chat(message: str):
    """Helper function to send messages to the personal chat."""
    send_telegram_message(
        message,
        config.TELEGRAM_PERSONAL_CHAT_ID,
        config.TELEGRAM_BOT_TOKEN
    )

# ============================================================
# MESSAGE FORMATTING FUNCTIONS FOR PERSONAL CHAT
# ============================================================

def format_entry_message(
    symbol: str,
    entry_price: float,
    sl: float,
    tp: float,
    position_size_usd: float,
    regime: str,
    strategy_version: str,
    trade_id: str,
    entry_dt_utc: datetime,
    risk_pct: float
) -> str:
    """Formats the message for a new trade entry."""
    
    # Timestamp for the message body
    ts_message = format_timestamp_message(entry_dt_utc)
    
    # Trade line for logging/analysis
    trade_line = format_trade_line(
        bot_version=config.BOT_VERSION,
        trade_id=trade_id,
        symbol=symbol,
        entry_dt_utc=entry_dt_utc,
        exit_dt_utc=None,
        side="LONG" if entry_price > 0 else "SHORT", # Infer side based on price, needs to be passed explicitly
        strategy_version=strategy_version,
        regime=regime,
        risk_pct=risk_pct,
        initial_sl=sl,
        entry_price=entry_price,
        tp=tp,
        position_size_usd=position_size_usd,
        exit_price=None,
        final_sl=None,
        exit_reason="OPEN",
        pnl_usd=None,
        pnl_pct=None,
        break_even_triggered=False,
        profit_lock_triggered=False
    )
    
    # Determine side based on entry/sl/tp relation if possible, otherwise pass it explicitly
    side = "LONG"
    if tp is not None and entry_price > tp: side = "SHORT"
    if sl is not None and entry_price > sl and side == "LONG": side = "SHORT" # More robust logic needed if price can be above SL/TP in SHORT
    if sl is not None and entry_price < sl and side == "SHORT": side = "LONG" # More robust logic needed if price can be below SL/TP in LONG

    # Re-format trade line with the determined side
    trade_line = format_trade_line(
        bot_version=config.BOT_VERSION,
        trade_id=trade_id,
        symbol=symbol,
        entry_dt_utc=entry_dt_utc,
        exit_dt_utc=None,
        side=side, # Use determined side
        strategy_version=strategy_version,
        regime=regime,
        risk_pct=risk_pct,
        initial_sl=sl,
        entry_price=entry_price,
        tp=tp,
        position_size_usd=position_size_usd,
        exit_price=None,
        final_sl=None,
        exit_reason="OPEN",
        pnl_usd=None,
        pnl_pct=None,
        break_even_triggered=False,
        profit_lock_triggered=False
    )

    message = (
        f"🚀 *NEW TRADE ENTRY — {symbol}*\n\n"
        f"*Trade ID:* `{trade_id}`\n"
        f"*Side:* `{side}`\n"
        f"*Entry Price:* `{entry_price:.6g}`\n"
        f"*Stop Loss:* `{sl:.6g}`\n"
        f"*Take Profit:* `{tp:.6g}`\n"
        f"*Position Size:* `${position_size_usd:.2f}`\n"
        f"*Risk:* `{risk_pct*100:.1f}%` (${(position_size_usd * (abs(entry_price - sl) / entry_price)):.2f})\n" # PnL if SL hit
        f"*Market Regime:* `{regime}`\n"
        f"*Strategy:* `{strategy_version}`\n\n"
        f"ℹ️ *Details:* {ts_message}\n\n"
        f"--- Manage your position ---\n"
        f"🛡 50% TP → Break-even\n"
        f"🔒 80% TP → Lock 25% TP distance"
    )
    
    return f"{message}\n\n`{trade_line}`"


def format_break_even_message(
    trade_id: str,
    symbol: str,
    entry_price: float,
    old_sl: float,
    new_sl: float,
    current_price: float,
    timestamp_utc: datetime
) -> str:
    """Formats the message for break-even trigger."""
    ts_message = format_timestamp_message(timestamp_utc)
    
    message = (
        f"🛡 *BREAK-EVEN TRIGGERED — {symbol}*\n\n"
        f"*Trade ID:* `{trade_id}`\n"
        f"*Position Entry:* `{entry_price:.6g}`\n"
        f"*Old SL:* `{old_sl:.6g}`\n"
        f"*New SL:* `{new_sl:.6g}`\n"
        f"*Current Price:* `{current_price:.6g}`\n\n"
        f"ℹ️ *Details:* {ts_message}"
    )
    # Note: Trade line is not generated here as it's not a closed trade,
    # but it should be appended to the relevant trade log/state.
    return message


def format_profit_lock_message(
    trade_id: str,
    symbol: str,
    old_sl: float,
    new_sl: float,
    current_price: float,
    timestamp_utc: datetime
) -> str:
    """Formats the message for profit lock trigger."""
    ts_message = format_timestamp_message(timestamp_utc)
    
    message = (
        f"🔒 *PROFIT LOCK TRIGGERED — {symbol}*\n\n"
        f"*Trade ID:* `{trade_id}`\n"
        f"*Old SL:* `{old_sl:.6g}`\n"
        f"*New SL:* `{new_sl:.6g}`\n"
        f"*Current Price:* `{current_price:.6g}`\n\n"
        f"ℹ️ *Details:* {ts_message}"
    )
    # Note: Trade line is not generated here as it's not a closed trade.
    return message


def format_trade_closed_message(
    symbol: str,
    position_type: str,
    entry: float,
    exit_price: float,
    initial_sl: float,
    final_sl: float,
    tp: float,
    exit_reason: str,
    pnl_usd: float,
    pnl_pct: float,
    trade_id: str,
    risk_pct: float,
    regime: str,
    strategy_version: str,
    entry_dt_utc: datetime,
    exit_dt_utc: datetime,
    break_even_triggered: bool,
    profit_lock_triggered: bool
) -> str:
    """Formats the message for a closed trade."""
    
    # Timestamp for the message body
    ts_message = format_timestamp_message(exit_dt_utc)
    
    # Determine status icon based on PnL
    status_icon = "🎯" if pnl_usd >= 0 else "🛑" # Use target icon for profit, stop icon for loss

    message = (
        f"{status_icon} *TRADE CLOSED — {symbol}*\n\n"
        f"*Trade ID:* `{trade_id}`\n"
        f"*Side:* `{position_type}`\n"
        f"*Entry Price:* `{entry:.6g}`\n"
        f"*Exit Price:* `{exit_price:.6g}`\n"
        f"*Exit Reason:* `{exit_reason}`\n"
        f"*Initial SL:* `{initial_sl:.6g}`\n"
        f"*Final SL:* `{final_sl:.6g}`\n"
        f"*Take Profit:* `{tp:.6g}`\n\n"
        f"💰 *PnL:* `${pnl_usd:+.2f}` (`{pnl_pct:+.2f}%`)\n"
        f"*Risk:* `{risk_pct*100:.1f}%` (${(position_size_usd * (abs(entry - initial_sl) / entry)):.2f})\n" # Calculate risk amount based on initial SL
        f"*Regime:* `{regime}`\n"
        f"*Strategy:* `{strategy_version}`\n"
        f"*Break-even:* {'YES' if break_even_triggered else 'NO'}\n"
        f"*Profit Lock:* {'YES' if profit_lock_triggered else 'NO'}\n\n"
        f"ℹ️ *Details:* {ts_message}"
    )
    
    # Generate the structured trade line for analysis
    trade_line = format_trade_line(
        bot_version=config.BOT_VERSION,
        trade_id=trade_id,
        symbol=symbol,
        entry_dt_utc=entry_dt_utc,
        exit_dt_utc=exit_dt_utc,
        side=position_type,
        strategy_version=strategy_version,
        regime=regime,
        risk_pct=risk_pct,
        initial_sl=initial_sl,
        entry_price=entry,
        tp=tp,
        position_size_usd=position_size_usd, # Needs to be passed or retrieved from position state
        exit_price=exit_price,
        final_sl=final_sl,
        exit_reason=exit_reason,
        pnl_usd=pnl_usd,
        pnl_pct=pnl_pct,
        break_even_triggered=break_even_triggered,
        profit_lock_triggered=profit_lock_triggered
    )
    
    return f"{message}\n\n`{trade_line}`"


def format_daily_journal(
    current_date_utc: datetime,
    starting_capital: float,
    ending_capital: float,
    daily_pnl: float,
    daily_pnl_pct: float,
    num_trades: int,
    winning_trades: int,
    losing_trades: int,
    win_rate: float,
    total_pnl: float,
    completed_trades_data: List[Dict[str, Any]], # List of trade dicts for the day
    open_positions_summary: List[Dict[str, Any]], # Summary of open positions
    market_snapshot: Dict[str, Dict[str, Any]] # Latest market data per symbol
) -> str:
    """
    Formats the complete daily trading journal report.

    This report includes account performance, a summary of closed trades,
    details of open positions, and a snapshot of current market conditions.
    """
    
    header_ts_str = format_timestamp_message(current_date_utc)

    msg = (
        f"📓 *DAILY TRADING JOURNAL*\n"
        f"Date: `{header_ts_str}`\n\n"

        f"💰 *ACCOUNT PERFORMANCE*\n"
        f"Starting Capital: `${starting_capital:,.2f}`\n"
        f"Ending Capital: `${ending_capital:,.2f}`\n"
        f"Daily PnL: `${daily_pnl:+.2f}` "
        f"(`{daily_pnl_pct:+.2f}%`)\n\n"

        f"📊 *TODAY'S TRADING STATS*\n"
        f"Total Trades: `{num_trades}`\n"
        f"Wins: `{winning_trades}`\n"
        f"Losses: `{losing_trades}`\n"
        f"Win Rate: `{win_rate:.1f}%`\n"
        f"Total PnL (All Time): `${total_pnl:+.2f}`\n" # Assuming total_pnl is managed globally or passed
    )

    # --- Closed Trades Section ---
    msg += "\n━━━━━━━━━━━━━━━━━━━━\n"
    msg += "📋 *CLOSED TRADES (TODAY)*\n\n"

    if not completed_trades_data:
        msg += "No trades were closed today.\n\n"
    else:
        for trade in completed_trades_data:
            # Use the trade_line directly if available, otherwise format it
            trade_line = trade.get("trade_line")
            if not trade_line:
                 # Need to reconstruct trade_line parts if not present
                 # This assumes trade dict has all necessary keys
                 trade_line = format_trade_line(
                     bot_version=config.BOT_VERSION, # Needs to be passed or inferred
                     trade_id=trade.get("trade_id", "UNKNOWN_ID"),
                     symbol=trade.get("symbol", "UNKNOWN_SYM"),
                     entry_dt_utc=trade.get("entry_dt_utc"), # Needs to be datetime object
                     exit_dt_utc=trade.get("exit_dt_utc"),   # Needs to be datetime object
                     side=trade.get("type", "UNKNOWN"),
                     strategy_version=trade.get("strategy_version", "UNKNOWN_STRAT"),
                     regime=trade.get("regime", "UNKNOWN_REGIME"),
                     risk_pct=trade.get("risk_pct", 0.0),
                     initial_sl=trade.get("initial_sl", 0.0),
                     entry_price=trade.get("entry", 0.0),
                     tp=trade.get("tp"),
                     position_size_usd=trade.get("size_usd", 0.0),
                     exit_price=trade.get("exit", 0.0),
                     final_sl=trade.get("final_sl"),
                     exit_reason=trade.get("exit_reason", "UNKNOWN"),
                     pnl_usd=trade.get("pnl_usd"),
                     pnl_pct=trade.get("pnl_pct"),
                     break_even_triggered=trade.get("break_even_triggered", False),
                     profit_lock_triggered=trade.get("profit_lock_triggered", False)
                 )
            
            pnl_icon = "✅" if trade.get("pnl_usd", 0) >= 0 else "❌"
            msg += (
                f"{pnl_icon} *{trade.get('symbol')} — {trade.get('type')}*\n"
                f"Entry: `{trade.get('entry', 0.0):.6g}` | Exit: `{trade.get('exit', 0.0):.6g}`\n"
                f"PnL: `${trade.get('pnl_usd', 0.0):+.2f}` (`{trade.get('pnl_pct', 0.0):+.2f}%`)\n"
                f"Reason: `{trade.get('exit_reason', 'N/A')}` | Regime: `{trade.get('regime', 'N/A')}`\n\n"
            )

    # --- Open Positions Section ---
    msg += "━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"📈 *OPEN POSITIONS ({len(open_positions_summary)}/{config.MAX_CONCURRENT_POSITIONS})*\n\n"

    if not open_positions_summary:
        msg += "No open positions.\n\n"
    else:
        for pos_summary in open_positions_summary:
            msg += (
                f"• *{pos_summary.get('symbol')}* {pos_summary.get('type')} | "
                f"Entry: `{pos_summary.get('entry_price', 0.0):.6g}` | "
                f"Current: `{pos_summary.get('current_price', 0.0):.6g}`\n"
                f"  PnL: `{pos_summary.get('current_pnl_pct', 0.0):+.2f}%` | "
                f"SL: `{pos_summary.get('sl', 0.0):.6g}` | "
                f"TP: `{pos_summary.get('tp', 0.0):.6g}`\n"
            )
        msg += "\n"

    # --- Market Snapshot Section ---
    msg += "━━━━━━━━━━━━━━━━━━━━\n"
    msg += "📊 *MARKET SNAPSHOT*\n\n"

    if not market_snapshot:
        msg += "Market data not available.\n\n"
    else:
        for symbol, data in market_snapshot.items():
            msg += (
                f"• *{symbol}*: Price `{data.get('price', 0.0):.6g}` | "
                f"RSI `{data.get('rsi', 0.0):.1f}` | "
                f"4H `{data.get('change_4h', 0.0):+.2f}%` | "
                f"1D `{data.get('change_1d', 0.0):+.2f}%` | "
                f"1W `{data.get('change_1w', 0.0):+.2f}%`\n"
            )
        msg += "\n"
        
    # Add all generated trade lines at the end of the journal for easy parsing
    if completed_trades_data:
        msg += "--- ALL CLOSED TRADE LINES ---\n"
        for trade in completed_trades_data:
            trade_line = trade.get("trade_line")
            if trade_line:
                msg += f"`{trade_line}`\n"
            else: # Fallback if trade_line wasn't pre-generated
                 trade_line = format_trade_line( # Needs all params
                     bot_version=config.BOT_VERSION, trade_id=trade.get("trade_id", "UNKNOWN_ID"),
                     symbol=trade.get("symbol", "UNKNOWN_SYM"), entry_dt_utc=trade.get("entry_dt_utc"),
                     exit_dt_utc=trade.get("exit_dt_utc"), side=trade.get("type", "UNKNOWN"),
                     strategy_version=trade.get("strategy_version", "UNKNOWN_STRAT"), regime=trade.get("regime", "UNKNOWN_REGIME"),
                     risk_pct=trade.get("risk_pct", 0.0), initial_sl=trade.get("initial_sl", 0.0),
                     entry_price=trade.get("entry", 0.0), tp=trade.get("tp"),
                     position_size_usd=trade.get("size_usd", 0.0), exit_price=trade.get("exit", 0.0),
                     final_sl=trade.get("final_sl"), exit_reason=trade.get("exit_reason", "UNKNOWN"),
                     pnl_usd=trade.get("pnl_usd"), pnl_pct=trade.get("pnl_pct"),
                     break_even_triggered=trade.get("break_even_triggered", False),
                     profit_lock_triggered=trade.get("profit_lock_triggered", False)
                 )
                 msg += f"`{trade_line}`\n"

    return msg


def format_4h_report(
    current_time_utc: datetime,
    capital: float,
    daily_pnl: float,
    win_rate: float,
    num_trades: int,
    today_closed_trades_summary: List[Dict[str, Any]], # Short summary of today's closed trades
    open_positions_summary: List[Dict[str, Any]],
    market_overview: Dict[str, Dict[str, Any]]
) -> str:
    """
    Formats the concise 4-hour market and account report.

    This report provides a quick overview of account status and market conditions.
    """
    
    ts_message = format_timestamp_message(current_time_utc)

    msg = (
        f"🕒 *4-HOUR ACCOUNT & MARKET REPORT*\n"
        f"Time: `{ts_message}`\n\n"

        f"💵 *ACCOUNT STATUS*\n"
        f"Current Capital: `${capital:,.2f}`\n"
        f"Today's PnL: `${daily_pnl:+.2f}`\n"
        f"Today's Trades: `{num_trades}` | Win Rate: `{win_rate:.1f}%`\n\n"
    )

    # --- Recent Closed Trades ---
    msg += "📋 *TODAY'S RECENTLY CLOSED TRADES*\n\n"
    if not today_closed_trades_summary:
        msg += "No closed trades today yet.\n\n"
    else:
        for trade in today_closed_trades_summary:
            icon = "✅" if trade.get("pnl_usd", 0) >= 0 else "❌"
            msg += (
                f"{icon} `{trade.get('symbol')}` {trade.get('type')} | "
                f"PnL: `${trade.get('pnl_usd', 0.0):+.2f}` | "
                f"{trade.get('exit_reason')}\n"
            )
        msg += "\n"

    # --- Open Positions Summary ---
    msg += f"📈 *OPEN POSITIONS ({len(open_positions_summary)}/{config.MAX_CONCURRENT_POSITIONS})*\n\n"
    if not open_positions_summary:
        msg += "No open positions.\n\n"
    else:
        for pos_summary in open_positions_summary:
            msg += (
                f"• *{pos_summary.get('symbol')}* {pos_summary.get('type')} | "
                f"Entry: `{pos_summary.get('entry_price', 0.0):.6g}` | "
                f"Current: `{pos_summary.get('current_price', 0.0):.6g}`\n"
                f"  PnL: `{pos_summary.get('current_pnl_pct', 0.0):+.2f}%` | "
                f"SL: `{pos_summary.get('sl', 0.0):.6g}`\n"
            )
        msg += "\n"

    # --- Market Overview ---
    msg += "📊 *MARKET OVERVIEW*\n\n"
    if not market_overview:
        msg += "Market data not available.\n\n"
    else:
        for symbol, data in market_overview.items():
            msg += (
                f"• *{symbol}*: Price `{data.get('price', 0.0):.6g}` | "
                f"RSI `{data.get('rsi', 0.0):.1f}` | "
                f"4H `{data.get('change_4h', 0.0):+.2f}%` | "
                f"1D `{data.get('change_1d', 0.0):+.2f}%`\n"
            )
        msg += "\n"

    return msg

# --- Example Usage ---
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format=config.LOGGING_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")

    print("--- Testing Telegram Personal Chat Formatting ---")

    # Mock data for testing
    mock_entry_dt_utc = datetime.now(config.TIMEZONE_UTC)
    mock_exit_dt_utc = mock_entry_dt_utc + pd.Timedelta(hours=2)
    mock_trade_id = "SHERPA_V5.3-BTCUSDT-20231027-000001"
    mock_symbol = "BTCUSDT"
    mock_entry = 30000.0
    mock_sl = 29500.0
    mock_tp = 31000.0
    mock_exit_price = 31000.0 # TP hit
    mock_pnl_usd = 100.0
    mock_pnl_pct = 0.33
    mock_position_size = 3000.0 # Example size
    mock_strategy_version = "EMA50-CROSS-V1"
    mock_regime = "WEAK_BULLISH"
    mock_risk_pct = 0.01

    # Test Entry Message
    entry_msg = format_entry_message(
        symbol=mock_symbol,
        entry_price=mock_entry,
        sl=mock_sl,
        tp=mock_tp,
        position_size_usd=mock_position_size,
        regime=mock_regime,
        strategy_version=mock_strategy_version,
        trade_id=mock_trade_id,
        entry_dt_utc=mock_entry_dt_utc,
        risk_pct=mock_risk_pct
    )
    print("\n--- Entry Message ---")
    print(entry_msg)

    # Test Trade Closed Message (TP Hit)
    closed_msg_tp = format_trade_closed_message(
        symbol=mock_symbol,
        position_type="LONG",
        entry=mock_entry,
        exit_price=mock_exit_price,
        initial_sl=mock_sl,
        final_sl=mock_sl, # SL didn't change in this TP hit scenario
        tp=mock_tp,
        exit_reason="TP",
        pnl_usd=mock_pnl_usd,
        pnl_pct=mock_pnl_pct,
        trade_id=mock_trade_id,
        risk_pct=mock_risk_pct,
        regime=mock_regime,
        strategy_version=mock_strategy_version,
        entry_dt_utc=mock_entry_dt_utc,
        exit_dt_utc=mock_exit_dt_utc,
        break_even_triggered=False,
        profit_lock_triggered=False
    )
    print("\n--- Trade Closed Message (TP Hit) ---")
    print(closed_msg_tp)

    # Test Trade Closed Message (SL Hit after Break-even)
    mock_exit_price_sl = 29500.0 # SL hit
    mock_pnl_usd_sl = -mock_position_size * (abs(mock_entry - mock_sl) / mock_entry)
    mock_pnl_pct_sl = (mock_pnl_usd_sl / mock_position_size) * 100
    
    closed_msg_sl = format_trade_closed_message(
        symbol=mock_symbol,
        position_type="LONG",
        entry=mock_entry,
        exit_price=mock_exit_price_sl,
        initial_sl=mock_sl,
        final_sl=mock_sl, # In this simple case, final SL is same as initial
        tp=mock_tp,
        exit_reason="SL", # Simple SL hit
        pnl_usd=mock_pnl_usd_sl,
        pnl_pct=mock_pnl_pct_sl,
        trade_id=mock_trade_id,
        risk_pct=mock_risk_pct,
        regime=mock_regime,
        strategy_version=mock_strategy_version,
        entry_dt_utc=mock_entry_dt_utc,
        exit_dt_utc=mock_exit_dt_utc,
        break_even_triggered=True, # Assume break-even was triggered before SL
        profit_lock_triggered=False
    )
    print("\n--- Trade Closed Message (SL Hit after Break-even) ---")
    print(closed_msg_sl)

    # Test Break-even and Profit Lock Messages
    mock_current_price = 30500.0 # Price has moved favorably
    mock_old_sl = 29500.0 # Initial SL
    # Simulate break-even: new SL is entry price
    mock_new_sl_be = mock_entry 
    # Simulate profit lock: new SL is 25% of TP distance from entry
    mock_tp_dist = abs(mock_tp - mock_entry)
    mock_new_sl_pl = mock_entry + 0.25 * mock_tp_dist 

    be_msg = format_break_even_message(
        trade_id=mock_trade_id,
        symbol=mock_symbol,
        entry_price=mock_entry,
        old_sl=mock_old_sl,
        new_sl=mock_new_sl_be,
        current_price=mock_current_price,
        timestamp_utc=mock_exit_dt_utc # Use a relevant timestamp
    )
    print("\n--- Break-even Message ---")
    print(be_msg)

    pl_msg = format_profit_lock_message(
        trade_id=mock_trade_id,
        symbol=mock_symbol,
        old_sl=mock_old_sl, # If PL happens before BE, old SL is initial
        new_sl=mock_new_sl_pl,
        current_price=mock_current_price,
        timestamp_utc=mock_exit_dt_utc
    )
    print("\n--- Profit Lock Message ---")
    print(pl_msg)

    # Mock data for Daily Journal and 4h Report
    mock_daily_trades_data = [
        { # Example of a completed trade dictionary
            "trade_id": "SHERPA_V5.3-BTCUSDT-20231027-000001",
            "symbol": "BTCUSDT", "type": "LONG", "entry": 30000.0, "exit": 31000.0,
            "tp": 31000.0, "initial_sl": 29500.0, "final_sl": 29500.0, "size_usd": 3000.0,
            "pnl_usd": 100.0, "pnl_pct": 0.33, "exit_reason": "TP", "regime": "WEAK_BULLISH",
            "strategy_version": "EMA50-CROSS-V1",
            "entry_dt_utc": mock_entry_dt_utc, "exit_dt_utc": mock_exit_dt_utc,
            "break_even_triggered": False, "profit_lock_triggered": False,
            # "trade_line": generated_trade_line_string # Optionally pre-generate
        },
        # ... more trades
    ]
    mock_open_positions = [
        {"symbol": "ETHUSDT", "type": "SHORT", "entry_price": 1800.0, "current_price": 1790.0,
         "sl": 1820.0, "tp": 1750.0, "current_pnl_pct": -0.56}
    ]
    mock_market_snapshot = {
        "BTCUSDT": {"price": 30500.0, "rsi": 62.5, "change_4h": 1.5, "change_1d": 3.0, "change_1w": 5.0},
        "ETHUSDT": {"price": 1790.0, "rsi": 45.0, "change_4h": -0.8, "change_1d": -1.0, "change_1w": -2.0}
    }

    # Test Daily Journal
    daily_journal_msg = format_daily_journal(
        current_date_utc=mock_entry_dt_utc,
        starting_capital=10000.0,
        ending_capital=10100.0,
        daily_pnl=100.0,
        daily_pnl_pct=1.0,
        num_trades=1,
        winning_trades=1,
        losing_trades=0,
        win_rate=100.0,
        total_pnl=100.0, # Assuming this is overall total PnL
        completed_trades_data=mock_daily_trades_data,
        open_positions_summary=mock_open_positions,
        market_snapshot=mock_market_snapshot
    )
    print("\n--- Daily Journal ---")
    print(daily_journal_msg)
    
    # Test 4-Hour Report
    report_4h_msg = format_4h_report(
        current_time_utc=mock_entry_dt_utc,
        capital=10100.0,
        daily_pnl=100.0,
        win_rate=100.0,
        num_trades=1,
        today_closed_trades_summary=[t for t in mock_daily_trades_data if t.get("pnl_usd", 0) >= 0], # Simplified summary
        open_positions_summary=mock_open_positions,
        market_overview=mock_market_snapshot
    )
    print("\n--- 4-Hour Report ---")
    print(report_4h_msg)
