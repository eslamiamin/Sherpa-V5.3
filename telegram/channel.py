"""
Telegram Channel Messaging Module.

Handles:
- Trading signals
- Trade status updates
- Market pulse
- Trading session alerts
- News alerts placeholder

Paper trading only.
"""

import logging
from datetime import datetime, timedelta, timezone, time
from typing import List, Dict, Any
from zoneinfo import ZoneInfo

import requests

import config

from telegram.personal import (
    format_timestamp_message,
    format_trade_line,
)


logger = logging.getLogger(__name__)


# ============================================================
# TELEGRAM CONFIG
# ============================================================

ADVISOR_BOT_TOKEN = config.TELEGRAM_BOT_TOKEN
CHANNEL_CHAT_ID = config.TELEGRAM_CHANNEL_CHAT_ID


# ============================================================
# SIGNAL SESSION FILTER
# ============================================================

# False = every valid strategy signal can be published.
# The strategy itself decides whether a trade should exist.
SIGNAL_ONLY_ACTIVE_SESSIONS = False

ACTIVE_SESSIONS = [
    "London",
    "New York",
]


# ============================================================
# TELEGRAM SENDER
# ============================================================

def send_telegram_message(
    msg: str,
    chat_id: str,
    bot_token: str,
) -> bool:

    if not bot_token or not chat_id:
        logger.warning(
            "Telegram Bot Token or Chat ID is not configured."
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
            timeout=getattr(
                config,
                "TELEGRAM_REQUEST_TIMEOUT",
                10,
            ),
        )

        response.raise_for_status()

        logger.debug(
            "Telegram message sent successfully."
        )

        return True

    except requests.exceptions.RequestException as exc:
        logger.error(
            f"Failed to send Telegram message: {exc}"
        )
        return False

    except Exception as exc:
        logger.exception(
            f"Unexpected Telegram error: {exc}"
        )
        return False


# ============================================================
# TRADING SIGNAL
# ============================================================

def publish_trading_signal(
    symbol: str,
    side: str,
    entry_price: float,
    stop_price: float,
    tp_price: float,
    risk_pct: float,
    regime: str,
    strategy_version: str,
    trade_id: str,
    entry_dt_utc: datetime,
    position_size_usd: float,
) -> None:

    if (
        SIGNAL_ONLY_ACTIVE_SESSIONS
        and not is_current_session_active(
            ACTIVE_SESSIONS
        )
    ):
        logger.debug(
            f"Signal suppressed outside active sessions: "
            f"{symbol} {side}"
        )
        return

    timestamp = format_timestamp_message(
        entry_dt_utc
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
        initial_sl=stop_price,
        entry_price=entry_price,
        tp=tp_price,
        position_size_usd=position_size_usd,
        exit_price=None,
        final_sl=None,
        exit_reason="OPEN",
        pnl_usd=None,
        pnl_pct=None,
        break_even_triggered=False,
        profit_lock_triggered=False,
    )

    side_upper = str(side).upper()

    if side_upper in {
        "LONG",
        "BUY_LONG",
        "BUY",
    }:
        direction_icon = "🟢"
    elif side_upper in {
        "SHORT",
        "SELL_SHORT",
        "SELL",
    }:
        direction_icon = "🔴"
    else:
        direction_icon = "⚪"

    message = (
        f"🚨 *NEW TRADING SIGNAL — "
        f"{direction_icon} {side}*\n\n"
        f"*Asset:* `{symbol}`\n"
        f"*Entry:* `{entry_price:.6g}`\n"
        f"*Stop Loss:* `{stop_price:.6g}`\n"
        f"*Take Profit:* `{tp_price:.6g}`\n"
        f"*Risk:* `{risk_pct * 100:.1f}%`\n"
        f"*Position Size:* "
        f"`${position_size_usd:.2f}`\n"
        f"*Regime:* `{regime}`\n"
        f"*Strategy:* `{strategy_version}`\n\n"
        f"🕒 {timestamp}\n\n"
        f"`{trade_line}`"
    )

    success = send_telegram_message(
        message,
        CHANNEL_CHAT_ID,
        ADVISOR_BOT_TOKEN,
    )

    if success:
        logger.info(
            f"Published trading signal: "
            f"{symbol} {side} | {trade_id}"
        )


# ============================================================
# TRADE STATUS UPDATE
# ============================================================

def publish_status_update(
    trade_id: str,
    symbol: str,
    status_type: str,
    details: Dict[str, Any],
) -> None:

    timestamp_utc = details.get(
        "timestamp_utc",
        datetime.now(timezone.utc),
    )

    if timestamp_utc.tzinfo is None:
        timestamp_utc = timestamp_utc.replace(
            tzinfo=timezone.utc
        )
    else:
        timestamp_utc = timestamp_utc.astimezone(
            timezone.utc
        )

    timestamp = format_timestamp_message(
        timestamp_utc
    )

    # --------------------------------------------------------
    # BREAK-EVEN
    # --------------------------------------------------------

    if status_type == "BREAK_EVEN":

        message = (
            f"🛡 *BREAK-EVEN — {symbol}*\n\n"
            f"*Trade ID:* `{trade_id}`\n"
            f"*Entry:* "
            f"`{details.get('entry_price', 0.0):.6g}`\n"
            f"*Old SL:* "
            f"`{details.get('old_sl', 0.0):.6g}`\n"
            f"*New SL:* "
            f"`{details.get('new_sl', 0.0):.6g}`\n"
            f"*Current Price:* "
            f"`{details.get('current_price', 0.0):.6g}`\n\n"
            f"🕒 {timestamp}"
        )

    # --------------------------------------------------------
    # PROFIT LOCK
    # --------------------------------------------------------

    elif status_type == "PROFIT_LOCK":

        message = (
            f"🔒 *PROFIT LOCK — {symbol}*\n\n"
            f"*Trade ID:* `{trade_id}`\n"
            f"*Old SL:* "
            f"`{details.get('old_sl', 0.0):.6g}`\n"
            f"*New SL:* "
            f"`{details.get('new_sl', 0.0):.6g}`\n"
            f"*Current Price:* "
            f"`{details.get('current_price', 0.0):.6g}`\n\n"
            f"🕒 {timestamp}"
        )

    # --------------------------------------------------------
    # TRADE CLOSED
    # --------------------------------------------------------

    elif status_type == "TRADE_CLOSED":

        trade_line = format_trade_line(
            bot_version=config.BOT_VERSION,
            trade_id=trade_id,
            symbol=symbol,
            entry_dt_utc=details.get(
                "entry_dt_utc"
            ),
            exit_dt_utc=details.get(
                "exit_dt_utc"
            ),
            side=details.get(
                "side",
                "UNKNOWN",
            ),
            strategy_version=details.get(
                "strategy_version",
                "UNKNOWN",
            ),
            regime=details.get(
                "regime",
                "UNKNOWN",
            ),
            risk_pct=details.get(
                "risk_pct",
                0.0,
            ),
            initial_sl=details.get(
                "initial_sl",
                0.0,
            ),
            entry_price=details.get(
                "entry",
                0.0,
            ),
            tp=details.get(
                "tp"
            ),
            position_size_usd=details.get(
                "size_usd",
                0.0,
            ),
            exit_price=details.get(
                "exit_price",
                0.0,
            ),
            final_sl=details.get(
                "final_sl"
            ),
            exit_reason=details.get(
                "exit_reason",
                "UNKNOWN",
            ),
            pnl_usd=details.get(
                "pnl_usd"
            ),
            pnl_pct=details.get(
                "pnl_pct"
            ),
            break_even_triggered=details.get(
                "break_even_triggered",
                False,
            ),
            profit_lock_triggered=details.get(
                "profit_lock_triggered",
                False,
            ),
        )

        pnl = float(
            details.get(
                "pnl_usd",
                0.0,
            )
        )

        icon = (
            "🎯"
            if pnl >= 0
            else "🛑"
        )

        message = (
            f"{icon} *TRADE CLOSED — {symbol}*\n\n"
            f"*Trade ID:* `{trade_id}`\n"
            f"*Side:* "
            f"`{details.get('side', 'N/A')}`\n"
            f"*Entry:* "
            f"`{details.get('entry', 0.0):.6g}`\n"
            f"*Exit:* "
            f"`{details.get('exit_price', 0.0):.6g}`\n"
            f"*Reason:* "
            f"`{details.get('exit_reason', 'N/A')}`\n"
            f"*PnL:* "
            f"`${pnl:+.2f}` "
            f"(`{float(details.get('pnl_pct', 0.0)):+.2f}%`)\n"
            f"*Regime:* "
            f"`{details.get('regime', 'N/A')}`\n\n"
            f"🕒 {timestamp}\n\n"
            f"`{trade_line}`"
        )

    else:
        logger.warning(
            f"Unknown Telegram status type: "
            f"{status_type}"
        )
        return

    send_telegram_message(
        message,
        CHANNEL_CHAT_ID,
        ADVISOR_BOT_TOKEN,
    )


# ============================================================
# MARKET PULSE
# ============================================================

def publish_market_pulse(
    asset_data: Dict[str, Dict[str, Any]]
) -> None:

    if not asset_data:
        logger.warning(
            "No asset data provided for market pulse."
        )
        return

    timestamp = format_timestamp_message(
        datetime.now(timezone.utc)
    )

    regime_map = {
        "STRONG_BULL": "Strong Bull",
        "WEAK_BULL": "Weak Bull",
        "STRONG_BEAR": "Strong Bear",
        "WEAK_BEAR": "Weak Bear",
        "GOOD_RANGE": "Good Range",
        "DEAD_CHOP": "Dead Chop",
    }

    message_parts = [
        "📊 *MARKET PULSE*\n\n",
        f"🕒 {timestamp}\n\n",
    ]

    for symbol, data in asset_data.items():

        regime = data.get(
            "regime",
            "UNKNOWN",
        )

        regime_description = regime_map.get(
            regime,
            regime,
        )

        message_parts.append(
            f"*{symbol}*\n"
            f"• Price: "
            f"`{data.get('price', 0.0):.6g}`\n"
            f"• RSI: "
            f"`{data.get('rsi', 0.0):.1f}`\n"
            f"• 4H: "
            f"`{data.get('change_4h', 0.0):+.2f}%`\n"
            f"• 1D: "
            f"`{data.get('change_1d', 0.0):+.2f}%`\n"
            f"• 1W: "
            f"`{data.get('change_1w', 0.0):+.2f}%`\n"
            f"• Regime: "
            f"`{regime_description}`\n\n"
        )

    send_telegram_message(
        "".join(message_parts),
        CHANNEL_CHAT_ID,
        ADVISOR_BOT_TOKEN,
    )


# ============================================================
# TRADING SESSIONS
# ============================================================

SESSION_CONFIG = {
    "Tokyo": {
        "timezone": ZoneInfo("Asia/Tokyo"),
        "start": time(9, 0),
        "end": time(15, 0),
    },
    "London": {
        "timezone": ZoneInfo("Europe/London"),
        "start": time(8, 0),
        "end": time(16, 30),
    },
    "New York": {
        "timezone": ZoneInfo("America/New_York"),
        "start": time(9, 30),
        "end": time(16, 0),
    },
}


last_session_alert_sent: Dict[
    tuple,
    datetime,
] = {}


def _get_session_window_utc(
    session_name: str,
    reference_utc: datetime,
) -> tuple[datetime, datetime]:

    session = SESSION_CONFIG[session_name]

    tz = session["timezone"]

    local_reference = reference_utc.astimezone(tz)

    local_start = datetime.combine(
        local_reference.date(),
        session["start"],
        tzinfo=tz,
    )

    local_end = datetime.combine(
        local_reference.date(),
        session["end"],
        tzinfo=tz,
    )

    start_utc = local_start.astimezone(
        timezone.utc
    )

    end_utc = local_end.astimezone(
        timezone.utc
    )

    if end_utc <= start_utc:
        end_utc += timedelta(days=1)

    return start_utc, end_utc


# ============================================================
# SESSION ALERT
# ============================================================

def publish_session_alert(
    session_name: str,
    start_time_utc: datetime,
    end_time_utc: datetime,
) -> None:

    message = (
        f"⏳ *TRADING SESSION — "
        f"{session_name}*\n\n"
        f"*Start:* "
        f"`{format_timestamp_message(start_time_utc)}`\n"
        f"*End:* "
        f"`{format_timestamp_message(end_time_utc)}`"
    )

    send_telegram_message(
        message,
        CHANNEL_CHAT_ID,
        ADVISOR_BOT_TOKEN,
    )


def check_and_publish_session_alerts(
    current_time_utc: datetime,
) -> None:

    if current_time_utc.tzinfo is None:
        current_time_utc = current_time_utc.replace(
            tzinfo=timezone.utc
        )
    else:
        current_time_utc = current_time_utc.astimezone(
            timezone.utc
        )

    for session_name in SESSION_CONFIG:

        session_start_utc, session_end_utc = (
            _get_session_window_utc(
                session_name,
                current_time_utc,
            )
        )

        # Alert once during the first 5 minutes
        # of the session.
        if (
            session_start_utc
            <= current_time_utc
            < session_start_utc + timedelta(minutes=5)
        ):

            alert_key = (
                session_name,
                session_start_utc.date(),
            )

            if alert_key in last_session_alert_sent:
                continue

            publish_session_alert(
                session_name,
                session_start_utc,
                session_end_utc,
            )

            last_session_alert_sent[
                alert_key
            ] = current_time_utc


# ============================================================
# SESSION CHECK
# ============================================================

def is_current_session_active(
    target_sessions: List[str],
) -> bool:

    now_utc = datetime.now(
        timezone.utc
    )

    for session_name in target_sessions:

        if session_name not in SESSION_CONFIG:
            continue

        session_start_utc, session_end_utc = (
            _get_session_window_utc(
                session_name,
                now_utc,
            )
        )

        if (
            session_start_utc
            <= now_utc
            < session_end_utc
        ):
            return True

    return False


# ============================================================
# NEWS
# ============================================================

def publish_news_alerts() -> None:
    """
    News integration is intentionally disabled.

    The current project does not have a real external news
    provider connected, so no fake news should be published.
    """

    if not getattr(
        config,
        "NEWS_ENABLED",
        False,
    ):
        return

    logger.warning(
        "NEWS_ENABLED=True but no real news provider "
        "is implemented."
    )
