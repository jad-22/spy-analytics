"""Project-wide defaults. Change values here, not inside functions."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"


@dataclass(frozen=True)
class Settings:
    ticker: str = "SPY"
    start: str = "2010-01-01"  # Phase 0 notebook-parity script; app/jobs use history_start
    short_periods: tuple[int, ...] = (10, 20, 50)
    long_periods: tuple[int, ...] = (100, 200)
    ma_kinds: tuple[str, ...] = ("sma", "ema")
    cost_bps: float = 0.0  # one-way cost per unit of turnover, in basis points
    prices_path: Path = field(default=DATA_DIR / "prices.parquet")

    # Data layer (DATA-01..05)
    history_start: str = "1993-01-29"  # SPY inception; app and events use full history
    meta_path: Path = field(default=DATA_DIR / "meta.json")
    meta_schema_version: int = 1
    detector_version: int = 0  # 0 = no event detector has run (Phase 2 bumps this)
    fetch_attempts: int = 4
    fetch_wait_min_s: float = 2.0  # seconds
    fetch_wait_max_s: float = 30.0  # seconds
    rewrite_tolerance_pct: float = 0.0001  # fraction, i.e. 0.01% (D-13)
    adj_close_factor_tolerance_pct: float = 0.0001  # fraction, i.e. 0.01% (D-13)
    session_complete_after_et: str = "16:30"  # US/Eastern wall-clock time today's bar is final
    stale_after_days: int = 3

    # Overview page (OVER-01..06)
    overview_default_years: int = 5
    overview_ma_options: tuple[str, ...] = (
        "sma20", "ema20", "sma50", "ema50", "sma100", "sma200", "ema200",
    )
    overview_default_mas: tuple[str, ...] = ("sma50", "sma200")
    drawdown_regimes: tuple[float, ...] = (-0.05, -0.10, -0.20)
    default_regimes_on: tuple[float, ...] = (-0.10, -0.20)
    top_drawdowns: int = 10
    realised_vol_window: int = 20  # trading days
    scattergl_threshold_bars: int = 2500
    candlestick_warn_bars: int = 2500

    # Strategy Lab (LAB-01..10)
    lab_default_start: str = "2010-10-19"  # D-01: reproduces docs/PHASE0_FINDINGS.md exactly
    lab_default_end: str = "2022-12-16"
    lab_default_short: tuple[str, int] = ("ema", 10)  # D-04
    lab_default_long: tuple[str, int] = ("sma", 200)
    short_period_bounds: tuple[int, int] = (5, 60)  # D-05
    long_period_bounds: tuple[int, int] = (50, 250)
    heatmap_short_range: tuple[int, int, int] = (5, 60, 5)  # (start, inclusive stop, step), D-06
    heatmap_long_range: tuple[int, int, int] = (100, 250, 10)
    trend_filter_period: int = 200
    default_split: str = "2022-12-16"  # D-12
    rolling_horizon_years: int = 5  # D-11
    cost_bps_max: float = 50.0
    grid_debounce_threshold_s: float = 2.0  # D-09 profiling threshold, used in Plan 05
    split_min_years: int = 1  # minimum in-sample length after the start (D-12)
    split_min_oos_months: int = 6  # minimum out-of-sample length before the latest data


SETTINGS = Settings()
