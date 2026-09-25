"""
Personal Telegram Messaging Module for SHERPA V5.3.

Handles:
- Personal trade entry notifications
- Break-even notifications
- Profit-lock notifications
- Closed-trade notifications
- Daily journal
- 4-hour report
- Structured TRADE|... lines for Excel / Power Query
"""

import logging
import requests
from datetime import datetime
from typing import List, Dict, Any, Optional

import config

logger = logging.getLogger(__name__)


# ============================================================
# TIME / FORMATTING
# ============================================================

def format_timestamp_message(timestamp_utc: datetime) -> str:
    """
    Format a datetime as UTC and Tehran time.

    Naive timestamps are assumed to be UTC.
    """

    if timestamp_utc is None:
        return "UTC: N/A | Tehran: N/A"

    if timestamp_utc.tzinfo is None:
        timestamp_utc = timestamp_utc.replace(
            tzinfo=config.TIMEZONE_UTC
        )
    else:
        timestamp_utc = timestamp_utc.astimezone(
            config.TIMEZONE_UTC
        )

    tehran_time = timestamp_utc.astimezone(
        config.TIMEZONE_TEHRAN
    )

    utc_str = timestamp_utc.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    tehran_str = tehran_time.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    return (
        f"UTC: {utc_str} | "
        f"Tehran: {tehran_str}"
    )


# ============================================================
# STRUCTURED TRADE LINE
# ============================================================

def format_trade_line(
    bot_version: str,
    trade_id: str,
    symbol: str,
    entry_dt_utc: datetime,
    exit_dt_utc: Optional[datetime],
    side: str,
    strategy_version: str,
    regime: str,
    risk_pct: float,
    initial_sl: float,
    entry_price: float,
    tp: Optional[float],
    position_size_usd: float,
    exit_price: Optional[float],
    final_sl: Optional[float],
    exit_reason: str,
    pnl_usd: Optional[float],
    pnl_pct: Optional[float],
    break_even_triggered: Optional[bool],
    profit_lock_triggered: Optional[bool],
) -> str:

    entry_ts = (
        entry_dt_utc.strftime("%Y-%m-%d %H:%M:%S")
        if entry_dt_utc
        else "NA"
    )

    exit_ts = (
        exit_dt_utc.strftime("%Y-%m-%d %H:%M:%S")
        if exit_dt_utc
        else "NA"
    )

    tp_str = (
        f"{tp:.6g}"
        if tp is not None
        else "NA"
    )

    exit_price_str = (
        f"{exit_price:.6g}"
        if exit_price is not None
        else "NA"
    )

    final_sl_str = (
        f"{final_sl:.6g}"
        if final_sl is not None
        else "NA"
    )

    pnl_usd_str = (
        f"{pnl_usd:+.2f}"
        if pnl_usd is not None
        else "NA"
    )

    pnl_pct_str = (
        f"{pnl_pct:+.2f}"
        if pnl_pct is not None
        else "NA"
    )

    break_even_str = (
        "YES"
        if break_even_triggered
        else "NO"
    )

    profit_lock_str = (
        "YES"
        if profit_lock_triggered
        else "NO"
    )

    parts = [
        "TRADE",
        bot_version,
        trade_id,
        symbol,
        entry_ts,
        exit_ts,
        side,
        strategy_version,
        regime,
        f"{risk_pct:.4f}",
        f"{initial_sl:.6g}",
        f"{entry_price:.6g}",
        tp_str,
        f"{position_size_usd:.2f}",
        exit_price_str,
        final_sl_str,
        exit_reason,
        pnl_usd_str,
        pnl_pct_str,
        break_even_str,
        profit_lock_str,
    ]

    return "|".join(parts)


# ============================================================
# TELEGRAM SENDING
# ============================================================

def send_telegram_message(
    msg: str,
    chat_id: str,
    bot_token: str,
):
    """Send a message through Telegram Bot API."""

    if not bot_token or not chat_id:
        logger.warning(
            "Telegram Bot Token or Chat ID is missing."
        )
        return False

    url = config.TELEGRAM_API_URL.format(
        token=bot_token
    )

    payload = {
        "chat_id": chat_id,
        "text": msg,
        "parse_mode": "Markdown",
    }

    try:
        response = requests.post(
            url,
            json=payload,
            timeout=config.TELEGRAM_REQUEST_TIMEOUT,
        )

        response.raise_for_status()

        logger.debug(
            "Telegram message sent to %s.",
            chat_id,
        )

        return True

    except requests.exceptions.RequestException as exc:
        logger.error(
            "Telegram request failed: %s",
            exc,
        )
        return False

    except Exception:
        logger.exception(
            "Unexpected Telegram error."
        )
        return False


def send_to_personal_chat(message: str):
    """Send a message to the personal Telegram chat."""

    return send_telegram_message(
        message,
        config.TELEGRAM_PERSONAL_CHAT_ID,
        config.TELEGRAM_BOT_TOKEN,
    )


# ============================================================
# ENTRY MESSAGE
# ============================================================

def format_entry_message(
    symbol: str,
    side: str,
    entry_price: float,
    sl: float,
    tp: float,
    position_size_usd: float,
    regime: str,
    strategy_version: str,
    trade_id: str,
    entry_dt_utc: datetime,
    risk_pct: float,
) -> str:

    ts_message = format_timestamp_message(
        entry_dt_utc
    )

    risk_amount = (
        position_size_usd
        * abs(entry_price - sl)
        / entry_price
    )

    trade_line = format_trade_line(
        bot_version=config.BOT_VERSION,
        trade_id=trade_id,
        symbol=symbol,
        entry_dt_utc=entry_dt_utc,
        exit_dt_utc=None,
        side=side,
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
        profit_lock_triggered=False,
    )

    message = (
        f"🚀 *NEW TRADE ENTRY — {symbol}*\n\n"
        f"*Trade ID:* `{trade_id}`\n"
        f"*Side:* `{side}`\n"
        f"*Entry Price:* `{entry_price:.6g}`\n"
        f"*Stop Loss:* `{sl:.6g}`\n"
        f"*Take Profit:* `{tp:.6g}`\n"
        f"*Position Size:* `${position_size_usd:.2f}`\n"
        f"*Risk:* `{risk_pct * 100:.1f}%` "
        f"(${risk_amount:.2f})\n"
        f"*Market Regime:* `{regime}`\n"
        f"*Strategy:* `{strategy_version}`\n\n"
        f"ℹ️ *Details:* {ts_message}\n\n"
        f"--- Position Management ---\n"
        f"🛡 50% TP → Break-even\n"
        f"🔒 80% TP → Lock 25% TP distance"
    )

    return (
        f"{message}\n\n"
        f"`{trade_line}`"
    )


# ============================================================
# BREAK-EVEN MESSAGE
# ============================================================

def format_break_even_message(
    trade_id: str,
    symbol: str,
    entry_price: float,
    old_sl: float,
    new_sl: float,
    current_price: float,
    timestamp_utc: datetime,
) -> str:

    ts_message = format_timestamp_message(
        timestamp_utc
    )

    return (
        f"🛡 *BREAK-EVEN TRIGGERED — {symbol}*\n\n"
        f"*Trade ID:* `{trade_id}`\n"
        f"*Position Entry:* `{entry_price:.6g}`\n"
        f"*Old SL:* `{old_sl:.6g}`\n"
        f"*New SL:* `{new_sl:.6g}`\n"
        f"*Current Price:* `{current_price:.6g}`\n\n"
        f"ℹ️ *Details:* {ts_message}"
    )


# ============================================================
# PROFIT LOCK MESSAGE
# ============================================================

def format_profit_lock_message(
    trade_id: str,
    symbol: str,
    old_sl: float,
    new_sl: float,
    current_price: float,
    timestamp_utc: datetime,
) -> str:

    ts_message = format_timestamp_message(
        timestamp_utc
    )

    return (
        f"🔒 *PROFIT LOCK TRIGGERED — {symbol}*\n\n"
        f"*Trade ID:* `{trade_id}`\n"
        f"*Old SL:* `{old_sl:.6g}`\n"
        f"*New SL:* `{new_sl:.6g}`\n"
        f"*Current Price:* `{current_price:.6g}`\n\n"
        f"ℹ️ *Details:* {ts_message}"
    )


# ============================================================
# CLOSED TRADE MESSAGE
# ============================================================

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
    profit_lock_triggered: bool,
    position_size_usd: float,
) -> str:

    ts_message = format_timestamp_message(
        exit_dt_utc
    )

    status_icon = (
        "🎯"
        if pnl_usd >= 0
        else "🛑"
    )

    risk_amount = (
        position_size_usd
        * abs(entry - initial_sl)
        / entry
    )

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
        f"💰 *PnL:* `${pnl_usd:+.2f}` "
        f"(`{pnl_pct:+.2f}%`)\n"
        f"*Risk:* `{risk_pct * 100:.1f}%` "
        f"(${risk_amount:.2f})\n"
        f"*Regime:* `{regime}`\n"
        f"*Strategy:* `{strategy_version}`\n"
        f"*Break-even:* "
        f"{'YES' if break_even_triggered else 'NO'}\n"
        f"*Profit Lock:* "
        f"{'YES' if profit_lock_triggered else 'NO'}\n\n"
        f"ℹ️ *Details:* {ts_message}"
    )

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
        position_size_usd=position_size_usd,
        exit_price=exit_price,
        final_sl=final_sl,
        exit_reason=exit_reason,
        pnl_usd=pnl_usd,
        pnl_pct=pnl_pct,
        break_even_triggered=break_even_triggered,
        profit_lock_triggered=profit_lock_triggered,
    )

    return (
        f"{message}\n\n"
        f"`{trade_line}`"
    )


# ============================================================
# DAILY JOURNAL
# ============================================================

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
    completed_trades_data: List[Dict[str, Any]],
    open_positions_summary: List[Dict[str, Any]],
    market_snapshot: Dict[str, Dict[str, Any]],
) -> str:

    header_ts = format_timestamp_message(
        current_date_utc
    )

    msg = (
        f"📓 *DAILY TRADING JOURNAL*\n"
        f"Date: `{header_ts}`\n\n"
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
        f"Total PnL (All Time): `${total_pnl:+.2f}`\n"
    )

    # --------------------------------------------------------
    # CLOSED TRADES
    # --------------------------------------------------------

    msg += (
        "\n━━━━━━━━━━━━━━━━━━━━\n"
        "📋 *CLOSED TRADES (TODAY)*\n\n"
    )

    if not completed_trades_data:

        msg += "No trades were closed today.\n\n"

    else:

        for trade in completed_trades_data:

            pnl = float(
                trade.get("pnl_usd", 0.0)
            )

            icon = (
                "✅"
                if pnl >= 0
                else "❌"
            )

            msg += (
                f"{icon} *{trade.get('symbol')} — "
                f"{trade.get('type')}*\n"
                f"Entry: "
                f"`{trade.get('entry', 0.0):.6g}` | "
                f"Exit: "
                f"`{trade.get('exit', 0.0):.6g}`\n"
                f"PnL: `${pnl:+.2f}` "
                f"(`{trade.get('pnl_pct', 0.0):+.2f}%`)\n"
                f"Reason: "
                f"`{trade.get('exit_reason', 'N/A')}` | "
                f"Regime: "
                f"`{trade.get('regime', 'N/A')}`\n\n"
            )

    # --------------------------------------------------------
    # OPEN POSITIONS
    # --------------------------------------------------------

    msg += (
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📈 *OPEN POSITIONS "
        f"({len(open_positions_summary)}/"
        f"{config.MAX_CONCURRENT_POSITIONS})*\n\n"
    )

    if not open_positions_summary:

        msg += "No open positions.\n\n"

    else:

        for position in open_positions_summary:

            msg += (
                f"• *{position.get('symbol')}* "
                f"{position.get('type')} | "
                f"Entry: "
                f"`{position.get('entry_price', 0.0):.6g}` | "
                f"Current: "
                f"`{position.get('current_price', 0.0):.6g}`\n"
                f"  PnL: "
                f"`{position.get('current_pnl_pct', 0.0):+.2f}%` | "
                f"SL: "
                f"`{position.get('sl', 0.0):.6g}` | "
                f"TP: "
                f"`{position.get('tp', 0.0):.6g}`\n"
            )

        msg += "\n"

    # --------------------------------------------------------
    # MARKET SNAPSHOT
    # --------------------------------------------------------

    msg += (
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📊 *MARKET SNAPSHOT*\n\n"
    )

    if not market_snapshot:

        msg += "Market data not available.\n\n"

    else:

        for symbol, data in market_snapshot.items():

            msg += (
                f"• *{symbol}*: "
                f"Price `{data.get('price', 0.0):.6g}` | "
                f"RSI `{data.get('rsi', 0.0):.1f}` | "
                f"4H `{data.get('change_4h', 0.0):+.2f}%` | "
                f"1D `{data.get('change_1d', 0.0):+.2f}%` | "
                f"1W `{data.get('change_1w', 0.0):+.2f}%`\n"
            )

        msg += "\n"

    # --------------------------------------------------------
    # STRUCTURED TRADE LINES
    # --------------------------------------------------------

    if completed_trades_data:

        msg += (
            "--- ALL CLOSED TRADE LINES ---\n"
        )

        for trade in completed_trades_data:

            trade_line = trade.get(
                "trade_line"
            )

            if trade_line:
                msg += (
                    f"`{trade_line}`\n"
                )

    return msg


# ============================================================
# 4-HOUR REPORT
# ============================================================

def format_4h_report(
    current_time_utc: datetime,
    capital: float,
    daily_pnl: float,
    win_rate: float,
    num_trades: int,
    today_closed_trades_summary: List[Dict[str, Any]],
    open_positions_summary: List[Dict[str, Any]],
    market_overview: Dict[str, Dict[str, Any]],
) -> str:

    ts_message = format_timestamp_message(
        current_time_utc
    )

    msg = (
        f"🕒 *4-HOUR ACCOUNT & MARKET REPORT*\n"
        f"Time: `{ts_message}`\n\n"
        f"💵 *ACCOUNT STATUS*\n"
        f"Current Capital: `${capital:,.2f}`\n"
        f"Today's PnL: `${daily_pnl:+.2f}`\n"
        f"Today's Trades: `{num_trades}` | "
        f"Win Rate: `{win_rate:.1f}%`\n\n"
    )

    # --------------------------------------------------------
    # CLOSED TRADES
    # --------------------------------------------------------

    msg += (
        "📋 *TODAY'S RECENTLY CLOSED TRADES*\n\n"
    )

    if not today_closed_trades_summary:

        msg += "No closed trades today yet.\n\n"

    else:

        for trade in today_closed_trades_summary:

            pnl = float(
                trade.get("pnl_usd", 0.0)
            )

            icon = (
                "✅"
                if pnl >= 0
                else "❌"
            )

            msg += (
                f"{icon} "
                f"`{trade.get('symbol')}` "
                f"{trade.get('type')} | "
                f"PnL: `${pnl:+.2f}` | "
                f"{trade.get('exit_reason')}\n"
            )

        msg += "\n"

    # --------------------------------------------------------
    # OPEN POSITIONS
    # --------------------------------------------------------

    msg += (
        f"📈 *OPEN POSITIONS "
        f"({len(open_positions_summary)}/"
        f"{config.MAX_CONCURRENT_POSITIONS})*\n\n"
    )

    if not open_positions_summary:

        msg += "No open positions.\n\n"

    else:

        for position in open_positions_summary:

            msg += (
                f"• *{position.get('symbol')}* "
                f"{position.get('type')} | "
                f"Entry: "
                f"`{position.get('entry_price', 0.0):.6g}` | "
                f"Current: "
                f"`{position.get('current_price', 0.0):.6g}`\n"
                f"  PnL: "
                f"`{position.get('current_pnl_pct', 0.0):+.2f}%` | "
                f"SL: "
                f"`{position.get('sl', 0.0):.6g}` | "
                f"TP: "
                f"`{position.get('tp', 0.0):.6g}`\n"
            )

        msg += "\n"

    # --------------------------------------------------------
    # MARKET OVERVIEW
    # --------------------------------------------------------

    msg += "📊 *MARKET OVERVIEW*\n\n"

    if not market_overview:

        msg += "Market data not available.\n\n"

    else:

        for symbol, data in market_overview.items():

            msg += (
                f"• *{symbol}*: "
                f"Price `{data.get('price', 0.0):.6g}` | "
                f"RSI `{data.get('rsi', 0.0):.1f}` | "
                f"4H `{data.get('change_4h', 0.0):+.2f}%` | "
                f"1D `{data.get('change_1d', 0.0):+.2f}%` | "
                f"1W `{data.get('change_1w', 0.0):+.2f}%`\n"
            )

    return msg
