import logging
import aiohttp
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID

logger = logging.getLogger("Sherpa.TelegramChannel")

class ChannelBroadcaster:
    def __init__(self):
        self.token = TELEGRAM_BOT_TOKEN
        self.channel_id = TELEGRAM_CHANNEL_ID
        self.api_url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        
        if not self.token or not self.channel_id:
            logger.warning("Telegram channel credentials missing. Broadcasting disabled.")
            
    async def _send_message(self, text: str, parse_mode: str = "HTML"):
        if not self.token or not self.channel_id:
            return False
            
        payload = {
            "chat_id": self.channel_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.api_url, json=payload) as response:
                    if response.status != 200:
                        error_data = await response.text()
                        logger.error(f"Failed to send message to channel: {error_data}")
                        return False
                    return True
        except Exception as e:
            logger.error(f"Exception sending message to channel: {e}")
            return False

    async def send_signal_alert(self, symbol: str, signal_data: dict):
        """Sends a formatted trading signal to the public channel."""
        direction = signal_data.get('direction', 'UNKNOWN')
        entry = signal_data.get('entry_price', 0)
        tp = signal_data.get('take_profit', 0)
        sl = signal_data.get('stop_loss', 0)
        score = signal_data.get('confluence_score', 0)
        
        # Emoji formatting
        icon = "🟢" if direction == "LONG" else "🔴"
        
        message = (
            f"{icon} <b>شروع موقعیت {direction}</b>
"
            f"<b>جفت‌ارز:</b> #{symbol.replace('USDT', '')}
"
            f"━━━━━━━━━━━━━━━━━━
"
            f"🎯 <b>نقطه ورود:</b> {entry:.4f}
"
            f"✅ <b>حد سود (TP):</b> {tp:.4f}
"
            f"❌ <b>حد ضرر (SL):</b> {sl:.4f}
"
            f"━━━━━━━━━━━━━━━━━━
"
            f"📊 <b>امتیاز استراتژی:</b> {score}/100
"
            f"⚠️ <i>لطفاً مدیریت سرمایه را رعایت کنید.</i>"
        )
        
        await self._send_message(message)

    async def send_startup_message(self):
        """Notifies the channel when the bot comes online."""
        msg = "🤖 <b>ربات تحلیل‌گر Sherpa روشن شد.</b>\n\nامکانات:\n- تحلیل ۲۴ ساعته بازار\n- سیگنال‌های مبتنی بر استراتژی ترکیبی"
        await self._send_message(msg)
