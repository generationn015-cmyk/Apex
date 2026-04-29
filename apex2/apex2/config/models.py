"""Pydantic config models for Apex v2."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class CapitalConfig(BaseModel):
    starting_balance_usd: float = Field(gt=0)
    risk_per_trade_pct: float = Field(default=1.0, gt=0, le=5.0)
    max_daily_loss_pct: float = Field(default=3.0, gt=0, le=20.0)
    max_open_positions: int = Field(default=5, ge=1, le=50)
    max_position_pct: float = Field(default=20.0, gt=0, le=100.0)
    kelly_fraction: float = Field(default=0.25, gt=0, le=1.0)


class AlpacaConfig(BaseModel):
    enabled: bool = True
    paper: bool = True
    api_key: str = ""
    api_secret: str = ""
    base_url: str = ""

    @field_validator("base_url", mode="before")
    @classmethod
    def _default_base(cls, v: str, info) -> str:
        if v:
            return v
        paper = info.data.get("paper", True)
        return "https://paper-api.alpaca.markets" if paper else "https://api.alpaca.markets"


class IBKRConfig(BaseModel):
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 7497
    client_id: int = 1


class CryptoExchangeConfig(BaseModel):
    enabled: bool = False
    exchange_id: Literal["coinbase", "kraken"] = "coinbase"
    api_key: str = ""
    api_secret: str = ""
    sandbox: bool = True


class BrokersConfig(BaseModel):
    alpaca: AlpacaConfig = AlpacaConfig()
    ibkr: IBKRConfig = IBKRConfig()
    crypto: CryptoExchangeConfig = CryptoExchangeConfig()


class DataConfig(BaseModel):
    cache_dir: str = "data/cache"
    parquet_compression: str = "snappy"
    primary_source: Literal["alpaca", "yfinance"] = "alpaca"
    fallback_source: Literal["alpaca", "yfinance", "none"] = "yfinance"


class BacktestConfig(BaseModel):
    commission_per_share: float = 0.0
    commission_per_trade: float = 0.0
    slippage_bps: float = 2.0
    fill_model: Literal["next_open", "close", "midpoint"] = "next_open"
    initial_cash: float = 10_000.0


class StrategyConfig(BaseModel):
    name: str
    enabled: bool = True
    params: dict = {}


class StrategiesConfig(BaseModel):
    etf_momentum: StrategyConfig = StrategyConfig(
        name="etf_momentum",
        params={
            "universe": ["SPY", "QQQ", "IWM", "DIA", "EFA", "EEM", "TLT", "GLD", "XLK", "XLF"],
            "lookback_days": 126,
            "skip_days": 21,
            "top_n": 3,
            "rebalance_days": 21,
            "abs_momentum_filter": True,
        },
    )
    rsi2_meanrev: StrategyConfig = StrategyConfig(
        name="rsi2_meanrev",
        params={
            "universe": ["SPY", "QQQ", "IWM", "XLK", "XLF", "XLE", "XLV", "XLY"],
            "rsi_period": 2,
            "rsi_oversold": 10,
            "rsi_exit": 70,
            "regime_sma": 200,
            "atr_stop_mult": 2.5,
        },
    )
    donchian_trend: StrategyConfig = StrategyConfig(
        name="donchian_trend",
        params={
            "universe": ["SPY", "QQQ", "TLT", "GLD", "USO", "UUP"],
            "entry_lookback": 55,
            "exit_lookback": 20,
            "atr_period": 20,
            "atr_risk_mult": 2.0,
        },
    )
    pairs_trading: StrategyConfig = StrategyConfig(
        name="pairs_trading",
        params={
            "pairs": [["XLF", "KRE"], ["XLK", "SOXX"], ["IWM", "IJR"]],
            "lookback_days": 60,
            "zscore_window": 30,
            "entry_z": 2.0,
            "exit_z": 0.5,
            "stop_z": 4.0,
        },
    )
    bond_equity_rotation: StrategyConfig = StrategyConfig(
        name="bond_equity_rotation",
        params={
            "equity_ticker": "SPY",
            "bond_ticker": "TLT",
            "slope_sma_days": 21,
            "enter_equity_threshold": 0.20,
            "enter_bond_threshold": -0.20,
        },
    )
    defensive_momentum: StrategyConfig = StrategyConfig(
        name="defensive_momentum",
        params={
            "universe": ["USMV", "SPLV", "XLV", "XLP", "XLU", "VIG", "QUAL", "MTUM"],
            "benchmark": "SPY",
            "regime_sma": 200,
            "momentum_lookback": 252,
            "momentum_skip": 21,
            "vol_window": 60,
            "top_k": 3,
            "rebalance_days": 21,
        },
    )


class MonitoringConfig(BaseModel):
    log_level: str = "INFO"
    log_file: str = "logs/apex2.log"
    db_file: str = "data/apex2.db"
    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""


class Config(BaseModel):
    mode: Literal["backtest", "paper", "live"] = "paper"
    capital: CapitalConfig
    brokers: BrokersConfig = BrokersConfig()
    data: DataConfig = DataConfig()
    backtest: BacktestConfig = BacktestConfig()
    strategies: StrategiesConfig = StrategiesConfig()
    monitoring: MonitoringConfig = MonitoringConfig()
