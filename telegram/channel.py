# Sherpa-V5.3-main/telegram/channel.py
"""
Telegram channel module for broadcasting trading signals and status updates.
Paper trading only.
"""

import logging
from config import TELEGRAM_TOKEN, TELEGRAM_CHANNEL_ID
from telegram import Bot
from telegram.error import TelegramError

# Setup logging
logger = logging.getLogger(__name__)

# Initialize Bot
bot = Bot(token=TELEGRAM_TOKEN)

def send_message(text: str) -> None:
    """Send a message to the configured Telegram channel."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHANNEL_ID, text=text, parse_mode="HTML")
    except TelegramError as e:
        logger.error(f"Failed to send Telegram message: {e}")

def publish_trading_signal(symbol: str, action: str, price: float, trade_data: dict, reason: str = "") -> None:
    """Publish trade signals to the channel."""
    
    icon = "🟢" if action == "OPEN" else "🔴"
    
    if action == "OPEN":
        message = (
            f"{icon} <b>شروع موقعیت {trade_data.get('direction', 'N/A')}</b>\n"
            f"نماد: #{symbol}\n"
            f"قیمت ورود: {price:.4f}\n"
            f"حد ضرر اولیه: {trade_data.get('stop_loss', 0):.4f}\n"
            f"رژیم بازار: {trade_data.get('regime', 'N/A')}\n"
            f"سایز معامله: {trade_data.get('size', 0):.4f}"
        )
    elif action == "CLOSE":
        message = (
            f"{icon} <b>بستن موقعیت</b>\n"
            f"نماد: #{symbol}\n"
            f"قیمت خروج: {price:.4f}\n"
            f"دلیل: {reason}"
        )
    else:
        return

    send_message(message)

def check_and_publish_session_alerts() -> None:
    """
    Placeholder for future scheduled session alerts.
    Currently empty to avoid errors while in development.
    """
    pass

def publish_market_summary(summary_data: dict) -> None:
    """
    Publish a periodic market summary.
    """
    message = (
        "📊 <b>خلاصه وضعیت بازار</b>\n"
        f"ساعت: {summary_data.get('time', 'N/A')}\n"
        "--------------------------\n"
        f"وضعیت استراتژی‌ها فعال است."
    )
    send_message(message)
