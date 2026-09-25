"""
Technical Indicators Calculation Module.

This module provides functions to calculate various technical indicators
required by the trading strategy. It takes a Pandas DataFrame of kline data
as input and adds new columns for each calculated indicator.

Supported Indicators:
- Exponential Moving Averages (EMA)
- Relative Strength Index (RSI)
- Average True Range (ATR)
- Bollinger Bands (BB)
- Moving Average Convergence Divergence (MACD) - Not used in current logic but kept for reference
- Average Directional Index (ADX)
- Money Flow Index (MFI)
- Volume Moving Average (vol_sma) - Used in the older strategy logic, adapted for current
"""

import pandas as pd
from typing import List

# Configure logger for this module
import logging
logger = logging.getLogger(__name__)

# Constants for indicator calculations
# These might be adjusted based on specific trading strategies or market conditions.
EMA_SHORT_PERIOD = 5   # Shorter EMA for trend direction
EMA_MEDIUM_PERIOD = 15  # Medium EMA for trend direction (used in old strategy.py)
EMA_50_PERIOD = 50      # EMA 50 for trend direction (used in main.py strategy)
EMA_200_PERIOD = 200    # EMA 200 for trend direction (used in main.py strategy)
RSI_PERIOD = 14
ATR_PERIOD = 14
BB_PERIOD = 20
BB_STD_DEV = 2
ADX_PERIOD = 14
MFI_PERIOD = 14
VOL_SMA_PERIOD = 20 # Period for Volume Simple Moving Average

def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate a comprehensive set of technical indicators and add them as columns to the DataFrame.

    Handles potential NaN values at the beginning of the series due to lookback periods.

    Args:
        df (pd.DataFrame): Input DataFrame with columns:
                           'timestamp', 'open', 'high', 'low', 'close', 'volume'.

    Returns:
        pd.DataFrame: The input DataFrame with added columns for each calculated indicator.
                      Returns an empty DataFrame if input is insufficient or invalid.
    """
    if df.empty or not all(col in df.columns for col in ['open', 'high', 'low', 'close', 'volume']):
        logger.warning("Input DataFrame is empty or missing required columns (open, high, low, close, volume).")
        return pd.DataFrame()

    # Ensure data is sorted by time, important for indicator calculations
    df = df.sort_values(by='timestamp').reset_index(drop=True)

    # --- Exponential Moving Averages (EMAs) ---
    # EMAs used in the current main.py strategy
    df[f'ema_{EMA_50_PERIOD}'] = df['close'].ewm(span=EMA_50_PERIOD, adjust=False).mean()
    df[f'ema_{EMA_200_PERIOD}'] = df['close'].ewm(span=EMA_200_PERIOD, adjust=False).mean()

    # EMAs used in the older strategy.py (kept for compatibility if needed)
    df[f'EMA_{EMA_SHORT_PERIOD}'] = df['close'].ewm(span=EMA_SHORT_PERIOD, adjust=False).mean()
    df[f'EMA_{EMA_MEDIUM_PERIOD}'] = df['close'].ewm(span=EMA_MEDIUM_PERIOD, adjust=False).mean()

    # --- RSI (Relative Strength Index) ---
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.ewm(span=RSI_PERIOD, adjust=False).mean()
    avg_loss = loss.ewm(span=RSI_PERIOD, adjust=False).mean()

    rs = avg_gain / avg_loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # --- ATR (Average True Range) ---
    # Calculate True Range (TR)
    high_low = df['high'] - df['low']
    high_close = abs(df['high'] - df['close'].shift())
    low_close = abs(df['low'] - df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    
    df['TR'] = tr
    df['ATR'] = df['TR'].ewm(span=ATR_PERIOD, adjust=False).mean()
    df.drop('TR', axis=1, inplace=True) # Drop intermediate TR column

    # --- Bollinger Bands (BB) ---
    df['bb_middle'] = df['close'].rolling(window=BB_PERIOD).mean()
    df['bb_std'] = df['close'].rolling(window=BB_PERIOD).std()
    df['bb_upper'] = df['bb_middle'] + (df['bb_std'] * BB_STD_DEV)
    df['bb_lower'] = df['bb_middle'] - (df['bb_std'] * BB_STD_DEV)

    # --- ADX (Average Directional Index) ---
    # Requires calculation of Directional Movement (+DM, -DM) and Directional Indices (DI+, DI-)
    df['upmove'] = df['high'] - df['high'].shift(1)
    df['downmove'] = df['low'].shift(1) - df['low']
    
    df['+DM'] = 0.0
    df['-DM'] = 0.0
    
    # Determine +DM and -DM
    # Using EMA for smoothing to match some libraries, could use rolling mean too
    df['+DM'] = ((df['upmove'] > df['downmove']) & (df['upmove'] > 0)) * df['upmove']
    df['-DM'] = ((df['downmove'] > df['upmove']) & (df['downmove'] > 0)) * df['downmove']

    # Calculate DI+ and DI- using EMA (similar to ATR calculation smoothing)
    df['+DI'] = df['+DM'].ewm(span=ADX_PERIOD, adjust=False).mean()
    df['-DI'] = df['-DI'].ewm(span=ADX_PERIOD, adjust=False).mean()

    df['DI_diff'] = abs(df['+DI'] - df['-DI'])
    df['DI_sum'] = df['+DI'] + df['-DI']

    # Calculate ADX
    # Avoid division by zero if DI_sum is zero
    df['ADX'] = (df['DI_diff'] / df['DI_sum']) * 100 if (df['DI_sum'] != 0).any() else 0.0
    df['ADX'] = df['ADX'].ewm(span=ADX_PERIOD, adjust=False).mean() # Smoothed ADX

    # Clean up intermediate columns used for ADX calculation
    df.drop(['upmove', 'downmove', '+DM', '-DM', '+DI', '-DI', 'DI_diff', 'DI_sum'], axis=1, inplace=True, errors='ignore')

    # --- MFI (Money Flow Index) ---
    df['Typical Price'] = (df['high'] + df['low'] + df['close']) / 3
    df['Raw Money Flow'] = df['Typical Price'] * df['volume']

    # Calculate positive and negative money flow over the MFI period
    money_flow_direction = pd.Series(0.0, index=df.index)
    money_flow_direction[df['Typical Price'].diff() > 0] = 1 # Positive flow
    money_flow_direction[df['Typical Price'].diff() < 0] = -1 # Negative flow

    positive_mf = (df['Raw Money Flow'] * money_flow_direction.where(money_flow_direction > 0, 0)).rolling(window=MFI_PERIOD).sum()
    negative_mf = (df['Raw Money Flow'] * money_flow_direction.where(money_flow_direction < 0, 0)).rolling(window=MFI_PERIOD).sum()
    
    money_ratio = positive_mf / negative_mf
    df['MFI'] = 100 - (100 / (1 + money_ratio))
    
    # Fill NaN for MFI if negative_mf is zero
    df['MFI'] = df['MFI'].fillna(100) # If negative MF is 0, MFI is 100

    # --- Volume Moving Average ---
    df['vol_sma'] = df['volume'].rolling(window=VOL_SMA_PERIOD).mean()


    # --- MACD (Moving Average Convergence Divergence) ---
    # Optional: Can be added if needed by a different strategy logic.
    # MACD_FAST_PERIOD = 12
    # MACD_SLOW_PERIOD = 26
    # MACD_SIGNAL_PERIOD = 9
    # df['MACD_diff'] = df['close'].ewm(span=MACD_FAST_PERIOD, adjust=False).mean() - \
    #                   df['close'].ewm(span=MACD_SLOW_PERIOD, adjust=False).mean()
    # df['MACD_signal'] = df['MACD_diff'].ewm(span=MACD_SIGNAL_PERIOD, adjust=False).mean()
    # df['MACD'] = df['MACD_diff'] - df['MACD_signal']

    # Drop intermediate columns if they are not meant for final output
    df.drop(['Typical Price', 'Raw Money Flow'], axis=1, inplace=True, errors='ignore')

    # Important: Handle NaNs at the beginning. These are expected due to lookback periods.
    # The calling functions (e.g., strategy.py, main.py) should handle these.
    # For example, by ensuring enough data points are available before processing.
    
    logger.debug(f"Calculated indicators for DataFrame with shape: {df.shape}")
    return df

# Example of how to use this module (for testing purposes)
if __name__ == "__main__":
    # Mock data for testing
    data = {
        'timestamp': pd.date_range(start='2023-01-01', periods=200, freq='60min', tz='UTC'),
        'open': [100 + i*0.1 for i in range(200)],
        'high': [101 + i*0.1 for i in range(200)],
        'low': [99 - i*0.1 for i in range(200)],
        'close': [100.5 + i*0.1 for i in range(200)],
        'volume': [1000 + i*10 for i in range(200)]
    }
    test_df = pd.DataFrame(data)
    
    # Add some volatility for ATR and BB
    test_df['high'] = test_df['high'] + 2
    test_df['low'] = test_df['low'] - 2

    print("Original DataFrame Head:")
    print(test_df.head())

    print("\nCalculating indicators...")
    indicators_df = calculate_indicators(test_df.copy()) # Use copy to not modify original

    print("\nDataFrame with Indicators Head:")
    print(indicators_df.head())
    
    print("\nDataFrame with Indicators Tail:")
    print(indicators_df.tail())

    print("\nDataFrame Info:")
    indicators_df.info()
