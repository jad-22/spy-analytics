# Phase 1: Foundation, Overview & Strategy Lab - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md. This log preserves the alternatives considered.

**Date:** 2026-10-07
**Phase:** 01-foundation-overview-strategy-lab
**Areas discussed:** Headline & default window, Rule picker & heatmap grid, Robustness views, Nightly price job

---

## Headline & default window

| Question | Options | Selected |
|---|---|---|
| Default window | 2010-10-19→2022-12-16 / 1993→today / 2010-10-19→today | 2010-10-19→2022-12-16 |
| Headline behaviour | Live recount + fixed anchor / Static Phase 0 only / Live only | Live recount + fixed anchor |
| "Beat B&H" definition | Higher total return / Higher Sharpe / Both counts | Higher total return |
| Default rule | EMA10 vs SMA200 0 bps / same at 5 bps / You decide | EMA10 vs SMA200, 0 bps |

## Rule picker & heatmap grid

| Question | Options | Selected |
|---|---|---|
| Picker freedom | Bounded any period / 24 notebook values / Heatmap grid values | Bounded any period |
| Heatmap density | Dense (5–60×100–250) / Notebook 24 / Medium | Dense |
| Compute location | Live + cache / Precompute in job / Decide after profiling | Live + cache |
| Grid uses sidebar settings | Yes, all views / Fixed at notebook settings | Yes, all views |

## Robustness views

| Question | Options | Selected |
|---|---|---|
| Rolling-start content | Selected rule 5y / With horizon picker / Whole-grid band | Selected rule 5y |
| Rolling-start window | Always full history / Respect sidebar | Always full history |
| IS/OOS default split | 2022-12-16 / 70% of window / 2016-01-01 | 2022-12-16 |
| Heatmap MA types | Selected type pair / 2×2 multiples / Tabs | Selected type pair |

## Nightly price job

| Question | Options | Selected |
|---|---|---|
| Rewrite check | Strict OHLCV + adj_close ratio / Ignore adj_close / Close only | Strict OHLCV + adj_close ratio |
| Schedule | Weekdays ~21:30 UTC / Tue–Sat 06:00 UTC / You decide | Weekdays ~21:30 UTC |
| CI loop guard | paths-ignore + GITHUB_TOKEN / [skip ci] / You decide | paths-ignore + GITHUB_TOKEN |
| Job scope | Prices + meta + dispatch / + failure notification / Local only | Prices + meta + dispatch |

## Claude's Discretion

- Overview defaults (range, overlays, drawdown table size, annualised vol), widget types, `Strategy`
  interface shape, Sortino/Calmar, meta.json extras, retry library.

## Deferred Ideas

- OPS-04 notifications and keepalive go to Phase 4. Possible later additions: a rolling-start horizon picker, a whole-grid band, and heatmap small multiples.
