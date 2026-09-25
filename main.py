"""
Main Execution Module for SHERPA V5.3 Trading Bot.

Responsibilities:
- Fetch market data.
- Cache daily/hourly data.
- Calculate indicators.
- Detect market regime.
- Generate signals.
- Manage open positions.
- Open new paper trades.
- Publish Telegram notifications.
- Run scheduled reports.
- Keep Render service alive.

Paper trading only.
"""

import logging
import os
import time
import threading
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any, Optional

import config
import trading.engine as engine

from data.mexc import fetch_mexc_klines
from strategy.indicators import calculate_indicators
from strategy.strategy import (
    detect_market_regime,
    generate_signals,
)

from telegram.personal import (
    send_to_personal_chat,
    format_4h_report,
    format_daily_journal,
)

from telegram.channel import (
    publish_trading_signal,
    check_and_publish_session_alerts,
    publish_news_alerts,
)


logger = logging.getLogger(__name__)


# ============================================================
# CACHE
# ============================================================

market_cache: Dict[str, Dict[str, Any]] = {}

last_hourly_candle: Dict[str, Any] = {}
last_daily_refresh: Optional[datetime] = None

last_4h_report_key: Optional[str] = None
last_daily_report_date: Optional[str] = None

# Prevent processing the same 1H candle repeatedly.
last_entry_signal_candle: Dict[str, Any] = {}


# ============================================================
# RENDER KEEP-ALIVE
# ============================================================

class DummyServer(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(
            b"SHERPA V5.3 Bot is alive and running!"
        )

    def log_message(self, format, *args):
        pass


def run_keep_alive_server():
    port = int(
        os.getenv("PORT", "8080")
    )

    try:
        server = HTTPServer(
            ("0.0.0.0", port),
            DummyServer,
        )

        logger.info(
            f"Render keep-alive server running on port {port}"
        )

        server.serve_forever()

    except Exception as exc:
        logger.exception(
            f"Keep-alive server failed: {exc}"
        )


# ============================================================
# HELPERS
# ============================================================

def percentage_change(
    current: float,
    previous: float,
) -> float:

    if previous == 0:
        return 0.0

    return (
        (current - previous)
        / previous
        * 100.0
    )


def should_refresh_daily_data(
    now_utc: datetime,
) -> bool:

    global last_daily_refresh

    if last_daily_refresh is None:
        return True

    elapsed_seconds = (
        now_utc - last_daily_refresh
    ).total_seconds()

    # Daily regime data does not need refreshing every 5 minutes.
    return elapsed_seconds >= 4 * 60 * 60


# ============================================================
# FETCH + PROCESS ONE SYMBOL
# ============================================================

def fetch_and_process_symbol(
    symbol: str,
    refresh_daily: bool,
) -> Optional[Dict[str, Any]]:

    try:

        # ----------------------------------------------------
        # 1. Hourly data
        # ----------------------------------------------------

        df_1h = fetch_mexc_klines(
            symbol=symbol,
            interval="60m",
            limit=config.HOURLY_CANDLE_LIMIT,
        )

        if df_1h.empty:
            logger.warning(
                f"{symbol}: empty hourly data"
            )
            return None

        # ----------------------------------------------------
        # 2. Daily data
        # ----------------------------------------------------

        cached = market_cache.get(symbol)

        if (
            not refresh_daily
            and cached is not None
            and cached.get("df_1d") is not None
        ):
            df_1d = cached["df_1d"]

        else:

            df_1d = fetch_mexc_klines(
                symbol=symbol,
                interval="1d",
                limit=config.DAILY_CANDLE_LIMIT,
            )

            if df_1d.empty:
                logger.warning(
                    f"{symbol}: empty daily data"
                )
                return None

        # ----------------------------------------------------
        # 3. Validate history
        # ----------------------------------------------------

        required_hourly = 205
        required_daily = 55

        if len(df_1h) < required_hourly:

            logger.warning(
                f"{symbol}: insufficient hourly data "
                f"{len(df_1h)} < {required_hourly}"
            )

            return None

        if len(df_1d) < required_daily:

            logger.warning(
                f"{symbol}: insufficient daily data "
                f"{len(df_1d)} < {required_daily}"
            )

            return None

        # ----------------------------------------------------
        # 4. Indicators
        # ----------------------------------------------------

        df_1h_ind = calculate_indicators(
            df_1h
        )

        df_1d_ind = calculate_indicators(
            df_1d
        )

        if (
            df_1h_ind.empty
            or df_1d_ind.empty
        ):
            logger.warning(
                f"{symbol}: indicator calculation failed"
            )
            return None

        # ----------------------------------------------------
        # 5. Latest candles
        # ----------------------------------------------------

        latest_hourly = df_1h_ind.iloc[-1]
        latest_daily = df_1d_ind.iloc[-1]

        candle_time = latest_hourly["timestamp"]

        now_utc = datetime.now(timezone.utc)

        price = float(
            latest_hourly["close"]
        )

        atr = float(
            latest_hourly["atr"]
        )

        # ----------------------------------------------------
        # 6. Regime
        # ----------------------------------------------------

        regime = detect_market_regime(
            df_1d_ind,
            df_1h_ind,
        )

        # ----------------------------------------------------
        # 7. Market snapshot
        # ----------------------------------------------------

        market_data = {
            "symbol": symbol,

            "price": price,

            "high": float(
                latest_hourly["high"]
            ),

            "low": float(
                latest_hourly["low"]
            ),

            "rsi": float(
                latest_hourly["rsi"]
            ),

            "atr": atr,

            "regime": regime,

            "change_4h": percentage_change(
                price,
                float(df_1h_ind.iloc[-5]["close"]),
            ),

            "change_1d": percentage_change(
                price,
                float(df_1h_ind.iloc[-25]["close"]),
            ),

            "change_1w": percentage_change(
                price,
                float(df_1h_ind.iloc[-169]["close"]),
            ),

            "candle_time": candle_time,

            "timestamp_utc": now_utc,
        }

        # ----------------------------------------------------
        # 8. Signal
        # ----------------------------------------------------

        signal = generate_signals(
            df_1h_ind,
            regime,
            candle_time,
        )

        signal["strategy_version"] = (
            config.STRATEGY_VERSION
        )

        # ----------------------------------------------------
        # 9. Detect whether this is a new 1H candle
        # ----------------------------------------------------

        previous_candle = last_hourly_candle.get(
            symbol
        )

        is_new_hourly_candle = (
            previous_candle is None
            or candle_time > previous_candle
        )

        last_hourly_candle[symbol] = candle_time

        # ----------------------------------------------------
        # 10. Store in cache
        # ----------------------------------------------------

        market_cache[symbol] = {
            "df_1h": df_1h,
            "df_1d": df_1d,
            "df_1h_indicators": df_1h_ind,
            "df_1d_indicators": df_1d_ind,
            "market_data": market_data,
            "signal": signal,
            "is_new_hourly_candle": is_new_hourly_candle,
            "fetched_at": now_utc,
        }

        return market_data

    except Exception as exc:

        logger.exception(
            f"{symbol}: failed to process market data: {exc}"
        )

        return None


# ============================================================
# PROCESS NEW ENTRIES
# ============================================================

def process_new_entries(
    current_capital: float,
):
    """
    Process signals using already-fetched cached data.

    No additional market API calls are made here.
    """

    for symbol in config.SYMBOLS:

        if len(engine.open_positions) >= config.MAX_CONCURRENT_POSITIONS:
            break

        cached = market_cache.get(symbol)

        if not cached:
            continue

        # Already have a position.
        if symbol in engine.open_positions:
            continue

        # Only evaluate an entry once per new closed 1H candle.
        if not cached.get("is_new_hourly_candle"):
            continue

        market_data = cached["market_data"]
        signal = cached["signal"]

        candle_time = market_data["candle_time"]

        if (
            last_entry_signal_candle.get(symbol)
            == candle_time
        ):
            continue

        # Mark as processed regardless of HOLD.
        last_entry_signal_candle[symbol] = candle_time

        if signal.get("action") == "HOLD":
            continue

        opened, position = engine.process_symbol_state(
            symbol=symbol,
            signal=signal,
            market_data=market_data,
            current_capital=current_capital,
        )

        if not opened or position is None:
            continue

        # ----------------------------------------------------
        # Public channel
        # ----------------------------------------------------

        try:

            publish_trading_signal(
                symbol=symbol,
                side=signal["action"],
                entry_price=signal["entry_price"],
                stop_price=signal["stop_price"],
                tp_price=signal["take_profit_price"],
                risk_pct=signal["risk_pct"],
                regime=market_data["regime"],
                strategy_version=signal["strategy_version"],
                trade_id=position["trade_id"],
                entry_dt_utc=position["entry_candle_time"],
                position_size_usd=position["size_usd"],
            )

        except Exception as exc:

            logger.exception(
                f"{symbol}: failed to publish trading signal: {exc}"
            )


# ============================================================
# REPORTS
# ============================================================

def handle_scheduled_tasks(
    current_capital: float,
):

    global last_4h_report_key
    global last_daily_report_date

    now_utc = datetime.now(timezone.utc)

    # --------------------------------------------------------
    # 4-Hour report
    # --------------------------------------------------------

    report_key = now_utc.strftime(
        "%Y-%m-%d-%H"
    )

    if (
        now_utc.hour % 4 == 0
        and report_key != last_4h_report_key
    ):

        completed = engine.daily_completed_trades

        daily_pnl = sum(
            trade.get("pnl_usd", 0.0)
            for trade in completed
        )

        wins = sum(
            1
            for trade in completed
            if trade.get("pnl_usd", 0.0) >= 0
        )

        num_trades = len(completed)

        win_rate = (
            wins / num_trades * 100
            if num_trades
            else 0.0
        )

        report = format_4h_report(
            current_time_utc=now_utc,
            capital=current_capital,
            daily_pnl=daily_pnl,
            win_rate=win_rate,
            num_trades=num_trades,
            today_closed_trades_summary=list(
                completed
            ),
            open_positions_summary=(
                engine.get_current_open_positions_summary()
            ),
            market_overview={
                symbol: data["market_data"]
                for symbol, data
                in market_cache.items()
            },
        )

        send_to_personal_chat(report)

        last_4h_report_key = report_key

        logger.info(
            "4-hour report sent."
        )

    # --------------------------------------------------------
    # Daily journal
    # --------------------------------------------------------

    current_date = now_utc.strftime(
        "%Y-%m-%d"
    )

    if (
        now_utc.hour == 23
        and current_date != last_daily_report_date
    ):

        completed_trades, stats = (
            engine.get_daily_journal_data()
        )

        journal = format_daily_journal(
            current_date_utc=now_utc,
            starting_capital=config.INITIAL_CAPITAL,
            ending_capital=current_capital,
            daily_pnl=stats["pnl_usd"],
            daily_pnl_pct=(
                stats["pnl_usd"]
                / config.INITIAL_CAPITAL
                * 100
                if config.INITIAL_CAPITAL
                else 0.0
            ),
            num_trades=stats["trades"],
            winning_trades=stats["wins"],
            losing_trades=stats["losses"],
            win_rate=stats["win_rate"],
            total_pnl=0.0,
            completed_trades_data=completed_trades,
            open_positions_summary=(
                engine.get_current_open_positions_summary()
            ),
            market_snapshot={
                symbol: data["market_data"]
                for symbol, data
                in market_cache.items()
            },
        )

        send_to_personal_chat(journal)

        last_daily_report_date = current_date

        # IMPORTANT:
        # Do NOT reset open positions here.
        engine.daily_completed_trades.clear()

        logger.info(
            "Daily journal sent and daily trade history cleared."
        )

    # --------------------------------------------------------
    # Session alerts
    # --------------------------------------------------------

    try:
        check_and_publish_session_alerts(
            now_utc
        )
    except Exception as exc:
        logger.exception(
            f"Session alert error: {exc}"
        )

    # --------------------------------------------------------
    # News alerts
    # --------------------------------------------------------

    # News should NOT be fetched every 5 minutes.
    # The provider should internally rate-limit / cache it.
    #
    # If publish_news_alerts() is enabled, call it on a
    # separate lower-frequency schedule.
    #
    # try:
    #     publish_news_alerts()
    # except Exception as exc:
    #     logger.exception(f"News alert error: {exc}")


# ============================================================
# MAIN LOOP
# ============================================================

def main_trading_loop():

    global last_daily_refresh

    logger.info(
        "Starting SHERPA V5.3 main trading loop."
    )

    engine.initialize_trading_state()

    current_capital = (
        config.INITIAL_CAPITAL
    )

    # --------------------------------------------------------
    # Startup message
    # --------------------------------------------------------

    try:

        send_to_personal_chat(
            f"🚀 *SHERPA Bot V{config.BOT_VERSION} Started*\n\n"
            f"Mode: Paper Trading\n"
            f"Initial Capital: `${current_capital:,.2f}`\n"
            f"Symbols: {', '.join(config.SYMBOLS)}\n\n"
            f"📈 Strategy: {config.STRATEGY_VERSION}\n"
            f"🛡 Break-even @ "
            f"{config.BREAK_EVEN_TRIGGER_RATIO * 100:.0f}% TP distance\n"
            f"🔒 Profit Lock @ "
            f"{config.PROFIT_LOCK_TRIGGER_RATIO * 100:.0f}% TP distance\n"
            f"❌ No continuous trailing stop"
        )

    except Exception as exc:

        logger.exception(
            f"Startup Telegram message failed: {exc}"
        )

    # --------------------------------------------------------
    # Main loop
    # --------------------------------------------------------

    while True:

        cycle_start = time.monotonic()

        try:

            now_utc = datetime.now(
                timezone.utc
            )

            refresh_daily = (
                should_refresh_daily_data(
                    now_utc
                )
            )

            logger.info(
                f"Starting market cycle | "
                f"daily_refresh={refresh_daily}"
            )

            # ------------------------------------------------
            # 1. Fetch/process each symbol ONCE
            # ------------------------------------------------

            for symbol in config.SYMBOLS:

                fetch_and_process_symbol(
                    symbol=symbol,
                    refresh_daily=refresh_daily,
                )

                time.sleep(
                    config.SYMBOL_DELAY_SECONDS
                )

            if refresh_daily:
                last_daily_refresh = now_utc

            # ------------------------------------------------
            # 2. Manage existing positions
            # ------------------------------------------------

            current_market_data = {
                symbol: data["market_data"]
                for symbol, data
                in market_cache.items()
            }

            if current_market_data:

                closed_trades = (
                    engine.manage_open_positions(
                        current_market_data
                    )
                )

                if closed_trades:

                    closed_pnl = sum(
                        trade.get("pnl_usd", 0.0)
                        for trade
                        in closed_trades.values()
                    )

                    current_capital += closed_pnl

                    logger.info(
                        f"Closed trades this cycle: "
                        f"{len(closed_trades)} | "
                        f"PnL: ${closed_pnl:+.2f} | "
                        f"Capital: ${current_capital:.2f}"
                    )

            # ------------------------------------------------
            # 3. Process new entries
            # ------------------------------------------------

            process_new_entries(
                current_capital=current_capital
            )

            # ------------------------------------------------
            # 4. Scheduled tasks
            # ------------------------------------------------

            handle_scheduled_tasks(
                current_capital=current_capital
            )

            # ------------------------------------------------
            # 5. Cycle statistics
            # ------------------------------------------------

            elapsed = (
                time.monotonic()
                - cycle_start
            )

            logger.info(
                f"Cycle completed in "
                f"{elapsed:.2f}s | "
                f"Open positions: "
                f"{len(engine.open_positions)}/"
                f"{config.MAX_CONCURRENT_POSITIONS}"
            )

        except KeyboardInterrupt:

            logger.info(
                "SHERPA stopped manually."
            )
            break

        except Exception as exc:

            logger.exception(
                f"Unexpected main-loop error: {exc}"
            )

        # ----------------------------------------------------
        # Wait before next cycle
        # ----------------------------------------------------

        elapsed = (
            time.monotonic()
            - cycle_start
        )

        sleep_time = max(
            1.0,
            config.LOOP_DELAY_SECONDS
            - elapsed,
        )

        logger.debug(
            f"Sleeping {sleep_time:.1f}s..."
        )

        time.sleep(
            sleep_time
        )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    logging.basicConfig(
        level=config.LOGGING_LEVEL,
        format=config.LOGGING_FORMAT,
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    keep_alive_thread = threading.Thread(
        target=run_keep_alive_server,
        daemon=True,
    )

    keep_alive_thread.start()

    main_trading_loop()
