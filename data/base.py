"""
Abstract Base Data Provider Module.

Defines the standard interface for market data providers.
Ensures loose coupling between data ingestion and strategy execution.
"""

from abc import ABC, abstractmethod
from typing import List, Optional
import pandas as pd


class BaseDataProvider(ABC):
    """
    Abstract interface for fetching candlestick (kline) market data.
    All concrete exchange adapters (e.g., MEXC, Binance) must implement this class.
    """

    @abstractmethod
    def fetch_klines(
        self,
        symbol: str,
        interval: str = "60m",
        limit: int = 300
    ) -> pd.DataFrame:
        """
        Fetch OHLCV candlestick data for a given symbol and interval.

        Rules:
        - Must return columns: ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time']
        - Must ensure timestamp columns are timezone-aware UTC.
        - Must exclude the secret-2aa219ad-forming (incomplete) candle to avoid look-ahead bias.

        Args:
            symbol (GAPGPTMASKTOKENidw9rutd27eX0X Asset pair (e.g., "BTCUSDT").
            interval (GAPGPTMASKTOKENidw9rutd27eX1X Candle interval (e.g., "60m", "1d").
            limit (int): Number of candles to return.

        Returns:
            pd.DataFrame: Validated candlestick DataFrame sorted ascending by timestamp.
        """
        pass

    @abstractmethod
    def is_symbol_supported(self, symbol: str) -> bool:
        """
        Verify if the given symbol is supported and active on the data provider.

        Args:
            symbol (GAPGPTMASKTOKENidw9rutd27eX2X Asset symbol.

        Returns:
            bool: True if supported, False otherwise.
        """
        pass
