"""
Telegram channel messaging module for SHERPA V5.3.

The channel is used for:
- New trading signals
- Trade status updates
- Market pulse
- Session alerts
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, List

import requests

import config

from telegram.personal import (
    format_timestamp_message,
    format_trade_line,
)

logger = logging.getLogger(__name__)


# ============================================================
# CONFIG
# ============================================================

CHANNEL_CHAT_ID = config.TELEGRAM_CHANNEL_ID
BOT_TOKEN = config.TELEGRAM_BOT_TOKEN

SIGNAL_ONLY_ACTIVE_SESSIONS = False

ACTIVE_SESSIONS = [
    "London",
    "New York",
]


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram_message(
    msg: str,
    chat_id: str,
    bot_token: str,
) -> bool:

    if not bot_token or not chat_id:
        logger.warning(
            "Telegram channel token or chat ID is not configured."
        )
        return False

    url = (
        "https://api.telegram.org/"
        f"bot{bot_token}/sendMessage"
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
        return True

    except requests.exceptions.RequestException as exc:
        logger.error(
            f"Telegram channel request failed: {exc}"
        )
        return False

    except Exception as exc:
        logger.exception(
            f"Unexpected Telegram channel error: {exc}"
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

    icon = (
        "🟢"
        if side == "LONG"
        else "🔴"
    )

    message = (
        f"🚨 *NEW TRADING SIGNAL — {icon} {side}*\n\n"
        f"*Asset:* `{symbol}`\n"
        f"*Entry:* `{entry_price:.6g}`\n"
        f"*Stop Loss:* `{stop_price:.6g}`\n"
        f"*Take Profit:* `{tp_price:.6g}`\n"
        f"*Risk:* `{risk_pct * 100:.1f}%`\n"
        f"*Position Size:* `${position_size_usd:.2f}`\n"
        f"*Regime:* `{regime}`\n"
        f"*Strategy:* `{strategy_version}`\n\n"
        f"🕒 {timestamp}\n\n"
        f"`{trade_line}`"
    )

    send_telegram_message(
        message,
        CHANNEL_CHAT_ID,
        BOT_TOKEN,
    )


# ============================================================
# STATUS UPDATE
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

    timestamp = format_timestamp_message(
        timestamp_utc
    )

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
            tp=details.get("tp"),
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
            details.get("pnl_usd", 0.0)
        )

        message = (
            f"{'🎯' if pnl >= 0 else '🛑'} "
            f"*TRADE CLOSED — {symbol}*\n\n"
            f"*Trade ID:* `{trade_id}`\n"
            f"*Side:* `{details.get('side', 'N/A')}`\n"
            f"*Entry:* "
            f"`{details.get('entry', 0.0):.6g}`\n"
            f"*Exit:* "
            f"`{details.get('exit_price', 0.0):.6g}`\n"
            f"*Reason:* "
            f"`{details.get('exit_reason', 'N/A')}`\n"
            f"*PnL:* "
            f"`${pnl:+.2f}` "
            f"(`{details.get('pnl_pct', 0.0):+.2f}%`)\n"
            f"*Regime:* "
            f"`{details.get('regime', 'N/A')}`\n\n"
            f"🕒 {timestamp}\n\n"
            f"`{trade_line}`"
        )

    else:
        logger.warning(
            f"Unknown status type: {status_type}"
        )
        return

    send_telegram_message(
        message,
        CHANNEL_CHAT_ID,
        BOT_TOKEN,
    )


# ============================================================
# MARKET PULSE
# ============================================================

def publish_market_pulse(
    asset_data: Dict[str, Dict[str, Any]]
) -> None:

    if not asset_data:
        return

    timestamp = format_timestamp_message(
        datetime.now(timezone.utc)
    )

    regime_map = {
        "STRONG_BULL": "Strong Bull",
        "WEAK_BULL": "Weak Bull",
        "STRONG_BEAR": "Strong Bear",
        "WEAK_BEAR": "Weak Bear",
        "GOOD_RANGE": "Range",
        "DEAD_CHOP": "Dead Chop",
    }

    parts = [
        "📊 *MARKET PULSE*\n\n",
        f"🕒 {timestamp}\n\n",
    ]

    for symbol, data in asset_data.items():

        regime = data.get(
            "regime",
            "UNKNOWN",
        )

        regime_text = regime_map.get(
            regime,
            regime,
        )

        parts.append(
            f"*{symbol}*\n"
            f"• Price: `{data.get('price', 0.0):.6g}`\n"
            f"• RSI: `{data.get('rsi', 0.0):.1f}`\n"
            f"• 4H: `{data.get('change_4h', 0.0):+.2f}%`\n"
            f"• 1D: `{data.get('change_1d', 0.0):+.2f}%`\n"
            f"• 1W: `{data.get('change_1w', 0.0):+.2f}%`\n"
            f"• Regime: `{regime_text}`\n\n"
        )

    send_telegram_message(
        "".join(parts),
        CHANNEL_CHAT_ID,
        BOT_TOKEN,
    )


# ============================================================
# SESSION ALERT
# ============================================================

def publish_session_alert(
    session_name: str,
    start_time_utc: datetime,
    end_time_utc: datetime,
) -> None:

    message = (
        f"⏳ *TRADING SESSION — {session_name}*\n\n"
        f"*Start:* "
        f"`{format_timestamp_message(start_time_utc)}`\n"
        f"*End:* "
        f"`{format_timestamp_message(end_time_utc)}`"
    )

    send_telegram_message(
        message,
        CHANNEL_CHAT_ID,
        BOT_TOKEN,
    )


# ============================================================
# SESSION DETECTION
# ============================================================

SESSION_TIMES = {
    "Tokyo": (1, 8),
    "London": (8, 17),
    "New York": (13, 22),
}


def get_current_session(
    timestamp_utc: datetime | None = None,
) -> str:

    if timestamp_utc is None:
        timestamp_utc = datetime.now(
            timezone.utc
        )

    hour = timestamp_utc.hour

    for session_name, (
        start_hour,
        end_hour,
    ) in SESSION_TIMES.items():

        if start_hour <= hour < end_hour:
            return session_name

    return "Off-Session"


def is_current_session_active(
    active_sessions: List[str],
) -> bool:

    current_session = get_current_session()

    return current_session in active_sessions


# ============================================================
# SESSION ALERT SCHEDULER
# ============================================================

_last_session_alert_key = None


def check_and_publish_session_alerts(
    now_utc: datetime | None = None,
) -> None:

    global _last_session_alert_key

    if now_utc is None:
        now_utc = datetime.now(
            timezone.utc
        )

    for session_name, (
        start_hour,
        end_hour,
    ) in SESSION_TIMES.items():

        if (
            now_utc.hour == start_hour
            and now_utc.minute < 5
        ):

            alert_key = (
                session_name,
                now_utc.date(),
                "START",
            )

            if alert_key == _last_session_alert_key:
                continue

            start_time = now_utc.replace(
                hour=start_hour,
                minute=0,
                second=0,
                microsecond=0,
            )

            end_time = now_utc.replace(
                hour=end_hour,
                minute=0,
                second=0,
                microsecond=0,
            )

            publish_session_alert(
                session_name,
                start_time,
                end_time,
            )

            _last_session_alert_key = alert_key


# ============================================================
# NEWS
# ============================================================

def publish_news_alerts() -> None:
    """
    Placeholder for future news integration.

    Disabled for now to avoid unnecessary external API calls.
    """
    return
