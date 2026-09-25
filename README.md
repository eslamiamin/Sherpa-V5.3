# Sherpa V5.3 Architecture

Sherpa is a modular Paper Trading bot engine designed for high maintainability 
and separation of concerns between strategy, execution, and advisory services.

## Directory Structure
- `main.py`: The orchestrator, responsible for the trading loop, scheduling, and error handling.
- `strategy/`: Contains core trading logic (Entry/Exit signals, Position sizing).
- `data/`: Abstracted data providers (e.g., Binance, MEXC). Ensures decoupled data ingestion.
- `trading/`: Handles execution lifecycle (Lifecycle manager, Trade state persistence).
- `advisor/`: Advisory modules providing market context:
    - `sessions.py`: Manages global market hours (London, NY, Tokyo) with DST.
    - `news.py`: Real-time macroeconomic event monitoring (USD/High impact).
    - `market_pulse.py`: Market regime summary and channel formatting.
- `telegram/`: Dedicated wrappers for Telegram API (Trading Bot & Advisor Bot).
- `.env`: (Ignored by Git) Contains sensitive tokens and IDs.
