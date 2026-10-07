"""Re-run the 2022 notebook's 24-rule MA grid with the corrected engine.

Usage (from the repo root, needs internet):
    python -m scripts.rerun_notebook_grid
    python -m scripts.rerun_notebook_grid --price-basis raw --cost-bps 5

Prints both windows the notebook used (to 2022-12-16 and to 2021-12-01) so the
corrected conclusions can go into the Methodology page.
"""
from __future__ import annotations

import argparse

import pandas as pd

from core.config import SETTINGS
from core.data import fetch_yfinance, to_total_return, write_prices
from core.grid import default_pairs, rolling_start, run_ma_grid
from core.indicators import MASpec

COLS = ["total_return", "bh_total_return", "excess_total_return", "cagr", "bh_cagr",
        "max_drawdown", "bh_max_drawdown", "time_in_market", "fills"]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--price-basis", choices=["total_return", "raw"], default="total_return")
    p.add_argument("--cost-bps", type=float, default=0.0)
    p.add_argument("--save", action="store_true", help="also write data/prices.parquet")
    args = p.parse_args()

    raw = fetch_yfinance(SETTINGS.ticker, start=SETTINGS.start)
    print(f"Loaded {len(raw)} rows from {raw.attrs['source']} "
          f"({raw.index[0].date()} to {raw.index[-1].date()})")
    if args.save:
        write_prices(raw, SETTINGS.prices_path)
    prices = to_total_return(raw) if args.price_basis == "total_return" else raw

    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", None)
    pd.set_option("display.float_format", "{:.3f}".format)
    pairs = default_pairs()
    for end in ("2022-12-16", "2021-12-01"):
        grid = run_ma_grid(prices.loc[:end], pairs, cost_bps=args.cost_bps)
        beats = int((grid["excess_total_return"] > 0).sum())
        print(f"\n=== Window ending {end} ({args.price_basis}, {args.cost_bps} bps) ===")
        print(f"{beats} of {len(grid)} rules beat buy-and-hold on total return")
        print(grid[COLS])

    print("\n=== Robustness: ema10 vs sma200, 5-year windows, yearly starts ===")
    print(rolling_start(prices, MASpec("ema", 10), MASpec("sma", 200), horizon_years=5,
                        cost_bps=args.cost_bps))


if __name__ == "__main__":
    main()
