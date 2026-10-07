# SPY Market Lens

Streamlit portfolio app: honest moving-average backtests on SPY, plus every major dip and
spike annotated with sourced world news.

- Spec: [`docs/SPEC.md`](docs/SPEC.md)
- Roadmap and phase gates: [`docs/ROADMAP.md`](docs/ROADMAP.md)
- Corrected notebook results: [`docs/PHASE0_FINDINGS.md`](docs/PHASE0_FINDINGS.md)

## Status: Phase 0 done, Phase 1 next

Re-run with a corrected engine, none of the notebook's 24 MA crossover rules beats
buy-and-hold on SPY from 2010 to 2022. The rules mainly cut drawdowns: the best rule's max
drawdown was −18.5%, against −32% for buy-and-hold. See the findings doc.

`core/` is a tested, pure-Python package that replaces the 2022 notebook's logic:

| Module | What it does |
| --- | --- |
| `data.py` | yfinance with Stooq fallback, total-return adjustment, parquet snapshot |
| `indicators.py` | SMA and EMA (`span=n`, fixing the notebook's centre-of-mass EMA) |
| `signals.py` | Target exposure per close, no look-ahead; MA crossover, 200D trend filter |
| `backtest.py` | Vectorised long/cash engine, next-open fills, costs in bps, matched benchmark |
| `metrics.py` | Total return, CAGR, max drawdown, Sharpe, time in market |
| `grid.py` | Notebook's 24-rule grid on a common window; rolling-start robustness |

`tests/test_legacy_notebook.py` reproduces the notebook's evaluation loop and shows it
returning a share price (132) where the correct portfolio value is 108.9.

## Run

Python 3.12. `.venv` here is a conda env (`conda create -p .venv python=3.12`), but a plain venv
works too.

```bash
pip install -e ".[dev]"
ruff check .
pytest
python -m scripts.rerun_notebook_grid            # needs internet
python -m scripts.rerun_notebook_grid --cost-bps 5 --save   # --save writes data/prices.parquet
```

## Layout

```
core/        tested analytics package (no Streamlit imports)
scripts/     one-off analysis scripts (Phase 0 acceptance check)
tests/       pytest suite
data/        committed Parquet/JSON snapshots, written only by jobs/scripts
notebooks/   original 2022 EDA, unmodified, kept for history
docs/        spec, roadmap, findings
archive/     original phase-0 zip (git-ignored)
```

Not investment advice.
