"""Project-wide defaults. Change values here, not inside functions."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"


@dataclass(frozen=True)
class Settings:
    ticker: str = "SPY"
    start: str = "2010-01-01"
    short_periods: tuple[int, ...] = (10, 20, 50)
    long_periods: tuple[int, ...] = (100, 200)
    ma_kinds: tuple[str, ...] = ("sma", "ema")
    cost_bps: float = 0.0  # one-way cost per unit of turnover, in basis points
    prices_path: Path = field(default=DATA_DIR / "prices.parquet")


SETTINGS = Settings()
