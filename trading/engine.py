"""
SHERPA V5.3 - Trading Engine
Paper-trading engine with conservative intrabar handling.

Main fixes in this version:
- Existing SL/TP are checked before BE/Profit-Lock changes.
- A newly triggered BE/Profit-Lock becomes effective from the next candle.
- If TP and SL are both touched in one candle, SL wins (conservative).
- Total open notional is capped by current capital.
- Telegram failures do not break trade execution.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

import config
from trading.risk import calculate_position_size
from telegram.personal import (
    send_to_personal_chat,
    format_entry_message,
    format_break_even_message,
    format_profit_lock_message,
    format_trade_closed_message,
    format_trade_line,
)

logger = logging.getLogger(__name__)

# ============================================================
# GLOBAL STATE
# ============================================================

open_positions: Dict[str, Dict[str, Any]] = {}

# Last 1H candle actually processed for position management.
last_processed_candle_time: Dict[str, pd.Timestamp] = {}

# Closed trades since the beginning of the current journal period.
daily_completed_trades: List[Dict[str, Any]] = []


# ============================================================
# HELPERS
# ============================================================

def _normalize_side(action: str) -> Optional[str]:
    """Convert strategy action to LONG / SHORT."""
    if not action:
        return None

    action = str(action).upper().strip()

    mapping = {
        "BUY_LONG": "LONG",
        "LONG": "LONG",
        "SELL_SHORT": "SHORT",
        "SHORT": "SHORT",
    }

    return mapping.get(action)


def _is_valid_timestamp(value: Any) -> bool:
    return value is not None


def _calculate_pnl(
    position: Dict[str, Any],
    exit_price: float,
) -> Tuple[float, float]:
    """
    Calculate absolute and percentage PnL.

    Position size is USD notional.
    """
    entry = float(position["entry"])
    size_usd = float(position["size_usd"])
    side = position["type"]

    if entry <= 0:
        return 0.0, 0.0

    if side == "LONG":
        price_return = (exit_price - entry) / entry
    else:
        price_return = (entry - exit_price) / entry

    pnl_usd = size_usd * price_return
    pnl_pct = price_return * 100.0

    return pnl_usd, pnl_pct


def get_position_pnl(
    position: Dict[str, Any],
    current_price: float,
    current_time_utc: Optional[datetime] = None,
) -> Tuple[float, float, float]:
    """Return pnl_usd, pnl_pct and current stop loss."""
    pnl_usd, pnl_pct = _calculate_pnl(
        position,
        float(current_price),
    )

    return (
        pnl_usd,
        pnl_pct,
        float(position["sl"]),
    )


def _get_total_open_exposure() -> float:
    """Return total USD notional currently allocated to open positions."""
    total = 0.0

    for position in open_positions.values():
        try:
            total += float(position.get("size_usd", 0.0))
        except (TypeError, ValueError):
            logger.warning(
                "Invalid size_usd found while calculating exposure: %s",
                position,
            )

    return total


def _send_telegram_safely(message: Any, context: str) -> None:
    """
    Telegram is a notification layer.
    A Telegram/API failure must never stop trade management.
    """
    try:
        send_to_personal_chat(message)
    except Exception as exc:
        logger.exception(
            "%s Telegram error: %s",
            context,
            exc,
        )


# ============================================================
# TRADE COMPLETION
# ============================================================

def record_trade_completion(
    symbol: str,
    position: Dict[str, Any],
    exit_price: float,
    exit_reason: str,
    exit_candle_time: pd.Timestamp,
) -> Dict[str, Any]:
    """Build and store a completed trade record."""

    pnl_usd, pnl_pct = _calculate_pnl(
        position,
        exit_price,
    )

    trade_line = format_trade_line(
        bot_version=config.BOT_VERSION,
        trade_id=position["trade_id"],
        symbol=symbol,
        entry_dt_utc=position["entry_candle_time"],
        exit_dt_utc=exit_candle_time,
        side=position["type"],
        strategy_version=position["strategy_version"],
        regime=position["regime"],
        risk_pct=position["risk_pct"],
        initial_sl=position["initial_sl"],
        entry_price=position["entry"],
        tp=position["tp"],
        position_size_usd=position["size_usd"],
        exit_price=exit_price,
        final_sl=position["sl"],
        exit_reason=exit_reason,
        pnl_usd=pnl_usd,
        pnl_pct=pnl_pct,
        break_even_triggered=position["break_even_triggered"],
        profit_lock_triggered=position["profit_lock_triggered"],
    )

    completed_trade = {
        "trade_id": position["trade_id"],
        "symbol": symbol,
        "type": position["type"],
        "entry": position["entry"],
        "exit": exit_price,
        "tp": position["tp"],
        "initial_sl": position["initial_sl"],
        "final_sl": position["sl"],
        "size_usd": position["size_usd"],
        "risk_pct": position["risk_pct"],
        "pnl_usd": pnl_usd,
        "pnl_pct": pnl_pct,
        "exit_reason": exit_reason,
        "regime": position["regime"],
        "strategy_version": position["strategy_version"],
        "entry_candle_time": position["entry_candle_time"],
        "exit_candle_time": exit_candle_time,
        "break_even_triggered": position["break_even_triggered"],
        "profit_lock_triggered": position["profit_lock_triggered"],
        "trade_line": trade_line,
    }

    daily_completed_trades.append(completed_trade)

    logger.info(
        "Trade closed | %s | %s %s | Reason=%s | PnL=$%+.2f",
        position["trade_id"],
        symbol,
        position["type"],
        exit_reason,
        pnl_usd,
    )

    return completed_trade


# ============================================================
# OPEN POSITION MANAGEMENT
# ============================================================

def manage_open_positions(
    current_market_data: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """
    Manage all currently open positions.

    Intrabar policy
    ---------------
    The engine receives OHLC for a closed 1H candle, but OHLC does not
    tell us the order in which HIGH and LOW happened.

    Therefore:

    1. Existing SL/TP are evaluated first.
    2. If both existing SL and TP are touched, SL wins.
    3. Only if the position survives the candle do we trigger
       Break-Even / Profit-Lock.
    4. A newly changed SL is therefore NOT used to close the same candle.

    This prevents look-ahead caused by:
        HIGH -> move SL -> LOW -> close at the new SL
    when the actual intrabar order could have been:
        LOW -> HIGH
    """

    closed_trades_info: Dict[str, Dict[str, Any]] = {}

    for symbol, position in list(open_positions.items()):

        market_info = current_market_data.get(symbol)

        if not market_info:
            logger.warning(
                "%s: no market data for open position.",
                symbol,
            )
            continue

        candle_time = market_info.get("candle_time")

        if candle_time is None:
            logger.warning(
                "%s: candle_time missing.",
                symbol,
            )
            continue

        previous_processed = last_processed_candle_time.get(symbol)

        if (
            previous_processed is not None
            and candle_time <= previous_processed
        ):
            continue

        try:
            current_price = float(market_info["price"])
            high_price = float(market_info["high"])
            low_price = float(market_info["low"])
        except (KeyError, TypeError, ValueError) as exc:
            logger.exception(
                "%s: invalid market data: %s",
                symbol,
                exc,
            )
            last_processed_candle_time[symbol] = candle_time
            continue

        current_time_utc = (
            market_info.get("timestamp_utc")
            or datetime.now(timezone.utc)
        )

        entry = float(position["entry"])
        tp = float(position["tp"])
        side = position["type"]
        current_sl = float(position["sl"])

        tp_distance = abs(tp - entry)

        if tp_distance <= 0:
            logger.error(
                "%s: invalid TP distance.",
                symbol,
            )
            last_processed_candle_time[symbol] = candle_time
            continue

        # Mark the candle as processed before any exit/trigger action.
        last_processed_candle_time[symbol] = candle_time

        # --------------------------------------------------------
        # STEP 1: EXISTING SL / TP
        # --------------------------------------------------------

        if side == "LONG":
            hit_tp = high_price >= tp
            hit_sl = low_price <= current_sl
        else:
            hit_tp = low_price <= tp
            hit_sl = high_price >= current_sl

        exit_reason: Optional[str] = None
        exit_price: Optional[float] = None

        # Conservative rule for ambiguous OHLC candles.
        if hit_tp and hit_sl:
            exit_reason = "SL (Simultaneous TP/SL)"
            exit_price = current_sl

        elif hit_sl:
            if position.get("profit_lock_triggered", False):
                exit_reason = "PROFIT LOCK SL"
            elif position.get("break_even_triggered", False):
                exit_reason = "BREAK-EVEN SL"
            else:
                exit_reason = "SL"

            exit_price = current_sl

        elif hit_tp:
            exit_reason = "TP"
            exit_price = tp

        # --------------------------------------------------------
        # STEP 2: BE / PROFIT LOCK
        #
        # Only reached when the current candle did NOT close
        # the position using the existing SL/TP.
        # --------------------------------------------------------

        if exit_reason is None:

            if side == "LONG":
                favorable_move = max(
                    0.0,
                    high_price - entry,
                )
            else:
                favorable_move = max(
                    0.0,
                    entry - low_price,
                )

            progress_ratio = favorable_move / tp_distance

            # ----------------------------------------------------
            # BREAK-EVEN
            # ----------------------------------------------------

            if (
                not position.get("break_even_triggered", False)
                and progress_ratio
                >= config.BREAK_EVEN_TRIGGER_RATIO
            ):

                old_sl = float(position["sl"])
                new_sl = entry

                # Never move a stop backwards.
                if side == "LONG":
                    new_sl = max(old_sl, new_sl)
                else:
                    new_sl = min(old_sl, new_sl)

                position["sl"] = new_sl
                position["break_even_triggered"] = True

                _send_telegram_safely(
                    format_break_even_message(
                        trade_id=position["trade_id"],
                        symbol=symbol,
                        entry_price=entry,
                        old_sl=old_sl,
                        new_sl=new_sl,
                        current_price=current_price,
                        timestamp_utc=current_time_utc,
                    ),
                    f"{symbol}: break-even",
                )

                logger.info(
                    "BREAK-EVEN | %s | %s | SL=%0.8g",
                    symbol,
                    position["trade_id"],
                    new_sl,
                )

            # ----------------------------------------------------
            # PROFIT LOCK
            # ----------------------------------------------------

            if (
                not position.get("profit_lock_triggered", False)
                and progress_ratio
                >= config.PROFIT_LOCK_TRIGGER_RATIO
            ):

                if side == "LONG":
                    locked_sl_price = (
                        entry
                        + tp_distance
                        * config.PROFIT_LOCK_SL_RATIO
                    )

                    new_sl = max(
                        float(position["sl"]),
                        locked_sl_price,
                    )

                else:
                    locked_sl_price = (
                        entry
                        - tp_distance
                        * config.PROFIT_LOCK_SL_RATIO
                    )

                    new_sl = min(
                        float(position["sl"]),
                        locked_sl_price,
                    )

                old_sl = float(position["sl"])
                position["sl"] = new_sl
                position["profit_lock_triggered"] = True

                _send_telegram_safely(
                    format_profit_lock_message(
                        trade_id=position["trade_id"],
                        symbol=symbol,
                        old_sl=old_sl,
                        new_sl=new_sl,
                        current_price=current_price,
                        timestamp_utc=current_time_utc,
                    ),
                    f"{symbol}: profit-lock",
                )

                logger.info(
                    "PROFIT LOCK | %s | %s | SL=%0.8g",
                    symbol,
                    position["trade_id"],
                    new_sl,
                )

        # --------------------------------------------------------
        # STEP 3: CLOSE POSITION
        # --------------------------------------------------------

        if (
            exit_reason is not None
            and exit_price is not None
        ):

            completed_trade = record_trade_completion(
                symbol=symbol,
                position=position,
                exit_price=exit_price,
                exit_reason=exit_reason,
                exit_candle_time=candle_time,
            )

            _send_telegram_safely(
                format_trade_closed_message(
                    symbol=symbol,
                    position_type=side,
                    entry=position["entry"],
                    exit_price=exit_price,
                    initial_sl=position["initial_sl"],
                    final_sl=position["sl"],
                    tp=position["tp"],
                    position_size_usd=position["size_usd"],
                    exit_reason=exit_reason,
                    pnl_usd=completed_trade["pnl_usd"],
                    pnl_pct=completed_trade["pnl_pct"],
                    trade_id=position["trade_id"],
                    risk_pct=position["risk_pct"],
                    regime=position["regime"],
                    strategy_version=position["strategy_version"],
                    entry_dt_utc=position["entry_candle_time"],
                    exit_dt_utc=candle_time,
                    break_even_triggered=position[
                        "break_even_triggered"
                    ],
                    profit_lock_triggered=position[
                        "profit_lock_triggered"
                    ],
                ),
                f"{symbol}: trade close",
            )

            closed_trades_info[symbol] = completed_trade

            del open_positions[symbol]

            logger.info(
                "POSITION CLOSED | %s | %s | %s",
                symbol,
                position["trade_id"],
                exit_reason,
            )

    return closed_trades_info


# ============================================================
# NEW ENTRY
# ============================================================

def process_new_entry_signal(
    symbol: str,
    signal: Dict[str, Any],
    market_data: Dict[str, Any],
    current_capital: float,
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Validate and open a new paper position."""

    action = signal.get("action")

    if action in (
        None,
        "",
        "HOLD",
        "ERROR",
    ):
        return False, None

    # --------------------------------------------------------
    # Normalize side
    # --------------------------------------------------------

    side = _normalize_side(action)

    if side is None:
        logger.error(
            "%s: unknown strategy action: %s",
            symbol,
            action,
        )
        return False, None

    # --------------------------------------------------------
    # One position per symbol
    # --------------------------------------------------------

    if symbol in open_positions:
        logger.debug(
            "%s: position already exists.",
            symbol,
        )
        return False, None

    # --------------------------------------------------------
    # Maximum concurrent positions
    # --------------------------------------------------------

    if len(open_positions) >= config.MAX_CONCURRENT_POSITIONS:
        logger.info(
            "Max concurrent positions reached. Cannot open %s.",
            symbol,
        )
        return False, None

    # --------------------------------------------------------
    # Validate signal
    # --------------------------------------------------------

    required_keys = [
        "entry_price",
        "stop_price",
        "take_profit_price",
        "risk_pct",
        "strategy_version",
    ]

    missing = [
        key
        for key in required_keys
        if signal.get(key) is None
    ]

    if missing:
        logger.error(
            "%s: incomplete signal. Missing=%s",
            symbol,
            missing,
        )
        return False, None

    try:
        entry_price = float(signal["entry_price"])
        stop_price = float(signal["stop_price"])
        tp_price = float(signal["take_profit_price"])
        risk_pct = float(signal["risk_pct"])
    except (TypeError, ValueError) as exc:
        logger.error(
            "%s: invalid signal numeric value: %s",
            symbol,
            exc,
        )
        return False, None

    # --------------------------------------------------------
    # Validate capital
    # --------------------------------------------------------

    try:
        current_capital = float(current_capital)
    except (TypeError, ValueError):
        logger.error(
            "%s: invalid current capital: %s",
            symbol,
            current_capital,
        )
        return False, None

    if current_capital <= 0:
        logger.error(
            "%s: current capital must be > 0.",
            symbol,
        )
        return False, None

    # --------------------------------------------------------
    # Validate price geometry
    # --------------------------------------------------------

    if (
        entry_price <= 0
        or stop_price <= 0
        or tp_price <= 0
    ):
        logger.error(
            "%s: invalid prices | entry=%s, SL=%s, TP=%s",
            symbol,
            entry_price,
            stop_price,
            tp_price,
        )
        return False, None

    if side == "LONG":

        if not (
            stop_price < entry_price < tp_price
        ):
            logger.error(
                "%s: invalid LONG geometry | SL=%s, Entry=%s, TP=%s",
                symbol,
                stop_price,
                entry_price,
                tp_price,
            )
            return False, None

    else:

        if not (
            tp_price < entry_price < stop_price
        ):
            logger.error(
                "%s: invalid SHORT geometry | TP=%s, Entry=%s, SL=%s",
                symbol,
                tp_price,
                entry_price,
                stop_price,
            )
            return False, None

    # --------------------------------------------------------
    # Position sizing based on risk
    # --------------------------------------------------------

    position_size_usd = calculate_position_size(
        capital=current_capital,
        risk_pct=risk_pct,
        entry_price=entry_price,
        stop_price=stop_price,
    )

    try:
        position_size_usd = float(position_size_usd)
    except (TypeError, ValueError):
        logger.error(
            "%s: invalid position size returned by risk module: %s",
            symbol,
            position_size_usd,
        )
        return False, None

    if position_size_usd <= 0:
        logger.warning(
            "%s: position size <= 0. Trade rejected.",
            symbol,
        )
        return False, None

    # --------------------------------------------------------
    # TOTAL EXPOSURE GUARD
    #
    # Existing configuration allows up to:
    # MAX_CONCURRENT_POSITIONS × MAX_POSITION_NOTIONAL_PCT
    #
    # With 5 × 25%, this could reach 125%.
    #
    # We cap the sum of all open notionals at current capital.
    # --------------------------------------------------------

    current_exposure = _get_total_open_exposure()

    max_total_exposure = current_capital

    remaining_exposure = max(
        0.0,
        max_total_exposure - current_exposure,
    )

    if remaining_exposure <= 0:
        logger.info(
            "%s: total exposure limit reached. "
            "Current=$%.2f / Max=$%.2f. Trade rejected.",
            symbol,
            current_exposure,
            max_total_exposure,
        )
        return False, None

    if position_size_usd > remaining_exposure:
        logger.info(
            "%s: position size reduced by total exposure limit | "
            "Requested=$%.2f | Remaining=$%.2f",
            symbol,
            position_size_usd,
            remaining_exposure,
        )

        position_size_usd = remaining_exposure

    if position_size_usd <= 0:
        logger.info(
            "%s: no remaining exposure available. Trade rejected.",
            symbol,
        )
        return False, None

    # --------------------------------------------------------
    # Trade ID
    # --------------------------------------------------------

    candle_time = market_data.get("candle_time")

    if candle_time is None:
        logger.error(
            "%s: candle_time missing.",
            symbol,
        )
        return False, None

    try:
        timestamp_str = candle_time.strftime(
            "%Y%m%d-%H%M%S"
        )
    except AttributeError:
        logger.error(
            "%s: invalid candle_time: %s",
            symbol,
            candle_time,
        )
        return False, None

    trade_id = (
        f"{config.BOT_VERSION}-"
        f"{symbol}-"
        f"{timestamp_str}-"
        f"{len(open_positions):04d}"
    )

    # --------------------------------------------------------
    # Market regime
    # --------------------------------------------------------

    regime = market_data.get("regime", "UNKNOWN")

    # --------------------------------------------------------
    # Create position
    # --------------------------------------------------------

    new_position = {
        "type": side,
        "entry": entry_price,
        "tp": tp_price,
        "sl": stop_price,
        "initial_sl": stop_price,
        "size_usd": position_size_usd,
        "risk_pct": risk_pct,
        "regime": regime,
        "strategy_version": signal["strategy_version"],
        "entry_candle_time": candle_time,
        "trade_id": trade_id,
        "break_even_triggered": False,
        "profit_lock_triggered": False,
    }

    open_positions[symbol] = new_position

    # --------------------------------------------------------
    # Do not manage the entry candle again.
    # --------------------------------------------------------

    last_processed_candle_time[symbol] = candle_time

    logger.info(
        "POSITION OPENED | %s | %s %s | Entry=%0.8g | "
        "SL=%0.8g | TP=%0.8g | Size=$%.2f | "
        "Exposure=$%.2f/$%.2f",
        trade_id,
        symbol,
        side,
        entry_price,
        stop_price,
        tp_price,
        position_size_usd,
        current_exposure + position_size_usd,
        max_total_exposure,
    )

    # --------------------------------------------------------
    # Telegram entry notification
    # --------------------------------------------------------

    _send_telegram_safely(
        format_entry_message(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            sl=stop_price,
            tp=tp_price,
            position_size_usd=position_size_usd,
            regime=regime,
            strategy_version=signal["strategy_version"],
            trade_id=trade_id,
            entry_dt_utc=candle_time,
            risk_pct=risk_pct,
        ),
        f"{symbol}: entry",
    )

    return True, new_position


# ============================================================
# SYMBOL STATE
# ============================================================

def process_symbol_state(
    symbol: str,
    signal: Dict[str, Any],
    market_data: Dict[str, Any],
    current_capital: float,
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Main entry point for processing a symbol.

    Existing positions are managed globally by
    manage_open_positions(). This function only attempts new entries.
    """

    candle_time = market_data.get("candle_time")

    if candle_time is None:
        logger.warning(
            "%s: missing candle time.",
            symbol,
        )
        return False, None

    if symbol in open_positions:
        return False, None

    if signal.get("action") in (
        None,
        "",
        "HOLD",
        "ERROR",
    ):
        return False, None

    return process_new_entry_signal(
        symbol=symbol,
        signal=signal,
        market_data=market_data,
        current_capital=current_capital,
    )


# ============================================================
# STATE INITIALIZATION
# ============================================================

def initialize_trading_state():
    """
    Initialize engine state.

    .clear() is used rather than reassignment so references held
    by other modules remain valid.
    """

    open_positions.clear()
    last_processed_candle_time.clear()
    daily_completed_trades.clear()

    logger.info(
        "Trading engine state initialized."
    )


# ============================================================
# OPEN POSITION SUMMARY
# ============================================================

def get_current_open_positions_summary(
    current_market_data: Optional[
        Dict[str, Dict[str, Any]]
    ] = None,
) -> List[Dict[str, Any]]:
    """
    Return current open-position information.

    If market data is supplied, calculate live PnL.
    Otherwise use entry price as fallback.
    """

    summary: List[Dict[str, Any]] = []

    current_market_data = current_market_data or {}

    for symbol, position in open_positions.items():

        market_info = current_market_data.get(symbol)

        if market_info:

            try:
                current_price = float(
                    market_info["price"]
                )

                pnl_usd, pnl_pct, current_sl = (
                    get_position_pnl(
                        position,
                        current_price,
                        market_info.get("timestamp_utc"),
                    )
                )

            except (KeyError, TypeError, ValueError) as exc:

                logger.warning(
                    "%s: invalid market data for summary: %s",
                    symbol,
                    exc,
                )

                current_price = float(position["entry"])
                pnl_usd = 0.0
                pnl_pct = 0.0
                current_sl = float(position["sl"])

        else:

            current_price = float(position["entry"])
            pnl_usd = 0.0
            pnl_pct = 0.0
            current_sl = float(position["sl"])

        summary.append(
            {
                "symbol": symbol,
                "type": position["type"],
                "entry_price": position["entry"],
                "current_price": current_price,
                "sl": current_sl,
                "tp": position["tp"],
                "size_usd": position["size_usd"],
                "current_pnl_usd": pnl_usd,
                "current_pnl_pct": pnl_pct,
                "trade_id": position["trade_id"],
                "risk_pct": position["risk_pct"],
                "regime": position["regime"],
                "break_even_triggered": position[
                    "break_even_triggered"
                ],
                "profit_lock_triggered": position[
                    "profit_lock_triggered"
                ],
            }
        )

    return summary


# ============================================================
# DAILY JOURNAL DATA
# ============================================================

def get_daily_journal_data() -> Tuple[
    List[Dict[str, Any]],
    Dict[str, Any],
]:
    """Return completed trades and daily statistics."""

    num_trades = len(daily_completed_trades)

    wins = sum(
        1
        for trade in daily_completed_trades
        if trade.get("pnl_usd", 0.0) > 0
    )

    losses = sum(
        1
        for trade in daily_completed_trades
        if trade.get("pnl_usd", 0.0) < 0
    )

    breakeven = (
        num_trades
        - wins
        - losses
    )

    pnl_total = sum(
        trade.get("pnl_usd", 0.0)
        for trade in daily_completed_trades
    )

    win_rate = (
        wins / num_trades * 100
        if num_trades > 0
        else 0.0
    )

    stats = {
        "trades": num_trades,
        "wins": wins,
        "losses": losses,
        "breakeven": breakeven,
        "pnl_usd": pnl_total,
        "win_rate": win_rate,
    }

    return (
        list(daily_completed_trades),
        stats,
    )


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    logging.basicConfig(
        level=config.LOGGING_LEVEL,
        format=config.LOGGING_FORMAT,
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    print(
        "SHERPA Trading Engine loaded successfully."
    )

    initialize_trading_state()

    print(
        f"Open positions: {open_positions}"
    )

    print(
        f"Daily trades: {daily_completed_trades}"
    )
