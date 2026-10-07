# Phase 0 findings: the 2022 notebook re-run with the corrected engine

Run on 2026-10-07 with `python -m scripts.rerun_notebook_grid` (yfinance, 4,216 daily rows,
2010-01-04 to 2026-10-07). These numbers are the source for the Methodology page's
"corrected notebook findings" section. Re-run the script to refresh them; do not hand-edit.

## Setup

- Same 24 rules as the notebook: {SMA, EMA} × {10, 20, 50} short vs {SMA, EMA} × {100, 200} long.
- All rules share one window, starting 2010-10-19 (the first bar every rule can trade once
  the slowest MA is available). The notebook started in November 2010.
- Signals decided at the close, filled at the next open. Long or cash; cash earns 0.
- Buy-and-hold uses the same window, fills and entry cost.

## Headline

**None of the 24 rules beats buy-and-hold, in either window, on any price basis or cost
setting tested.** The notebook's "EMA10 vs SMA200 beats buy-and-hold by 59.2%" comes from
the returns-loop bug (audit #1 and #2), not from the strategy.

| Window end | Prices | Cost (bps/side) | Rules beating B&H | Best rule | Best rule total return | B&H total return |
| --- | --- | --- | --- | --- | --- | --- |
| 2022-12-16 | total return | 0 | 0 / 24 | ema10 vs sma200 | +215.0% | +315.2% |
| 2022-12-16 | total return | 5 | 0 / 24 | ema10 vs sma200 | +212.2% | +315.0% |
| 2022-12-16 | raw close | 0 | 0 / 24 | sma10 vs sma200 | +152.0% | +228.7% |
| 2021-12-01 | total return | 0 | 0 / 24 | ema10 vs sma200 | +247.4% | +387.9% |
| 2021-12-01 | total return | 5 | 0 / 24 | ema10 vs sma200 | +244.8% | +387.7% |
| 2021-12-01 | raw close | 0 | 0 / 24 | sma10 vs sma200 | +178.3% | +293.9% |

Average excess total return across the 24 rules (to 2022-12-16, total return, 0 bps): −168
percentage points.

## What the notebook got right, and what it got wrong

| Notebook claim | Corrected finding |
| --- | --- |
| 15 of 24 rules beat buy-and-hold to Dec 2022 | 0 of 24 |
| EMA10 vs SMA200 is best, +59.2% vs baseline | EMA10 vs SMA200 is still the best-ranked rule, but it trails B&H by ~100 pp (CAGR 9.9% vs 12.4%) |
| All rules trail baseline to Dec 2021 (−24.9% on average) | The direction is right; the size is much larger. Trailing is the normal case, not a 2021 quirk |
| "MAs are lagged, so we enter late in bull markets" | Supported. Time in market is 78–86%, and SPY's up days compound while the rule waits for confirmation |
| Hand-picked timings give ~743% | Hindsight. Not reproducible by any rule; shown at most as a labelled oracle bound |

## What the rules do offer

They are a risk-reduction tool, not a return-enhancement tool. To 2022-12-16, EMA10 vs SMA200
had a max drawdown of −18.5% against −32.0% for buy-and-hold. This trade-off (lower return for
smaller drawdowns) is what the Strategy Lab should make visible.

## Robustness: EMA10 vs SMA200, 5-year windows, yearly starts

Excess return is negative for all 11 start years from 2011 to 2021, ranging from −11 pp
(2018 start) to −38 pp (2019 start). The result does not depend on the chosen window.

## Engine bug found while running the acceptance check

`run_ma_grid` started the 100-day rules one bar earlier than the 200-day rules. Exposure lags
the target by one bar, so the common start must be the bar *after* the slowest target becomes
valid. The fix is in `core/grid.py`, with a regression test in `tests/test_grid.py` (B&H return
must be identical for every rule). Before the fix, B&H read 3.132 for the 100-day rules and
3.152 for the 200-day rules.
