"""
MEXC Data Provider Module.

Handles fetching historical and current market klines (candlesticks)
from the MEXC exchange API. It ensures that only completed candles
are returned to prevent look-ahead bias in the trading strategy.
"""

import logging
import requests
import pandas as pd
from datetime import datetime, timezone

import config

# Configure logger for this module
logger = logging.getLogger(__name__)

def fetch_mexc_klines(
    symbol: str,
    interval: str = "60m",
    limit: int = 300
) -> pd.DataFrame:
    """
    Fetch OHLCV candles from MEXC for a given symbol and interval.

    The function retrieves data and filters out the currently-forming candle.
    This is crucial for ensuring that the trading strategy operates only
    on complete historical data.

    Args:
        symbol (str): The trading pair symbol (e.g., "BTCUSDT").
        interval (str): The candle interval (e.g., "60m", "1d").
        limit (int): The maximum number of candles to retrieve.

    Returns:
        pd.DataFrame: A DataFrame containing historical kline data,
                      with columns for timestamp, open, high, low, close,
                      volume, close_time, and quote asset volume.
                      The DataFrame is sorted by time and the last
                      (currently forming) candle is excluded.

    Raises:
        requests.exceptions.RequestException: If the API request fails.
        ValueError: If the returned data is not in the expected format.
    """
    api_url = config.MEXC_API_URL
    
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }

    try:
        response = requests.get(
            api_url,
            params=params,
            headers={"User-Agent": "Mozilla/5.0"}, # Mimic browser for potential API restrictions
            timeout=10 # Set a timeout for the request
        )
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)

        data = response.json()

        if not isinstance(data, list):
            raise ValueError(f"Unexpected API response format for {symbol}: Expected a list, got {type(data)}")

        if not data:
            logger.warning(f"No kline data received from MEXC for {symbol} with interval {interval}.")
            return pd.DataFrame() # Return empty DataFrame if no data

        # Define column names based on Binance/MEXC kline structure
        column_names = [
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "qav" # quote asset volume
            # "ignore1", "ignore2", "ignore3", "ignore4" # Sometimes extra fields are present
        ]
        
        # Ensure we only take the expected number of columns
        df = pd.DataFrame(data, columns=column_names[:len(data[0])])

        # Convert relevant columns to numeric types
        numeric_columns = ["open", "high", "low", "close", "volume", "qav"]
        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col])
            else:
                logger.warning(f"Numeric column '{col}' not found in MEXC response for {symbol}.")

        # Convert timestamp columns to datetime objects with UTC timezone
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)

        # Filter out the currently-forming (incomplete) candle
        now_utc = datetime.now(timezone.utc)
        df = df[df["close_time"] <= now_utc].copy() # Use .copy() to avoid SettingWithCopyWarning

        # Reset index to ensure clean DataFrame after filtering
        df.reset_index(drop=True, inplace=True)

        logger.debug(f"Fetched {len(df)} closed candles for {symbol} ({interval}).")
        return df

    except requests.exceptions.RequestException as e:
        logger.error(f"HTTP request failed for {symbol} ({interval}): {e}")
        raise # Re-raise the exception to be handled by the caller
    except (ValueError, KeyError, IndexError) as e:
        logger.error(f"Error processing MEXC kline data for {symbol} ({interval}): {e}")
        # Potentially log response content here for debugging if needed
        # logger.error(f"Response content: {response.text}")
        raise ValueError(f"Failed to parse kline data for {symbol}.") from e

# Example of how to use this module (for testing purposes)
if __name__ == "__main__":
    # Configure basic logging for standalone testing
    logging.basicConfig(level=logging.DEBUG, format=config.LOGGING_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")
    
    test_symbol = "BTCUSDT"
    test_interval = "60m"
    test_limit = 200

    try:
        logger.info(f"Testing data fetching for {test_symbol} ({test_interval})...")
        klines_df = fetch_mexc_klines(test_symbol, test_interval, test_limit)

        if not klines_df.empty:
            logger.info(f"Successfully fetched {len(klines_df)} closed candles.")
            print("\nSample Data:")
            print(klines_df.head())
            print("\nDataFrame Info:")
            klines_df.info()
        else:
            logger.warning("No data fetched.")

    except Exception as e:
        logger.error(f"Test failed: {e}")
