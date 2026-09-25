"""
Trading Strategy Module.

This module defines the core logic for generating trading signals based on
market data and the detected market regime. It encompasses:
1. Market Regime Detection: Classifying the market into distinct states (e.g., Bullish, Bearish, Ranging, Choppy).
2. Signal Generation: Deciding on the trading action (BUY_LONG, SELL_SHORT, HOLD) and associated risk parameters.

The strategy aims to be trend-following in trending markets and mean-reverting in ranging markets,
while avoiding trades in highly volatile or directionless (choppy) conditions.

This module relies on indicators calculated by the `indicators.py` module.
"""

import pandas as pd
import logging

import config
from strategy.indicators import (
    EMA_SHORT_PERIOD, EMA_MEDIUM_PERIOD, EMA_50_PERIOD, EMA_200_PERIOD,
    RSI_PERIOD, ATR_PERIOD, BB_PERIOD, BB_STD_DEV, ADX_PERIOD, MFI_PERIOD, VOL_SMA_PERIOD
)

logger = logging.getLogger(__name__)

# Define constants for market regimes
REGIME_DEAD_CHOP = "DEAD_CHOP"
REGIME_GOOD_RANGE = "GOOD_RANGE"
REGIME_STRONG_BULL = "STRONG_BULL"
REGIME_WEAK_BULL = "WEAK_BULL"
REGIME_STRONG_BEAR = "STRONG_BEAR"
REGIME_WEAK_BEAR = "WEAK_BEAR"

# Thresholds used in regime detection (can be tuned)
ADX_LOW_THRESHOLD = 18  # ADX below this is considered weak trend
ADX_MEDIUM_THRESHOLD = 25 # ADX between low and medium is good for ranging/moderate trends
ADX_HIGH_THRESHOLD = 30 # ADX above this is considered strong trend

# RSI thresholds for entry signals
RSI_OVERSOLD_LONG = 35
RSI_OVERBOUGHT_SHORT = 65
RSI_BULL_ENTRY = 55
RSI_BEAR_ENTRY = 45

# MFI thresholds for entry signals
MFI_OVERSOLD_LONG = 30
MFI_OVERBOUGHT_SHORT = 70

# Bollinger Bands width threshold for 'DEAD_CHOP' detection
BB_WIDTH_THRESHOLD_CHOP = 0.02

# Strategy Version (should align with config or be managed separately)
STRATEGY_VERSION = "EMA50-CROSS-V1" # Example version, adjust as needed


def detect_market_regime(
    df_1d: pd.DataFrame,
    df_1h: pd.DataFrame
) -> str:
    """
    Determine the current market regime using daily and hourly indicators.

    This function combines signals from different timeframes and indicators
    to classify the market into one of several defined regimes.

    Args:
        df_1d (pd.DataFrame): DataFrame containing daily data with indicators.
        df_1h (pd.DataFrame): DataFrame containing hourly data with indicators.

    Returns:
        str: The detected market regime (e.g., "STRONG_BULLISH", "WEAK_BEARISH", "CHOP_DEAD").
    """
    if df_1d.empty or df_1h.empty:
        logger.warning("Daily or hourly DataFrame is empty, cannot detect market regime.")
        return REGIME_DEAD_CHOP # Default to dead chop if data is insufficient

    # Use the latest closed candle from each timeframe
    d1_last = df_1d.iloc[-1]
    h1_last = df_1h.iloc[-1]

    # --- Calculate derived indicators ---
    # Bollinger Band width as a percentage of the middle band
    bb_middle = h1_last.get('bb_middle', 0)
    bb_upper = h1_last.get('bb_upper', 0)
    bb_lower = h1_last.get('bb_lower', 0)

    bb_width_pct = 0.0
    if bb_middle and bb_middle != 0:
        bb_width_pct = (bb_upper - bb_lower) / bb_middle

    # Extract key indicators
    adx = h1_last.get('adx', 0)
    ema_50_daily = d1_last.get(f'ema_{EMA_50_PERIOD}', 0)
    close_daily = d1_last.get('close', 0)
    ema_50_hourly = h1_last.get(f'ema_{EMA_50_PERIOD}', 0)
    ema_200_hourly = h1_last.get(f'ema_{EMA_200_PERIOD}', 0)

    # --- Regime Logic ---

    # 1. CHOP_DEAD: Very low volatility and weak trend strength.
    # Conditions: Narrow Bollinger Bands AND low ADX.
    if bb_width_pct < BB_WIDTH_THRESHOLD_CHOP and adx < ADX_LOW_THRESHOLD:
        logger.debug(f"Regime: CHOP_DEAD (BB Width: {bb_width_pct:.4f}, ADX: {adx:.2f})")
        return REGIME_DEAD_CHOP

    # 2. BULLISH REGIMES: Determined by alignment of daily close vs EMA50 and hourly EMAs.
    if close_daily > ema_50_daily and ema_50_hourly > ema_200_hourly:
        if adx > ADX_HIGH_THRESHOLD:
            logger.debug(f"Regime: STRONG_BULLISH (ADX: {adx:.2f})")
            return REGIME_STRONG_BULL
        elif adx > ADX_MEDIUM_THRESHOLD: # Use medium threshold here for weak bullish
            logger.debug(f"Regime: WEAK_BULLISH (ADX: {adx:.2f})")
            return REGIME_WEAK_BULL
        else: # If ADX is low but trends align, still consider it weak bullish
            logger.debug(f"Regime: WEAK_BULLISH (ADX: {adx:.2f}) - Trend alignment without strong ADX")
            return REGIME_WEAK_BULL

    # 3. BEARISH REGIMES: Determined by alignment of daily close vs EMA50 and hourly EMAs.
    if close_daily < ema_50_daily and ema_50_hourly < ema_200_hourly:
        if adx > ADX_HIGH_THRESHOLD:
            logger.debug(f"Regime: STRONG_BEARISH (ADX: {adx:.2f})")
            return REGIME_STRONG_BEAR
        elif adx > ADX_MEDIUM_THRESHOLD: # Use medium threshold here for weak bearish
            logger.debug(f"Regime: WEAK_BEARISH (ADX: {adx:.2f})")
            return REGIME_WEAK_BEAR
        else: # If ADX is low but trends align, still consider it weak bearish
            logger.debug(f"Regime: WEAK_BEARISH (ADX: {adx:.2f}) - Trend alignment without strong ADX")
            return REGIME_WEAK_BEAR

    # 4. GOOD_RANGING: Moderate ADX suggests a range or sideways movement that might be tradable.
    # This condition captures cases where trends don't clearly align but ADX is moderate.
    if ADX_LOW_THRESHOLD <= adx <= ADX_HIGH_THRESHOLD: # Adjusted range for GOOD_RANGING
        logger.debug(f"Regime: GOOD_RANGING (ADX: {adx:.2f})")
        return REGIME_GOOD_RANGE

    # Fallback regime if none of the above conditions are met (e.g., unusual indicator values)
    logger.warning(f"Falling back to CHOP_DEAD regime. Conditions not met: BB Width: {bb_width_pct:.4f}, ADX: {adx:.2f}")
    return REGIME_DEAD_CHOP


def generate_signals(
    df_1h: pd.DataFrame,
    regime: str,
    current_candle_close_time: pd.Timestamp
) -> dict:
    """
    Generate a trading signal (action and parameters) based on the current market state.

    This function implements the entry logic for LONG and SHORT positions,
    considering the market regime and specific indicator conditions.

    Args:
        df_1h (pd.DataFrame): DataFrame of the *latest closed* hourly candle with all indicators.
        regime (str): The current market regime detected by `detect_market_regime`.
        current_candle_close_time (pd.Timestamp): The close time of the candle being evaluated.

    Returns:
        dict: A dictionary containing the trading signal:
              - "action": "BUY_LONG", "SELL_SHORT", or "HOLD".
              - "risk_pct": Capital percentage to risk for this trade (if action is not HOLD).
              - "tp_mult": ATR multiplier for Take Profit (if action is not HOLD).
              - "sl_mult": ATR multiplier for Stop Loss (if action is not HOLD).
              - "entry_price": The price at which the trade signal is generated.
              - "stop_price": The initial stop loss price.
              - "take_profit_price": The initial take profit price.
              - "signal_candle_time": The close time of the candle that generated the signal.
    """
    if df_1h.empty:
        logger.warning("Hourly DataFrame is empty, cannot generate signals.")
        return {"action": "HOLD"}

    # Use the last row of the DataFrame (which represents the latest closed candle)
    last = df_1h.iloc[-1]

    # Extract key values needed for signal generation
    price = last['close']
    atr = last['atr']
    rsi = last['rsi']
    mfi = last['mfi']
    ema_50 = last[f'ema_{EMA_50_PERIOD}']
    ema_200 = last[f'ema_{EMA_200_PERIOD}']
    bb_lower = last['bb_lower']
    bb_upper = last['bb_upper']
    volume = last['volume']
    vol_sma = last.get('vol_sma', 0) # Handle potential missing vol_sma if not calculated

    # --- Default Signal: HOLD ---
    # If no entry conditions are met, the default action is to hold.
    signal = {
        "action": "HOLD",
        "risk_pct": 0.0,
        "tp_mult": 0.0,
        "sl_mult": 0.0,
        "entry_price": price,
        "stop_price": price,
        "take_profit_price": price,
        "signal_candle_time": current_candle_close_time
    }

    # --- No Trading in Dead Chop Regime ---
    if regime == REGIME_DEAD_CHOP:
        logger.debug("Regime is DEAD_CHOP. No trading signals generated.")
        return signal

    # --- Entry Logic based on Regime ---

    # 1. GOOD_RANGE: Mean Reversion Strategy
    if regime == REGIME_GOOD_RANGE:
        # LONG Entry Condition: Price hits lower Bollinger Band, RSI oversold, MFI oversold
        if (
            price < bb_lower
            and rsi < RSI_OVERSOLD_LONG
            and mfi < MFI_OVERSOLD_LONG
        ):
            signal.update({
                "action": "BUY_LONG",
                "risk_pct": config.NORMAL_REGIME_RISK_PCT, # Standard risk for normal regimes
                "tp_mult": 1.5, # TP multiplier for ranging markets
                "sl_mult": 1.2, # SL multiplier for ranging markets
                "entry_price": price,
                "stop_price": price - ATR_PERIOD * atr, # Initial SL based on ATR
                "take_profit_price": price + 1.5 * atr, # Initial TP based on ATR
            })
            logger.debug(f"Generated BUY_LONG signal in {regime} regime.")

        # SHORT Entry Condition: Price hits upper Bollinger Band, RSI overbought, MFI overbought
        elif (
            price > bb_upper
            and rsi > RSI_OVERBOUGHT_SHORT
            and mfi > MFI_OVERBOUGHT_SHORT
        ):
            signal.update({
                "action": "SELL_SHORT",
                "risk_pct": config.NORMAL_REGIME_RISK_PCT,
                "tp_mult": 1.5,
                "sl_mult": 1.2,
                "entry_price": price,
                "stop_price": price + ATR_PERIOD * atr, # Initial SL based on ATR
                "take_profit_price": price - 1.5 * atr, # Initial TP based on ATR
            })
            logger.debug(f"Generated SELL_SHORT signal in {regime} regime.")

    # 2. BULLISH REGIMES: Trend Following Strategy
    # Conditions: EMA50 > EMA200, RSI above bull threshold, Volume confirmation.
    elif REGIME_STRONG_BULL in regime or REGIME_WEAK_BULL in regime:
        # Check for EMA50 crossover up (main.py logic uses this)
        # Need previous candle's data for crossover detection
        if len(df_1h) >= 2:
            prev = df_1h.iloc[-2]
            ema_50_prev = prev[f'ema_{EMA_50_PERIOD}']
            close_prev = prev['close']

            ema_cross_up = (close_prev <= ema_50_prev) and (price > ema_50)

            if (
                ema_cross_up # EMA50 cross up
                and rsi > RSI_BULL_ENTRY
                # and mfi < MFI_OVERBOUGHT_SHORT # Optional: Avoid entering if heavily overbought
                and volume > vol_sma # Volume confirmation for trend
            ):
                risk = config.STRONG_REGIME_RISK_PCT if regime == REGIME_STRONG_BULL else config.NORMAL_REGIME_RISK_PCT
                signal.update({
                    "action": "BUY_LONG",
                    "risk_pct": risk,
                    "tp_mult": 3.0, # TP multiplier for trending markets (larger)
                    "sl_mult": 1.5, # SL multiplier for trending markets
                    "entry_price": price,
                    "stop_price": price - ATR_PERIOD * atr, # Initial SL based on ATR
                    "take_profit_price": price + 3.0 * atr, # Initial TP based on ATR
                })
                logger.debug(f"Generated BUY_LONG signal in {regime} regime.")

    # 3. BEARISH REGIMES: Trend Following Strategy
    # Conditions: EMA50 < EMA200, RSI below bear threshold, Volume confirmation.
    elif REGIME_STRONG_BEAR in regime or REGIME_WEAK_BEAR in regime:
        # Check for EMA50 crossover down
        if len(df_1h) >= 2:
            prev = df_1h.iloc[-2]
            ema_50_prev = prev[f'ema_{EMA_50_PERIOD}']
            close_prev = prev['close']

            ema_cross_down = (close_prev >= ema_50_prev) and (price < ema_50)

            if (
                ema_cross_down # EMA50 cross down
                and rsi < RSI_BEAR_ENTRY
                # and mfi > MFI_OVERSOLD_LONG # Optional: Avoid entering if heavily oversold
                and volume > vol_sma # Volume confirmation for trend
            ):
                risk = config.STRONG_REGIME_RISK_PCT if regime == REGIME_STRONG_BEAR else config.NORMAL_REGIME_RISK_PCT
                signal.update({
                    "action": "SELL_SHORT",
                    "risk_pct": risk,
                    "tp_mult": 3.0,
                    "sl_mult": 1.5,
                    "entry_price": price,
                    "stop_price": price + ATR_PERIOD * atr, # Initial SL based on ATR
                    "take_profit_price": price - 3.0 * atr, # Initial TP based on ATR
                })
                logger.debug(f"Generated SELL_SHORT signal in {regime} regime.")

    # If no specific entry conditions were met, the default HOLD signal is returned.
    return signal


# --- Example Usage ---
if __name__ == "__main__":
    # Mock data for testing
    logging.basicConfig(level=logging.DEBUG, format=config.LOGGING_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")
    
    # Dummy DataFrame structure needed for testing
    # This requires indicators to be pre-calculated or mocked.
    # Let's simulate a DataFrame with indicators for demonstration.

    # Simulate a DataFrame with enough data points and indicators
    mock_data_1h = {
        'timestamp': pd.date_range(start='2023-01-01', periods=300, freq='60min', tz='UTC'),
        'open': [100 + i*0.1 for i in range(300)],
        'high': [101 + i*0.1 for i in range(300)],
        'low': [99 - i*0.1 for i in range(300)],
        'close': [100.5 + i*0.1 for i in range(300)],
        'volume': [1000 + i*10 for i in range(300)],
        'ema_50': [100.2 + i*0.05 for i in range(300)], # Mock EMA values
        'ema_200': [99.8 + i*0.02 for i in range(300)],
        'rsi': [50 + i*0.1 for i in range(300)],
        'atr': [1.0 + i*0.01 for i in range(300)],
        'bb_middle': [100.5 + i*0.1 for i in range(300)],
        'bb_upper': [102.0 + i*0.1 for i in range(300)],
        'bb_lower': [99.0 + i*0.1 for i in range(300)],
        'adx': [20 + i*0.1 for i in range(300)],
        'mfi': [50 + i*0.1 for i in range(300)],
        'vol_sma': [1050 + i*5 for i in range(300)]
    }
    df_1h_test = pd.DataFrame(mock_data_1h)

    mock_data_1d = {
        'timestamp': pd.date_range(start='2023-01-01', periods=300, freq='1d', tz='UTC'),
        'close': [100.5 + i*0.5 for i in range(300)],
        f'ema_{EMA_50_PERIOD}': [100.2 + i*0.2 for i in range(300)],
    }
    df_1d_test = pd.DataFrame(mock_data_1d)

    # Test regime detection
    print("\n--- Testing Regime Detection ---")
    test_regimes = [
        ("STRONG_BULLISH", REGIME_STRONG_BULL),
        ("WEAK_BULLISH", REGIME_WEAK_BULL),
        ("STRONG_BEARISH", REGIME_STRONG_BEAR),
        ("WEAK_BEARISH", REGIME_WEAK_BEAR),
        ("GOOD_RANGING", REGIME_GOOD_RANGE),
        ("DEAD_CHOP", REGIME_DEAD_CHOP),
    ]
    
    # Modify mock data to simulate different regimes for testing
    for regime_name, expected_regime in test_regimes:
        # Adjust mock data based on regime characteristics for testing
        if "BULL" in regime_name:
            df_1h_test['close'] = df_1h_test['ema_50'] + 0.5
            df_1h_test['ema_50'] = df_1h_test['ema_200'] + 0.2
            df_1h_test['adx'] = 35 if "STRONG" in regime_name else 20
            df_1d_test['close'] = df_1d_test[f'ema_{EMA_50_PERIOD}'] + 0.5
        elif "BEAR" in regime_name:
            df_1h_test['close'] = df_1h_test['ema_50'] - 0.5
            df_1h_test['ema_50'] = df_1h_test['ema_200'] - 0.2
            df_1h_test['adx'] = 35 if "STRONG" in regime_name else 20
            df_1d_test['close'] = df_1d_test[f'ema_{EMA_50_PERIOD}'] - 0.5
        elif "RANGE" in regime_name:
            df_1h_test['adx'] = 22
            df_1h_test['close'] = df_1h_test['bb_middle'] + (df_1h_test['bb_upper'] - df_1h_test['bb_lower']) / 4 # Mid-range
            df_1d_test['close'] = df_1d_test[f'ema_{EMA_50_PERIOD}'] # Close near EMA
        elif "CHOP" in regime_name:
            df_1h_test['adx'] = 10
            df_1h_test['bb_upper'] = df_1h_test['bb_middle'] + 0.01 * df_1h_test['bb_middle']
            df_1h_test['bb_lower'] = df_1h_test['bb_middle'] - 0.01 * df_1h_test['bb_middle']
            df_1d_test['close'] = df_1d_test[f'ema_{EMA_50_PERIOD}'] # Close near EMA

        detected_regime = detect_market_regime(df_1d_test.tail(1), df_1h_test.tail(1))
        print(f"Test for '{regime_name}': Detected = {detected_regime}")
        assert detected_regime == expected_regime, f"Mismatch: Expected {expected_regime}, got {detected_regime}"

    # Test signal generation (use a specific regime scenario)
    print("\n--- Testing Signal Generation ---")
    # Simulate a WEAK_BULLISH scenario for signal generation
    df_1h_test['close'] = df_1h_test['ema_50'] + 0.1 # Slightly above EMA50
    df_1h_test['ema_50'] = df_1h_test['ema_200'] + 0.1 # EMA50 > EMA200
    df_1h_test['rsi'] = RSI_BULL_ENTRY + 5 # Above bull entry RSI
    df_1h_test['adx'] = ADX_MEDIUM_THRESHOLD + 5 # Above medium ADX
    df_1h_test['volume'] = df_1h_test['vol_sma'] + 500 # Volume confirmation
    df_1d_test['close'] = df_1d_test[f'ema_{EMA_50_PERIOD}'] + 0.2 # Daily close above EMA
    
    # Ensure enough data for crossover check
    if len(df_1h_test) >= 2:
        df_1h_test.iloc[-2, df_1h_test.columns.get_loc('close')] = df_1h_test.iloc[-2]['ema_50'] - 0.1 # Simulate previous close below EMA50
        df_1h_test.iloc[-2, df_1h_test.columns.get_loc(f'ema_{EMA_50_PERIOD}')] = df_1h_test.iloc[-2]['ema_200'] + 0.05

        current_regime = detect_market_regime(df_1d_test.tail(1), df_1h_test.tail(1))
        print(f"Current Simulated Regime for Signal Test: {current_regime}")

        signal = generate_signals(df_1h_test.tail(1), current_regime, df_1h_test['timestamp'].iloc[-1])
        print(f"Generated Signal: {signal}")

        assert signal["action"] == "BUY_LONG"
        assert signal["risk_pct"] == config.NORMAL_REGIME_RISK_PCT
        assert signal["tp_mult"] == 3.0
        assert signal["sl_mult"] == 1.5

    else:
        print("Not enough data points to simulate crossover for signal generation test.")
