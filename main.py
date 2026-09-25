"""
Technical Indicators for SHERPA V5.3.
"""

import logging
import pandas as pd

logger = logging.getLogger(__name__)

EMA_SHORT_PERIOD = 5
EMA_MEDIUM_PERIOD = 15
EMA_50_PERIOD = 50
EMA_200_PERIOD = 200

RSI_PERIOD = 14
ATR_PERIOD = 14
BB_PERIOD = 20
BB_STD_DEV = 2

ADX_PERIOD = 14
MFI_PERIOD = 14
VOL_SMA_PERIOD = 20


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:

    if df is None or df.empty:
        return pd.DataFrame()

    required = [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]

    if not all(col in df.columns for col in required):
        logger.warning("Missing required OHLCV columns.")
        return pd.DataFrame()

    df = df.copy()

    df = df.sort_values("timestamp").reset_index(drop=True)

    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # ========================================================
    # EMA
    # ========================================================

    df["ema_5"] = df["close"].ewm(
        span=EMA_SHORT_PERIOD,
        adjust=False,
    ).mean()

    df["ema_15"] = df["close"].ewm(
        span=EMA_MEDIUM_PERIOD,
        adjust=False,
    ).mean()

    df["ema_50"] = df["close"].ewm(
        span=EMA_50_PERIOD,
        adjust=False,
    ).mean()

    df["ema_200"] = df["close"].ewm(
        span=EMA_200_PERIOD,
        adjust=False,
    ).mean()

    # ========================================================
    # RSI
    # ========================================================

    delta = df["close"].diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1 / RSI_PERIOD,
        adjust=False,
        min_periods=RSI_PERIOD,
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / RSI_PERIOD,
        adjust=False,
        min_periods=RSI_PERIOD,
    ).mean()

    rs = avg_gain / avg_loss.replace(0, pd.NA)

    df["rsi"] = 100 - (
        100 / (1 + rs)
    )

    # If there is no loss, RSI is effectively 100.
    df.loc[
        (avg_loss == 0) & (avg_gain > 0),
        "rsi",
    ] = 100.0

    # ========================================================
    # ATR
    # ========================================================

    previous_close = df["close"].shift(1)

    tr_components = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - previous_close).abs(),
            (df["low"] - previous_close).abs(),
        ],
        axis=1,
    )

    true_range = tr_components.max(axis=1)

    df["atr"] = true_range.ewm(
        alpha=1 / ATR_PERIOD,
        adjust=False,
        min_periods=ATR_PERIOD,
    ).mean()

    # ========================================================
    # Bollinger Bands
    # ========================================================

    df["bb_middle"] = df["close"].rolling(
        BB_PERIOD,
        min_periods=BB_PERIOD,
    ).mean()

    bb_std = df["close"].rolling(
        BB_PERIOD,
        min_periods=BB_PERIOD,
    ).std()

    df["bb_upper"] = (
        df["bb_middle"]
        + BB_STD_DEV * bb_std
    )

    df["bb_lower"] = (
        df["bb_middle"]
        - BB_STD_DEV * bb_std
    )

    # ========================================================
    # ADX
    # ========================================================

    up_move = df["high"].diff()
    down_move = -df["low"].diff()

    plus_dm = pd.Series(
        0.0,
        index=df.index,
    )

    minus_dm = pd.Series(
        0.0,
        index=df.index,
    )

    plus_dm[
        (up_move > down_move) & (up_move > 0)
    ] = up_move[
        (up_move > down_move) & (up_move > 0)
    ]

    minus_dm[
        (down_move > up_move) & (down_move > 0)
    ] = down_move[
        (down_move > up_move) & (down_move > 0)
    ]

    atr_for_adx = true_range.ewm(
        alpha=1 / ADX_PERIOD,
        adjust=False,
        min_periods=ADX_PERIOD,
    ).mean()

    plus_dm_smoothed = plus_dm.ewm(
        alpha=1 / ADX_PERIOD,
        adjust=False,
        min_periods=ADX_PERIOD,
    ).mean()

    minus_dm_smoothed = minus_dm.ewm(
        alpha=1 / ADX_PERIOD,
        adjust=False,
        min_periods=ADX_PERIOD,
    ).mean()

    df["plus_di"] = (
        100 * plus_dm_smoothed / atr_for_adx
    )

    df["minus_di"] = (
        100 * minus_dm_smoothed / atr_for_adx
    )

    di_sum = (
        df["plus_di"] +
        df["minus_di"]
    )

    di_diff = (
        df["plus_di"] -
        df["minus_di"]
    ).abs()

    dx = (
        100 * di_diff / di_sum.replace(0, pd.NA)
    )

    df["adx"] = dx.ewm(
        alpha=1 / ADX_PERIOD,
        adjust=False,
        min_periods=ADX_PERIOD,
    ).mean()

    # ========================================================
    # MFI
    # ========================================================

    typical_price = (
        df["high"] +
        df["low"] +
        df["close"]
    ) / 3

    raw_money_flow = (
        typical_price * df["volume"]
    )

    price_change = typical_price.diff()

    positive_flow = raw_money_flow.where(
        price_change > 0,
        0.0,
    )

    negative_flow = raw_money_flow.where(
        price_change < 0,
        0.0,
    )

    positive_sum = positive_flow.rolling(
        MFI_PERIOD,
        min_periods=MFI_PERIOD,
    ).sum()

    negative_sum = negative_flow.rolling(
        MFI_PERIOD,
        min_periods=MFI_PERIOD,
    ).sum()

    money_ratio = (
        positive_sum /
        negative_sum.replace(0, pd.NA)
    )

    df["mfi"] = 100 - (
        100 / (1 + money_ratio)
    )

    # No negative money flow => maximum MFI.
    df.loc[
        (negative_sum == 0) &
        (positive_sum > 0),
        "mfi",
    ] = 100.0

    # ========================================================
    # Volume SMA
    # ========================================================

    df["vol_sma"] = df["volume"].rolling(
        VOL_SMA_PERIOD,
        min_periods=VOL_SMA_PERIOD,
    ).mean()

    # Keep the dataframe clean.
    df.replace(
        [float("inf"), float("-inf")],
        pd.NA,
        inplace=True,
    )

    return df
