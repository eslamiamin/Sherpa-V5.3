"""
SHERPA V5.3 - Risk Management and Position Sizing.

Calculates paper-trading position notional based on:
- Available capital
- Risk percentage
- Entry price
- Initial stop-loss distance

Also enforces the maximum position notional configured in config.py.
"""

import logging

import config


logger = logging.getLogger(__name__)


# ============================================================
# POSITION SIZE
# ============================================================

def calculate_position_size(
    capital: float,
    risk_pct: float,
    entry_price: float,
    stop_price: float,
) -> float:
    """
    Calculate position notional in USD.

    Formula:

        risk_amount = capital × risk_pct

        stop_distance_pct =
            abs(entry_price - stop_price) / entry_price

        position_notional =
            risk_amount / stop_distance_pct

    The result is capped by:

        capital × MAX_POSITION_NOTIONAL_PCT

    Args:
        capital:
            Current paper-trading capital.

        risk_pct:
            Fraction of capital to risk.
            Example: 0.01 = 1%.

        entry_price:
            Planned entry price.

        stop_price:
            Initial stop-loss price.

    Returns:
        Position notional in USD.
        Returns 0.0 if inputs are invalid.
    """

    # --------------------------------------------------------
    # Validate inputs
    # --------------------------------------------------------

    if capital <= 0:
        logger.warning(
            f"Invalid capital: {capital}"
        )
        return 0.0

    if risk_pct <= 0:
        logger.warning(
            f"Invalid risk_pct: {risk_pct}"
        )
        return 0.0

    if risk_pct > 1:
        logger.warning(
            f"risk_pct must be <= 1. "
            f"Received: {risk_pct}"
        )
        return 0.0

    if entry_price <= 0:
        logger.warning(
            f"Invalid entry price: {entry_price}"
        )
        return 0.0

    if stop_price <= 0:
        logger.warning(
            f"Invalid stop price: {stop_price}"
        )
        return 0.0

    # --------------------------------------------------------
    # Stop distance
    # --------------------------------------------------------

    stop_distance = abs(
        entry_price - stop_price
    )

    if stop_distance <= 0:
        logger.warning(
            "Stop distance is zero. "
            "Position size cannot be calculated."
        )
        return 0.0

    stop_distance_pct = (
        stop_distance / entry_price
    )

    if stop_distance_pct <= 0:
        return 0.0

    # --------------------------------------------------------
    # Risk amount
    # --------------------------------------------------------

    risk_amount = (
        capital * risk_pct
    )

    # --------------------------------------------------------
    # Raw position notional
    # --------------------------------------------------------

    position_notional = (
        risk_amount
        / stop_distance_pct
    )

    # --------------------------------------------------------
    # Maximum position notional
    # --------------------------------------------------------

    max_notional_position = (
        capital
        * config.MAX_POSITION_NOTIONAL_PCT
    )

    calculated_position_size = min(
        position_notional,
        max_notional_position,
    )

    # --------------------------------------------------------
    # Final validation
    # --------------------------------------------------------

    if calculated_position_size <= 0:
        logger.warning(
            f"Calculated position size is invalid: "
            f"{calculated_position_size}"
        )
        return 0.0

    logger.debug(
        "Position size calculated | "
        f"Capital=${capital:.2f} | "
        f"Risk={risk_pct * 100:.2f}% | "
        f"Entry=${entry_price:.8g} | "
        f"SL=${stop_price:.8g} | "
        f"StopDist={stop_distance_pct * 100:.4f}% | "
        f"RiskAmount=${risk_amount:.2f} | "
        f"RawNotional=${position_notional:.2f} | "
        f"MaxNotional=${max_notional_position:.2f} | "
        f"Final=${calculated_position_size:.2f}"
    )

    return float(
        calculated_position_size
    )


# ============================================================
# STANDALONE TEST
# ============================================================

if __name__ == "__main__":

    logging.basicConfig(
        level=config.LOGGING_LEVEL,
        format=config.LOGGING_FORMAT,
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    test_capital = 10000.0
    test_entry = 100.0
    test_atr = 1.0

    print(
        "=========================================="
    )
    print(
        "SHERPA V5.3 - Risk Module Test"
    )
    print(
        "=========================================="
    )

    # --------------------------------------------------------
    # Test 1: Normal regime
    # --------------------------------------------------------

    risk_pct_normal = (
        config.NORMAL_REGIME_RISK_PCT
    )

    stop_price_normal = (
        test_entry
        - (
            test_atr
            * config.SL_ATR_MULTIPLIER
        )
    )

    position_size_normal = (
        calculate_position_size(
            capital=test_capital,
            risk_pct=risk_pct_normal,
            entry_price=test_entry,
            stop_price=stop_price_normal,
        )
    )

    print(
        "\nNormal Risk:"
    )

    print(
        f"Risk: "
        f"{risk_pct_normal * 100:.1f}%"
    )

    print(
        f"Entry: "
        f"${test_entry:.2f}"
    )

    print(
        f"Stop: "
        f"${stop_price_normal:.2f}"
    )

    print(
        f"Position Size: "
        f"${position_size_normal:.2f}"
    )

    # --------------------------------------------------------
    # Test 2: Strong regime
    # --------------------------------------------------------

    risk_pct_strong = (
        config.STRONG_REGIME_RISK_PCT
    )

    stop_price_strong = (
        test_entry
        - (
            test_atr
            * config.SL_ATR_MULTIPLIER
        )
    )

    position_size_strong = (
        calculate_position_size(
            capital=test_capital,
            risk_pct=risk_pct_strong,
            entry_price=test_entry,
            stop_price=stop_price_strong,
        )
    )

    print(
        "\nStrong Risk:"
    )

    print(
        f"Risk: "
        f"{risk_pct_strong * 100:.1f}%"
    )

    print(
        f"Entry: "
        f"${test_entry:.2f}"
    )

    print(
        f"Stop: "
        f"${stop_price_strong:.2f}"
    )

    print(
        f"Position Size: "
        f"${position_size_strong:.2f}"
    )

    # --------------------------------------------------------
    # Test 3: Maximum notional cap
    # --------------------------------------------------------

    tight_stop = (
        test_entry
        - (
            test_atr
            * 0.1
        )
    )

    max_allowed_notional = (
        test_capital
        * config.MAX_POSITION_NOTIONAL_PCT
    )

    position_size_tight = (
        calculate_position_size(
            capital=test_capital,
            risk_pct=risk_pct_normal,
            entry_price=test_entry,
            stop_price=tight_stop,
        )
    )

    print(
        "\nMaximum Notional Test:"
    )

    print(
        f"Calculated: "
        f"${position_size_tight:.2f}"
    )

    print(
        f"Maximum Allowed: "
        f"${max_allowed_notional:.2f}"
    )

    assert (
        position_size_tight
        <= max_allowed_notional
    )

    print(
        "PASS: Maximum notional cap works."
    )

    # --------------------------------------------------------
    # Test 4: Invalid inputs
    # --------------------------------------------------------

    print(
        "\nInvalid Input Tests:"
    )

    zero_capital = calculate_position_size(
        capital=0,
        risk_pct=0.01,
        entry_price=100,
        stop_price=99,
    )

    zero_distance = calculate_position_size(
        capital=1000,
        risk_pct=0.01,
        entry_price=100,
        stop_price=100,
    )

    invalid_risk = calculate_position_size(
        capital=1000,
        risk_pct=1.5,
        entry_price=100,
        stop_price=99,
    )

    print(
        f"Zero capital: "
        f"${zero_capital:.2f}"
    )

    print(
        f"Zero stop distance: "
        f"${zero_distance:.2f}"
    )

    print(
        f"Invalid risk: "
        f"${invalid_risk:.2f}"
    )

    assert zero_capital == 0.0
    assert zero_distance == 0.0
    assert invalid_risk == 0.0

    print(
        "PASS: Invalid input handling works."
    )
