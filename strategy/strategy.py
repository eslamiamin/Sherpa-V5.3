"""
SHERPA V5.3 - Trading Strategy

Market regime detection:
- DEAD_CHOP
- GOOD_RANGE
- STRONG_BULL
- WEAK_BULL
- STRONG_BEAR
- WEAK_BEAR

Entry logic:
- Trend-following in bullish/bearish regimes
- Mean-reversion/re-entry logic in GOOD_RANGE
- No trading in DEAD_CHOP

Risk:
- Strong regime: config.STRONG_REGIME_RISK_PCT
- Normal regime: config.NORMAL_REGIME_RISK_PCT

Trade geometry:
- TP = config.TP_ATR_MULTIPLIER * ATR
- SL = config.SL_ATR_MULTIPLIER * ATR
"""

import logging

import pandas as pd

import config

from strategy.indicators import (
    EMA_50_PERIOD,
    EMA_200_PERIOD,
)


logger = logging.getLogger(__name__)


# ============================================================
# REGIMES
# ============================================================

REGIME_DEAD_CHOP = "DEAD_CHOP"
REGIME_GOOD_RANGE = "GOOD_RANGE"

REGIME_STRONG_BULL = "STRONG_BULL"
REGIME_WEAK_BULL = "WEAK_BULL"

REGIME_STRONG_BEAR = "STRONG_BEAR"
REGIME_WEAK_BEAR = "WEAK_BEAR"


# ============================================================
# REGIME THRESHOLDS
# ============================================================

ADX_LOW_THRESHOLD = 18.0
ADX_MEDIUM_THRESHOLD = 25.0
ADX_HIGH_THRESHOLD = 30.0

BB_WIDTH_THRESHOLD_CHOP = 0.02


# ============================================================
# ENTRY THRESHOLDS
# ============================================================

RSI_OVERSOLD_LONG = 35.0
RSI_OVERBOUGHT_SHORT = 65.0

RSI_BULL_ENTRY = 55.0
RSI_BEAR_ENTRY = 45.0

MFI_OVERSOLD_LONG = 30.0
MFI_OVERBOUGHT_SHORT = 70.0


# ============================================================
# STRATEGY VERSION
# ============================================================

STRATEGY_VERSION = getattr(
    config,
    "STRATEGY_VERSION",
    "EMA50-CROSS-V1",
)


# ============================================================
# HELPERS
# ============================================================

def _safe_float(
    value,
    default: float = 0.0,
) -> float:

    try:

        result = float(value)

        if pd.isna(result):
            return default

        return result

    except (
        TypeError,
        ValueError,
    ):

        return default


def _has_valid_indicator(
    value,
) -> bool:

    try:

        return pd.notna(value)

    except Exception:

        return False


# ============================================================
# MARKET REGIME
# ============================================================

def detect_market_regime(
    df_1d: pd.DataFrame,
    df_1h: pd.DataFrame,
) -> str:
    """
    Detect the current market regime.

    Daily timeframe:
        close vs EMA50

    Hourly timeframe:
        EMA50 vs EMA200
        ADX
        Bollinger Band width
    """

    if (
        df_1d is None
        or df_1d.empty
        or df_1h is None
        or df_1h.empty
    ):

        logger.warning(
            "Insufficient data for regime detection."
        )

        return REGIME_DEAD_CHOP

    daily = df_1d.iloc[-1]
    hourly = df_1h.iloc[-1]

    required_columns = [
        f"ema_{EMA_50_PERIOD}",
        "close",
    ]

    for column in required_columns:

        if column not in df_1d.columns:

            logger.warning(
                f"Daily indicator missing: {column}"
            )

            return REGIME_DEAD_CHOP

    hourly_required = [
        f"ema_{EMA_50_PERIOD}",
        f"ema_{EMA_200_PERIOD}",
        "adx",
        "bb_width",
    ]

    for column in hourly_required:

        if column not in df_1h.columns:

            logger.warning(
                f"Hourly indicator missing: {column}"
            )

            return REGIME_DEAD_CHOP

    daily_close = _safe_float(
        daily["close"]
    )

    daily_ema50 = _safe_float(
        daily[f"ema_{EMA_50_PERIOD}"]
    )

    hourly_ema50 = _safe_float(
        hourly[f"ema_{EMA_50_PERIOD}"]
    )

    hourly_ema200 = _safe_float(
        hourly[f"ema_{EMA_200_PERIOD}"]
    )

    adx = _safe_float(
        hourly["adx"]
    )

    bb_width = _safe_float(
        hourly["bb_width"]
    )

    # --------------------------------------------------------
    # Validate
    # --------------------------------------------------------

    if (
        daily_close <= 0
        or daily_ema50 <= 0
        or hourly_ema50 <= 0
        or hourly_ema200 <= 0
        or adx < 0
        or bb_width < 0
    ):

        logger.warning(
            f"Invalid regime indicators | "
            f"daily_close={daily_close}, "
            f"daily_ema50={daily_ema50}, "
            f"h1_ema50={hourly_ema50}, "
            f"h1_ema200={hourly_ema200}, "
            f"ADX={adx}, "
            f"BBWidth={bb_width}"
        )

        return REGIME_DEAD_CHOP

    # ========================================================
    # 1. DEAD CHOP
    # ========================================================

    if (
        bb_width < BB_WIDTH_THRESHOLD_CHOP
        and adx < ADX_LOW_THRESHOLD
    ):

        logger.debug(
            f"{REGIME_DEAD_CHOP} | "
            f"BBWidth={bb_width:.4f} | "
            f"ADX={adx:.2f}"
        )

        return REGIME_DEAD_CHOP

    # ========================================================
    # 2. BULLISH
    # ========================================================

    bullish_alignment = (
        daily_close > daily_ema50
        and hourly_ema50 > hourly_ema200
    )

    if bullish_alignment:

        if adx >= ADX_HIGH_THRESHOLD:

            return REGIME_STRONG_BULL

        return REGIME_WEAK_BULL

    # ========================================================
    # 3. BEARISH
    # ========================================================

    bearish_alignment = (
        daily_close < daily_ema50
        and hourly_ema50 < hourly_ema200
    )

    if bearish_alignment:

        if adx >= ADX_HIGH_THRESHOLD:

            return REGIME_STRONG_BEAR

        return REGIME_WEAK_BEAR

    # ========================================================
    # 4. GOOD RANGE
    # ========================================================

    if (
        ADX_LOW_THRESHOLD
        <= adx
        < ADX_HIGH_THRESHOLD
    ):

        return REGIME_GOOD_RANGE

    # ========================================================
    # 5. FALLBACK
    # ========================================================

    return REGIME_DEAD_CHOP


# ============================================================
# SIGNAL TEMPLATE
# ============================================================

def _hold_signal(
    price: float,
    candle_time: pd.Timestamp,
) -> dict:

    return {

        "action": "HOLD",

        "risk_pct": 0.0,

        "tp_mult": 0.0,

        "sl_mult": 0.0,

        "entry_price": price,

        "stop_price": price,

        "take_profit_price": price,

        "signal_candle_time": candle_time,

        "strategy_version": STRATEGY_VERSION,
    }


# ============================================================
# SIGNAL GENERATION
# ============================================================

def generate_signals(
    df_1h: pd.DataFrame,
    regime: str,
    current_candle_close_time: pd.Timestamp,
) -> dict:
    """
    Generate an entry signal from the latest closed 1H candle.

    Actions:
        BUY_LONG
        SELL_SHORT
        HOLD
    """

    if (
        df_1h is None
        or df_1h.empty
    ):

        logger.warning(
            "Cannot generate signal: empty 1H data."
        )

        return {
            "action": "HOLD",
            "strategy_version": STRATEGY_VERSION,
        }

    last = df_1h.iloc[-1]

    price = _safe_float(
        last.get("close")
    )

    atr = _safe_float(
        last.get("atr")
    )

    if (
        price <= 0
        or atr <= 0
    ):

        logger.warning(
            "Invalid price/ATR. Returning HOLD."
        )

        return _hold_signal(
            price,
            current_candle_close_time,
        )

    signal = _hold_signal(
        price,
        current_candle_close_time,
    )

    # ========================================================
    # Required indicators
    # ========================================================

    rsi = last.get("rsi")
    mfi = last.get("mfi")

    ema50 = last.get(
        f"ema_{EMA_50_PERIOD}"
    )

    ema200 = last.get(
        f"ema_{EMA_200_PERIOD}"
    )

    bb_lower = last.get(
        "bb_lower"
    )

    bb_upper = last.get(
        "bb_upper"
    )

    vol_sma = last.get(
        "vol_sma"
    )

    values = [
        rsi,
        mfi,
        ema50,
        ema200,
        bb_lower,
        bb_upper,
    ]

    if not all(
        _has_valid_indicator(value)
        for value in values
    ):

        logger.warning(
            "Missing/invalid indicators. "
            "Returning HOLD."
        )

        return signal

    rsi = _safe_float(rsi)
    mfi = _safe_float(mfi)

    ema50 = _safe_float(ema50)
    ema200 = _safe_float(ema200)

    bb_lower = _safe_float(bb_lower)
    bb_upper = _safe_float(bb_upper)

    volume = _safe_float(
        last.get("volume")
    )

    vol_sma_value = _safe_float(
        vol_sma
    )

    # ========================================================
    # DEAD CHOP
    # ========================================================

    if regime == REGIME_DEAD_CHOP:

        return signal

    # ========================================================
    # Previous candle
    # ========================================================

    if len(df_1h) < 2:

        return signal

    previous = df_1h.iloc[-2]

    previous_close = _safe_float(
        previous.get("close")
    )

    previous_ema50 = _safe_float(
        previous.get(
            f"ema_{EMA_50_PERIOD}"
        )
    )

    # ========================================================
    # EMA50 CROSS
    # ========================================================

    cross_up = (
        previous_close
        <= previous_ema50
        and price > ema50
    )

    cross_down = (
        previous_close
        >= previous_ema50
        and price < ema50
    )

    # ========================================================
    # RISK / TP / SL
    # ========================================================

    if regime == REGIME_STRONG_BULL:

        risk_pct = (
            config.STRONG_REGIME_RISK_PCT
        )

    else:

        risk_pct = (
            config.NORMAL_REGIME_RISK_PCT
        )

    tp_mult = (
        config.TP_ATR_MULTIPLIER
    )

    sl_mult = (
        config.SL_ATR_MULTIPLIER
    )

    # ========================================================
    # BULLISH REGIMES
    # ========================================================

    if regime in (
        REGIME_STRONG_BULL,
        REGIME_WEAK_BULL,
    ):

        # -----------------------------------------------
        # LONG
        # -----------------------------------------------

        volume_ok = (
            vol_sma_value <= 0
            or volume > vol_sma_value
        )

        momentum_ok = (
            rsi >= RSI_BULL_ENTRY
            and mfi > MFI_OVERSOLD_LONG
        )

        if (
            cross_up
            and momentum_ok
            and volume_ok
        ):

            stop_price = (
                price
                - sl_mult * atr
            )

            take_profit_price = (
                price
                + tp_mult * atr
            )

            signal.update({

                "action": "BUY_LONG",

                "risk_pct": risk_pct,

                "tp_mult": tp_mult,

                "sl_mult": sl_mult,

                "entry_price": price,

                "stop_price": stop_price,

                "take_profit_price":
                    take_profit_price,

            })

            logger.info(
                f"LONG signal | "
                f"Regime={regime} | "
                f"Price={price:.8g} | "
                f"RSI={rsi:.2f} | "
                f"MFI={mfi:.2f}"
            )

            return signal

    # ========================================================
    # BEARISH REGIMES
    # ========================================================

    if regime in (
        REGIME_STRONG_BEAR,
        REGIME_WEAK_BEAR,
    ):

        volume_ok = (
            vol_sma_value <= 0
            or volume > vol_sma_value
        )

        momentum_ok = (
            rsi <= RSI_BEAR_ENTRY
            and mfi < MFI_OVERBOUGHT_SHORT
        )

        if (
            cross_down
            and momentum_ok
            and volume_ok
        ):

            stop_price = (
                price
                + sl_mult * atr
            )

            take_profit_price = (
                price
                - tp_mult * atr
            )

            signal.update({

                "action": "SELL_SHORT",

                "risk_pct": risk_pct,

                "tp_mult": tp_mult,

                "sl_mult": sl_mult,

                "entry_price": price,

                "stop_price": stop_price,

                "take_profit_price":
                    take_profit_price,

            })

            logger.info(
                f"SHORT signal | "
                f"Regime={regime} | "
                f"Price={price:.8g} | "
                f"RSI={rsi:.2f} | "
                f"MFI={mfi:.2f}"
            )

            return signal

    # ========================================================
    # GOOD RANGE
    # ========================================================

    if regime == REGIME_GOOD_RANGE:

        # In a range we do NOT want to blindly buy simply
        # because price touched the lower band.
        #
        # We want:
        #   previous candle at/below lower band
        #   current candle back above lower band
        #   RSI/MFI still indicate recovery
        #
        # This makes the signal a re-entry rather than
        # catching a falling knife.

        previous_bb_lower = _safe_float(
            previous.get("bb_lower")
        )

        previous_bb_upper = _safe_float(
            previous.get("bb_upper")
        )

        previous_rsi = _safe_float(
            previous.get("rsi")
        )

        previous_mfi = _safe_float(
            previous.get("mfi")
        )

        # -----------------------------------------------
        # Range LONG
        # -----------------------------------------------

        range_long_reentry = (
            previous_close
            <= previous_bb_lower
            and price > bb_lower
        )

        range_long_momentum = (
            previous_rsi
            <= RSI_OVERSOLD_LONG
            and rsi > previous_rsi
            and previous_mfi
            <= MFI_OVERSOLD_LONG
            and mfi > previous_mfi
        )

        if (
            range_long_reentry
            and range_long_momentum
        ):

            stop_price = (
                price
                - sl_mult * atr
            )

            take_profit_price = (
                price
                + tp_mult * atr
            )

            signal.update({

                "action": "BUY_LONG",

                "risk_pct":
                    config.NORMAL_REGIME_RISK_PCT,

                "tp_mult": tp_mult,

                "sl_mult": sl_mult,

                "entry_price": price,

                "stop_price": stop_price,

                "take_profit_price":
                    take_profit_price,

            })

            logger.info(
                f"RANGE LONG signal | "
                f"Price={price:.8g} | "
                f"RSI={rsi:.2f} | "
                f"MFI={mfi:.2f}"
            )

            return signal

        # -----------------------------------------------
        # Range SHORT
        # -----------------------------------------------

        range_short_reentry = (
            previous_close
            >= previous_bb_upper
            and price < bb_upper
        )

        range_short_momentum = (
            previous_rsi
            >= RSI_OVERBOUGHT_SHORT
            and rsi < previous_rsi
            and previous_mfi
            >= MFI_OVERBOUGHT_SHORT
            and mfi < previous_mfi
        )

        if (
            range_short_reentry
            and range_short_momentum
        ):

            stop_price = (
                price
                + sl_mult * atr
            )

            take_profit_price = (
                price
                - tp_mult * atr
            )

            signal.update({

                "action": "SELL_SHORT",

                "risk_pct":
                    config.NORMAL_REGIME_RISK_PCT,

                "tp_mult": tp_mult,

                "sl_mult": sl_mult,

                "entry_price": price,

                "stop_price": stop_price,

                "take_profit_price":
                    take_profit_price,

            })

            logger.info(
                f"RANGE SHORT signal | "
                f"Price={price:.8g} | "
                f"RSI={rsi:.2f} | "
                f"MFI={mfi:.2f}"
            )

            return signal

    return signal


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    print(
        "SHERPA strategy module loaded successfully."
    )

    print(
        f"Strategy version: {STRATEGY_VERSION}"
    )

    print(
        f"TP multiplier: "
        f"{config.TP_ATR_MULTIPLIER}"
    )

    print(
        f"SL multiplier: "
        f"{config.SL_ATR_MULTIPLIER}"
    )

    print(
        f"Strong risk: "
        f"{config.STRONG_REGIME_RISK_PCT}"
    )

    print(
        f"Normal risk: "
        f"{config.NORMAL_REGIME_RISK_PCT}"
    )
