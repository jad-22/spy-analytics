# Phase 2: Event Detection & Macro Calendar - Research

**Researched:** 2026-10-08
**Domain:** Deterministic time-series event detection (shock/gap/drawdown/rally clustering) + external calendar-data sourcing (FRED/Federal Reserve)
**Confidence:** MEDIUM-HIGH (thresholds and clustering behavior verified empirically against the real committed dataset; calendar sourcing verified live against FRED and federalreserve.gov; a few design choices below are genuinely open and need a decision, not just a lookup)

## Summary

This phase has two halves that are almost independent: (1) a pure, deterministic detector in
`core/events.py` that turns `data/prices.parquet` into `data/episodes.parquet`, and (2) a
one-off/rerunnable calendar builder that turns FRED + federalreserve.gov into
`data/macro_calendar.parquet`, plus a small tagging step that joins the two.

I ran the four detector rules exactly as specified in `docs/SPEC.md` against the real,
committed 1993–2026 SPY total-return series (8,480 rows) and found the single biggest design
fork for this phase: **what counts as an episode's "span" for the 3-trading-day merge** matters
enormously.

- If drawdown episodes are merged using their full peak-to-**recovery** span (literally "ends at
  a new high," per DET-03's own wording), the 2000–02 and 2007–09 bear markets don't resolve for
  2–5 years, and every unrelated shock/gap day that happens to fall inside that multi-year window
  gets silently absorbed into one mega-episode. Result: only **87 total episodes** for 1993+ —
  too few, and wrong in substance (Aug 2011, Aug 2015-adjacent noise, etc. would wrongly disappear
  inside the GFC episode if its window ran to 2012).
- If drawdown episodes are merged using only their **peak-to-trough** span (the steepest leg —
  which is also what the spec already prescribes for the *search window*, just not explicitly for
  clustering), the result is **151 total episodes**, squarely in the "low hundreds" DET-06 target,
  and all seven DET-07 known episodes come back as exactly one cluster each, correctly separated
  from their neighbors.
- A naive point-only merge (ignoring episode spans entirely, clustering only single flagged dates)
  gives 355 clusters — too many, and it fails to treat a multi-day crash as one story.

**Primary recommendation:** cluster using each primitive's *steepest-leg* interval (peak→trough
for drawdowns, trough→peak for rallies, single-day for shock/gap), not the full "ends at a new
high" recovery span. Store the full peak→recovery span separately as `end_date`/"recovered" label
for the Methodology/Overview-style drawdown table, but use the short leg for episode-boundary
*and* clustering purposes. This is `[VERIFIED: empirical run against data/prices.parquet]` for the
counts; the semantic split between "clustering window" and "recovery label" is `[ASSUMED]` —
flag for discuss-phase/planner confirmation since it's a genuine interpretation choice `docs/SPEC.md`
doesn't spell out.

For the calendar: FRED's `fred/release/dates` API requires a free, personal API key (confirmed
live — an unauthenticated call returns HTTP 400 "Variable api_key is not set"). CPI is
`release_id=10`, Employment Situation (payrolls) is `release_id=50` `[CITED: fred.stlouisfed.org/release?rid=10, rid=50 — found via WebSearch, not official API docs directly]`. `realtime_start` defaults to 1776 (no hard floor), so 1993+ coverage is not a concern once a key exists. FOMC has no FRED release ID; it must be scraped from federalreserve.gov's per-year historical pages, which I confirmed live go back to 1993 and distinguish "Meeting" from unscheduled "Conference Call" in the section headers for at least 1993–1994 (useful for scheduled-vs-surprise tagging) but years with no conference calls (e.g. 2015) don't carry the distinction at all since there's nothing to distinguish from.

## User Constraints

No `02-CONTEXT.md` exists for this phase (`has_context: false`) — `/gsd-discuss-phase` has not
been run. There are no locked decisions or discretion notes to copy verbatim. The planner should
treat every open question below as needing either a discuss-phase pass or an explicit planning
decision, not as pre-resolved.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DET-01 | Flag shock days (\|log return\| > 2.5 × 60-day σ lagged one day) | Verified live on `data/prices.parquet`: 242 shock days (total-return close), 1993–2026. See Standard Stack / Code Examples. |
| DET-02 | Flag gap opens (\|open/prev close − 1\| > 1.5%) | Verified live: 285 gap days (total-return basis). |
| DET-03 | Drawdown episodes (≥5%, ends at new high) and rally episodes (≥8% in 30 days) | Verified live: 36 drawdown episodes (close basis, 4 of them ≥20%), 92 rally episodes. See Common Pitfalls for the "ends at new high" multi-year-span trap. |
| DET-04 | Merge flags within 3 trading days into one episode with `anchor_date`, severity, search window | Empirically tested three merge strategies; steepest-leg interval merge recommended (151 episodes). See Architecture Patterns. |
| DET-05 | Deterministic, replay-stable episode IDs | Design pattern below (date+trigger-derived ID, no sequence numbers); the peak→trough/trough→peak boundary choice is itself what makes closed episodes immutable under append-only data. |
| DET-06 | Thresholds in config; 1993+ backfill in "low hundreds" | 151 under steepest-leg merge — hits the target. 87 (full-span merge) undershoots; 355 (point-only merge) overshoots. |
| DET-07 | All 7 known historical episodes detected, asserted by test | Verified live: all 7 (2000-02, 2008, Aug 2015, Feb 2018, Q4 2018, Mar 2020, 2022) come back as exactly one cluster each under the steepest-leg merge. |
| CAL-01 | `data/macro_calendar.parquet`: FOMC/CPI/payrolls from 1993, source URL each | FRED `release_id=10` (CPI) / `50` (payrolls) verified to need an API key; FOMC scrape source confirmed live back to 1993. See Architecture Patterns / Environment Availability. |
| CAL-02 | Tag episodes with scheduled releases in window (scheduled vs surprise) | See Common Pitfalls — FOMC "Conference Call" vs "Meeting" distinction matters here. |

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Shock/gap/drawdown/rally detection math | `core/events.py` (pure) | — | Deterministic, no I/O; must be unit-testable without the parquet file, matching `core/regimes.py`/`core/signals.py` precedent. |
| Episode clustering + ID assignment | `core/events.py` (pure) | — | Same module — clustering is a pure function of flagged dates, not a job concern. |
| `data/episodes.parquet` write | `jobs/detect_events.py` | — | Mirrors `jobs/refresh_prices.py`: job owns I/O, calls pure `core/` functions, writes the artifact. No network call here (reads committed `data/prices.parquet` only). |
| FRED/Fed network fetch | `core/data.py` (extended) | `jobs/build_macro_calendar.py` | CLAUDE.md states network calls live **only** in `core/data.py` among `core/` modules; the existing `fetch_yfinance` already sets this precedent. Add `fetch_fred_release_dates` / `fetch_fomc_dates` there, called by a job. |
| Macro-calendar parsing/tagging logic | `core/calendar.py` (pure) | — | Per `docs/SPEC.md`'s repo tree; pure match-episode-to-release-window logic, no network. |
| `data/macro_calendar.parquet` write | `jobs/build_macro_calendar.py` (new) | — | Not a true one-off: the calendar needs to extend into the near future for Phase 4's nightly tagging of newly-detected episodes (see Open Questions). Keep it a rerunnable job, not a disposable script. |
| App-side read of episodes/calendar | `core/storage.py` (extended) | `app/components/store.py` | Add `load_episodes(path)` / `load_macro_calendar(path)` next to existing `load_prices`/`load_meta`, same no-network/cached-by-app-layer pattern. |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|---------------|
| `pandas` | 3.0.6 (already installed in `.venv`) | Rolling σ, log returns, interval merging | Already the project's only data layer; no new dependency. `[VERIFIED: .venv/python.exe -c "import pandas"]` |
| `numpy` | installed via pandas/pyarrow stack | `np.log` for log returns | Already a dependency (`pyproject.toml` `numpy>=1.26`). |
| `requests` | `>=2.31` (already in `pyproject.toml`) | FRED API calls, Fed page fetch for the calendar builder | Already a Phase 0 dependency per `pyproject.toml`; reuse rather than adding `fredapi`. This matches the project's own prior research (`STACK.md`, already embedded in `CLAUDE.md`): "the calls needed (`fred/releases/dates`, `fred/release/dates`) are simple GET+JSON." `[CITED: project's own prior research, already committed]` |

**No new packages are required for Phase 2.** Detection math uses only pandas/numpy; calendar
fetching uses `requests`, already a dependency. **Package Legitimacy Audit is not applicable** —
skipped per the protocol's own scope ("whenever this phase installs external packages").

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pandas.tseries.holiday` primitives (already used in `core/market_calendar.py`) | n/a | Not for FOMC/CPI dates — just a reminder these are a *different* calendar (NYSE sessions) from the macro-release calendar this phase builds | Don't conflate `core/market_calendar.py` (trading-day calendar) with the new `core/calendar.py` (macro-release calendar) — they serve different purposes and should stay separate modules. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `requests` + hand-rolled FRED/Fed-page parsing | `fredapi` (PyPI package) | Adds a dependency for what is a ~20-line GET+JSON wrapper; project's own prior research already rejected this. Not revisited here. |
| FRED API (`fred/release/dates`, needs free API key) | Scraping `alfred.stlouisfed.org/releases/calendar?rid=X&y=YYYY` (no key required) | **Verified live: `alfred.stlouisfed.org`'s per-year release calendar HTML page works for historical years** (1994 confirmed showing 12 CPI dates) whereas `fred.stlouisfed.org/releases/calendar` (no `alfred.` prefix) only goes back to 2025 ("first year that releases are available is 2025" — confirmed live). The ALFRED HTML page is a viable **no-key fallback** if Jason doesn't want to request a FRED API key, at the cost of HTML scraping fragility instead of stable JSON. Recommend: try for a free FRED API key first (one-time, personal use, instant signup per FRED's own docs); fall back to ALFRED HTML scraping only if that's undesirable. `[VERIFIED: live WebFetch against alfred.stlouisfed.org and fred.stlouisfed.org]` |

**Installation:** none — no `pip install` needed for this phase.

## Package Legitimacy Audit

Not applicable — this phase introduces no new external packages. All required libraries
(`pandas`, `numpy`, `requests`) are already installed and already declared in `pyproject.toml`.

## Architecture Patterns

### System Architecture Diagram

```
data/prices.parquet (committed, from Phase 0/1)
        │
        ▼
core/events.py (pure)
  ├─ shock_days(close)         -> log-return z-score flags
  ├─ gap_days(open, prev_close)-> overnight gap flags
  ├─ drawdown_episodes(close)  -> peak/trough/recovery spans ≥5%
  ├─ rally_episodes(close)     -> trough/peak spans ≥8% in ≤30d
  └─ cluster(flags, spans)     -> merged Episode records (id, anchor_date,
                                   direction, trigger, move_pct, max_z,
                                   severity, search_from, search_to)
        │
        ▼
jobs/detect_events.py (I/O only)
  reads data/prices.parquet via core.storage.load_prices
  calls core.events.detect(...)
  writes data/episodes.parquet (+ bumps detector_version in meta.json)

core/data.py (extended — the ONE core module allowed to touch the network)
  ├─ fetch_fomc_dates(year)        -> scrape federalreserve.gov per-year page
  └─ fetch_fred_release_dates(release_id, start, end, api_key) -> FRED JSON
        │
        ▼
jobs/build_macro_calendar.py (new, I/O only; rerunnable, not disposable)
  calls core.data fetch_* helpers
  writes data/macro_calendar.parquet (date, release, source_url)

core/calendar.py (pure)
  tag_episode(episode, macro_calendar_df) -> scheduled release(s) in
  [episode.search_from, episode.search_to], or None -> "surprise"
        │
        ▼
jobs/detect_events.py (same job, final step)
  joins tags onto episodes before writing data/episodes.parquet

core/storage.py (extended)
  load_episodes(path), load_macro_calendar(path)  -- same no-network,
  FileNotFoundError-propagating pattern as load_prices/load_meta
```

A visitor-facing page never appears in this diagram — Phase 2 produces artifacts only;
Phase 4 is what reads `episodes.parquet`/`macro_calendar.parquet` into the app.

### Recommended Project Structure
```
core/
├── events.py          # NEW — shock/gap/drawdown/rally detection + clustering (pure)
├── calendar.py        # NEW — episode-to-release tagging (pure)
└── data.py            # EXTENDED — add fetch_fomc_dates, fetch_fred_release_dates
jobs/
├── detect_events.py          # NEW — writes data/episodes.parquet
└── build_macro_calendar.py   # NEW — writes data/macro_calendar.parquet
tests/
├── test_events.py                # NEW — DET-01..07, replay-stability test
└── test_build_macro_calendar.py  # NEW — parsing correctness (can run offline
                                   #        against a fixture page/response)
```

### Pattern 1: Steepest-leg interval merge (recommended clustering semantics)
**What:** When merging flagged primitives into episodes, use the *shortest* structural span
for each primitive — single day for shock/gap, peak→trough for drawdown, trough→peak for
rally — as the interval that participates in the "within 3 trading days" proximity test.
Track the full peak→recovery span separately if a "recovered" label is wanted elsewhere
(e.g. for a future Overview-style table), but do not use it for clustering.

**When to use:** Any time a drawdown's literal DET-03 "ends at a new high" condition would
make the span open for a very long time (multiple years for 2000–02 and 2007–09 — confirmed
empirically: dot-com didn't make a new SPY high until 2006-10-26, and the 2008 low didn't
recover to a new high until 2012-08-16).

**Example (verified against real data, integer trading-day positions for distance):**
```python
# Source: this research session's scratch script, run against data/prices.parquet
intervals = []
for d in shock_dates: intervals.append((pos[d], pos[d], "shock"))
for d in gap_dates:   intervals.append((pos[d], pos[d], "gap"))
for e in drawdowns:   intervals.append((pos[e.peak], pos[e.trough], "drawdown"))  # NOT e.recovery
for e in rallies:     intervals.append((pos[e.trough], pos[e.peak], "rally"))

intervals.sort(key=lambda x: x[0])
merged, cur = [], intervals[0]
for s, e, kind in intervals[1:]:
    if s - cur[1] <= MERGE_DAYS:            # cfg.merge_window_days = 3
        cur = (cur[0], max(cur[1], e), cur[2] | {kind})
    else:
        merged.append(cur); cur = (s, e, {kind})
merged.append(cur)
```
Result on `data/prices.parquet` (1993-01-29 to 2026-10-07, total-return basis): **151 merged
episodes**, all 7 DET-07 known episodes present as single, correctly-separated clusters.
`[VERIFIED: empirical run this session]`

### Pattern 2: Deterministic episode ID
**What:** `episode_id = f"{anchor_date:%Y-%m-%d}_{trigger}"`, matching the exact format already
shown in `docs/SPEC.md`'s news-enrichment example (`"2020-03-09_shock"`). `anchor_date` is the
single day with the largest |log return| (or largest |z|) inside the already-closed episode's
window — and because the window boundary is fixed the moment the episode closes (reaches its
steepest-leg endpoint), no future append-only data can change which day that is. This is what
makes DET-05's replay-stability test pass: the ID is a pure function of data already inside a
closed window, never of row position/sequence number.

**When to use:** Always — never use an auto-incrementing integer or "nth episode found" as part
of the ID; that breaks the moment detection re-runs with one more day of history and a new
episode is inserted earlier in time than expected (the real risk `core/events.py`'s tests must
cover, per DET-05).

**Collision handling (open question, not yet resolved — see below):** two different trigger
types can legitimately share the same `anchor_date` (e.g. a day that's both a shock day and a
gap day). Recommend a precedence order for the single `trigger` column — structural first:
`drawdown > rally > shock > gap` — and append a numeric suffix only in the (currently unobserved
in this dataset) case of an exact collision.

### Pattern 3: `core/data.py` extension for the macro-calendar network calls
**What:** Add fetch functions to `core/data.py` alongside the existing `fetch_yfinance`, not a
new network-capable module — this matches both CLAUDE.md's explicit rule ("no network calls
except in `core/data.py`") and `test_app_purity.py`'s existing forbidden-module list (which
already names `core.data` as the one app-forbidden, job-only network boundary).

**Example skeleton (not yet written — this is the shape to follow):**
```python
# core/data.py, following the existing fetch_yfinance pattern exactly
def fetch_fred_release_dates(release_id: int, api_key: str, start: str) -> list[str]:
    """Scheduled FRED release dates for one release_id, from `start` onward.

    Raises on any non-200 response or missing api_key — same fail-loud convention
    as fetch_yfinance's `raise ValueError(...)` on empty data.
    """
    import requests
    resp = requests.get(
        "https://api.stlouisfed.org/fred/release/dates",
        params={"release_id": release_id, "realtime_start": start,
                "file_type": "json", "api_key": api_key},
        timeout=10,
    )
    resp.raise_for_status()
    return [row["date"] for row in resp.json()["release_dates"]]
```
`[VERIFIED: live call this session — an unauthenticated call to this exact endpoint returned
HTTP 400 "Variable api_key is not set. Read https://fred.stlouisfed.org/docs/api/api_key.html
for more information." — confirming both the endpoint shape and the mandatory key.]`

### Anti-Patterns to Avoid
- **Hard-coding `release_id=10`/`release_id=50` meaning anywhere but a config constant:** these
  came from `[CITED: fred.stlouisfed.org/release?rid=10 and rid=50]` via WebSearch, not official
  FRED API documentation directly (the official `fred/release_dates.html` docs page doesn't
  enumerate ID meanings). Treat as `[ASSUMED]`-adjacent even though cited — confirm once with a
  real API key before the backfill, since a wrong release_id silently produces a wrong-but-valid
  calendar (DET/CAL tests wouldn't catch a semantically wrong release, only a missing one).
- **Scraping `fred.stlouisfed.org/releases/calendar` (no `alfred.` prefix) for history:** confirmed
  live this session that it only goes back to 2025. Don't use it for 1993+ coverage.
- **Treating every federalreserve.gov "Conference Call" as a scheduled release:** see Common
  Pitfalls below — these are frequently the *surprise* catalyst itself, not a scheduled fixture.
- **Using price-only (non-total-return) close for shock/gap thresholds:** empirically produces 9
  different shock-day flags and 3 different gap-day flags out of ~240/~285 total, concentrated
  around ex-dividend dates (confirmed differing gap dates include 2011-11-02, 2012-12-21,
  2022-09-16 — all near SPY's quarterly ex-div windows). Small in count, but it's an avoidable,
  honesty-relevant artifact (CLAUDE.md's "every number... honest and traceable" principle,
  already how `core/backtest.py`/`core/regimes.py` work) — use `core.data.to_total_return(df)`
  before computing log returns and gaps, matching how the Overview/Strategy Lab already treat
  the total-return toggle. `[VERIFIED: empirical run this session]`

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Rolling σ / log returns | A manual loop over bars | `pandas`'s `.rolling()`, `np.log` (already used in `core/regimes.py::overview_kpis`) | Already the exact pattern this codebase uses for realised vol; reuse it for DET-01's lagged 60-day σ instead of writing a second implementation. |
| Interval merging / clustering | Ad hoc nested loops with off-by-one risk | Sort-and-sweep over `(start_pos, end_pos)` tuples using integer trading-day positions (see Pattern 1) | Classic interval-merge algorithm; trading-day integer positions (not calendar-day deltas) avoid weekend/holiday distance bugs — the same reason `core/market_calendar.py` exists at all. |
| NYSE trading-day distance ("within 3 trading days") | Calendar-day arithmetic (`pd.Timedelta(days=3)`) | Integer position in `close.index` (already a `DatetimeIndex` of trading sessions only) | A calendar-day window would silently stretch across a long weekend/holiday; `core/market_calendar.py`'s `nyse_sessions` already proves trading-day-aware thinking is a project norm (D-13's gap check). |
| FOMC date scraping | A brittle single-regex scraper assuming one fixed HTML structure forever | Per-year page fetch + simple table/header parse, with a unit test fixture per confirmed year (1993, 1994, 2015 shapes already verified this session) | The page structure already showed two distinct shapes (years with conference calls label them; years without, like 2015, don't) — a hand-rolled single-pattern scraper will break silently on some year. Write the parser against multiple real fixture years, not one. |

**Key insight:** every piece of "don't hand-roll" guidance above is really the same insight
repeated: the codebase already has the right primitive (trading-day calendar, total-return
helper, rolling-window vol) sitting one import away in `core/`; Phase 2's job is almost entirely
composition of existing `core/` building blocks plus ~150 lines of genuinely new clustering logic.

## Common Pitfalls

### Pitfall 1: "Ends at a new high" makes two episodes pathologically long
**What goes wrong:** Read literally, DET-03's drawdown-episode end condition ("peak-to-trough
≥5% on closes, ending at a new high") means the 2000–02 episode doesn't close until
2006-10-26, and the 2007–09 episode doesn't close until 2012-08-16 — both multi-year spans.
**Why it happens:** SPY took years to re-make its all-time high after each of those two crashes.
**How to avoid:** Use the full peak→recovery span only as a *display*/"recovered" fact (useful
for something like `core/regimes.py::drawdown_table`'s existing `days_underwater` concept), but
use the much shorter peak→trough steepest leg as the episode's *clustering and search-window*
boundary (this is already explicitly how the spec treats search windows — "for drawdown
episodes, the 5 trading days around the steepest leg" — the research finding here is that the
same steepest-leg logic should also govern clustering, not just the search window).
**Warning signs:** If a Phase 2 test ever asserts "1993+ backfill episode count," watch for a
number far outside 100–300: ~87 signals the full-span bug; ~355 signals the opposite bug (no
span absorption at all, pure point-clustering). 151 (steepest-leg) is the empirically verified
middle ground. `[VERIFIED: three merge strategies run against real data this session]`

### Pitfall 2: FOMC "Conference Call" entries can themselves be the surprise, not the schedule
**What goes wrong:** federalreserve.gov's historical pages list both regularly scheduled
"Meeting" entries and ad hoc "Conference Call" entries (used historically for emergency
decisions, e.g. inter-meeting rate cuts) under the same per-year page with no structural field
distinguishing them except the header text. If the calendar builder ingests both as "scheduled
FOMC releases," an episode caused by an *emergency* inter-meeting conference-call rate cut would
get mislabeled `scheduled: true` under CAL-02 — exactly backwards, since an unscheduled
emergency action is the textbook "surprise" case the scheduled/surprise distinction exists to
catch.
**Why it happens:** The page's only readable distinction is the literal header string ("Meeting"
vs "Conference Call") — confirmed present for 1993/1994 (which had several conference calls) but
absent for a year with none, like 2015 (confirmed; all 8 entries say "Meeting").
**How to avoid:** Parse the header string and tag `release_type` explicitly as `meeting` or
`conference_call`; only feed `meeting` rows into CAL-02's "scheduled" calendar, or — better —
flag `conference_call` rows as `scheduled: false` catalysts that CAL-02 can still surface for
context without claiming they were pre-announced.
**Warning signs:** A detected shock-day episode landing exactly on a FOMC conference-call date
but tagged `scheduled: true` — a strong sign this distinction wasn't implemented.
`[VERIFIED: live WebFetch of federalreserve.gov/monetarypolicy/fomchistorical1993.htm,
fomchistorical1994.htm, fomchistorical2015.htm this session]`

### Pitfall 3: FRED's keyless HTML calendar does not cover history
**What goes wrong:** Assuming `fred.stlouisfed.org/releases/calendar?rid=X&y=1994` (no API key)
works for historical years because the equivalent ALFRED URL does.
**Why it happens:** FRED's own (non-ALFRED) public calendar view explicitly states "the first
year that releases are available is 2025" when a pre-2025 year is requested — confirmed live this
session. Only the `alfred.stlouisfed.org` (archival) domain's equivalent page serves historical
years (1994 confirmed working, showing all 12 CPI dates).
**How to avoid:** If avoiding the FRED API key entirely, scrape `alfred.stlouisfed.org`, not
`fred.stlouisfed.org`, for historical years. Prefer the authenticated JSON API if a key is
obtained — it's far less fragile than HTML scraping either way.
**Warning signs:** An empty or current-year-only calendar for CPI/payrolls below 2025 is the
tell.

### Pitfall 4: Multi-trigger episodes need an explicit precedence rule for the single `trigger` column
**What goes wrong:** `episodes.parquet`'s data model (per `docs/SPEC.md`) has one `trigger`
column, but a real merged cluster very often contains more than one trigger kind — empirically,
of the 151 steepest-leg-merged episodes, only 51 are shock/gap-only; the rest mix drawdown and/or
rally spans with shock/gap days (see kind-combination counts in the scratch run — e.g. 20
clusters contain all four kinds at once). Writing "whichever kind happened to iterate last" into
`trigger` is nondeterministic/fragile against refactors.
**Why it happens:** The four detector rules are not mutually exclusive — a single violent move
is very often simultaneously a shock day, a gap day, part of a drawdown leg, and/or part of the
rally that follows it.
**How to avoid:** Pick and document an explicit precedence order (recommended above: `drawdown >
rally > shock > gap`) and compute it as a pure function of the episode's flagged kinds, not of
dict/set iteration order.
**Warning signs:** The DET-05 replay-stability test is the natural place this would be caught —
if `trigger` isn't a deterministic function of (kinds present, anchor_date), a replay could change
it even when start/end/anchor stay fixed.

## Code Examples

### DET-01: shock days, verified counts
```python
# Source: this research session's scratch script, run against data/prices.parquet
# (core.storage.load_prices + core.data.to_total_return)
import numpy as np
log_ret = np.log(close / close.shift(1))
sigma = log_ret.rolling(60, min_periods=60).std().shift(1)   # lagged 1 day, per DET-01
z = log_ret / sigma
shock_days = z[z.abs() > 2.5]
# Result on data/prices.parquet (1993-01-29..2026-10-07, total-return basis): 242 rows
```

### DET-02: gap opens, verified counts
```python
gap = open_ / close.shift(1) - 1
gap_days = gap[gap.abs() > 0.015]
# Result: 285 rows (total-return basis)
```

### DET-03: drawdown/rally episode detection (causal, no look-ahead)
```python
# Peak-tracking scan, single pass, no future information used at any point —
# same causal style as core/regimes.py::drawdown_table, which this closely resembles
# and could plausibly share logic with (both walk peak -> trough -> recovery).
peak_price = close.iloc[0]; in_dd = False
for date, price in close.items():
    if price >= peak_price:
        if in_dd and (trough_price / peak_price - 1) <= -0.05:
            emit_drawdown_episode(peak_date, trough_date, recovery=date)
        peak_price, in_dd = price, False
    else:
        in_dd = True
        trough_price = min(trough_price, price)
# Result: 36 drawdown episodes >= 5% (close basis), 4 of them >= 20%
```
Note the structural similarity to the already-existing, already-tested
`core/regimes.py::drawdown_table` — strongly consider factoring the shared peak/trough-scan logic
so DET-03 doesn't reimplement it from scratch. `[ASSUMED — a refactor opportunity, not verified
as strictly necessary; flag for the planner to decide, don't force a shared-code requirement that
might over-couple Overview's table semantics (which wants *all* drawdowns, unfiltered by 5%)
with the detector's semantics (which wants only >=5% ones as episodes).]`

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| n/a | n/a | n/a | This is greenfield detection logic specific to this project; there is no deprecated prior version inside this repo (Phase 0/1 didn't touch event detection). |

No "state of the art" drift risk here — this phase is bespoke statistical logic plus two public
government data sources, not a fast-moving library API surface.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|----------------|
| A1 | `release_id=10` = CPI, `release_id=50` = Employment Situation (payrolls) | Standard Stack / Anti-Patterns | If wrong, the macro calendar silently tags episodes against the wrong economic release — CAL-01/CAL-02 would pass their own tests (dates would still parse and populate) but mean something different than claimed. Must be confirmed with a real FRED API key call (`fred/release?release_id=10` returns a release name) before relying on it for the backfill. |
| A2 | Steepest-leg (peak→trough / trough→peak) is the right clustering span, not full peak→recovery | Summary, Architecture Patterns, Pitfall 1 | This is the single highest-leverage interpretive call in the whole phase — it's the difference between 87, 151, and 355 total episodes. It is grounded in empirical counts and in the spec's own search-window wording, but `docs/SPEC.md` never says explicitly "cluster on the steepest leg" — that's this research's inference. If the planner/user actually wants full peak-to-recovery as the episode span (accepting multi-year episodes for the two biggest crashes), DET-06's "low hundreds" target would need recalibrating or the merge-window constant would need changing instead. |
| A3 | Precedence order `drawdown > rally > shock > gap` for the single `trigger` column on multi-kind clusters | Architecture Patterns Pattern 2, Pitfall 4 | Low risk to correctness (any deterministic rule satisfies DET-05's replay-stability requirement), but affects what a human reading `episodes.parquet` believes "caused" the episode label — worth a quick gut-check with the project owner since it's a labeling/UX choice as much as a technical one. |
| A4 | `federalreserve.gov/monetarypolicy/fomchistorical{YEAR}.htm` is a stable URL pattern across the full 1993–2020ish range (only 1993, 1994, 2015 directly verified this session) | Architecture Patterns, Common Pitfalls Pitfall 2, Don't Hand-Roll | If the Fed changes this URL scheme for some intermediate years, the scraper needs per-year fallback logic. Low risk (government archival pages are usually stable for decades) but not exhaustively checked year-by-year in this session. |
| A5 | The exact cutover year between the historical per-year pages and the live `fomccalendars.htm` page (confirmed covering 2021–2027) is somewhere in 2019–2021 — not pinned down precisely | Architecture Patterns | If the builder assumes a wrong cutover year, it could either double-fetch a year or miss one entirely between the two source patterns. Cheap to fix at build time: dedupe by date after merging both sources. |

## Open Questions

1. **Does the project want full peak→recovery drawdown spans (the literal DET-03 wording) or
   steepest-leg spans for clustering/boundaries?**
   - What we know: literal wording makes two historical episodes span multiple years and
     swallows unrelated later shocks into them; steepest-leg spans hit the "low hundreds" target
     and keep all 7 DET-07 episodes cleanly separated.
   - What's unclear: whether "ends at a new high" is meant as the *display* fact only, or as a
     hard requirement on episode identity/boundaries that the planner must honor literally even
     if it produces far fewer, much longer episodes.
   - Recommendation: adopt the steepest-leg interpretation (A2 above) unless a discuss-phase pass
     with the project owner says otherwise; it's directly supported by empirical counts matching
     DET-06's explicit numeric target.

2. **Does the macro calendar need to extend into the future, and if so how is it kept fresh?**
   - What we know: Phase 2 only needs 1993→today for the backfill (CAL-01's literal ask). Phase 4
     adds nightly detection of *new* episodes, which will need to check scheduled releases that
     may be only days or weeks away (FOMC publishes meeting dates ~1–2 years ahead; BLS publishes
     its release schedule similarly far ahead).
   - What's unclear: whether Phase 2 should build `jobs/build_macro_calendar.py` as genuinely
     one-off (historical only, rerun manually if ever needed) and let Phase 4 own "keep it
     current," or whether Phase 2 should make it nightly-safe (idempotent, appends new future
     dates) now so Phase 4 just calls it.
   - Recommendation: build it idempotent/rerunnable now (cheap — it's the same fetch logic either
     way) even though Phase 2 only needs to run it once for the backfill; this avoids a Phase 4
     rewrite. Not load-bearing for Phase 2's own gate, but avoids rework.

3. **FRED API key acquisition — who gets it, and does it need to be a GitHub Actions secret?**
   - What we know: the key is free and instant per FRED's own signup flow (not independently
     re-verified in this session beyond confirming the key requirement itself); CLAUDE.md's
     existing pattern (Anthropic key as a GH secret, never in Streamlit Cloud/the repo) is the
     obvious template to follow if the calendar builder ever runs inside CI rather than once
     locally.
   - What's unclear: whether the one-off 1993+ backfill will be run locally by Jason (key lives
     only in his local env, never committed) or inside a GitHub Actions workflow (key needs to be
     a repo secret, following the existing `nightly.yml`/Anthropic-key pattern).
   - Recommendation: default to local-only for the Phase 2 backfill (simplest, no secret
     management needed yet); only promote to a GH secret if/when Phase 4's nightly job needs to
     refresh the calendar unattended.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| FRED API key (`api.stlouisfed.org`) | CAL-01 (CPI/payrolls dates) | ✗ (none found in local env or `gh secret list`) | — | Scrape `alfred.stlouisfed.org/releases/calendar?rid=X&y=YYYY` HTML instead (confirmed working for historical years; no key needed, more fragile parsing). |
| Network access to `federalreserve.gov` | CAL-01 (FOMC dates) | ✓ (confirmed live this session) | — | — |
| Network access to `api.stlouisfed.org` / `alfred.stlouisfed.org` | CAL-01 | ✓ (confirmed live this session, 400 response proves reachability) | — | — |
| `data/prices.parquet` (committed) | DET-01..07 (detector input) | ✓ | 8,480 rows, 1993-01-29 to 2026-10-07 | — |
| `.venv` conda Python 3.12 env | Running any script in this phase | ✓ | Python 3.12.15, pandas 3.0.6 | — |

**Missing dependencies with no fallback:** none.

**Missing dependencies with fallback:**
- FRED API key — fallback is the ALFRED HTML scrape path (see Open Question 3 and Pitfall 3).

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | No | No user-facing auth in this phase; the app remains read-only. |
| V3 Session Management | No | N/A. |
| V4 Access Control | No | N/A. |
| V5 Input Validation | Yes | Validate every parsed FRED/Fed date (parseable as a real calendar date, within a sane range) before writing `data/macro_calendar.parquet` — raise loudly on a malformed scrape result, matching `core/validate.py`'s existing fail-loud convention for `jobs/refresh_prices.py`, rather than silently writing a bad row. |
| V6 Cryptography | No | No crypto operations in this phase; if a FRED API key is ever stored as a GitHub Actions secret (see Open Question 3), that's secret *management* (already covered by the project's existing Anthropic-key pattern), not a cryptography control to design fresh. |

### Known Threat Patterns for this phase's stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| Malformed/changed HTML from federalreserve.gov silently producing wrong or missing FOMC dates | Tampering (data integrity, not an attacker) | Parse defensively and raise on unexpected structure (don't swallow parse errors); cover with fixture-based unit tests against the real page shapes confirmed this session (1993, 1994, 2015), so a future structure change fails a test rather than silently writing bad data. |
| FRED API key committed to the repo by accident during local development | Information Disclosure | Follow the exact existing project pattern: key lives only in a local `.env`/shell env never committed (`.gitignore` already excludes typical env files — verify `.env` is listed), promoted to a GitHub Actions secret only if/when a nightly job needs it (same as the Anthropic key's documented path in `docs/SPEC.md`). |
| Detector thresholds silently drifting from `core/config.py` into hard-coded literals during implementation | Tampering (self-inflicted, not external) | DET-06 already requires "all thresholds in config" — enforce with a simple grep-style test (no magic numbers for `2.5`, `0.015`, `0.05`, `0.08`, `30`, `3` inside `core/events.py`), mirroring how `core/regimes.py`'s docstring states the same rule for its own thresholds. |

## Sources

### Primary (HIGH confidence)
- `D:\GitHub\spy-analytics\docs\SPEC.md` — phase's own authority doc for thresholds, data model, repo layout.
- `D:\GitHub\spy-analytics\.planning\ROADMAP.md`, `docs\ROADMAP.md` — phase goal, success criteria, known-episode list.
- `D:\GitHub\spy-analytics\core\{config,storage,data,market_calendar,regimes,signals,indicators,validate}.py`, `jobs\refresh_prices.py`, `tests\{conftest,test_regimes,test_app_purity}.py` — read directly this session for existing conventions (pure-function style, dataclass usage, fail-loud validation, purity test boundaries).
- Live empirical run of DET-01..04 against the real committed `data/prices.parquet` (8,480 rows), this session — `.venv/python.exe` scratch script (pandas 3.0.6, numpy).
- Live `requests.get("https://api.stlouisfed.org/fred/release/dates", ...)` call without an `api_key`, this session — confirmed HTTP 400 and exact error text.

### Secondary (MEDIUM confidence)
- [fred.stlouisfed.org/release?rid=10 — Consumer Price Index](https://fred.stlouisfed.org/release?rid=10) — WebSearch result, cross-checked against the FRED URL's own `rid=` parameter naming convention.
- [fred.stlouisfed.org/release?rid=50 — Employment Situation](https://fred.stlouisfed.org/release?rid=50) — same caveat as above.
- [fred.stlouisfed.org/docs/api/fred/release_dates.html](https://fred.stlouisfed.org/docs/api/fred/release_dates.html) — official docs, fetched live this session; confirms `api_key` required, `realtime_start` defaults to 1776, but does not itself enumerate release_id meanings.
- [federalreserve.gov/monetarypolicy/fomc_historical.htm](https://www.federalreserve.gov/monetarypolicy/fomc_historical.htm) — fetched live this session; confirms per-year historical materials exist back through 1993 but gave no machine-readable index.
- [federalreserve.gov/monetarypolicy/fomchistorical1993.htm](https://www.federalreserve.gov/monetarypolicy/fomchistorical1993.htm), [...1994.htm](https://www.federalreserve.gov/monetarypolicy/fomchistorical1994.htm), [...2015.htm](https://www.federalreserve.gov/monetarypolicy/fomchistorical2015.htm) — fetched live this session; confirmed exact meeting-date lists and the Meeting/Conference-Call header distinction.
- [federalreserve.gov/monetarypolicy/fomccalendars.htm](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm) — fetched live this session; confirms current page covers 2021–2027.
- [alfred.stlouisfed.org/releases/calendar?rid=10&y=1994](https://alfred.stlouisfed.org/releases/calendar?rid=10&y=1994) — fetched live this session; confirms historical coverage via the ALFRED domain, unlike the equivalent non-ALFRED URL.

### Tertiary (LOW confidence)
- None used as load-bearing claims; the `release_id` meanings (A1 in Assumptions Log) are the
  closest thing to a tertiary-sourced claim and are explicitly flagged for confirmation.

## Metadata

**Confidence breakdown:**
- Detection thresholds / episode counts: HIGH — directly measured against the real committed dataset with three different merge strategies, not estimated.
- Clustering/merge semantics recommendation: MEDIUM — empirically well-supported, but the "steepest-leg vs full-span" choice (A2) is an interpretation of `docs/SPEC.md`, not something the spec states unambiguously; flagged as the top item for discuss-phase/planner attention.
- Macro calendar sourcing: MEDIUM-HIGH — FOMC source confirmed live across three sample years; FRED API mechanics confirmed live; release_id meanings only WebSearch-sourced (MEDIUM, flagged A1).
- Security: HIGH for "no new ASVS surface" conclusion (phase has no auth/session/UI surface); MEDIUM for the secrets-handling recommendation (follows existing project pattern, not independently re-verified against FRED's ToS).

**Research date:** 2026-10-08
**Valid until:** ~30 days for the detection-math findings (stable, data-dependent only on new price rows arriving, which won't change the fundamental merge-strategy conclusion). ~14 days for the FRED/Fed scraping specifics (government page structures are generally stable, but unverified for every intermediate year and worth a quick re-check at build time rather than trusting this research indefinitely).
