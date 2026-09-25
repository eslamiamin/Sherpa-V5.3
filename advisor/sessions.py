"""
Trading Sessions Management with dynamic DST support.

Calculates active trading sessions (London, New York, Tokyo) by checking
local exchange times using IANA timezones (handling Daylight Saving Time natively).
"""

from datetime import datetime, timezone, time
from zoneinfo import ZoneInfo
from typing import Dict, List, Tuple, Optional


class SessionManager:
    """
    Tracks global market sessions and evaluates session filters.

    Uses exact local exchange timezones to account for Daylight Saving Time (DST).
    """

    def __init__(self):
        # Timezone definitions for accurate DST resolution
        self.tz_london = ZoneInfo("Europe/London")
        self.tz_new_york = ZoneInfo("America/New_York")
        self.tz_tokyo = ZoneInfo("Asia/Tokyo")

        # Standard trading hours in local times (open_time, close_time)
        self.session_hours = {
            "London": (time(8, 0), time(16, 30), self.tz_london),
            "New York": (time(9, 30), time(16, 0), self.tz_new_york),
            "Tokyo": (time(9, 0), time(15, 0), self.tz_tokyo),
        }

    def get_active_sessions(
        self,
        dt_utc: Optional[datetime] = None
    ) -> List[str]:
        """
        Determine which sessions are open at a given UTC time.

        Args:
            dt_utc:
                UTC time to evaluate.
                Defaults to current UTC time.

        Returns:
            List[str]:
                List of currently active session names.
        """

        if dt_utc is None:
            dt_utc = datetime.now(timezone.utc)

        elif dt_utc.tzinfo is None:
            # Treat naive datetime as UTC
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)

        # Exclude weekends
        # Saturday = 5, Sunday = 6
        if dt_utc.weekday() in (5, 6):
            return []

        active_sessions: List[str] = []

        for session_name, (open_t, close_t, tz) in self.session_hours.items():
            local_dt = dt_utc.astimezone(tz)
            local_time = local_dt.time()

            if open_t <= local_time <= close_t:
                active_sessions.append(session_name)

        return active_sessions

    def is_channel_entry_allowed(
        self,
        allowed_sessions: Tuple[str, ...] = ("London", "New York")
    ) -> bool:
        """
        Check whether channel publication is allowed based on active sessions.

        Args:
            allowed_sessions:
                Sessions that permit channel entry signals.

        Returns:
            bool:
                True if at least one allowed session is active.
        """

        active = self.get_active_sessions()

        return any(
            session in active
            for session in allowed_sessions
        )

    def get_session_status_summary(self) -> Dict[str, bool]:
        """
        Return a boolean mapping of all monitored sessions.

        Returns:
            Dict[str, bool]:
                Example:
                {
                    "London": True,
                    "New York": False,
                    "Tokyo": False
                }
        """

        active = self.get_active_sessions()

        return {
            name: name in active
            for name in self.session_hours
        }
