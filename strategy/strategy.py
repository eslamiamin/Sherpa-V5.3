"""
SHERPA V5.3 Trading Strategy.
"""

import logging
import pandas as pd

import config

from strategy.indicators import (
    EMA_50_PERIOD,
    EMA_200_PERIOD,
)

logger = logging.getLogger(__name__)


REGIME_DEAD_CHOP = "DEAD_CHOP"
REGIME_GOOD_RANGE = "GOOD_RANGE"
REGIME_STRONG_BULL = "STRONG_BULL"
REGIME_WEAK_BULL = "WEAK_BULL"
REGIME_STRONG_BEAR = "STRONG_BEAR"
REGIME_WEAK_BEAR = "WEAK_BEAR"

STRATEGY_VERSION = "EMA50-CROSS-V1"

ADX_LOW_THRESHOLD = 18
ADX_MEDIUM_THRESHOLD = 25
ADX_HIGH_THRESHOLD = 30

RSI_OVERSOLD_LONG = 35
RSI_OVERBOUGHT_SHORT = 65

RSI_BULL_ENTRY = 55
RSI_BEAR_ENTRY = 45

MFI_OVERSOLD_LONG = 30
MFI_OVERBOUGHT_SHORT = 70

BB_WIDTH_THRESHOLD_CHOP = 0.02


def detect_market_regime(
    df_1d: pd.DataFrame,
    df_1h: pd.DataFrame,
) -> str:

    if df_1d.empty or df_1h.empty:
        return REGIME_DEAD_CHOP

    d1 = df_1d.iloc[-1]
    h1 = df_1h.iloc[-1]

    values = [
        d1.get("close"),
        d1.get("ema_50"),
        h1.get("ema_50"),
        h1.get("ema_200"),
        h1.get("adx"),
        h1.get("bb_middle"),
        h1.get("bb_upper"),
        h1.get("bb_lower"),
    ]

    if any(pd.isna(v) for v in values):
        return REGIME_DEAD_CHOP

    close_daily = float(d1["close"])
    ema_50_daily = float(d1["ema_50"])

    ema_50_hourly = float(h1["ema_50"])
    ema_200_hourly = float(h1["ema_200"])

    adx = float(h1["adx"])

    bb_middle = float(h1["bb_middle"])
    bb_upper = float(h1["bb_upper"])
    bb_lower = float(h1["bb_lower"])

    bb_width = (
        (bb_upper - bb_lower) / bb_middle
        if bb_middle != 0
        else 0.0
    )

    # Dead chop
    if (
        bb_width < BB_WIDTH_THRESHOLD_CHOP
        and adx < ADX_LOW_THRESHOLD
    ):
        return REGIME_DEAD_CHOP

    # Bull
    if (
        close_daily > ema_50_daily
        and ema_50_hourly > ema_200_hourly
    ):

        if adx > ADX_HIGH_THRESHOLD:
            return REGIME_STRONG_BULL

        return REGIME_WEAK_BULL

    # Bear
    if (
        close_daily < ema_50_daily
        and ema_50_hourly < ema_200_hourly
    ):

        if adx > ADX_HIGH_THRESHOLD:
            return REGIME_STRONG_BEAR

        return REGIME_WEAK_BEAR

    # Tradable range
    if (
        ADX_LOW_THRESHOLD <= adx <= ADX_HIGH_THRESHOLD
    ):
        return REGIME_GOOD_RANGE

    return REGIME_DEAD_CHOP


def generate_signals(
    df_1h: pd.DataFrame,
    regime: str,
    current_candle_close_time,
) -> dict:

    if df_1h.empty or len(df_1h) < 2:
        return {
            "action": "HOLD",
            "signal_candle_time": current_candle_close_time,
        }

    last = df_1h.iloc[-1]
    prev = df_1h.iloc[-2]

    required = [
        "close",
        "atr",
        "rsi",
        "mfi",
        "ema_50",
        "ema_200",
        "bb_lower",
        "bb_upper",
        "volume",
        "vol_sma",
    ]

    if any(
        pd.isna(last.get(col))
        for col in required
    ):
        return {
            "action": "HOLD",
            "signal_candle_time": current_candle_close_time,
        }

    price = float(last["close"])
    atr = float(last["atr"])
    rsi = float(last["rsi"])
    mfi = float(last["mfi"])

    ema_50 = float(last["ema_50"])
    ema_200 = float(last["ema_200"])

    prev_ema_50 = float(prev["ema_50"])
    prev_close = float(prev["close"])

    volume = float(last["volume"])
    vol_sma = float(last["vol_sma"])

    signal = {
        "action": "HOLD",
        "risk_pct": 0.0,
        "tp_mult": 0.0,
        "sl_mult": 0.0,
        "entry_price": price,
        "stop_price": price,
        "take_profit_price": price,
        "signal_candle_time": current_candle_close_time,
        "strategy_version": STRATEGY_VERSION,
    }

    if atr <= 0:
        return signal

    # ========================================================
    # GOOD RANGE
    # ========================================================

    if regime == REGIME_GOOD_RANGE:

        if (
            price < float(last["bb_lower"])
            and rsi < RSI_OVERSOLD_LONG
            and mfi < MFI_OVERSOLD_LONG
        ):
            sl_mult = config.SL_ATR_MULTIPLIER
            tp_mult = config.TP_ATR_MULTIPLIER

            signal.update({
                "action": "BUY_LONG",
                "risk_pct": config.NORMAL_REGIME_RISK_PCT,
                "tp_mult": tp_mult,
                "sl_mult": sl_mult,
                "stop_price": price - sl_mult * atr,
                "take_profit_price": price + tp_mult * atr,
            })

        elif (
            price > float(last["bb_upper"])
            and rsi > RSI_OVERBOUGHT_SHORT
            and mfi > MFI_OVERBOUGHT_SHORT
        ):
            sl_mult = config.SL_ATR_MULTIPLIER
            tp_mult = config.TP_ATR_MULTIPLIER

            signal.update({
                "action": "SELL_SHORT",
                "risk_pct": config.NORMAL_REGIME_RISK_PCT,
                "tp_mult": tp_mult,
                "sl_mult": sl_mult,
                "stop_price": price + sl_mult * atr,
                "take_profit_price": price - tp_mult * atr,
            })

        return signal

    # ========================================================
    # BULL
    # ========================================================

    if regime in (
        REGIME_STRONG_BULL,
        REGIME_WEAK_BULL,
    ):

        ema_cross_up = (
            prev_close <= prev_ema_50
            and price > ema_50
        )

        if (
            ema_cross_up
            and rsi > RSI_BULL_ENTRY
            and volume > vol_sma
        ):

            risk = (
                config.STRONG_REGIME_RISK_PCT
                if regime == REGIME_STRONG_BULL
                else config.NORMAL_REGIME_RISK_PCT
            )

            sl_mult = config.SL_ATR_MULTIPLIER
            tp_mult = config.TP_ATR_MULTIPLIER

            signal.update({
                "action": "BUY_LONG",
                "risk_pct": risk,
                "tp_mult": tp_mult,
                "sl_mult": sl_mult,
                "stop_price": price - sl_mult * atr,
                "take_profit_price": price + tp_mult * atr,
            })

        return signal

    # ========================================================
    # BEAR
    # ========================================================

    if regime in (
        REGIME_STRONG_BEAR,
        REGIME_WEAK_BEAR,
    ):

        ema_cross_down = (
            prev_close >= prev_ema_50
            and price < ema_50
        )

        if (
            ema_cross_down
            and rsi < RSI_BEAR_ENTRY
            and volume > vol_sma
        ):

            risk = (
                config.STRONG_REGIME_RISK_PCT
                if regime == REGIME_STRONG_BEAR
                else config.NORMAL_REGIME_RISK_PCT
            )

            sl_mult = config.SL_ATR_MULTIPLIER
            tp_mult = config.TP_ATR_MULTIPLIER

            signal.update({
                "action": "SELL_SHORT",
                "risk_pct": risk,
                "tp_mult": tp_mult,
                "sl_mult": sl_mult,
                "stop_price": price + sl_mult * atr,
                "take_profit_price": price - tp_mult * atr,
            })

        return signal

    return signal
