"""
Market Pulse Aggregator and Channel Formatter.

Generates high-level technical and regime snapshots for the Advisor Channel
at scheduled intervals (typically every 3 hours).
"""

from datetime import datetime, timezone
from typing import Dict, Any
from zoneinfo import ZoneInfo

TIMEZONE_TEHRAN = ZoneInfo("Asia/Tehran")


class MarketPulseAdvisor:
    """
    Transforms multi-symbol technical stats into comprehensive Persian broadcast messages.
    """

    REGIME_TRANSLATIONS = {
        "STRONG_BULL": "صعودی پرقدرت (Strong Bull)",
        "WEAK_BULL": "صعودی ملایم (Weak Bull)",
        "STRONG_BEAR": "نزولی پرقدرت (Strong Bear)",
        "WEAK_BEAR": "نزولی ملایم (Weak Bear)",
        "GOOD_RANGE": "رنج مناسب معامله (Tradeable Range)",
        "DEAD_CHOP": "خنثی فرسایشی (Dead Chop)",
    }

    @staticmethod
    def format_pulse_message(market_data_map: Dict[str, Dict[str, Any]]) -> str:
        """
        Format a multi-asset overview into a clear Persian Telegram broadcast.

        Args:
            market_data_map (Dict): Map of symbol to its indicator snapshot dictionary.

        Returns:
            str: Ready-to-send Markdown formatted message.
        """
        now_utc = datetime.now(timezone.utc)
        now_tehran = now_utc.astimezone(TIMEZONE_TEHRAN)

        utc_str = now_utc.strftime("%Y-%m-%d %H:%M:%S")
        tehran_str = now_tehran.strftime("%Y-%m-%d %H:%M:%S")

        lines = [
            "📡 *نبض بازار و وضعیت رژیم نمادها (Market Pulse)*",
            f"🕒 `UTC: {utc_str}`",
            f"🇮🇷 `Tehran: {tehran_str}`",
            "━━━━━━━━━━━━━━━━━━━━",
            ""
        ]

        for symbol, data in market_data_map.items():
            price = data.get("price", 0.0)
            rsi = data.get("rsi", 0.0)
            adx = data.get("adx", 0.0)
            chg_4h = data.get("change_4h", 0.0)
            chg_24h = data.get("change_1d", 0.0)
            regime = data.get("regime", "DEAD_CHOP")
            regime_fa = MarketPulseAdvisor.REGIME_TRANSLATIONS.get(regime, regime)

            trend_icon = "🟢" if "BULL" in regime else ("🔴" if "BEAR" in regime else "⚪️")

            lines.append(f"{trend_icon} *{symbol}* — `${price:,.2f}`")
            lines.append(f"• رژیم: `{regime_fa}`")
            lines.append(f"• شاخص‌ها: RSI(14): `{rsi:.1f}` | ADX(14): `{adx:.1f}`")
            lines.append(f"• بازدهی: 4H: `{chg_4h:+.2f}%` | 24H: `{chg_24h:+.2f}%`")
            lines.append("")

        lines.append("⚠️ _تحلیل‌های ارائه‌شده صرفاً محاسبات الگوریتمی موتور SHERPA است._")
        return "\n".join(lines)
