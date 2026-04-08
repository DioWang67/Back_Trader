"""Global configuration for the SMC backtest system."""

from dataclasses import dataclass


@dataclass(slots=True)
class Config:
    """Runtime configuration parameters."""

    # Data
    taifex_url: str = (
        "https://www.taifex.com.tw/file/taifex/Dailydownload/DailydownloadCSV/Daily_"
        "Futures.zip"
    )
    timeout: int = 30

    # Instrument / execution
    tick_size: float = 1.0
    slippage_ticks: int = 1
    commission_per_order_ntd: float = 50.0
    contract_multiplier: float = 200.0

    # Strategy
    ema_fast: int = 50
    ema_slow: int = 200
    swing_lookback: int = 5
    fvg_valid_bars: int = 20
    risk_per_trade: float = 0.01
    reward_risk: float = 2.0

    # Risk controls
    max_drawdown: float = 0.25
    max_open_positions: int = 2

    # Backtest
    initial_capital: float = 1_000_000.0


DEFAULT_CONFIG = Config()
