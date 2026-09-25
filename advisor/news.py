"""
Economic News Ingestion Module.

Fetches real-world scheduled high-impact macroeconomic events (CPI, FOMC, NFP, etc.)
from genuine financial calendar feeds. Zero synthetic or fake data.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
import requests

logger = logging.getLogger(__name__)


class NewsAdvisor:
    """
    Ingests and filters real macroeconomic news calendar data.
    Gracefully handles network drops or provider outages without halting the bot.
    """

    # Public, reliable JSON weekly calendar endpoint
    CALENDAR_FEED_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

    def __init__(self, request_timeout: int = 10):
        self.request_timeout = request_timeout

    def fetch_upcoming_high_impact_events(self, lookahead_hours: int = 4) -> List[Dict[str, Any]]:
        """
        Retrieve genuine high-impact economic news scheduled within the lookahead window.

        Args:
            lookahead_hours (int): Time horizon in hours to look forward.

        Returns:
            List[Dict[str, Any]]: Cleaned and validated upcoming news items.
        """
        now_utc = datetime.now(timezone.utc)
        horizon_utc = now_utc + timedelta(hours=lookahead_hours)
        events_found: List[Dict[str, Any]] = []

        try:
            response = requests.get(
                self.CALENDAR_FEED_URL,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=self.request_timeout
            )
            response.raise_for_status()
            data = response.json()

            if not isinstance(data, list):
                logger.warning("Unexpected response structure from economic calendar feed.")
                return []

            for item in data:
                # Filter solely for USD / high impact events (most critical for crypto/risk assets)
                impact = str(item.get("impact", "")).strip().capitalize()
                currency = str(item.get("country", "")).strip().upper()

                if impact != "High" or currency != "USD":
                    continue

                raw_date_str = item.get("date")
                if not raw_date_str:
                    continue

                # Parse event datetime (ForexFactory format: 2026-03-24T08:30:00-04:00)
                try:
                    event_dt = datetime.fromisoformat(raw_date_str)
                    event_dt_utc = event_dt.astimezone(timezone.utc)
                except ValueError:
                    continue

                if now_utc <= event_dt_utc <= horizon_utc:
                    mins_remaining = int((event_dt_utc - now_utc).total_seconds() / 60)
                    events_found.append({
                        "title": item.get("title", "High-Impact Economic Release"),
                        "country": currency,
                        "impact": impact,
                        "event_time_utc": event_dt_utc,
                        "minutes_remaining": mins_remaining,
                        "forecast": item.get("forecast", "N/A"),
                        "previous": item.get("previous", "N/A"),
                    })

        except requests.exceptions.RequestException as exc:
            logger.warning(f"Could not retrieve economic news: {exc}. Continuing without news alerts.")
            return []
        except Exception as exc:
            logger.error(f"Unexpected error in news ingestion: {exc}")
            return []

        return events_found
