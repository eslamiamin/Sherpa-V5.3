"""
SHERPA V5.3 - Technical Indicators

Calculates all indicators required by the trading strategy.

Indicators:
- EMA 50
- EMA 200
- RSI
- ATR
- Bollinger Bands
- ADX
- MFI
- Volume SMA

All indicator names use lowercase consistently because strategy.py
expects lowercase column names.
"""

import logging

import pandas as pd

logger = logging.getLogger(__name__)


# ============================================================
# PARAMETERS
# ============================================================

EMA_SHORT_PERIOD = 5
EMA_MEDIUM_PERIOD = 15

EMA_50_PERIOD = 50
EMA_200_PERIOD = 200

RSI_PERIOD = 14
ATR_PERIOD = 14

BB_PERIOD = 20
BB_STD_DEV = 2.0

ADX_PERIOD = 14
MFI_PERIOD = 14

VOL_SMA_PERIOD = 20


# ============================================================
# VALIDATION
# ============================================================

REQUIRED_COLUMNS = [
    "open",
    "high",
    "low",
    "close",
    "volume",
]


# ============================================================
# MAIN CALCULATION
# ============================================================

def calculate_indicators(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Calculate all strategy indicators.

    Parameters
    ----------
    df:
        OHLCV DataFrame.

    Returns
    -------
    pd.DataFrame
        DataFrame with calculated indicators.
    """

    if df is None or df.empty:

        logger.warning(
            "Cannot calculate indicators: empty DataFrame."
        )

        return pd.DataFrame()

    missing_columns = [
        column
        for column in REQUIRED_COLUMNS
        if column not in df.columns
    ]

    if missing_columns:

        logger.warning(
            f"Cannot calculate indicators. "
            f"Missing columns: {missing_columns}"
        )

        return pd.DataFrame()

    # Never modify the original DataFrame.
    df = df.copy()

    # --------------------------------------------------------
    # Sort
    # --------------------------------------------------------

    if "timestamp" in df.columns:

        df.sort_values(
            "timestamp",
            inplace=True,
        )

    df.reset_index(
        drop=True,
        inplace=True,
    )

    # --------------------------------------------------------
    # Numeric conversion
    # --------------------------------------------------------

    for column in REQUIRED_COLUMNS:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    # Remove rows where OHLC data is unusable.
    df.dropna(
        subset=[
            "open",
            "high",
            "low",
            "close",
            "volume",
        ],
        inplace=True,
    )

    if df.empty:

        logger.warning(
            "No valid OHLCV rows after cleaning."
        )

        return pd.DataFrame()

    # ========================================================
    # EMA
    # ========================================================

    df["ema_5"] = (
        df["close"]
        .ewm(
            span=EMA_SHORT_PERIOD,
            adjust=False,
        )
        .mean()
    )

    df["ema_15"] = (
        df["close"]
        .ewm(
            span=EMA_MEDIUM_PERIOD,
            adjust=False,
        )
        .mean()
    )

    df["ema_50"] = (
        df["close"]
        .ewm(
            span=EMA_50_PERIOD,
            adjust=False,
        )
        .mean()
    )

    df["ema_200"] = (
        df["close"]
        .ewm(
            span=EMA_200_PERIOD,
            adjust=False,
        )
        .mean()
    )

    # ========================================================
    # RSI
    # ========================================================

    delta = df["close"].diff()

    gain = delta.clip(
        lower=0
    )

    loss = -delta.clip(
        upper=0
    )

    # Wilder-style smoothing.
    avg_gain = (
        gain
        .ewm(
            alpha=1 / RSI_PERIOD,
            adjust=False,
            min_periods=RSI_PERIOD,
        )
        .mean()
    )

    avg_loss = (
        loss
        .ewm(
            alpha=1 / RSI_PERIOD,
            adjust=False,
            min_periods=RSI_PERIOD,
        )
        .mean()
    )

    rs = avg_gain.div(
        avg_loss.replace(
            0,
            pd.NA,
        )
    )

    df["rsi"] = (
        100
        - (
            100
            / (1 + rs)
        )
    )

    # If there are gains but no losses, RSI is effectively 100.
    df.loc[
        (avg_loss == 0)
        & (avg_gain > 0),
        "rsi",
    ] = 100.0

    # If both are zero, market has not moved.
    df.loc[
        (avg_loss == 0)
        & (avg_gain == 0),
        "rsi",
    ] = 50.0

    # ========================================================
    # ATR
    # ========================================================

    previous_close = (
        df["close"].shift(1)
    )

    high_low = (
        df["high"]
        - df["low"]
    )

    high_prev_close = (
        df["high"]
        - previous_close
    ).abs()

    low_prev_close = (
        df["low"]
        - previous_close
    ).abs()

    true_range = pd.concat(
        [
            high_low,
            high_prev_close,
            low_prev_close,
        ],
        axis=1,
    ).max(axis=1)

    df["atr"] = (
        true_range
        .ewm(
            alpha=1 / ATR_PERIOD,
            adjust=False,
            min_periods=ATR_PERIOD,
        )
        .mean()
    )

    # ========================================================
    # BOLLINGER BANDS
    # ========================================================

    df["bb_middle"] = (
        df["close"]
        .rolling(
            BB_PERIOD,
            min_periods=BB_PERIOD,
        )
        .mean()
    )

    df["bb_std"] = (
        df["close"]
        .rolling(
            BB_PERIOD,
            min_periods=BB_PERIOD,
        )
        .std()
    )

    df["bb_upper"] = (
        df["bb_middle"]
        + (
            df["bb_std"]
            * BB_STD_DEV
        )
    )

    df["bb_lower"] = (
        df["bb_middle"]
        - (
            df["bb_std"]
            * BB_STD_DEV
        )
    )

    # Useful normalized width.
    df["bb_width"] = (
        (
            df["bb_upper"]
            - df["bb_lower"]
        )
        / df["bb_middle"].replace(
            0,
            pd.NA,
        )
    )

    # ========================================================
    # ADX / DIRECTIONAL MOVEMENT
    # ========================================================

    up_move = (
        df["high"]
        - df["high"].shift(1)
    )

    down_move = (
        df["low"].shift(1)
        - df["low"]
    )

    plus_dm = pd.Series(
        0.0,
        index=df.index,
    )

    minus_dm = pd.Series(
        0.0,
        index=df.index,
    )

    plus_dm[
        (up_move > down_move)
        & (up_move > 0)
    ] = up_move[
        (up_move > down_move)
        & (up_move > 0)
    ]

    minus_dm[
        (down_move > up_move)
        & (down_move > 0)
    ] = down_move[
        (down_move > up_move)
        & (down_move > 0)
    ]

    # Wilder smoothing.
    atr_for_adx = (
        true_range
        .ewm(
            alpha=1 / ADX_PERIOD,
            adjust=False,
            min_periods=ADX_PERIOD,
        )
        .mean()
    )

    smoothed_plus_dm = (
        plus_dm
        .ewm(
            alpha=1 / ADX_PERIOD,
            adjust=False,
            min_periods=ADX_PERIOD,
        )
        .mean()
    )

    smoothed_minus_dm = (
        minus_dm
        .ewm(
            alpha=1 / ADX_PERIOD,
            adjust=False,
            min_periods=ADX_PERIOD,
        )
        .mean()
    )

    df["plus_di"] = (
        100
        * smoothed_plus_dm
        / atr_for_adx.replace(
            0,
            pd.NA,
        )
    )

    df["minus_di"] = (
        100
        * smoothed_minus_dm
        / atr_for_adx.replace(
            0,
            pd.NA,
        )
    )

    di_sum = (
        df["plus_di"]
        + df["minus_di"]
    )

    di_diff = (
        df["plus_di"]
        - df["minus_di"]
    ).abs()

    dx = (
        100
        * di_diff
        / di_sum.replace(
            0,
            pd.NA,
        )
    )

    df["adx"] = (
        dx
        .ewm(
            alpha=1 / ADX_PERIOD,
            adjust=False,
            min_periods=ADX_PERIOD,
        )
        .mean()
    )

    # ========================================================
    # MFI
    # ========================================================

    typical_price = (
        df["high"]
        + df["low"]
        + df["close"]
    ) / 3.0

    raw_money_flow = (
        typical_price
        * df["volume"]
    )

    price_change = (
        typical_price.diff()
    )

    positive_money_flow = (
        raw_money_flow
        .where(
            price_change > 0,
            0.0,
        )
    )

    negative_money_flow = (
        raw_money_flow
        .where(
            price_change < 0,
            0.0,
        )
    )

    positive_sum = (
        positive_money_flow
        .rolling(
            MFI_PERIOD,
            min_periods=MFI_PERIOD,
        )
        .sum()
    )

    negative_sum = (
        negative_money_flow
        .rolling(
            MFI_PERIOD,
            min_periods=MFI_PERIOD,
        )
        .sum()
    )

    money_ratio = (
        positive_sum
        / negative_sum.replace(
            0,
            pd.NA,
        )
    )

    df["mfi"] = (
        100
        - (
            100
            / (1 + money_ratio)
        )
    )

    # If no negative flow exists, MFI is effectively 100.
    df.loc[
        (negative_sum == 0)
        & (positive_sum > 0),
        "mfi",
    ] = 100.0

    # ========================================================
    # VOLUME SMA
    # ========================================================

    df["vol_sma"] = (
        df["volume"]
        .rolling(
            VOL_SMA_PERIOD,
            min_periods=VOL_SMA_PERIOD,
        )
        .mean()
    )

    # ========================================================
    # CLEANUP
    # ========================================================

    df.drop(
        columns=[
            "plus_di",
            "minus_di",
        ],
        inplace=True,
        errors="ignore",
    )

    logger.debug(
        f"Indicators calculated successfully. "
        f"Rows={len(df)}, Columns={len(df.columns)}"
    )

    return df


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    import numpy as np

    np.random.seed(42)

    periods = 300

    prices = (
        100
        + np.cumsum(
            np.random.normal(
                0,
                1,
                periods,
            )
        )
    )

    test_df = pd.DataFrame({

        "timestamp": pd.date_range(
            "2025-01-01",
            periods=periods,
            freq="1h",
            tz="UTC",
        ),

        "open": prices,

        "high": prices + np.random.uniform(
            0.1,
            2.0,
            periods,
        ),

        "low": prices - np.random.uniform(
            0.1,
            2.0,
            periods,
        ),

        "close": prices
        + np.random.normal(
            0,
            0.5,
            periods,
        ),

        "volume": np.random.uniform(
            1000,
            5000,
            periods,
        ),
    })

    result = calculate_indicators(
        test_df
    )

    print(
        result[
            [
                "timestamp",
                "close",
                "ema_50",
                "ema_200",
                "rsi",
                "atr",
                "bb_width",
                "adx",
                "mfi",
                "vol_sma",
            ]
        ].tail(10)
    )
