# SPY Market Lens

Streamlit portfolio app: honest moving-average backtests on SPY, plus every major dip and
spike annotated with sourced world news.

- Spec: [`docs/SPEC.md`](docs/SPEC.md)
- Roadmap and phase gates: [`docs/ROADMAP.md`](docs/ROADMAP.md)
- Corrected notebook results: [`docs/PHASE0_FINDINGS.md`](docs/PHASE0_FINDINGS.md)

## Status: Phase 1 done: Overview and Strategy Lab live

## Live app

(URL added after deploy — see `docs/ROADMAP.md` Phase 1 status)

Run locally: `python -m streamlit run app/Home.py`

Re-run with a corrected engine, none of the notebook's 24 MA crossover rules beats
buy-and-hold on SPY from 2010 to 2022. The rules mainly cut drawdowns: the best rule's max
drawdown was −18.5%, against −32% for buy-and-hold. See the findings doc.

`core/` is a tested, pure-Python package that replaces the 2022 notebook's logic, and `app/`
is a Streamlit multipage app that reads only from committed `data/` files:

| Module | What it does |
| --- | --- |
| `data.py` | yfinance price fetch (`auto_adjust=False`), total-return adjustment, parquet snapshot |
| `indicators.py` | SMA and EMA (`span=n`, fixing the notebook's centre-of-mass EMA) |
| `signals.py` | Target exposure per close, no look-ahead; MA crossover, 200D trend filter, `Strategy` protocol |
| `backtest.py` | Vectorised long/cash engine, next-open fills, costs in bps, matched benchmark |
| `metrics.py` | Total return, CAGR, max drawdown, Sharpe, Sortino, Calmar, time in market |
| `grid.py` | Notebook's 24-rule grid on a common window; rolling-start robustness; short×long heatmap grid; in-sample/out-of-sample split |
| `storage.py` | Pure read/write contract for `data/prices.parquet` and `data/meta.json` |
| `regimes.py` | Drawdown series, regime spans, drawdown table, Overview KPI calcs |
| `validate.py` | D-13 nightly validation gate (row count, last date, OHLCV rewrite tolerance, missing-session gap) |
| `market_calendar.py` | NYSE trading-session calendar built from `pandas.tseries.holiday` rules |

`tests/test_legacy_notebook.py` reproduces the notebook's evaluation loop and shows it
returning a share price (132) where the correct portfolio value is 108.9.

## Run

Python 3.12. `.venv` here is a conda env (`conda create -p .venv python=3.12`), but a plain venv
works too.

```bash
pip install -e ".[dev]"
ruff check .
pytest
python -m streamlit run app/Home.py              # local app, reads only data/
python -m jobs.refresh_prices                    # needs internet; validates before writing, exits 1 on failure
python -m scripts.rerun_notebook_grid            # needs internet
python -m scripts.rerun_notebook_grid --cost-bps 5 --save   # --save writes data/prices.parquet
```

## Layout

```
core/        tested analytics package (no Streamlit imports)
app/         Streamlit multipage app (Home.py entrypoint, views/, components/)
jobs/        offline writers (nightly price refresh)
scripts/     one-off analysis scripts (Phase 0 acceptance check)
tests/       pytest suite
data/        committed Parquet/JSON snapshots, written only by jobs/scripts
notebooks/   original 2022 EDA, unmodified, kept for history
docs/        spec, roadmap, findings
.streamlit/  app theme config
archive/     original phase-0 zip (git-ignored)
```

Not investment advice.
