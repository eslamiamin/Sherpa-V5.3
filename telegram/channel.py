"""
Telegram Channel Messaging Module.

This module handles sending curated messages to a private Telegram channel.
It is responsible for:
- Publishing trading signals derived from the paper trading engine.
- Broadcasting market analysis and alerts (Market Pulse, Session Alerts, News Alerts).
- Ensuring messages adhere to the specified format (timestamps, Persian language, clarity).
- Implementing filters, such as activating signal publication only during specific trading sessions.

This module acts as the "Advisor Bot" interface.
"""

import logging
import requests
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any

import config
from telegram.personal import format_timestamp_message # Reuse formatting helpers

logger = logging.getLogger(__name__)

# --- Channel Specific Configuration ---
# Load from config if available, otherwise use defaults or raise error
ADVISOR_BOT_TOKEN = config.TELEGRAM_BOT_TOKEN # Assumed to be the same token for simplicity, or load separately
CHANNEL_CHAT_ID = config.TELEGRAM_CHANNEL_CHAT_ID

# Session Filter Configuration
SIGNAL_ONLY_ACTIVE_SESSIONS = True # Only publish entry signals during London/New York sessions if True
ACTIVE_SESSIONS = ["London", "New York"] # Sessions during which entry signals are published

# --- Helper Functions (shared with personal.py, can be refactored to a common module later) ---

def send_telegram_message(msg: str, chat_id: str, bot_token: str):
    """
    Sends a formatted message to a specified Telegram chat ID using the bot token.
    (Copied from telegram.personal for standalone use, ideally refactor to common util)
    """
    if not bot_token or not chat_id:
        logger.warning("Telegram Bot Token or Chat ID is not configured. Cannot send message to channel.")
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
        logger.debug(f"Message sent to Telegram channel {chat_id}.")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send Telegram message to channel {chat_id}: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred while sending Telegram message to channel: {e}")

# --- Core Channel Functions ---

def publish_trading_signal(
    symbol: str,
    side: str, # "LONG" or "SHORT"
    entry_price: float,
    stop_price: float,
    tp_price: float,
    risk_pct: float,
    regime: str,
    strategy_version: str,
    trade_id: str,
    entry_dt_utc: datetime,
    position_size_usd: float # Include size for context if desired
) -> None:
    """
    Publishes a trading signal to the Telegram channel.

    Applies session filtering if enabled. Formats the message in Persian with
    timestamps and structured trade line.
    """
    if not SIGNAL_ONLY_ACTIVE_SESSIONS or is_current_session_active(ACTIVE_SESSIONS):
        
        # Format message components
        ts_message = format_timestamp_message(entry_dt_utc)
        
        # Construct the trade line (similar to personal chat, but might omit some details for brevity if needed)
        # Using a simplified trade line format for channel signals if desired, or the full one.
        # For now, let's use the full format for consistency.
        trade_line = format_trade_line( # Reuse from personal.py
            bot_version=config.BOT_VERSION,
            trade_id=trade_id,
            symbol=symbol,
            entry_dt_utc=entry_dt_utc,
            exit_dt_utc=None,
            side=side,
            strategy_version=strategy_version,
            regime=regime,
            risk_pct=risk_pct,
            initial_sl=stop_price, # Initial SL provided
            entry_price=entry_price,
            tp=tp_price,
            position_size_usd=position_size_usd,
            exit_price=None,
            final_sl=None,
            exit_reason="OPEN",
            pnl_usd=None,
            pnl_pct=None,
            break_even_triggered=False,
            profit_lock_triggered=False
        )

        # Persian message for the channel
        signal_direction_icon = "🟢" if side == "LONG" else "🔴"
        message = (
            f"🚨 *جدید: سیگنال معاملاتی {signal_direction_icon} {side}*\n\n"
            f"*دارایی:* `{symbol}`\n"
            f"*قیمت ورود:* `{entry_price:.6g}`\n"
            f"*حد ضرر (SL):* `{stop_price:.6g}`\n"
            f"*هدف سود (TP):* `{tp_price:.6g}`\n"
            f"*ریسک:* `{risk_pct*100:.1f}%`\n"
            f"*رژیم:* `{regime}`\n"
            f"*استراتژی:* `{strategy_version}`\n\n"
            f"ℹ️ *زمان:* {ts_message}\n\n"
            f"**نکات مهم:**\n"
            f"• این سیگنال بر اساس تصمیمات موتور معاملاتی ما صادر شده است.\n"
            f"• مدیریت پوزیشن (تغییر حد ضرر) در پیام‌های بعدی اطلاع‌رسانی خواهد شد.\n\n"
            f"`{trade_line}`" # Include the structured trade line
        )
        
        send_telegram_message(message, CHANNEL_CHAT_ID, ADVISOR_BOT_TOKEN)
        logger.info(f"Published trading signal for {symbol} ({side}) to channel.")
        
    else:
        logger.debug(f"Signal for {symbol} ({side}) not published: Outside active trading sessions ({', '.join(ACTIVE_SESSIONS)}).")


def publish_status_update(
    trade_id: str,
    symbol: str,
    status_type: str, # e.g., "BREAK_EVEN", "PROFIT_LOCK", "TRADE_CLOSED"
    details: Dict[str, Any] # Contains relevant data like new_sl, exit_price, pnl, etc.
) -> None:
    """
    Publishes status updates for an ongoing trade (Break-even, Profit Lock) or a closed trade.
    Session filtering is NOT applied here, as these are updates to existing trades.
    """
    
    # Format common fields
    timestamp_utc = details.get("timestamp_utc", datetime.now(timezone.utc))
    ts_message = format_timestamp_message(timestamp_utc)
    
    message = f"*{status_type.replace('_', ' ').title()}* Update for {symbol} (Trade ID: `{trade_id}`)\n\n"
    trade_line = None # Placeholder for the structured trade line

    if status_type == "BREAK_EVEN":
        message += (
            f"*نوع:* Break-even\n"
            f"*ورود:* `{details.get('entry_price', 'N/A'):.6g}`\n"
            f"*حد ضرر قبلی:* `{details.get('old_sl', 'N/A'):.6g}`\n"
            f"*حد ضرر جدید:* `{details.get('new_sl', 'N/A'):.6g}`\n\n"
            f"ℹ️ *زمان:* {ts_message}"
        )
    elif status_type == "PROFIT_LOCK":
        message += (
            f"*نوع:* Profit Lock\n"
            f"*حد ضرر قبلی:* `{details.get('old_sl', 'N/A'):.6g}`\n"
            f"*حد ضرر جدید:* `{details.get('new_sl', 'N/A'):.6g}`\n\n"
            f"ℹ️ *زمان:* {ts_message}"
        )
    elif status_type == "TRADE_CLOSED":
        # Extract details for closed trade and format the trade line
        trade_line = format_trade_line( # Reuse from personal.py
            bot_version=config.BOT_VERSION,
            trade_id=trade_id,
            symbol=symbol,
            entry_dt_utc=details.get("entry_dt_utc"),
            exit_dt_utc=details.get("exit_dt_utc"),
            side=details.get("side", "UNKNOWN"),
            strategy_version=details.get("strategy_version", "UNKNOWN"),
            regime=details.get("regime", "UNKNOWN"),
            risk_pct=details.get("risk_pct", 0.0),
            initial_sl=details.get("initial_sl", 0.0),
            entry_price=details.get("entry", 0.0),
            tp=details.get("tp"),
            position_size_usd=details.get("size_usd", 0.0),
            exit_price=details.get("exit_price", 0.0),
            final_sl=details.get("final_sl"),
            exit_reason=details.get("exit_reason", "UNKNOWN"),
            pnl_usd=details.get("pnl_usd"),
            pnl_pct=details.get("pnl_pct"),
            break_even_triggered=details.get("break_even_triggered", False),
            profit_lock_triggered=details.get("profit_lock_triggered", False)
        )
        
        message = (
            f"📊 *معامله بسته شد:* {symbol} ({details.get('side', 'N/A')})\n\n"
            f"*شناسه معامله:* `{trade_id}`\n"
            f"*قیمت ورود:* `{details.get('entry', 'N/A'):.6g}`\n"
            f"*قیمت خروج:* `{details.get('exit_price', 'N/A'):.6g}`\n"
            f"*دلیل خروج:* `{details.get('exit_reason', 'N/A')}`\n"
            f"*سود/زیان:* `${details.get('pnl_usd', 0.0):+.2f}` (`{details.get('pnl_pct', 0.0):+.2f}%`)\n"
            f"*رژیم:* `{details.get('regime', 'N/A')}`\n\n"
            f"ℹ️ *زمان خروج:* {ts_message}\n\n"
            f"`{trade_line}`" # Append trade line
        )
        
    if message:
        send_telegram_message(message, CHANNEL_CHAT_ID, ADVISOR_BOT_TOKEN)
        logger.info(f"Published status update '{status_type}' for {symbol} ({trade_id}) to channel.")


def publish_market_pulse(asset_data: Dict[str, Dict[str, Any]]) -> None:
    """
    Publishes a market pulse report, summarizing key metrics for specified assets.
    This is intended for regular updates, e.g., every 3 hours.
    """
    if not asset_data:
        logger.warning("No asset data provided for market pulse report.")
        return

    message_parts = ["📊 *نبض بازار*\n\n"]
    
    # Add a timestamp for the report
    report_time_utc = datetime.now(timezone.utc)
    ts_message = format_timestamp_message(report_time_utc)
    message_parts.append(f"زمان به‌روزرسانی: {ts_message}\n\n")

    for symbol, data in asset_data.items():
        regime = data.get("regime", "نامشخص")
        
        # Map regime codes to Persian descriptions
        regime_persian_map = {
            "STRONG_BULLISH": "صعودی قوی",
            "WEAK_BULLISH": "صعودی ضعیف",
            "STRONG_BEARISH": "نزولی قوی",
            "WEAK_BEARISH": "نزولی ضعیف",
            "GOOD_RANGING": "خنثی/رنج",
            "DEAD_CHOP": "بدون روند/مرده"
        }
        regime_desc = regime_persian_map.get(regime, regime)

        # Add a brief textual explanation for the regime
        regime_explanation = ""
        if regime == "STRONG_BULLISH":
            regime_explanation = "روند صعودی قوی در تایم‌فریم‌های بالا و پایین."
        elif regime == "WEAK_BULLISH":
            regime_explanation = "روند تایم‌فریم بالاتر صعودی است اما قدرت روند فعلی متوسط است.\nشرایط بیشتر با معاملات روندی ملایم سازگار است."
        elif regime == "STRONG_BEARISH":
            regime_explanation = "روند نزولی قوی در تایم‌فریم‌های بالا و پایین."
        elif regime == "WEAK_BEARISH":
            regime_explanation = "روند تایم‌فریم بالاتر نزولی است اما قدرت روند فعلی متوسط است.\nشرایط بیشتر با معاملات روندی ملایم سازگار است."
        elif regime == "GOOD_RANGING":
            regime_explanation = "بازار در یک محدوده نوسان می‌کند و پتانسیل بازگشت قیمت به میانگین وجود دارد."
        elif regime == "DEAD_CHOP":
            regime_explanation = "نوسانات کم و عدم وجود روند مشخص؛ ریسک معاملات روند بالا است."
            
        message_parts.append(
            f"*{symbol}*\n"
            f"• قیمت فعلی: `{data.get('price', 0.0):.6g}`\n"
            f"• RSI: `{data.get('rsi', 0.0):.1f}`\n"
            f"• تغییرات اخیر:\n"
            f"  4H: `{data.get('change_4h', 0.0):+.2f}%` | "
            f"1D: `{data.get('change_1d', 0.0):+.2f}%` | "
            f"1W: `{data.get('change_1w', 0.0):+.2f}%`\n"
            f"*رژیم بازار:* `{regime_desc}`\n"
            f"{regime_explanation}\n\n"
        )

    send_telegram_message("".join(message_parts), CHANNEL_CHAT_ID, ADVISOR_BOT_TOKEN)
    logger.info("Published market pulse report to channel.")


def publish_session_alert(session_name: str, start_time_utc: datetime, end_time_utc: datetime) -> None:
    """
    Publishes an alert for the start or end of a major trading session.
    """
    ts_message = format_timestamp_message(start_time_utc)
    
    message = (
        f"⏳ *هشدار جلسه معاملاتی*\n\n"
        f"*جلسه:* {session_name}\n"
        f"*زمان شروع:* {ts_message}\n"
        f"*زمان پایان:* {format_timestamp_message(end_time_utc)}\n\n"
        f"در طول این جلسه، نوسانات بازار ممکن است افزایش یابد."
    )
    
    send_telegram_message(message, CHANNEL_CHAT_ID, ADVISOR_BOT_TOKEN)
    logger.info(f"Published session alert for {session_name} to channel.")

# --- Session Management (Basic Implementation) ---
# NOTE: This is a simplified implementation. A robust solution would handle DST changes correctly
# and potentially use a more sophisticated scheduling library.
# For now, assumes fixed times and relies on ZoneInfo for Tehran offset.

# Example session times (UTC) - These need to be precise and account for DST.
# Using fixed times for now, assuming they are valid for the current period.
# A more advanced approach would use libraries like `pytz` or `zoneinfo` with historical DST data.
SESSION_TIMES = {
    "Tokyo": {"start_utc": (1, 0), "end_utc": (8, 0)}, # Approx. 01:00-08:00 UTC
    "London": {"start_utc": (8, 0), "end_utc": (17, 0)}, # Approx. 08:00-17:00 UTC
    "New York": {"start_utc": (13, 0), "end_utc": (22, 0)}, # Approx. 13:00-22:00 UTC
}

# Keep track of alerts sent to avoid spamming
last_session_alert_sent: Dict[str, datetime] = {}

def check_and_publish_session_alerts(current_time_utc: datetime):
    """
    Checks if any trading sessions are starting or ending and publishes alerts.
    """
    for session_name, times in SESSION_TIMES.items():
        start_hour, start_minute = times["start_utc"]
        end_hour, end_minute = times["end_utc"]
        
        # Calculate start and end datetimes for the current day
        session_start_utc = datetime(
            current_time_utc.year, current_time_utc.month, current_time_utc.day,
            start_hour, start_minute, tzinfo=config.TIMEZONE_UTC
        )
        session_end_utc = datetime(
            current_time_utc.year, current_time_utc.month, current_time_utc.day,
            end_hour, end_minute, tzinfo=config.TIMEZONE_UTC
        )
        
        # Handle sessions that span across midnight (e.g., end time is earlier than start time)
        if session_end_utc < session_start_utc:
            session_end_utc += timedelta(days=1) # End time is on the next day

        # Check if the session is currently active
        is_active = session_start_utc <= current_time_utc < session_end_utc
        
        # Check if it's time to send an alert (e.g., session just started)
        # Simple check: send alert if session just started in the last hour and hasn't been alerted yet.
        alert_window_start = session_start_utc - timedelta(hours=1)
        alert_window_end = session_start_utc + timedelta(minutes=30) # Alert within 30 mins of start

        last_alert_time = last_session_alert_sent.get(session_name)

        if alert_window_start <= current_time_utc < alert_window_end:
            if last_alert_time is None or (current_time_utc - last_alert_time).total_seconds() > 3600: # Alert only once per hour
                 publish_session_alert(session_name, session_start_utc, session_end_utc)
                 last_session_alert_sent[session_name] = current_time_utc


def is_current_session_active(target_sessions: List[str]) -> bool:
    """
    Checks if the current UTC time falls within any of the specified active trading sessions.
    """
    now_utc = datetime.now(timezone.utc)
    
    for session_name in target_sessions:
        if session_name in SESSION_TIMES:
            times = SESSION_TIMES[session_name]
            start_hour, start_minute = times["start_utc"]
            end_hour, end_minute = times["end_utc"]
            
            session_start_utc = datetime(
                now_utc.year, now_utc.month, now_utc.day, start_hour, start_minute, tzinfo=config.TIMEZONE_UTC
            )
            session_end_utc = datetime(
                now_utc.year, now_utc.month, now_utc.day, end_hour, end_minute, tzinfo=config.TIMEZONE_UTC
            )
            
            # Adjust end time if session spans midnight
            if session_end_utc < session_start_utc:
                session_end_utc += timedelta(days=1)

            # Check if current time is within the session
            if session_start_utc <= now_utc < session_end_utc:
                return True
                
    return False

# --- News Alerts (Placeholder) ---
# This module would need integration with a news API (e.g., ForexFactory, Investing.com)
# to fetch relevant economic events.

class NewsProviderPlaceholder:
    """A placeholder for a real News Provider API."""
    def get_upcoming_events(self, lookahead_hours: int = 2) -> List[Dict[str, Any]]:
        """
        Simulates fetching upcoming news events.
        In a real implementation, this would call an external API.
        """
        logger.debug("Using placeholder for news provider. No real news fetched.")
        # Example placeholder data
        now_utc = datetime.now(timezone.utc)
        return [
            {
                "event": "US CPI (Consumer Price Index)",
                "country": "USA",
                "importance": "High",
                "utc_time": now_utc + timedelta(hours=1),
                "relevant_assets": ["BTCUSDT", "ETHUSDT", "PAXGUSDT", "OILUSDT"], # Example assets
                "time_remaining_str": "حدود ۱ ساعت دیگر"
            },
            {
                "event": "EUR GDP (Gross Domestic Product)",
                "country": "Eurozone",
                "importance": "Medium",
                "utc_time": now_utc + timedelta(hours=3),
                "relevant_assets": ["EURUSD", "XAUUSD"], # Example assets
                "time_remaining_str": "حدود ۳ ساعت دیگر"
            }
        ]

news_provider = NewsProviderPlaceholder() # Instantiate the placeholder

def publish_news_alerts():
    """
    Fetches upcoming news events and publishes alerts to the channel.
    """
    try:
        upcoming_events = news_provider.get_upcoming_events()
        
        if not upcoming_events:
            logger.debug("No upcoming news events found.")
            return

        message_parts = ["🔔 *هشدار اخبار مهم*\n\n"]
        
        for event in upcoming_events:
            event_time_utc = event["utc_time"]
            ts_message = format_timestamp_message(event_time_utc)
            
            message_parts.append(
                f"*{event['event']}* ({event['country']} - {event['importance']})\n"
                f"• زمان انتشار: {ts_message}\n"
                f"• دارایی‌های مرتبط: `{', '.join(event['relevant_assets'])}`\n"
                f"• زمان باقی‌مانده: {event['time_remaining_str']}\n"
                f"• **هشدار:** احتمال افزایش نوسانات در زمان انتشار خبر وجود دارد.\n\n"
            )
            
        send_telegram_message("".join(message_parts), CHANNEL_CHAT_ID, ADVISOR_BOT_TOKEN)
        logger.info(f"Published news alerts for {len(upcoming_events)} upcoming events.")

    except Exception as e:
        logger.error(f"Failed to fetch or publish news alerts: {e}")


# --- Example Usage ---
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format=config.LOGGING_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")

    print("--- Testing Telegram Channel Messaging ---")

    # Mock data
    mock_trade_id = "SHERPA_V5.3-BTCUSDT-20231027-000001"
    mock_symbol = "BTCUSDT"
    mock_side = "LONG"
    mock_entry = 30000.0
    mock_sl = 29500.0
    mock_tp = 31000.0
    mock_risk_pct = 0.01
    mock_regime = "WEAK_BULLISH"
    mock_strategy_version = "EMA50-CROSS-V1"
    mock_entry_dt_utc = datetime.now(timezone.utc)
    mock_entry_pos_size = 3000.0

    # Mock status updates
    mock_be_details = {
        "entry_price": mock_entry, "old_sl": mock_sl, "new_sl": mock_entry,
        "timestamp_utc": mock_entry_dt_utc + timedelta(hours=1)
    }
    mock_pl_details = {
        "old_sl": mock_entry, "new_sl": mock_entry + (mock_tp - mock_entry) * 0.25,
        "timestamp_utc": mock_entry_dt_utc + timedelta(hours=2)
    }
    mock_closed_details = {
        "trade_id": mock_trade_id, "symbol": mock_symbol, "side": mock_side, "entry": mock_entry,
        "exit_price": 31000.0, "exit_reason": "TP", "pnl_usd": 100.0, "pnl_pct": 0.33,
        "initial_sl": mock_sl, "final_sl": mock_entry, # Final SL after BE/PL
        "tp": mock_tp, "risk_pct": mock_risk_pct, "regime": mock_regime,
        "strategy_version": mock_strategy_version, "entry_dt_utc": mock_entry_dt_utc,
        "exit_dt_utc": mock_entry_dt_utc + timedelta(hours=3),
        "break_even_triggered": True, "profit_lock_triggered": False, "size_usd": mock_entry_pos_size
    }

    # Test publishing signal
    print("\n--- Publishing Trading Signal ---")
    publish_trading_signal(
        symbol=mock_symbol, side=mock_side, entry_price=mock_entry, stop_price=mock_sl,
        tp_price=mock_tp, risk_pct=mock_risk_pct, regime=mock_regime,
        strategy_version=mock_strategy_version, trade_id=mock_trade_id,
        entry_dt_utc=mock_entry_dt_utc, position_size_usd=mock_entry_pos_size
    )

    # Test publishing status updates
    print("\n--- Publishing Status Updates ---")
    publish_status_update(mock_trade_id, mock_symbol, "BREAK_EVEN", mock_be_details)
    publish_status_update(mock_trade_id, mock_symbol, "PROFIT_LOCK", mock_pl_details)
    publish_status_update(mock_trade_id, mock_symbol, "TRADE_CLOSED", mock_closed_details)

    # Test Market Pulse
    print("\n--- Publishing Market Pulse ---")
    mock_asset_data = {
        "BTCUSDT": {"price": 30500.0, "rsi": 62.5, "change_4h": 1.5, "change_1d": 3.0, "change_1w": 5.0, "regime": "WEAK_BULLISH"},
        "ETHUSDT": {"price": 1790.0, "rsi": 45.0, "change_4h": -0.8, "change_1d": -1.0, "change_1w": -2.0, "regime": "GOOD_RANGING"},
        "PAXGUSDT": {"price": 2000.0, "rsi": 55.0, "change_4h": 0.2, "change_1d": 0.5, "change_1w": 1.0, "regime": "WEAK_BULLISH"} # Example for Gold
    }
    publish_market_pulse(mock_asset_data)

    # Test Session Alerts (requires mocking current time to trigger alerts)
    # For example, simulate current time being just before London session start
    # mock_current_time_before_london = datetime(2023, 10, 27, 7, 50, 0, tzinfo=timezone.utc)
    # check_and_publish_session_alerts(mock_current_time_before_london)
    
    # Test News Alerts
    print("\n--- Publishing News Alerts (Placeholder) ---")
    publish_news_alerts()
