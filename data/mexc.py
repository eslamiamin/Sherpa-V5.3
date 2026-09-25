"""
MEXC Data Provider Module.

Fetches closed OHLCV candles from the MEXC public API.

The provider:
- Uses a reusable HTTP session.
- Applies request timeout and limited retries.
- Filters out the currently-forming candle.
- Returns normalized pandas DataFrames.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import config


logger = logging.getLogger(__name__)


# ============================================================
# HTTP SESSION
# ============================================================

def _create_session() -> requests.Session:
    """
    Create a reusable HTTP session with limited automatic retries.

    Retries are only used for transient server/network errors.
    """

    session = requests.Session()

    retry_strategy = Retry(
        total=2,
        connect=2,
        read=2,
        status=2,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )

    adapter = HTTPAdapter(
        max_retries=retry_strategy,
        pool_connections=10,
        pool_maxsize=10,
    )

    session.mount("https://", adapter)
    session.mount("http://", adapter)

    session.headers.update({
        "User-Agent": "SHERPA-V5.3"
    })

    return session


SESSION = _create_session()


# ============================================================
# KLINE FETCHER
# ============================================================

def fetch_mexc_klines(
    symbol: str,
    interval: str = "60m",
    limit: int = 300,
) -> pd.DataFrame:
    """
    Fetch closed OHLCV candles from MEXC.

    Parameters
    ----------
    symbol:
        Example: BTCUSDT, ETHUSDT, PAXGUSDT

    interval:
        Example: 60m, 1d

    limit:
        Number of candles requested.

    Returns
    -------
    pd.DataFrame
        Closed candles sorted chronologically.
    """

    if not symbol:
        raise ValueError("Symbol cannot be empty.")

    if limit <= 0:
        raise ValueError("Limit must be greater than zero.")

    params = {
        "symbol": symbol.upper(),
        "interval": interval,
        "limit": int(limit),
    }

    try:
        response = SESSION.get(
            config.MEXC_API_URL,
            params=params,
            timeout=getattr(config, "MEXC_REQUEST_TIMEOUT", 10),
        )

        response.raise_for_status()

        data = response.json()

        if not isinstance(data, list):
            raise ValueError(
                f"Unexpected MEXC response for {symbol} {interval}: "
                f"expected list, got {type(data).__name__}"
            )

        if not data:
            logger.warning(
                f"{symbol}: MEXC returned no data for interval={interval}"
            )
            return pd.DataFrame()

        # MEXC kline response:
        # [
        #   open_time,
        #   open,
        #   high,
        #   low,
        #   close,
        #   volume,
        #   close_time,
        #   quote_asset_volume,
        #   ...
        # ]

        column_names = [
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "qav",
        ]

        # Only keep the columns we actually use.
        rows = [
            row[:len(column_names)]
            for row in data
            if isinstance(row, (list, tuple))
        ]

        if not rows:
            raise ValueError(
                f"Invalid kline rows returned for {symbol} {interval}"
            )

        df = pd.DataFrame(
            rows,
            columns=column_names[:len(rows[0])]
        )

        required_columns = [
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
        ]

        missing_columns = [
            col for col in required_columns
            if col not in df.columns
        ]

        if missing_columns:
            raise ValueError(
                f"Missing columns for {symbol} {interval}: "
                f"{missing_columns}"
            )

        # --------------------------------------------------------
        # Numeric conversion
        # --------------------------------------------------------

        numeric_columns = [
            "open",
            "high",
            "low",
            "close",
            "volume",
            "qav",
        ]

        for column in numeric_columns:
            if column in df.columns:
                df[column] = pd.to_numeric(
                    df[column],
                    errors="coerce"
                )

        # --------------------------------------------------------
        # Timestamp conversion
        # --------------------------------------------------------

        df["timestamp"] = pd.to_datetime(
            df["timestamp"],
            unit="ms",
            utc=True,
            errors="coerce",
        )

        df["close_time"] = pd.to_datetime(
            df["close_time"],
            unit="ms",
            utc=True,
            errors="coerce",
        )

        # Remove malformed rows.
        df.dropna(
            subset=[
                "timestamp",
                "close_time",
                "open",
                "high",
                "low",
                "close",
            ],
            inplace=True,
        )

        # --------------------------------------------------------
        # Only closed candles
        # --------------------------------------------------------

        now_utc = datetime.now(timezone.utc)

        df = df[
            df["close_time"] <= now_utc
        ].copy()

        # --------------------------------------------------------
        # Sort / deduplicate
        # --------------------------------------------------------

        df.sort_values(
            "timestamp",
            inplace=True
        )

        df.drop_duplicates(
            subset=["timestamp"],
            keep="last",
            inplace=True,
        )

        df.reset_index(
            drop=True,
            inplace=True
        )

        logger.debug(
            f"MEXC: {symbol} {interval} -> "
            f"{len(df)} closed candles"
        )

        return df

    except requests.exceptions.RequestException as exc:
        logger.error(
            f"MEXC HTTP error: {symbol} {interval}: {exc}"
        )
        raise

    except (ValueError, TypeError, KeyError, IndexError) as exc:
        logger.error(
            f"MEXC data parsing error: "
            f"{symbol} {interval}: {exc}"
        )
        raise ValueError(
            f"Failed to parse MEXC data for "
            f"{symbol} {interval}"
        ) from exc

    except Exception as exc:
        logger.exception(
            f"Unexpected MEXC error for "
            f"{symbol} {interval}: {exc}"
        )
        raise


# ============================================================
# STANDALONE TEST
# ============================================================

if __name__ == "__main__":

    logging.basicConfig(
        level=logging.DEBUG,
        format=config.LOGGING_FORMAT,
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    for test_symbol in ["BTCUSDT", "PAXGUSDT"]:

        try:
            logger.info(
                f"Testing {test_symbol}..."
            )

            df = fetch_mexc_klines(
                symbol=test_symbol,
                interval="60m",
                limit=10,
            )

            if df.empty:
                logger.warning(
                    f"No data received for {test_symbol}"
                )
            else:
                logger.info(
                    f"{test_symbol}: "
                    f"{len(df)} candles received"
                )
                print(df.tail())

        except Exception as exc:
            logger.error(
                f"Test failed for {test_symbol}: {exc}"
            )
