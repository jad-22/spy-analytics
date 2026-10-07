# Architecture Research

**Domain:** Offline data pipeline + read-only Streamlit dashboard (committed-file data contract, no runtime secrets/API calls)
**Researched:** 2026-10-07
**Confidence:** HIGH for component boundaries and data contracts (derived directly from `docs/SPEC.md` and the existing `core/` package conventions); MEDIUM for idempotency/versioning/testing patterns (general software-engineering practice, verified against multiple current sources, not a named framework specific to this stack)

This is not a domain with a named reference architecture (no "the Django of offline-pipeline-plus-dashboard"). It is a composition of well-understood, individually documented patterns: batch ETL idempotency, static-site-style "build then serve," a provider/strategy interface for a swappable LLM backend, and Streamlit's file-based caching model. The recommendations below synthesize those patterns against this repo's existing `core/` conventions (pure functions, dataclasses, pandas in/out, no framework imports) rather than inventing new ones.

## Standard Architecture

### System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│  OFFLINE SIDE — GitHub Actions, weekday evenings (nightly.yml)         │
│  Has network access + ANTHROPIC_API_KEY secret. Never deployed.        │
├──────────────────────────────────────────────────────────────────────┤
│  jobs/refresh_prices.py → jobs/detect_events.py → jobs/enrich_events.py│
│         │                        │                        │           │
│         ▼                        ▼                        ▼           │
│   core/data.py            core/events.py            core/news/*.py    │
│   (yfinance/Stooq)        core/calendar.py           (Claude+search)  │
│         │                        │                        │           │
│         └────────────┬───────────┴────────────┬───────────┘           │
│                       ▼                        ▼                      │
│              core/storage.py (schema-validated parquet/json read+write)│
│                       │                                                │
│                       ▼                                                │
│   jobs/nightly.py writes data/meta.json, then git-auto-commit-action   │
│   commits data/*.parquet + data/*.json  →  push  →  triggers redeploy  │
└──────────────────────────────────────────────────────────────────────┘
                                   │
                         (git commit is the API)
                                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│  READ SIDE — Streamlit Community Cloud (app/), ephemeral FS, no secret │
├──────────────────────────────────────────────────────────────────────┤
│  app/Home.py + app/pages/*.py                                         │
│      │ (st.cache_data-wrapped reads only)                             │
│      ▼                                                                │
│  core/storage.py read_*()  →  core/{indicators,signals,backtest,      │
│                                 metrics,grid,events}.py (recomputed    │
│                                 live from cached DataFrames, cheap)    │
│      ▲                                                                │
│      └── jobs/review_events.py (LOCAL ONLY, never imported by app/)   │
│          writes data/event_overrides.json by hand, outside nightly    │
└──────────────────────────────────────────────────────────────────────┘
```

The one-way arrow across the middle — files committed by the offline side, read by the online side — **is the entire integration contract**. There is no RPC, no shared process, no database connection. This is the same shape as a static-site generator (Hugo/Jekyll build → CDN serve), applied to a Streamlit app instead of HTML.

### Component Responsibilities

| Component | Responsibility | Notes |
|-----------|----------------|-------|
| `core/data.py`, `core/indicators.py`, `core/signals.py`, `core/backtest.py`, `core/metrics.py`, `core/grid.py` | Existing Phase 0 package: pure price/strategy math | Already built, zero Streamlit imports — the template to copy for new `core/` modules |
| `core/events.py` (new) | Pure event *detection*: price DataFrame in, episodes DataFrame out. No I/O, no LLM, no randomness | Must be callable identically from a job and from a test; this is where episode-ID stability logic lives (see below) |
| `core/calendar.py` (new) | Deterministic US macro calendar (FOMC/CPI/payrolls dates) | Static reference data wrapped in a lookup function; no network call needed if dates are vendored/hand-maintained per year |
| `core/news/base.py`, `core/news/schema.py` (new) | `NewsProvider` Protocol + pydantic `EventExplanation` model | The contract both `ClaudeSearchProvider` and `NullProvider` implement; this is the seam tests and future providers (GDELT) attach to |
| `core/news/claude_search.py` (new) | Impure: calls Anthropic API with web search tool, parses/validates response | Only module in `core/` that reaches the network at runtime — isolate it so it's easy to mock |
| `core/news/null.py` (new) | Deterministic fake provider, no network | Used by every test and by local app dev without an API key |
| `core/storage.py` (new) | Schema-validated read/write for every `data/*.parquet` and `data/*.json` file; owns file paths, dtypes, and the override-merge logic | The single chokepoint for the data contract — jobs write through it, app reads through it, nothing touches `data/` directly from elsewhere |
| `jobs/*.py` | Orchestration only: call `core/` functions, decide what's new vs. already done, write via `core/storage.py` | Thin; if a job script has real logic beyond "fetch inputs, call core, decide idempotency, write," that logic belongs in `core/` instead |
| `app/` | Streamlit pages; reads via `st.cache_data`-wrapped `core/storage.py` calls; recomputes indicators/signals/backtests live from cached inputs | Never imports `jobs/` or `core/news/claude_search.py`; never calls `requests`/`yfinance`/`anthropic` at runtime |
| `.github/workflows/nightly.yml` | Cron trigger, checkout, run `jobs/nightly.py`, commit via `git-auto-commit-action`, push | The only thing that turns "offline job ran" into "app sees new data" |

## Recommended Project Structure

This matches `docs/SPEC.md`'s repo layout almost exactly; the additions below are the modules that don't exist yet in `core/`, plus the test layout for the new provider/pipeline pieces.

```
core/
├── data.py / indicators.py / signals.py / backtest.py / metrics.py / grid.py   # existing, unchanged
├── events.py            # NEW — pure detection: shock/gap/drawdown/rally → episodes DataFrame
├── calendar.py           # NEW — US macro calendar lookup, deterministic
├── storage.py             # NEW — schema-validated read/write for every data/ file, override merge
└── news/
    ├── base.py            # NEW — NewsProvider Protocol
    ├── schema.py           # NEW — EventExplanation pydantic model, validation rules
    ├── claude_search.py    # NEW — real provider, isolated network boundary
    └── null.py             # NEW — deterministic fake, used by tests + local dev

jobs/
├── refresh_prices.py       # calls core.data, writes via core.storage
├── detect_events.py        # calls core.events, idempotent write (new episodes + open-episode updates only)
├── enrich_events.py        # calls core.news provider for unenriched episode_ids only, capped per run
├── review_events.py        # LOCAL ONLY — CLI or hidden page, writes event_overrides.json
└── nightly.py              # orchestrates the four above in order, writes meta.json last

tests/
├── conftest.py             # existing price fixtures + NEW: fixture episodes/events DataFrames
├── fixtures/
│   └── news/               # NEW — recorded Claude request/response pairs (sanitized), one file per scenario:
│       ├── explained.json          # normal case, sources inside window
│       ├── unexplained.json        # no dated source in window
│       └── needs_review.json       # low confidence / conflicting sources
├── test_events.py          # NEW — detection correctness + episode-ID stability under re-run
├── test_news_schema.py     # NEW — pydantic validation rules (date-in-window, confidence threshold)
└── test_storage.py         # NEW — round-trip + idempotent-write behaviour
```

### Structure Rationale

- **`core/news/` as its own subpackage, not flat files in `core/`:** keeps the one impure, network-touching module (`claude_search.py`) visually and structurally separated from the rest of `core/`, which stays import-safe (no `anthropic`, no `requests`) for every module except `data.py` and `news/claude_search.py`.
- **`core/storage.py` as a single chokepoint:** every other option (each job writing its own parquet/json ad hoc) means the override-precedence rule and the idempotent-write rule end up duplicated three or four times and drift. One module owns "how do episodes.parquet and events.json get merged into what the app reads."
- **`tests/fixtures/news/` as flat recorded JSON, not `vcrpy` cassettes:** the Claude web-search-tool response is already structured JSON (per `docs/SPEC.md`'s schema), so a plain fixture file is simpler than an HTTP-level cassette and doesn't need to replay TLS/connection details — see Testing Strategy below.

## Architectural Patterns

### Pattern 1: Build-then-serve (static-site-generator shape)

**What:** All expensive/impure work (network fetch, LLM calls) happens in a separate offline process that writes finished artifacts; the serving layer only reads finished artifacts and does cheap, pure recomputation.
**When to use:** Read-heavy, low-cardinality-of-writers systems where the data changes on a schedule, not per-request — exactly this app (daily bars, nightly-only writers).
**Trade-offs:** Freshness is bounded by the job schedule (acceptable here — SPEC explicitly says "never more than one trading day stale"). In exchange you get zero runtime secrets, zero runtime rate limits, and a deployment platform with an ephemeral filesystem becomes a non-issue instead of a blocker.
**Example (already the shape of `core/data.py`):**
```python
# jobs/refresh_prices.py (offline, has network)
df = load_prices(ticker, start)          # core.data — network
write_prices(df, SETTINGS.prices_path)   # core.storage — commits a file

# app/pages/1_Overview.py (online, no network)
@st.cache_data
def _prices():
    return read_prices(SETTINGS.prices_path)   # core.storage — just reads
```

### Pattern 2: Idempotent incremental write ("merge new, never blind-append")

**What:** Every job that writes to `data/` computes a diff against what's already there (by key — `episode_id`, trading date) and only adds/updates what's new or still "open"; it never blindly appends, and a full rebuild only happens on an explicit version bump.
**When to use:** Any nightly job that runs repeatedly against overlapping input (today's run sees yesterday's episodes again).
**Trade-offs:** Slightly more code per job (compute a key-set diff) versus "just overwrite everything" — but overwriting everything would silently shift `episode_id`s and detach `event_overrides.json`, which is the one failure mode that would put a visibly wrong explanation on a public page.
**Example:**
```python
existing = read_episodes(path)                       # core.storage
detected = detect_episodes(prices, cfg)               # core.events — pure, full re-detect is fine, it's cheap
new_or_open = detected[
    ~detected["episode_id"].isin(existing["episode_id"])
    | detected["episode_id"].isin(existing.loc[existing["status"] == "open", "episode_id"])
]
write_episodes(merge(existing, new_or_open), path)     # core.storage — upsert by episode_id
```

### Pattern 3: Provider interface with a null/fake implementation as a first-class citizen

**What:** `NewsProvider` (`core/news/base.py`) is a `Protocol`; `NullProvider` is not a test-only mock bolted on afterward but a real, shippable implementation used for local dev, CI, and as the fallback when no API key is configured.
**When to use:** Any external paid/rate-limited service behind an interface, especially one with cost caps (SPEC: ≤$25 backfill, hard per-run caps).
**Trade-offs:** Slightly more upfront design (the Protocol has to be stable before the real provider is written) in exchange for: the app and every downstream job/test can be built and fully exercised before `claude_search.py` exists or an API key is available.
**Example (already specified in `docs/SPEC.md`):**
```python
class NewsProvider(Protocol):
    name: str
    def explain(self, episode: Episode) -> EventExplanation: ...
```

## Data Flow

### Nightly pipeline flow

```
yfinance/Stooq → core.data.load_prices → data/prices.parquet
                                              │
                                              ▼
                        core.events.detect_episodes (+ core.calendar lookup)
                                              │
                                   upsert by episode_id ──→ data/episodes.parquet
                                              │
                        episode_ids with no entry in events.json
                                              │
                                   capped batch (config: max per run)
                                              │
                           core.news.claude_search.ClaudeSearchProvider.explain()
                                              │
                              pydantic-validate → status: explained|unexplained|needs_review
                                              │
                                   append-only by episode_id ──→ data/events.json
                                              │
                                   write run stats ──→ data/meta.json
                                              │
                              git-auto-commit-action commits + pushes
                                              │
                                 Streamlit Cloud redeploy (process restart, cache cleared)
```

### App read flow (per page load)

```
st.cache_data(read_prices) ─┐
st.cache_data(read_episodes)├─→ merge with event_overrides.json (override wins) ─→ page components
st.cache_data(read_events)  │        (core.storage.load_events_with_overrides)
st.cache_data(read_overrides)┘
         │
         ▼
core.indicators / core.signals / core.backtest / core.metrics   (recomputed live, cheap, driven by sidebar widgets)
```

### Key Data Flows

1. **Price refresh → everything downstream:** `prices.parquet` is the only input that changes nightly in a way that affects every page; `episodes.parquet` and `events.json` are derived and cached independently, so a price-only refresh (no new episodes) still redeploys a current chart without re-running detection or spending LLM budget.
2. **Override precedence at read time, not write time:** `event_overrides.json` is never merged into `events.json` on disk. `core/storage.py`'s read path always layers overrides on top at read time (`override field > model field`, keyed by `episode_id`). This keeps the model's original output auditable (SPEC's "honesty" constraint — every figure traceable) and makes an override reversible by deleting one JSON entry, not by re-running the pipeline.
3. **Episode status (`open`/`closed`) gates both detection idempotency and enrichment eligibility:** a drawdown/rally episode that hasn't yet hit its end condition (new high / 30-day window elapsed) is `open` — its `end_date` and `severity` can still change on the next nightly run, so it is re-evaluated each time. Only `closed` episodes are eligible for enrichment, so `enrich_events.py` never explains a story that might still change shape.

## Episode ID Stability (the core correctness requirement)

This is the one piece of this architecture that is genuinely domain-specific rather than off-the-shelf, so it gets its own section.

**The problem:** `detect_episodes` re-runs over the *entire* price history every night (cheap — a few thousand rows). If `episode_id` were assigned by row position or by enumeration order ("3rd episode detected this run"), every new day of data appended to the front, or any change in episode count, would renumber and detach every existing `event_overrides.json` entry and silently reassign LLM explanations to the wrong episode.

**The fix — deterministic, content-derived IDs, not sequence numbers:**
```python
episode_id = f"{anchor_date:%Y-%m-%d}_{trigger}"   # e.g. "2020-03-09_shock"
```
`anchor_date` (the single largest-move day in the episode, per SPEC) and `trigger` (`shock`/`gap`/`drawdown`/`rally`) are both determined by data *strictly before* the episode closes. Because:
- shock/gap detection uses only a **lagged** rolling-60-day σ (per SPEC: "σ lagged one day") — classification of day *t* never depends on data after *t*;
- clustering only looks 3 trading days forward/back to merge adjacent flagged days — a fixed, small, backward-stable window;
- drawdown/rally episodes close only on a confirmed new high / elapsed 30-day window — before closing they are `open` and their `anchor_date` can still move (handled above), but once `closed` the anchor is frozen and never recomputed;

...an episode's ID cannot change once `status == closed`, no matter how much future data arrives. This is what makes "detect over full history every night" safe and idempotent: re-running the detector doesn't redetect the past differently, it only ever adds new episodes or advances `open` ones.

**The escape hatch — `detector_version`:** if detection thresholds or clustering logic change (Phase 2 calibration, or a bug fix later), IDs for *already-closed* episodes must not be silently reassigned under the new logic. Bump `detector_version` in `core/config.py`; `jobs/detect_events.py` compares it against the `detector_version` stored in `data/meta.json`:
- same version → incremental upsert (new/open episodes only), as above;
- different version → full rebuild, logged loudly in `meta.json` and in the Actions run output, with a note that `event_overrides.json` entries for IDs that no longer exist need manual review (`jobs/review_events.py` should flag orphaned overrides).

This mirrors the general "idempotent pipeline" pattern (partition-overwrite only on an explicit, versioned rebuild; upsert-by-key otherwise) confirmed as current practice for batch pipelines — see Sources.

## Caching in Streamlit

**Confidence: HIGH** — current Streamlit docs (`docs.streamlit.io/develop/concepts/architecture/caching`) confirm `st.cache_data` is the correct decorator for functions returning DataFrames/dicts (not `st.cache_resource`, which is for unserializable objects like DB connections — not applicable here since there's no live connection).

Recommendations specific to this app's "purity" constraint (`core/` must stay Streamlit-import-free):
- `st.cache_data` decorators live in `app/` (e.g., `app/components/data.py` or inline at the top of `Home.py`), wrapping the plain, undecorated functions in `core/storage.py`. `core/storage.py` itself must not import `streamlit` — this preserves it as independently testable and keeps `core/` deployable in a non-Streamlit context (scripts, tests, a future CLI).
- **No TTL is needed**, unlike a typical production dashboard reading a live warehouse: a nightly commit triggers a full Streamlit Cloud redeploy, which restarts the process and clears every `st.cache_data` entry automatically. A TTL would only protect against staleness *within* a single long-lived process between redeploys — which can't happen here because the only writer is the nightly job, and the only way new data reaches the app is a redeploy. Document this reasoning in code (a comment next to the cache decorators) so a future contributor doesn't "fix" perceived staleness by adding a TTL that masks a real redeploy failure instead.
- Cache functions on the **file path, not on a manually-specified key** — `st.cache_data` already hashes function arguments, and passing `SETTINGS.prices_path` as the only argument is enough; there's no need for a manual cache-busting parameter since Streamlit Cloud's redeploy is the busting mechanism.
- Keep `core/storage.py` read functions **pure and copy-safe** (return a fresh DataFrame each call, as `core/data.py::read_prices` already does) — `st.cache_data` relies on this to safely return copies to each caller.

## Provider Interface for News

Already specified in `docs/SPEC.md`; the architectural point worth adding:

| Aspect | Recommendation | Why |
|--------|-----------------|-----|
| Interface location | `core/news/base.py`, a `Protocol`, not an ABC | Matches this repo's existing style (dataclasses, light abstractions) and lets `NullProvider`/`ClaudeSearchProvider` satisfy it structurally without inheritance ceremony |
| Where network lives | Only `core/news/claude_search.py` imports `anthropic` | Every other module in `core/news/` (schema, base, null) stays import-light and safe to use anywhere |
| Config injection | Provider chosen by `jobs/enrich_events.py` based on config/env (e.g., `NewsProvider = ClaudeSearchProvider() if ANTHROPIC_API_KEY else NullProvider()`), not hardcoded | Lets local dev and CI run the full pipeline end-to-end against `NullProvider` with zero network/cost, matching the "offline jobs only" and budget constraints |
| Future providers (GDELT, deferred per PROJECT.md) | Add a new file in `core/news/`, nothing else changes | This is the entire point of the Protocol — confirmed as the reason it's in scope per SPEC's rejected-alternatives table |

## Local Review Tool

`jobs/review_events.py` sits in an unusual spot: it writes to the same `data/` directory the nightly job writes to, but it must **never** be reachable from the deployed app (no API key, no write access on Streamlit Cloud's ephemeral FS, and a public visitor must never be able to edit event records).

- Keep it a plain script (CLI, `argparse` or just hardcoded prompts) or a Streamlit app run with `streamlit run jobs/review_events.py` **locally only** — if it's a Streamlit app, it must live outside `app/pages/` (which Streamlit auto-discovers and would deploy) — e.g. `jobs/review_events.py` as a standalone entry point, not a page.
- It reads `events.json` + `episodes.parquet` (read-only, via `core.storage`), and writes only to `event_overrides.json`, never to `events.json` — this preserves the "model output vs. human override, always auditable separately" boundary described above.
- No test coverage needed for its UI, but the merge/precedence logic it exercises (override > model output) belongs in `core/storage.py` and *does* need tests, since both the app and the review tool depend on it behaving identically.

## Test Strategy

**Confidence: MEDIUM** — these are current, widely-documented patterns (VCR-style record/replay for LLM calls, fixture-based provider substitution) rather than something unique to this stack; verified against multiple 2026 sources, not vendor docs, hence MEDIUM rather than HIGH.

| Layer | Strategy | Why |
|-------|----------|-----|
| `core/events.py` detection | Synthetic price fixtures (extend existing `tests/conftest.py` fixtures with engineered shocks/drawdowns at known dates) + property-style re-run test: run detection on `prices[:t]` then on `prices[:t+30]` and assert every `closed` episode's ID and fields from the first run are unchanged in the second | This is the single most important test in the whole system — it directly verifies the "episode IDs don't churn" requirement, not just detection correctness |
| `core/news/schema.py` validation | Pure pydantic unit tests, no I/O: date-outside-window → `unexplained`, low confidence/conflicting sources → `needs_review`, well-formed input → `explained` | Fast, no network, covers the validation rules directly from SPEC's "Validation rules" list |
| `core/news/claude_search.py` | **Record/replay, not live calls in CI.** Record a handful of real request/response pairs once (sanitized of the API key) into `tests/fixtures/news/*.json`; tests feed the recorded response through the same parse+validate path the real provider uses, asserting on the schema/validation behaviour, not on the API call itself | This is the standard current pattern for testing LLM-backed code without cost, flakiness, or needing network in CI (VCR.py / pytest-recording / pytest-llm-vcr are the named tools for this; a hand-rolled fixture-replay is equally valid here since the provider's output is already a single structured JSON blob, not a multi-turn HTTP conversation) |
| `core/news/null.py` | Direct unit test — deterministic output for a given `episode_id`, used as the default provider in every other test that needs *a* provider without caring which | Also doubles as the provider used by `jobs/enrich_events.py` tests and by local app dev |
| `jobs/*.py` idempotency | Run each job twice against the same fixture `data/` directory (tmp_path), assert second run is a no-op (no new rows) except for still-`open` episodes | Directly tests the idempotent-write pattern above; cheap since these are pure-Python/pandas, no network if `NullProvider` is injected |
| `core/storage.py` override precedence | Fixture `events.json` + fixture `event_overrides.json`, assert merged read result prefers override fields field-by-field | Protects the one rule a reviewer relies on (override always wins) |
| `app/` | Out of scope for unit tests beyond "does it import without hitting network" — Streamlit page logic is thin by design (reads + chart calls); if coverage is wanted later, Streamlit's `AppTest` harness is the current official tool, but this is lower priority than the pipeline tests above | App logic should stay thin enough that most bugs are caught by testing `core/` directly |

## Anti-Patterns

### Anti-Pattern 1: App importing `jobs/` or any network-calling module

**What people do:** Import a helper from `jobs/refresh_prices.py` into an `app/` page "just to reuse a function," or call `core.data.fetch_yfinance` directly from a page for a "live" feature.
**Why it's wrong:** Breaks three explicit constraints at once — ephemeral FS (nothing persists what it fetches), no secrets in the app (the API key isn't there to use anyway, so it would just fail or need a key to be added to Streamlit Cloud, reintroducing the exact risk SPEC rules out), and public-visitor cost/abuse risk.
**Do this instead:** If a page needs something a job computes, that computation belongs in `core/` as a pure function the job *and* a test can call, with its output written to `data/` for the app to read. If it's genuinely runtime-only (e.g., a date range slider), compute it from already-loaded DataFrames, never from a new fetch.

### Anti-Pattern 2: Rebuilding `episodes.parquet` from scratch on every run without versioning

**What people do:** `detect_events.py` just does `df.to_parquet(path)` over the freshly detected full-history result every night, reasoning "it's cheap to recompute, why bother with upsert logic."
**Why it's wrong:** As long as detection logic is unchanged this happens to be safe *only* because IDs are content-derived (see Episode ID Stability above) — but it silently loses any `open`→`closed` transition tracking, and worse, it means a detector-logic change (even a one-line threshold tweak) retroactively and invisibly changes historical IDs with no record that it happened, orphaning `event_overrides.json` without any warning.
**Do this instead:** Always diff against `detector_version` in `meta.json`; upsert by key on matching versions, full rebuild with a loud log line + orphaned-override check on a version bump.

### Anti-Pattern 3: Treating `NullProvider` as test-only scaffolding to delete later

**What people do:** Write `NullProvider` quickly to unblock early development, intending to remove it once `ClaudeSearchProvider` works.
**Why it's wrong:** It's the only way to run the full pipeline (and develop/demo the app) without an API key or network access, and it's what every test for `jobs/enrich_events.py` and `core/storage.py` override-merge logic should inject instead of a mock.
**Do this instead:** Keep it in `core/news/null.py` permanently as a first-class provider, matching the Protocol exactly, documented as the default when no key is configured.

### Anti-Pattern 4: Storing raw article text or full LLM responses as the "source of truth"

**What people do:** Cache the full Claude API response (including quoted article text) in `events.json` "in case we need it later," or let the summary field contain lightly-edited copy-paste from a source.
**Why it's wrong:** Violates the copyright constraint (own-words summaries, links out, no stored article text) and makes `events.json` bloat over time as a de facto audit log instead of a lean read model.
**Do this instead:** Store only the validated structured fields (`headline`, `summary` in the model's own words, `sources` as title/url/publisher/date). If a raw-response audit trail is wanted for debugging, write it to a separate, not-committed, or short-retention location (e.g., a GitHub Actions run artifact), never into the committed `data/` files the app reads.

## Scaling Considerations

This genuinely does not need to scale beyond its current shape — restated here because it's an explicit project decision (PROJECT.md: "Hosted database / SQL Server — a few thousand rows fit in committed Parquet/JSON"), not an oversight.

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Current (≈4,000 price rows, low hundreds of episodes) | Exactly the architecture above: committed Parquet/JSON, Streamlit Cloud, GitHub Actions cron. No changes needed. |
| If episode count grew 10x (unlikely — SPEC caps backfill to keep it in "low hundreds") | `events.json` as one file read entirely on every page load is still fine (a few hundred KB); if it ever got into the tens of MB, split by year, still read through `core/storage.py` so the app boundary doesn't change. |
| If this became multi-ticker or multi-strategy (explicitly out of scope per PROJECT.md) | Would need a real reconsideration, not an incremental tweak — the whole point of the current design is "a few thousand rows of one ticker." Not worth designing for pre-emptively. |

## Build Order

Dependency-driven, not calendar-driven; items at the same letter can be parallelized.

1. **`core/storage.py`** — schema-validated read/write + override-merge, before anything else, since every job and every app page depends on this contract being stable. Pairs naturally with `core/events.py`'s `Episode`/episode DataFrame shape being settled first.
2. **`core/events.py`** (detection) and **`core/calendar.py`** (macro dates) — independent of each other, both pure, both testable immediately with synthetic fixtures extending `tests/conftest.py`. This is where the episode-ID-stability test belongs, before any job wraps it.
3. **`core/news/base.py` + `core/news/schema.py`** — the Protocol and pydantic model, with validation-rule unit tests, before any real provider exists.
4. **`core/news/null.py`** — trivial once (3) exists; unblocks everything downstream that needs "a provider" without needing an API key.
5. **`jobs/refresh_prices.py`** — thin wrapper, low risk; can run manually immediately to populate/refresh `data/prices.parquet` for local app development.
6. **`app/` skeleton + Overview page** — can start as soon as (1) and (5) exist, in parallel with steps 2–4, since Overview only needs prices. This matches PROJECT.md's Active-requirements ordering (Overview/Strategy Lab before event detection).
7. **`jobs/detect_events.py`** — wraps (2), writes via (1), idempotently; needs (1)(2)(5) done first (needs prices to detect against).
8. **`core/news/claude_search.py`** — the real provider; build once (3) is stable, test via recorded fixtures (no live calls needed to develop the parsing/validation path, only to record the initial fixtures).
9. **`jobs/enrich_events.py`** — needs (3)(4)(7)(8); injects `NullProvider` or `ClaudeSearchProvider` based on config, processes unenriched `closed` episodes up to the per-run cap.
10. **`app/pages/3_Event_Explorer.py`, `4_Event_Study.py`** — need (7) and (9) to have real `data/episodes.parquet` + `events.json` to render against; can be developed against fixture data earlier if needed, but the real pipeline should exist first for the one-off backfill this phase requires per SPEC.
11. **`jobs/review_events.py`** — needs (9) producing `events.json` to review; lowest priority of the jobs, can slip to just before the backfill is reviewed rather than before it's generated.
12. **`jobs/nightly.py`** — orchestrates 5, 7, 9 in order and writes `data/meta.json`; needs all three working standalone first.
13. **`.github/workflows/nightly.yml`** — wraps (12) + `git-auto-commit-action`; build and dry-run last, once `jobs/nightly.py` works end-to-end locally against a small date range.
14. **Methodology page** — last; documents the corrected engine, detection thresholds, LLM caveats and disclaimer, so it should reflect the final, settled behaviour of everything above.

This ordering lets the Strategy Lab / Overview pages (pure `core/` + prices only) ship as an early milestone while the event-detection/news-enrichment track (steps 2–4, 7–11) proceeds in parallel — consistent with `docs/SPEC.md`'s own note that "Phases 1 and 2 can overlap if the detector is built while the MVP is deployed."

## Sources

- [Streamlit caching overview (official docs)](https://docs.streamlit.io/develop/concepts/architecture/caching) — HIGH confidence, current official docs; confirms `st.cache_data` is correct for DataFrame-returning functions and that it returns safe copies.
- [git-auto-commit-action (GitHub Marketplace / stefanzweifel)](https://github.com/marketplace/actions/git-auto-commit) — MEDIUM confidence (community action, widely used); confirms the "nightly job commits its own output" pattern and required `contents: write` permission + `persist-credentials: true`.
- [Idempotent Data Pipelines with Spark and SQLMesh](https://medium.com/@andymadson/idempotent-data-pipelines-with-spark-and-sqlmesh-eda8056b07c5) and [Idempotent Pipelines: Build Once, Run Safely Forever](https://dev.to/alexmercedcoder/idempotent-pipelines-build-once-run-safely-forever-2o2o) — MEDIUM confidence; corroborate the upsert-by-key-over-blind-append pattern applied to `episodes.parquet`/`events.json` above.
- [dbt incremental patterns for near real-time data](https://docs.getdbt.com/best-practices/how-we-handle-real-time-data/2-incremental-patterns) — MEDIUM confidence; general confirmation of "only process new records since last watermark" as current best practice, adapted here to `episode_id`/`status` rather than a timestamp watermark since episodes aren't strictly append-only in arrival order.
- [VCR-Style Record/Replay for LLM Tests](https://dev.to/mukundakatta/vcr-style-recordreplay-for-llm-tests-make-your-agent-tests-deterministic-and-free-3o6d) and [pytest-llm-vcr (PyPI)](https://pypi.org/project/pytest-llm-vcr/0.6.0/) — MEDIUM confidence; confirms record-once/replay-in-CI is the current standard approach for LLM-backed test suites, used here to justify the hand-rolled `tests/fixtures/news/*.json` approach rather than requiring a new dependency.
- `docs/SPEC.md` (this repo) — HIGH confidence; primary source for the data model, provider interface signature, validation rules, and repo layout that this research extends rather than re-derives.
- `core/data.py`, `core/backtest.py`, `core/metrics.py`, `core/signals.py`, `core/config.py`, `tests/conftest.py` (this repo) — HIGH confidence; primary source for the existing `core/` conventions (pure functions, dataclasses, no Streamlit/network imports outside `data.py`, pandas-copy-safety) that new modules should match.

---
*Architecture research for: offline-pipeline + read-only Streamlit dashboard (SPY Market Lens)*
*Researched: 2026-10-07*
