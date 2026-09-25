"""
SHERPA V5.3 - Trading Engine

Responsible for:
- Opening paper-trading positions
- Managing open positions
- Break-even logic
- Profit-lock logic
- TP / SL detection
- PnL calculation
- Trade journaling
- Preventing duplicate candle processing

Paper trading only.
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

# {
#     "BTCUSDT": {
#         "type": "LONG" | "SHORT",
#         "entry": float,
#         "tp": float,
#         "sl": float,
#         "initial_sl": float,
#         "size_usd": float,
#         "risk_pct": float,
#         "regime": str,
#         "strategy_version": str,
#         "entry_candle_time": pd.Timestamp,
#         "trade_id": str,
#         "break_even_triggered": bool,
#         "profit_lock_triggered": bool,
#     }
# }

open_positions: Dict[str, Dict[str, Any]] = {}

# Last candle that was actually processed for position management.
#
# This is important because main.py runs every 5 minutes while the
# strategy candle is 1H. Without this guard, the same closed candle
# could trigger TP/SL repeatedly.
last_processed_candle_time: Dict[str, pd.Timestamp] = {}

# Closed trades since the beginning of the current journal period.
daily_completed_trades: List[Dict[str, Any]] = []


# ============================================================
# HELPERS
# ============================================================

def _normalize_side(action: str) -> Optional[str]:
    """
    Convert strategy action into the internal engine representation.

    Strategy may return:
        BUY_LONG
        SELL_SHORT

    Engine stores:
        LONG
        SHORT
    """

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

    Position size is treated as USD notional.
    """

    entry = float(position["entry"])
    size_usd = float(position["size_usd"])
    side = position["type"]

    if entry <= 0:
        return 0.0, 0.0

    if side == "LONG":
        price_return = (
            exit_price - entry
        ) / entry

    else:
        price_return = (
            entry - exit_price
        ) / entry

    pnl_usd = size_usd * price_return
    pnl_pct = price_return * 100.0

    return pnl_usd, pnl_pct


def get_position_pnl(
    position: Dict[str, Any],
    current_price: float,
    current_time_utc: Optional[datetime] = None,
) -> Tuple[float, float, float]:
    """
    Return:
        pnl_usd
        pnl_pct
        current_stop_loss
    """

    pnl_usd, pnl_pct = _calculate_pnl(
        position,
        float(current_price),
    )

    return (
        pnl_usd,
        pnl_pct,
        float(position["sl"]),
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
    """
    Build and store a completed trade record.
    """

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
        break_even_triggered=position[
            "break_even_triggered"
        ],
        profit_lock_triggered=position[
            "profit_lock_triggered"
        ],
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
        "strategy_version": position[
            "strategy_version"
        ],
        "entry_candle_time": position[
            "entry_candle_time"
        ],
        "exit_candle_time": exit_candle_time,
        "break_even_triggered": position[
            "break_even_triggered"
        ],
        "profit_lock_triggered": position[
            "profit_lock_triggered"
        ],
        "trade_line": trade_line,
    }

    daily_completed_trades.append(
        completed_trade
    )

    logger.info(
        f"Trade closed | "
        f"{position['trade_id']} | "
        f"{symbol} {position['type']} | "
        f"Reason={exit_reason} | "
        f"PnL=${pnl_usd:+.2f}"
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

    Important:
    The bot runs every few minutes but the strategy is based on
    closed 1H candles. Therefore each candle is processed only once.
    """

    closed_trades_info: Dict[
        str, Dict[str, Any]
    ] = {}

    for symbol, position in list(
        open_positions.items()
    ):

        market_info = current_market_data.get(
            symbol
        )

        if not market_info:
            logger.warning(
                f"{symbol}: no market data for open position."
            )
            continue

        candle_time = market_info.get(
            "candle_time"
        )

        if candle_time is None:
            logger.warning(
                f"{symbol}: candle_time missing."
            )
            continue

        # ----------------------------------------------------
        # Do not process the same candle twice.
        # ----------------------------------------------------

        previous_processed = (
            last_processed_candle_time.get(symbol)
        )

        if (
            previous_processed is not None
            and candle_time <= previous_processed
        ):
            continue

        current_price = float(
            market_info["price"]
        )

        high_price = float(
            market_info["high"]
        )

        low_price = float(
            market_info["low"]
        )

        current_time_utc = (
            market_info.get("timestamp_utc")
            or datetime.now(timezone.utc)
        )

        entry = float(
            position["entry"]
        )

        tp = float(
            position["tp"]
        )

        side = position["type"]

        current_sl = float(
            position["sl"]
        )

        tp_distance = abs(
            tp - entry
        )

        if tp_distance <= 0:
            logger.error(
                f"{symbol}: invalid TP distance."
            )

            last_processed_candle_time[
                symbol
            ] = candle_time

            continue

        # ----------------------------------------------------
        # Mark candle as processed.
        #
        # This prevents the same candle from being evaluated
        # again if main.py runs again before a new 1H candle.
        # ----------------------------------------------------

        last_processed_candle_time[
            symbol
        ] = candle_time

        # ----------------------------------------------------
        # Favorable excursion.
        #
        # Use HIGH for LONG and LOW for SHORT rather than
        # current close. This means BE/Profit Lock can trigger
        # when the candle actually reached the threshold.
        # ----------------------------------------------------

        if side == "LONG":

            favorable_price = high_price

        else:

            favorable_price = low_price

        if side == "LONG":

            favorable_move = max(
                0.0,
                favorable_price - entry,
            )

        else:

            favorable_move = max(
                0.0,
                entry - favorable_price,
            )

        progress_ratio = (
            favorable_move / tp_distance
        )

        # ----------------------------------------------------
        # 1. BREAK-EVEN
        # ----------------------------------------------------

        if (
            not position["break_even_triggered"]
            and progress_ratio
            >= config.BREAK_EVEN_TRIGGER_RATIO
        ):

            old_sl = position["sl"]

            position["sl"] = entry

            position[
                "break_even_triggered"
            ] = True

            send_to_personal_chat(
                format_break_even_message(
                    trade_id=position[
                        "trade_id"
                    ],
                    symbol=symbol,
                    entry_price=entry,
                    old_sl=old_sl,
                    new_sl=position["sl"],
                    current_price=current_price,
                    timestamp_utc=current_time_utc,
                )
            )

            logger.info(
                f"BREAK-EVEN | "
                f"{symbol} | "
                f"{position['trade_id']} | "
                f"SL={position['sl']:.8g}"
            )

            current_sl = position["sl"]

        # ----------------------------------------------------
        # 2. PROFIT LOCK
        # ----------------------------------------------------

        if (
            not position["profit_lock_triggered"]
            and progress_ratio
            >= config.PROFIT_LOCK_TRIGGER_RATIO
        ):

            if side == "LONG":

                locked_sl_price = (
                    entry
                    + tp_distance
                    * config.PROFIT_LOCK_SL_RATIO
                )

            else:

                locked_sl_price = (
                    entry
                    - tp_distance
                    * config.PROFIT_LOCK_SL_RATIO
                )

            old_sl = position["sl"]

            # Never move the stop backwards.
            if side == "LONG":

                new_sl = max(
                    old_sl,
                    locked_sl_price,
                )

            else:

                new_sl = min(
                    old_sl,
                    locked_sl_price,
                )

            position["sl"] = new_sl

            position[
                "profit_lock_triggered"
            ] = True

            send_to_personal_chat(
                format_profit_lock_message(
                    trade_id=position[
                        "trade_id"
                    ],
                    symbol=symbol,
                    old_sl=old_sl,
                    new_sl=position["sl"],
                    current_price=current_price,
                    timestamp_utc=current_time_utc,
                )
            )

            logger.info(
                f"PROFIT LOCK | "
                f"{symbol} | "
                f"{position['trade_id']} | "
                f"SL={position['sl']:.8g}"
            )

            current_sl = position["sl"]

        # ----------------------------------------------------
        # 3. TP / SL DETECTION
        # ----------------------------------------------------

        hit_tp = False
        hit_sl = False

        if side == "LONG":

            if high_price >= tp:
                hit_tp = True

            if low_price <= current_sl:
                hit_sl = True

        else:

            if low_price <= tp:
                hit_tp = True

            if high_price >= current_sl:
                hit_sl = True

        # ----------------------------------------------------
        # Determine exit.
        #
        # If TP and SL are both touched in the same candle,
        # we do NOT know which happened first.
        #
        # Conservative assumption:
        # SL takes priority.
        # ----------------------------------------------------

        exit_reason: Optional[str] = None
        exit_price: Optional[float] = None

        if hit_tp and hit_sl:

            exit_reason = (
                "SL (Simultaneous TP/SL)"
            )

            exit_price = current_sl

        elif hit_sl:

            if (
                position["profit_lock_triggered"]
            ):

                exit_reason = "PROFIT LOCK SL"

            elif (
                position["break_even_triggered"]
            ):

                exit_reason = "BREAK-EVEN SL"

            else:

                exit_reason = "SL"

            exit_price = current_sl

        elif hit_tp:

            exit_reason = "TP"
            exit_price = tp

        # ----------------------------------------------------
        # 4. CLOSE POSITION
        # ----------------------------------------------------

        if (
            exit_reason is not None
            and exit_price is not None
        ):

            completed_trade = (
                record_trade_completion(
                    symbol=symbol,
                    position=position,
                    exit_price=exit_price,
                    exit_reason=exit_reason,
                    exit_candle_time=candle_time,
                )
            )

            send_to_personal_chat(
                format_trade_closed_message(
                    symbol=symbol,
                    position_type=side,
                    entry=position["entry"],
                    exit_price=exit_price,
                    initial_sl=position[
                        "initial_sl"
                    ],
                    final_sl=position["sl"],
                    tp=position["tp"],
                    position_size_usd=position[
                        "size_usd"
                    ],
                    exit_reason=exit_reason,
                    pnl_usd=completed_trade[
                        "pnl_usd"
                    ],
                    pnl_pct=completed_trade[
                        "pnl_pct"
                    ],
                    trade_id=position[
                        "trade_id"
                    ],
                    risk_pct=position[
                        "risk_pct"
                    ],
                    regime=position[
                        "regime"
                    ],
                    strategy_version=position[
                        "strategy_version"
                    ],
                    entry_dt_utc=position[
                        "entry_candle_time"
                    ],
                    exit_dt_utc=candle_time,
                    break_even_triggered=position[
                        "break_even_triggered"
                    ],
                    profit_lock_triggered=position[
                        "profit_lock_triggered"
                    ],
                )
            )

            closed_trades_info[
                symbol
            ] = completed_trade

            del open_positions[
                symbol
            ]

            logger.info(
                f"POSITION CLOSED | "
                f"{symbol} | "
                f"{position['trade_id']} | "
                f"{exit_reason}"
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
) -> Tuple[
    bool,
    Optional[Dict[str, Any]]
]:
    """
    Validate and open a new paper position.
    """

    action = signal.get(
        "action"
    )

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

    side = _normalize_side(
        action
    )

    if side is None:

        logger.error(
            f"{symbol}: unknown strategy action: "
            f"{action}"
        )

        return False, None

    # --------------------------------------------------------
    # One position per symbol
    # --------------------------------------------------------

    if symbol in open_positions:

        logger.debug(
            f"{symbol}: position already exists."
        )

        return False, None

    # --------------------------------------------------------
    # Maximum concurrent positions
    # --------------------------------------------------------

    if (
        len(open_positions)
        >= config.MAX_CONCURRENT_POSITIONS
    ):

        logger.info(
            f"Max concurrent positions reached. "
            f"Cannot open {symbol}."
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
            f"{symbol}: incomplete signal. "
            f"Missing={missing}"
        )

        return False, None

    entry_price = float(
        signal["entry_price"]
    )

    stop_price = float(
        signal["stop_price"]
    )

    tp_price = float(
        signal["take_profit_price"]
    )

    risk_pct = float(
        signal["risk_pct"]
    )

    # --------------------------------------------------------
    # Validate price geometry
    # --------------------------------------------------------

    if (
        entry_price <= 0
        or stop_price <= 0
        or tp_price <= 0
    ):

        logger.error(
            f"{symbol}: invalid prices | "
            f"entry={entry_price}, "
            f"SL={stop_price}, "
            f"TP={tp_price}"
        )

        return False, None

    if side == "LONG":

        if not (
            stop_price < entry_price < tp_price
        ):

            logger.error(
                f"{symbol}: invalid LONG geometry | "
                f"SL={stop_price}, "
                f"Entry={entry_price}, "
                f"TP={tp_price}"
            )

            return False, None

    else:

        if not (
            tp_price < entry_price < stop_price
        ):

            logger.error(
                f"{symbol}: invalid SHORT geometry | "
                f"TP={tp_price}, "
                f"Entry={entry_price}, "
                f"SL={stop_price}"
            )

            return False, None

    # --------------------------------------------------------
    # Position sizing
    # --------------------------------------------------------

    position_size_usd = (
        calculate_position_size(
            capital=current_capital,
            risk_pct=risk_pct,
            entry_price=entry_price,
            stop_price=stop_price,
        )
    )

    if position_size_usd <= 0:

        logger.warning(
            f"{symbol}: position size <= 0. "
            f"Trade rejected."
        )

        return False, None

    # --------------------------------------------------------
    # Trade ID
    # --------------------------------------------------------

    candle_time = market_data.get(
        "candle_time"
    )

    if candle_time is None:

        logger.error(
            f"{symbol}: candle_time missing."
        )

        return False, None

    timestamp_str = (
        candle_time.strftime(
            "%Y%m%d-%H%M%S"
        )
    )

    trade_id = (
        f"{config.BOT_VERSION}-"
        f"{symbol}-"
        f"{timestamp_str}-"
        f"{len(open_positions):04d}"
    )

    # --------------------------------------------------------
    # Create position
    # --------------------------------------------------------

    new_position = {

        "type": side,

        "entry": entry_price,

        "tp": tp_price,

        "sl": stop_price,

        "initial_sl": stop_price,

        "size_usd": float(
            position_size_usd
        ),

        "risk_pct": risk_pct,

        "regime": market_data[
            "regime"
        ],

        "strategy_version": signal[
            "strategy_version"
        ],

        "entry_candle_time": candle_time,

        "trade_id": trade_id,

        "break_even_triggered": False,

        "profit_lock_triggered": False,
    }

    open_positions[
        symbol
    ] = new_position

    # --------------------------------------------------------
    # IMPORTANT:
    # Mark entry candle as already processed.
    #
    # Otherwise main.py may immediately manage the newly
    # opened position against the very same candle.
    # --------------------------------------------------------

    last_processed_candle_time[
        symbol
    ] = candle_time

    logger.info(
        f"POSITION OPENED | "
        f"{trade_id} | "
        f"{symbol} {side} | "
        f"Entry={entry_price:.8g} | "
        f"SL={stop_price:.8g} | "
        f"TP={tp_price:.8g} | "
        f"Size=${position_size_usd:.2f}"
    )

    # --------------------------------------------------------
    # Telegram entry notification
    # --------------------------------------------------------

    try:

        send_to_personal_chat(
            format_entry_message(
                symbol=symbol,
                side=side,
                entry_price=entry_price,
                sl=stop_price,
                tp=tp_price,
                position_size_usd=position_size_usd,
                regime=market_data[
                    "regime"
                ],
                strategy_version=signal[
                    "strategy_version"
                ],
                trade_id=trade_id,
                entry_dt_utc=candle_time,
                risk_pct=risk_pct,
            )
        )

    except Exception as exc:

        logger.exception(
            f"{symbol}: entry Telegram error: {exc}"
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
) -> Tuple[
    bool,
    Optional[Dict[str, Any]]
]:
    """
    Main entry point for processing a symbol.

    Existing positions are managed globally by
    manage_open_positions().

    This function only attempts new entries.
    """

    candle_time = market_data.get(
        "candle_time"
    )

    if candle_time is None:

        logger.warning(
            f"{symbol}: missing candle time."
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
    Initialize the engine state.

    IMPORTANT:
    Use .clear() rather than reassigning dictionaries/lists.

    This preserves references held by other modules.
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

    summary: List[
        Dict[str, Any]
    ] = []

    current_market_data = (
        current_market_data or {}
    )

    for symbol, position in (
        open_positions.items()
    ):

        market_info = (
            current_market_data.get(symbol)
        )

        if market_info:

            current_price = float(
                market_info["price"]
            )

            pnl_usd, pnl_pct, current_sl = (
                get_position_pnl(
                    position,
                    current_price,
                    market_info.get(
                        "timestamp_utc"
                    ),
                )
            )

        else:

            current_price = float(
                position["entry"]
            )

            pnl_usd = 0.0
            pnl_pct = 0.0
            current_sl = float(
                position["sl"]
            )

        summary.append({

            "symbol": symbol,

            "type": position["type"],

            "entry_price": position[
                "entry"
            ],

            "current_price": current_price,

            "sl": current_sl,

            "tp": position["tp"],

            "size_usd": position[
                "size_usd"
            ],

            "current_pnl_usd": pnl_usd,

            "current_pnl_pct": pnl_pct,

            "trade_id": position[
                "trade_id"
            ],

            "risk_pct": position[
                "risk_pct"
            ],

            "regime": position[
                "regime"
            ],

            "break_even_triggered": position[
                "break_even_triggered"
            ],

            "profit_lock_triggered": position[
                "profit_lock_triggered"
            ],
        })

    return summary


# ============================================================
# DAILY JOURNAL DATA
# ============================================================

def get_daily_journal_data(
) -> Tuple[
    List[Dict[str, Any]],
    Dict[str, Any],
]:
    """
    Return completed trades and statistics.
    """

    num_trades = len(
        daily_completed_trades
    )

    wins = sum(
        1
        for trade
        in daily_completed_trades
        if trade.get(
            "pnl_usd", 0.0
        ) > 0
    )

    losses = sum(
        1
        for trade
        in daily_completed_trades
        if trade.get(
            "pnl_usd", 0.0
        ) < 0
    )

    breakeven = (
        num_trades
        - wins
        - losses
    )

    pnl_total = sum(
        trade.get(
            "pnl_usd", 0.0
        )
        for trade
        in daily_completed_trades
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
