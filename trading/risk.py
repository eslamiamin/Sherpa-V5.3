"""
Risk Management and Position Sizing Module.

This module contains functions for calculating the appropriate trade size
based on the user's capital, defined risk percentage, and the distance to the
initial stop loss. It ensures that no single trade exposes the portfolio to
excessive risk and adheres to maximum position notional limits.
"""

import logging
import pandas as pd

import config

logger = logging.getLogger(__name__)

def calculate_position_size(
    capital: float,
    risk_pct: float,
    entry_price: float,
    stop_price: float
) -> float:
    """
    Calculate the notional value (USD amount) for a trade based on risk parameters.

    The calculation determines how much capital to allocate to a position
    such that if the stop loss is hit, the loss does not exceed the specified
    risk percentage of the total capital. It also enforces a maximum
    notional value per position.

    Args:
        capital (float): The total available trading capital.
        risk_pct (float): The percentage of capital to risk on this trade (e.g., 0.01 for 1%).
        entry_price (float): The price at which the trade is intended to enter.
        stop_price (float): The price at which the initial stop loss is set.

    Returns:
        float: The calculated notional value (in USD) of the position. Returns 0.0 if
               parameters are invalid or calculation results in zero/negative size.
    """
    if capital <= 0 or risk_pct <= 0 or entry_price <= 0 or stop_price <= 0:
        logger.warning("Invalid input parameters for position size calculation: "
                       f"capital={capital}, risk_pct={risk_pct}, entry={entry_price}, stop={stop_price}")
        return 0.0

    # Calculate the amount of capital to risk in USD
    risk_amount = capital * risk_pct

    # Calculate the price difference between entry and stop
    stop_distance = abs(entry_price - stop_price)

    # Ensure stop distance is positive to avoid division by zero or invalid calculations
    if stop_distance <= 0:
        logger.warning(f"Stop distance is zero or negative ({stop_distance}). Cannot calculate position size.")
        return 0.0

    # Calculate the stop loss distance as a percentage of the entry price
    stop_distance_pct = stop_distance / entry_price

    # Calculate the required position size in notional value (USD)
    # Position Size (USD) = Risk Amount (USD) / Stop Loss Distance (%)
    position_notional = risk_amount / stop_distance_pct

    # Apply the maximum notional position size constraint
    # This prevents a single trade from taking up too much capital, even if risk % allows it.
    max_notional_position = capital * config.MAX_POSITION_NOTIONAL_PCT
    
    calculated_position_size = min(position_notional, max_notional_position)

    # Ensure the final calculated size is not negative (shouldn't happen with checks above, but good practice)
    if calculated_position_size < 0:
        logger.error(f"Calculated negative position size: {calculated_position_size}. Resetting to 0.")
        return 0.0
        
    logger.debug(f"Calculated position size: "
                 f"Capital=${capital:.2f}, Risk%={risk_pct:.4f}, Entry=${entry_price:.4f}, "
                 f"Stop=${stop_price:.4f} -> "
                 f"RiskAmount=${risk_amount:.2f}, StopDist%={stop_distance_pct:.4f}, "
                 f"Notional=${position_notional:.2f}, MaxNotional=${max_notional_position:.2f} -> "
                 f"FinalSize=${calculated_position_size:.2f}")

    return calculated_position_size


# --- Example Usage ---
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format=config.LOGGING_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")

    test_capital = 10000.0
    test_entry = 100.0
    test_stop_atr_mult = 1.2
    test_atr = 1.0

    print(f"--- Testing Position Sizing (Capital: ${test_capital:.2f}) ---")

    # Test case 1: Normal risk regime
    risk_pct_normal = config.NORMAL_REGIME_RISK_PCT
    stop_price_normal = test_entry - (test_atr * test_stop_atr_mult)
    position_size_normal = calculate_position_size(
        capital=test_capital,
        risk_pct=risk_pct_normal,
        entry_price=test_entry,
        stop_price=stop_price_normal
    )
    print(f"Normal Risk ({risk_pct_normal*100:.1f}%):")
    print(f"  Entry: ${test_entry:.2f}, Stop: ${stop_price_normal:.2f}")
    print(f"  Calculated Position Size: ${position_size_normal:.2f}")

    # Test case 2: Strong risk regime
    risk_pct_strong = config.STRONG_REGIME_RISK_PCT
    stop_price_strong = test_entry - (test_atr * test_stop_atr_mult) # Stop distance is the same
    position_size_strong = calculate_position_size(
        capital=test_capital,
        risk_pct=risk_pct_strong,
        entry_price=test_entry,
        stop_price=stop_price_strong
    )
    print(f"\nStrong Risk ({risk_pct_strong*100:.1f}%):")
    print(f"  Entry: ${test_entry:.2f}, Stop: ${stop_price_strong:.2f}")
    print(f"  Calculated Position Size: ${position_size_strong:.2f}")

    # Test case 3: Scenario hitting Max Position Notional Limit
    # Assume a very tight stop loss, which would normally lead to a huge position size
    tight_stop_atr_mult = 0.1 # Very tight stop
    tight_stop_price = test_entry - (test_atr * tight_stop_atr_mult)
    max_allowed_notional = test_capital * config.MAX_POSITION_NOTIONAL_PCT
    
    # Calculate size with tight stop first
    position_size_tight_stop = calculate_position_size(
        capital=test_capital,
        risk_pct=risk_pct_normal, # Using normal risk
        entry_price=test_entry,
        stop_price=tight_stop_price
    )
    print(f"\nTight Stop Scenario (Risk: {risk_pct_normal*100:.1f}%, Stop Distance: {tight_stop_atr_mult*test_atr:.4f}):")
    print(f"  Entry: ${test_entry:.2f}, Stop: ${tight_stop_price:.2f}")
    print(f"  Calculated Position Size (before max limit): ${position_size_tight_stop:.2f}")
    print(f"  Max Notional Limit: ${max_allowed_notional:.2f}")
    
    # The function should automatically cap it at max_allowed_notional
    if position_size_tight_stop > max_allowed_notional:
         print("  -> Position size correctly capped by MAX_POSITION_NOTIONAL_PCT.")
    else:
         print("  -> Position size was not capped (unexpected).")

    # Test case 4: Invalid inputs
    print("\n--- Testing Invalid Inputs ---")
    invalid_size = calculate_position_size(0, 0.01, 100, 99)
    print(f"Size with zero capital: ${invalid_size:.2f}")
    invalid_size = calculate_position_size(1000, 0.01, 100, 100) # Zero stop distance
    print(f"Size with zero stop distance: ${invalid_size:.2f}")
