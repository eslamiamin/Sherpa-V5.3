"""
SHERPA V5.3 Trading Engine.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Tuple, List

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


open_positions: Dict[str, Dict[str, Any]] = {}

last_processed_candle_time: Dict[str, pd.Timestamp] = {}

daily_completed_trades: List[Dict[str, Any]] = []


def initialize_trading_state():

    open_positions.clear()
    last_processed_candle_time.clear()
    daily_completed_trades.clear()

    logger.info("Trading state initialized.")


def reset_daily_tracking():

    daily_completed_trades.clear()

    logger.info(
        "Daily tracking reset. Open positions preserved."
    )


def get_position_pnl(
    position: Dict[str, Any],
    current_price: float,
) -> Tuple[float, float]:

    entry = float(position["entry"])
    size = float(position["size_usd"])

    if position["type"] == "BUY_LONG":

        pnl_pct = (
            (current_price - entry) / entry * 100
        )

        pnl_usd = (
            (current_price - entry)
            * size
            / entry
        )

    else:

        pnl_pct = (
            (entry - current_price) / entry * 100
        )

        pnl_usd = (
            (entry - current_price)
            * size
            / entry
        )

    return pnl_usd, pnl_pct


def record_trade_completion(
    symbol: str,
    position: Dict[str, Any],
    exit_price: float,
    exit_reason: str,
    exit_candle_time,
) -> Dict[str, Any]:

    entry = float(position["entry"])
    size = float(position["size_usd"])

    if position["type"] == "BUY_LONG":

        pnl_pct = (
            (exit_price - entry)
            / entry
            * 100
        )

        pnl_usd = (
            (exit_price - entry)
            * size
            / entry
        )

        side = "LONG"

    else:

        pnl_pct = (
            (entry - exit_price)
            / entry
            * 100
        )

        pnl_usd = (
            (entry - exit_price)
            * size
            / entry
        )

        side = "SHORT"

    trade_line = format_trade_line(
        bot_version=config.BOT_VERSION,
        trade_id=position["trade_id"],
        symbol=symbol,
        entry_dt_utc=position["entry_candle_time"],
        exit_dt_utc=exit_candle_time,
        side=side,
        strategy_version=position["strategy_version"],
        regime=position["regime"],
        risk_pct=position["risk_pct"],
        initial_sl=position["initial_sl"],
        entry_price=entry,
        tp=position["tp"],
        position_size_usd=size,
        exit_price=exit_price,
        final_sl=position["sl"],
        exit_reason=exit_reason,
        pnl_usd=pnl_usd,
        pnl_pct=pnl_pct,
        break_even_triggered=position["break_even_triggered"],
        profit_lock_triggered=position["profit_lock_triggered"],
    )

    trade = {
        "trade_id": position["trade_id"],
        "symbol": symbol,
        "type": side,
        "entry": entry,
        "exit": exit_price,
        "tp": position["tp"],
        "initial_sl": position["initial_sl"],
        "final_sl": position["sl"],
        "size_usd": size,
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

    daily_completed_trades.append(trade)

    return trade


def manage_open_positions(
    current_market_data: Dict[str, Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:

    closed_trades = {}

    for symbol, position in list(open_positions.items()):

        market = current_market_data.get(symbol)

        if not market:
            continue

        candle_time = market["candle_time"]

        # Do not process the same closed candle twice.
        if (
            last_processed_candle_time.get(symbol)
            == candle_time
        ):
            continue

        last_processed_candle_time[symbol] = candle_time

        current_price = float(market["price"])
        high = float(market["high"])
        low = float(market["low"])

        entry = float(position["entry"])
        tp = float(position["tp"])
        current_sl = float(position["sl"])

        tp_distance = abs(tp - entry)

        if tp_distance <= 0:
            continue

        is_long = position["type"] == "BUY_LONG"

        # ----------------------------------------------------
        # Determine whether TP-distance was reached inside bar
        # ----------------------------------------------------

        if is_long:
            favorable_price = high
        else:
            favorable_price = low

        if is_long:
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
        # Break-even
        # ----------------------------------------------------

        if (
            not position["break_even_triggered"]
            and progress_ratio >= config.BREAK_EVEN_TRIGGER_RATIO
        ):

            old_sl = position["sl"]

            position["sl"] = entry
            position["break_even_triggered"] = True

            send_to_personal_chat(
                format_break_even_message(
                    trade_id=position["trade_id"],
                    symbol=symbol,
                    entry_price=entry,
                    old_sl=old_sl,
                    new_sl=position["sl"],
                    current_price=current_price,
                    timestamp_utc=market["timestamp_utc"],
                )
            )

        # ----------------------------------------------------
        # Profit lock
        # ----------------------------------------------------

        if (
            not position["profit_lock_triggered"]
            and progress_ratio >= config.PROFIT_LOCK_TRIGGER_RATIO
        ):

            old_sl = position["sl"]

            if is_long:
                new_sl = (
                    entry
                    + tp_distance
                    * config.PROFIT_LOCK_SL_RATIO
                )
            else:
                new_sl = (
                    entry
                    - tp_distance
                    * config.PROFIT_LOCK_SL_RATIO
                )

            position["sl"] = new_sl
            position["profit_lock_triggered"] = True

            send_to_personal_chat(
                format_profit_lock_message(
                    trade_id=position["trade_id"],
                    symbol=symbol,
                    old_sl=old_sl,
                    new_sl=new_sl,
                    current_price=current_price,
                    timestamp_utc=market["timestamp_utc"],
                )
            )

        # ----------------------------------------------------
        # TP / SL
        # ----------------------------------------------------

        current_sl = float(position["sl"])

        if is_long:

            hit_tp = high >= tp
            hit_sl = low <= current_sl

        else:

            hit_tp = low <= tp
            hit_sl = high >= current_sl

        exit_reason = None
        exit_price = None

        # Conservative assumption when both hit in one candle.
        if hit_tp and hit_sl:

            exit_reason = "SL (Simultaneous TP/SL)"
            exit_price = current_sl

        elif hit_sl:

            if position["profit_lock_triggered"]:
                exit_reason = "PROFIT LOCK SL"
            elif position["break_even_triggered"]:
                exit_reason = "BREAK-EVEN SL"
            else:
                exit_reason = "SL"

            exit_price = current_sl

        elif hit_tp:

            exit_reason = "TP"
            exit_price = tp

        if exit_reason is None:
            continue

        trade = record_trade_completion(
            symbol=symbol,
            position=position,
            exit_price=float(exit_price),
            exit_reason=exit_reason,
            exit_candle_time=candle_time,
        )

        send_to_personal_chat(
            format_trade_closed_message(
                symbol=symbol,
                position_type=(
                    "LONG"
                    if is_long
                    else "SHORT"
                ),
                entry=entry,
                exit_price=float(exit_price),
                initial_sl=position["initial_sl"],
                final_sl=position["sl"],
                tp=position["tp"],
                exit_reason=exit_reason,
                pnl_usd=trade["pnl_usd"],
                pnl_pct=trade["pnl_pct"],
                trade_id=position["trade_id"],
                risk_pct=position["risk_pct"],
                regime=position["regime"],
                strategy_version=position["strategy_version"],
                entry_dt_utc=position["entry_candle_time"],
                exit_dt_utc=candle_time,
                break_even_triggered=position["break_even_triggered"],
                profit_lock_triggered=position["profit_lock_triggered"],
                position_size_usd=position["size_usd"],
            )
        )

        del open_positions[symbol]

        closed_trades[symbol] = trade

    return closed_trades


def process_new_entry_signal(
    symbol: str,
    signal: Dict[str, Any],
    market_data: Dict[str, Any],
    current_capital: float,
) -> Tuple[bool, Dict[str, Any] | None]:

    action = signal.get("action")

    if action not in (
        "BUY_LONG",
        "SELL_SHORT",
    ):
        return False, None

    if symbol in open_positions:
        return False, None

    if len(open_positions) >= config.MAX_CONCURRENT_POSITIONS:
        return False, None

    required = [
        "entry_price",
        "stop_price",
        "take_profit_price",
        "risk_pct",
    ]

    if not all(
        signal.get(k) is not None
        for k in required
    ):
        return False, None

    entry = float(signal["entry_price"])
    stop = float(signal["stop_price"])
    tp = float(signal["take_profit_price"])
    risk_pct = float(signal["risk_pct"])

    if entry <= 0 or stop <= 0 or tp <= 0:
        return False, None

    # Validate direction.
    if action == "BUY_LONG":
        if not (stop < entry < tp):
            logger.warning(
                "%s invalid LONG levels: entry=%s sl=%s tp=%s",
                symbol,
                entry,
                stop,
                tp,
            )
            return False, None

    else:
        if not (tp < entry < stop):
            logger.warning(
                "%s invalid SHORT levels: entry=%s sl=%s tp=%s",
                symbol,
                entry,
                stop,
                tp,
            )
            return False, None

    position_size = calculate_position_size(
        capital=current_capital,
        risk_pct=risk_pct,
        entry_price=entry,
        stop_price=stop,
    )

    if position_size <= 0:
        return False, None

    timestamp_str = (
        market_data["candle_time"]
        .strftime("%Y%m%d-%H%M%S")
    )

    trade_id = (
        f"{config.BOT_VERSION}-"
        f"{symbol}-"
        f"{timestamp_str}-"
        f"{len(open_positions):04d}"
    )

    position = {
        "type": action,
        "entry": entry,
        "tp": tp,
        "sl": stop,
        "initial_sl": stop,
        "size_usd": position_size,
        "risk_pct": risk_pct,
        "regime": market_data["regime"],
        "strategy_version": signal.get(
            "strategy_version",
            config.STRATEGY_VERSION,
        ),
        "entry_candle_time": market_data["candle_time"],
        "trade_id": trade_id,
        "break_even_triggered": False,
        "profit_lock_triggered": False,
    }

    open_positions[symbol] = position

    last_processed_candle_time[symbol] = (
        market_data["candle_time"]
    )

    send_to_personal_chat(
        format_entry_message(
            symbol=symbol,
            side=(
                "LONG"
                if action == "BUY_LONG"
                else "SHORT"
            ),
            entry_price=entry,
            sl=stop,
            tp=tp,
            position_size_usd=position_size,
            regime=market_data["regime"],
            strategy_version=position["strategy_version"],
            trade_id=trade_id,
            entry_dt_utc=market_data["candle_time"],
            risk_pct=risk_pct,
        )
    )

    logger.info(
        "Opened %s %s | entry=%s | size=$%.2f",
        symbol,
        action,
        entry,
        position_size,
    )

    return True, position


def process_symbol_state(
    symbol: str,
    signal: Dict[str, Any],
    market_data: Dict[str, Any],
    current_capital: float,
) -> Tuple[bool, Dict[str, Any] | None]:

    if symbol in open_positions:
        return False, None

    return process_new_entry_signal(
        symbol=symbol,
        signal=signal,
        market_data=market_data,
        current_capital=current_capital,
    )


def get_current_open_positions_summary(
    market_data: Dict[str, Dict[str, Any]] | None = None,
) -> list[dict]:

    market_data = market_data or {}

    summary = []

    for symbol, position in open_positions.items():

        market = market_data.get(symbol)

        if market:
            current_price = float(
                market["price"]
            )

            pnl_usd, pnl_pct = get_position_pnl(
                position,
                current_price,
            )

        else:
            current_price = position["entry"]
            pnl_usd = 0.0
            pnl_pct = 0.0

        summary.append({
            "symbol": symbol,
            "type": (
                "LONG"
                if position["type"] == "BUY_LONG"
                else "SHORT"
            ),
            "entry_price": position["entry"],
            "current_price": current_price,
            "current_pnl_usd": pnl_usd,
            "current_pnl_pct": pnl_pct,
            "sl": position["sl"],
            "tp": position["tp"],
            "trade_id": position["trade_id"],
        })

    return summary


def get_daily_journal_data():

    trades = list(daily_completed_trades)

    wins = sum(
        1
        for t in trades
        if float(t.get("pnl_usd", 0)) >= 0
    )

    losses = len(trades) - wins

    pnl = sum(
        float(t.get("pnl_usd", 0))
        for t in trades
    )

    win_rate = (
        wins / len(trades) * 100
        if trades
        else 0.0
    )

    return trades, {
        "trades": len(trades),
        "wins": wins,
        "losses": losses,
        "pnl_usd": pnl,
        "win_rate": win_rate,
    }
