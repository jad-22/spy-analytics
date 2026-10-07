# CLAUDE.md

SPY Market Lens: Streamlit portfolio app for honest MA backtests on SPY, plus sourced news
explanations for major moves. Authority docs: `docs/SPEC.md` (what and why), `docs/ROADMAP.md`
(phase tasks, gates, open questions). Update the roadmap checkboxes as work lands.

## Commands (Windows, from repo root)

```powershell
.\.venv\python.exe -m pip install -e ".[dev]"
.\.venv\python.exe -m ruff check .
.\.venv\python.exe -m pytest -q
.\.venv\python.exe -m scripts.rerun_notebook_grid   # live data, needs internet
```

`.venv` is a conda-created Python 3.12 env. Use `.venv\python.exe`, not `Scripts\`. The
system `python` is Anaconda 3.9 and too old.

## Rules that keep the project honest

- **Backtest conventions** (see `core/backtest.py` docstring): target decided at close t,
  filled at open t+1, exposure = target shifted by one bar. Any new rule returns a target
  exposure series. Never index future values.
- `core/` stays pure: no Streamlit imports, no globals, and no network calls except in
  `core/data.py`, which only jobs and scripts use.
- The app is read-only. Pages read `data/` through cached readers and never call yfinance or
  the Claude API. API keys live only in GitHub Actions secrets.
- Thresholds and defaults go in `core/config.py`, not inside functions.
- Every audit fix gets a test. Reported numbers (`docs/PHASE0_FINDINGS.md`) come from scripts;
  don't hand-edit them.
- `notebooks/` is historical and excluded from ruff; don't modify it.
- Before Phase 3, check current Claude model IDs and web-search pricing; the model ID goes in config.
