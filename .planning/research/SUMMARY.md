# Project Research Summary

**Project:** SPY Market Lens
**Domain:** Public Streamlit financial-analytics portfolio app — backtesting dashboard + LLM-sourced market-event explainer, offline nightly pipeline feeding a read-only deployed app
**Researched:** 2026-10-07
**Confidence:** MEDIUM-HIGH

## Executive Summary

This is a brownfield portfolio project: a corrected, tested `core/` backtest engine (Phase 0, done) needs a Streamlit front end, an event-detection + macro-calendar layer, and an LLM-driven news-enrichment pipeline, all deployed read-only on Streamlit Community Cloud and fed nightly by GitHub Actions. Experts build this class of app as two cleanly separated halves joined only by committed files: an offline side (GitHub Actions, has network + secrets, runs `refresh → detect → enrich → commit`) and a read side (Streamlit Cloud, ephemeral filesystem, no secrets, no runtime API calls, only reads committed Parquet/JSON). This "build-then-serve" shape — the same pattern as a static-site generator — is what resolves nearly every platform constraint at once (no secrets exposure, no runtime rate limits, ephemeral FS is a non-issue) and should be treated as the project's organizing architectural decision, not an implementation detail.

The recommended approach layers `st.navigation`-based multipage Streamlit (not the literal `pages/` directory sketched in SPEC.md), Plotly for charts with WebGL fallback for full-history views, pydantic-validated LLM output via the Anthropic SDK's native structured outputs plus the web-search tool, and a strict `core/` purity rule (no Streamlit or network imports outside `data.py` and `news/claude_search.py`). Feature-wise, the MVP is already correctly scoped in SPEC.md's Active requirements — Overview, Strategy Lab, Event Explorer, Event Study, Methodology — and research confirms the project's strongest differentiator is leading with a rigorously negative finding ("0/24 rules beat buy-and-hold") rather than hiding it, paired with a genuine event-study CAAR-style aggregation that no comparable retail tool (GuruFocus, Macrotrends, AnyChart) attempts.

The key risks cluster around three places where "looks correct" and "is correct" diverge: (1) presentation-layer data-snooping creeping back into the heatmap/IS-OOS/rolling-start charts even though the underlying engine is already corrected; (2) event-detector episode-ID instability under incremental nightly re-runs, which silently orphans or duplicates LLM-enriched records and wastes backfill spend; and (3) LLM web-search attribution producing confident, well-cited, but wrong or hindsight-biased explanations that the planned schema validation doesn't fully catch. All three have concrete, specific mitigations documented in PITFALLS.md and should be treated as acceptance criteria for their respective phases, not polish. A fourth, lower-stakes risk — GitHub Actions' silent 60-day workflow auto-disable and DST cron drift — needs an independent staleness check, since this app's core value proposition ("every number is honest and traceable") is undermined by silent staleness more than by almost any other failure mode.

## Key Findings

### Recommended Stack

The stack is largely already decided by SPEC.md/PROJECT.md; research confirms and sharpens specific choices rather than overturning them. Python 3.12 (already the project floor and Streamlit Cloud's default), Streamlit `>=1.49` using `st.navigation`/`st.Page` (not the spec's literal `pages/` directory — this is a one-way-door decision, make it from the first page), Plotly `>=5.24` with `go.Scattergl` for full-33-year line views and a default windowed range for candlesticks (perf degrades above ~2-5k OHLC points), `st.plotly_chart(..., on_select="rerun")` for click-to-detail (verify it actually fires on heatmap/imshow chart types — documented Streamlit gaps exist there), pydantic `>=2.9` for validating LLM output schemas, and the `anthropic` Python SDK `>=1.11` using `client.messages.parse(output_format=...)` native structured outputs combined with the `web_search` tool in one call per episode.

**Core technologies:**
- Streamlit (`st.navigation`) — multipage app host and deploy target — gives explicit URL/label/sidebar-grouping control the spec's `pages/` sketch doesn't
- Plotly — candlestick/line/marker charts with click-to-select — the only library here that supports the event-marker + shaded-region + selection interaction the spec needs
- pydantic — validates `EventExplanation`/episode/calendar schemas before anything is trusted and written to `data/events.json`
- `anthropic` SDK — structured-output + web-search calls for news enrichment, isolated to a single `core/news/claude_search.py` module
- `tenacity` — retry/backoff around yfinance and Claude calls (not yet in `pyproject.toml` — add it)

**Unverified / needs confirmation before use:** STACK.md recommends a model it calls `claude-haiku-5-5` at $0.10/$0.50 per MTok and estimates the $25 backfill budget (~$5-10) against that model/pricing. That exact model ID is **not** on the orchestrator's verified current model list (`claude-fable-5-1`, `claude-opus-5-5`, `claude-sonnet-5`, `claude-haiku-4-5-20251001`). Treat both the model choice and the dollar estimate as unverified placeholders — re-confirm the correct current Haiku-tier model ID and its actual pricing against official Anthropic docs (web search) before scoping or running the real backfill. This is already a spec requirement (budget cap discipline) and should be an explicit early step in whichever phase builds `core/news/claude_search.py`, not an afterthought.

Also flagged: the spec's literal Stooq-via-`pandas-datareader` fallback is confirmed broken in 2026 (reader removed, Stooq now requires a CAPTCHA-gated API key) — recommend simplifying to "yfinance + retries + last-good-committed-snapshot" rather than rebuilding a second scraped fallback, and revisiting that line in PROJECT.md's Key Decisions.

### Expected Features

The MVP scope already in SPEC.md's Active requirements matches table-stakes conventions from Portfolio Visualizer/testfol.io/QuantConnect (equity-vs-benchmark, metrics table, heatmap, rolling-start, IS/OOS split) and event-timeline tools (GuruFocus/AnyChart-style markers with click-through detail, filterable table). Nothing in the existing MVP scope should be cut.

**Must have (table stakes, already scoped):**
- Equity curve vs. buy-and-hold, core metrics table (CAGR, max DD, Sharpe, time in market — add Sortino/Calmar cheaply)
- Parameter heatmap + rolling-start robustness + IS/OOS split, each with a visible caveat against cherry-picking
- Event markers with click-through detail panel + filterable table; sourced citations with dates on every event
- Methodology/about page — research flags this as the single highest-ROI page for a recruiter audience

**Should have (differentiators, cheap to add alongside MVP):**
- Leading with "0/24 rules beat buy-and-hold" as the headline finding, not buried — costs nothing, is the strongest differentiator identified
- Risk-reduction scatter (CAGR vs max DD across all 24 rules) — one new Plotly chart, high narrative payoff
- Overfitting-awareness caption tied to the heatmap; marker-level status styling (hollow/grey for unexplained vs. needs_review) so the honesty signal is visible at the chart level, not just in a tooltip
- Event Study category-average paths + recovery-time distribution — the single most differentiating page vs. every comparable annotated-chart competitor (none of them aggregate across events)

**Anti-features / explicitly out of scope (orchestrator-corrected):**
- **"Oracle" hindsight line/marker in the UI** — FEATURES.md suggested a labelled dashed "oracle" line on the Strategy Lab chart as a differentiator. **This is dropped per PROJECT.md's Key Decisions** ("Drop the notebook's oracle trades from the UI... mentioned only as a lesson in Methodology text"). Treat as an anti-feature for the UI layer; the lesson belongs in Methodology prose only, never as a chart element.
- Runtime LLM Q&A/chatbot, parameter auto-optimizer action, user accounts/saved runs, live/intraday data, non-US macro calendar — all explicitly out of scope per PROJECT.md and structurally incompatible with the read-only/no-runtime-API architecture or the honest-negative-finding narrative.

### Architecture Approach

The system is two halves joined only by committed files — an offline GitHub Actions side (`refresh_prices → detect_events → enrich_events → nightly.py` orchestrator, writes via a single `core/storage.py` chokepoint, commits and pushes) and a read-only Streamlit Cloud side (`app/` pages read via `st.cache_data`-wrapped `core/storage.py` calls, recompute indicators/backtests live and cheaply, never import `jobs/` or any network-calling module). This is a static-site-generator shape applied to a Streamlit app.

**Major components:**
1. `core/storage.py` (new) — the single schema-validated read/write chokepoint for every `data/*.parquet`/`*.json` file, owns override-merge logic; build this first, before anything else depends on it
2. `core/events.py` + `core/calendar.py` (new) — pure, deterministic event detection and US macro-calendar lookup; this is where episode-ID stability logic must live, tested via a replay test across incremental historical slices
3. `core/news/` subpackage (`base.py` Protocol, `schema.py` pydantic model, `claude_search.py` real provider, `null.py` deterministic fake) — isolates the one network-touching module and makes `NullProvider` a first-class, permanent default (not test scaffolding) so the full pipeline runs with zero cost/network when no API key is present
4. `jobs/*.py` — thin orchestration only; any real logic belongs in `core/` instead, enforced so jobs stay testable
5. `.github/workflows/nightly.yml` — cron trigger + `git-auto-commit-action`; the only thing that turns "offline job ran" into "app sees new data"

The one domain-specific correctness requirement with no off-the-shelf pattern is **episode ID stability**: IDs must be content-derived (`anchor_date + trigger`) and frozen once an episode is `closed`, with a `detector_version` escape hatch for any logic change — this is what makes nightly full-history re-detection safe and keeps `event_overrides.json` from silently detaching.

### Critical Pitfalls

1. **Heatmap/IS-OOS/rolling-start charts re-introduce data-snooping bias at the presentation layer** even though the underlying engine is corrected (picking a "best cell" post-hoc, a visitor-tunable split date, rolling windows that share trailing history and aren't independent trials) — avoid by fixing the IS/OOS split date in config (not a slider), captioning every chart with a selection-bias caveat, and making the Methodology page state plainly that the heatmap's purpose is showing risk reduction, not finding a winner.
2. **Event detector warm-up/clustering/episode-ID-churn bugs silently corrupt the downstream news pipeline** — the first ~60 trading days of 1993 history lack valid rolling sigma, naive pairwise clustering is order-dependent, and IDs derived from a still-shifting anchor date orphan already-enriched records. Avoid by dropping the warm-up window explicitly, implementing clustering via union-find/transitive closure, freezing episode boundaries once closed, and writing an incremental-replay test (detect on data through date A, then through date B, assert closed-episode IDs never change, only extend).
3. **LLM web-search attribution produces confident, well-cited, wrong explanations** that pass the planned schema/date-window validation: post-hoc retrospective articles dated inside the window, confident single-cause narratives on genuinely multi-causal days, and hallucinated-but-plausible citation URLs. Avoid by parsing URLs from the tool's structured citation metadata (never model prose), forcing `needs_review` when the macro calendar shows multiple qualifying releases in the window, and treating self-reported confidence as a weak signal only — gate on human review for the largest/most visible episodes regardless of confidence.
4. **Claude API cost blowup from uncapped search iterations, retries, and re-enrichment of unchanged episodes** — cap `max_uses` on the web-search tool per call *and* a per-run episode cap, never auto-retry a failed episode from scratch (mark `needs_review` instead), and log actual spend to `meta.json` with a hard ceiling assertion. This must be resolved before the one-off backfill since that spend is irreversible.
5. **GitHub Actions nightly workflow silently disables after 60 days of repo inactivity, and UTC cron drifts against UK time across DST** — add an independent staleness check (separate workflow or alert reading `meta.json`'s `last_refresh`) that fires if data is stale beyond ~2 trading days, since this is the most likely way the public app goes quietly stale without the owner noticing, directly undermining the "honest and traceable" core value.

## Implications for Roadmap

Based on combined research, the project naturally splits along the architecture's dependency order and the spec's own stated "Phases 1 and 2 can overlap" note, while respecting the orchestrator's locked decision for **coarse granularity (3-5 phases)** and **vertical MVP slices**.

### Phase 1: Foundation + Overview/Strategy Lab (price-only vertical slice)
**Rationale:** `core/storage.py` is the one chokepoint every later job and page depends on; it must be stable first. Overview and Strategy Lab need only prices (already in Phase 0's `core/data.py` + a nightly refresh job) — no event detection or LLM dependency — so this is the fastest path to a deployed, demoable vertical slice and lets the Strategy Lab/events tracks proceed in parallel afterward, per SPEC.md's own note.
**Delivers:** `core/storage.py`; `jobs/refresh_prices.py` (with `auto_adjust`/`multi_level_index` pinned explicitly, snapshot-diff anomaly guard); Streamlit app skeleton using `st.navigation`; Overview page (price chart, MA overlays, drawdown shading, KPI strip); Strategy Lab (rule picker, costs, equity vs. B&H, metrics incl. Sortino/Calmar, heatmap, rolling-start, IS/OOS split); first Streamlit Cloud deploy + nightly GitHub Actions job wired end-to-end on prices only.
**Addresses:** All P1 table-stakes features for Overview/Strategy Lab from FEATURES.md, plus the P2 risk-reduction scatter and overfitting-awareness caption (cheap, no new pipeline, same phase as their parent charts).
**Avoids:** Pitfall 1 (presentation-layer data-snooping — fix IS/OOS split as a config constant and caption every chart from day one); Pitfall 2 (yfinance adjusted-price drift — pin `auto_adjust` explicitly with a test); Pitfall 6/7 (nightly automation + Streamlit Cloud caching/memory — get the redeploy-while-session-open and resource-ceiling behavior verified on this simplest possible page set, before event/news complexity is layered on).

### Phase 2: Event Detection + Macro Calendar
**Rationale:** Event detection and the macro calendar are both pure, independently testable, and have no LLM dependency — they can be built and fully validated (including the episode-ID-stability replay test) before any backfill spend is at risk. This must be solid before enrichment, since enrichment cost is wasted if IDs churn.
**Delivers:** `core/events.py` (shock/gap/drawdown/rally detection with explicit warm-up handling and union-find clustering), `core/calendar.py` (US FOMC/CPI/payrolls lookup), `jobs/detect_events.py` with idempotent upsert-by-key writes, `detector_version` versioning in `meta.json`.
**Uses:** pandas/pyarrow from the existing stack; no new external dependency beyond what's already pinned.
**Implements:** The episode-ID-stability pattern (content-derived IDs frozen on `closed` status) — the one domain-specific architectural requirement flagged as HIGH-importance across both ARCHITECTURE.md and PITFALLS.md.
**Avoids:** Pitfall 3 (detector warm-up/clustering/ID-churn) directly — the replay test (detect on `prices[:t]` then `prices[:t+30]`, assert closed-episode IDs unchanged) is the explicit acceptance criterion for this phase, not an optional nice-to-have.

### Phase 3: News Enrichment + Backfill
**Rationale:** Depends on Phase 2's stable episode IDs (enrichment cost is wasted otherwise) and is the phase with the most unverified assumptions (model ID, pricing, structured-output + web-search interaction) — isolate it so the irreversible backfill spend happens only after the Protocol/schema/NullProvider path is proven end-to-end with zero cost.
**Delivers:** `core/news/base.py` + `schema.py` (Protocol + pydantic `EventExplanation`, validation rules) -> `core/news/null.py` (first-class fake provider) -> `core/news/claude_search.py` (real provider, built against recorded fixtures first) -> `jobs/enrich_events.py` (capped, idempotent, spend-logged) -> `jobs/review_events.py` (local-only manual review/override tool) -> the one-off historical backfill itself.
**Research flag:** **Before scoping or running the backfill, verify the actual current Haiku-tier model ID and its official pricing via web search against `platform.claude.com`** — STACK.md's `claude-haiku-5-5`/$0.10-$0.50-per-MTok figures are unverified against the orchestrator's confirmed model list and must not be taken as given. Re-run the budget estimate once the real model ID and prices are confirmed, and dry-run a small batch (~20 episodes) before committing to the full backfill, within the locked **$25 cap**.
**Avoids:** Pitfall 4 (confident-wrong LLM attribution — parse citations from tool metadata, force `needs_review` on multi-causal/macro-calendar-overlap days); Pitfall 5 (cost blowup from retries/re-enrichment — hard caps on `max_uses` and per-run episode count, no auto-retry-from-scratch, spend logged and asserted against the $25 cap); Pitfall 8 (copyright drift in "own words" summaries — similarity check against fetched snippet text baked into the same validation pass).

### Phase 4: Event Explorer + Event Study + Methodology (UI completion + launch hardening)
**Rationale:** These pages need real, enriched `episodes.parquet` + `events.json` to be demo-worthy (markers/detail panels with empty or all-"unexplained" content undercut the demo value) — sequencing them last means the data they render is real by the time the pages are built and reviewed. Methodology is written last so it documents the final, settled behavior of everything above, and this phase is also where cross-cutting launch risks (staleness alerting, "looks done but isn't" verification) get closed out.
**Delivers:** Event Explorer (markers sized/colored by severity/category, status-styled for explained/needs_review/unexplained, detail panel, filterable table); Event Study (category-average CAAR-style paths with confidence bands, recovery-time distribution); Methodology page (definitions, thresholds, corrected notebook findings front and center, LLM caveats, disclaimer, last-refresh timestamp); independent staleness-alert workflow; final verification pass against the "Looks Done But Isn't" checklist (episode-ID stability on real data, source-URL spot-check, a full week of unattended nightly runs, a verified redeploy-while-session-open behavior, a copyright/raw-text sweep of `data/`).
**Addresses:** The remaining P1 features (Event Explorer, Event Study, Methodology) plus the P2 marker-level status styling.
**Avoids:** Pitfall 6 (silent 60-day GitHub Actions disable + DST cron drift — ship the independent staleness check here, before calling the project "done"); Pitfall 7 (Streamlit Cloud memory/caching under the now-full data volume — profile the heaviest page, likely the 24-rule grid or Event Study aggregation, under realistic data size).

### Phase Ordering Rationale

- **Dependency-driven:** `core/storage.py` before everything; price-only pages before event detection (events need prices to detect against); event detection before enrichment (enrichment cost wasted on unstable IDs); enrichment before the Event Explorer/Study pages (need real data, not empty states) — this mirrors the Build Order already laid out in ARCHITECTURE.md almost exactly.
- **Risk-isolation-driven:** the irreversible-spend step (LLM backfill) is deliberately isolated into its own phase (3) so that the model-ID/pricing verification gap and the cost-blowup pitfalls are resolved in a contained, dry-runnable scope before real money is spent — this directly reflects the orchestrator's $25 budget cap decision.
- **Narrative-driven:** per PROJECT.md's "Strategy Lab and events story weighted equally," both tracks are fully represented in the roadmap (Phase 1 covers Strategy Lab's payoff; Phases 2-4 cover the events story) rather than one being treated as secondary.
- **This avoids** shipping confusing detail before a headline comparison exists (Pitfall 1's root cause), avoids wasting LLM spend on unstable IDs (Pitfall 3 before Pitfall 5), and avoids launching without a staleness safety net (Pitfall 6 closed before "done").

### Research Flags

Needs deeper research during planning:
- **Phase 3 (News Enrichment + Backfill):** Confirm current Haiku-tier model ID + official pricing via web search before budget-scoping the backfill (STACK.md's figures are explicitly unverified per orchestrator correction); also confirm the "web search + `messages.parse()` structured outputs in one call" interaction end-to-end with a small spike, since Anthropic's docs describe both independently without a dedicated combined worked example (STACK.md, MEDIUM confidence).
- **Phase 2 (Event Detection):** The clustering/warm-up/ID-stability logic is domain-specific with no off-the-shelf reference implementation — budget explicit design + replay-test time, don't treat it as a standard CRUD-style job.

Phases with standard, well-documented patterns (research-phase likely unnecessary):
- **Phase 1 (Foundation + Overview/Strategy Lab):** Streamlit multipage (`st.navigation`), Plotly charting, and `st.cache_data` are all officially documented, HIGH-confidence patterns; the existing `core/` package already establishes the conventions to extend.
- **Phase 4 (Event Explorer/Study UI):** Marker-based chart interaction and category-aggregation charts are standard Plotly/pandas work once the underlying data exists; the main non-standard risk (staleness alerting) is a small, well-scoped addition, not a research-heavy one.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM-HIGH | Streamlit/Plotly/pydantic facts verified against official current docs; the Anthropic model ID and pricing used for the budget estimate are explicitly unverified against the orchestrator's confirmed model list and must be re-checked before Phase 3 is scoped |
| Features | MEDIUM-HIGH | Grounded in direct comparison against four named reference tools (Portfolio Visualizer, testfol.io, QuantConnect/quantstats, GuruFocus/AnyChart/Macrotrends) plus the project's own SPEC.md; the "oracle" item in FEATURES.md is overridden by a locked PROJECT.md decision and treated as an anti-feature here, not a gap |
| Architecture | HIGH for component boundaries/data contracts (derived directly from SPEC.md and existing `core/` conventions); MEDIUM for idempotency/versioning/testing specifics (general current practice, not a named framework) |
| Pitfalls | MEDIUM-HIGH | Platform limits (Streamlit Cloud sleep/memory, GitHub Actions 60-day disable, yfinance defaults) verified via current official docs/community sources; LLM-attribution and event-detection judgment calls are MEDIUM, grounded in the project's own SPEC.md risk analysis rather than an external authority |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address

- **Claude model ID + pricing (Phase 3):** STACK.md's `claude-haiku-5-5` and $0.10/$0.50-per-MTok figures are unverified against the orchestrator's current model list — resolve via web search against official `platform.claude.com` docs before Phase 3 planning, not during it.
- **Stooq fallback viability:** Confirmed broken as specced (`pandas-datareader` dropped its Stooq reader; Stooq's endpoint now requires a CAPTCHA-gated API key) — PROJECT.md's Key Decisions table should be revisited to either adopt a direct API-key-based Stooq client or simplify to "yfinance + retries + last-good-snapshot" before Phase 1's nightly refresh job is finalized.
- **`st.plotly_chart(on_select=...)` on heatmap/imshow chart types:** Documented Streamlit gaps exist for selection events firing on heatmap-style charts specifically — verify this works for the Strategy Lab heatmap during Phase 1 build, with a dropdown/table-row fallback ready if it doesn't.
- **Web-search + structured-outputs combined call:** Anthropic's docs confirm both features independently but don't provide a dedicated worked example combining them — budget a small Phase 3 spike to confirm the end-to-end pattern before the real backfill.
- **FRED historical coverage back to 1993:** Assumed but not independently confirmed in this research pass for the specific release IDs needed (CPI, payrolls) — verify with a direct API test call early in Phase 2.

## Sources

### Primary (HIGH confidence)
- docs.streamlit.io — multipage apps overview, `st.navigation`, `st.plotly_chart`, caching overview, deploy/Python-version docs, manage-your-app (sleep/redeploy behavior)
- platform.claude.com — models overview, pricing, web search tool, structured outputs (official, but see model-ID gap above)
- pypi.org/project/pydantic — version/compatibility facts
- Project repo: `docs/SPEC.md`, `.planning/PROJECT.md`, `docs/PHASE0_FINDINGS.md`, `core/data.py`, `core/backtest.py`, `core/metrics.py`, `core/signals.py`, `core/config.py`, `tests/conftest.py`

### Secondary (MEDIUM confidence)
- GitHub streamlit/streamlit issues #8388, #8760, #8933, #8766 (navigation launch, heatmap/imshow selection gaps)
- GitHub ranaroussi/yfinance issues #687, #2431, #2480, #2125 (auto_adjust defaults, rate limiting)
- Plotly community candlestick-performance thread
- GitHub Community Discussion #57858 + efrecon/gh-action-keepalive (60-day workflow auto-disable)
- Streamlit Discourse/community threads on sleep/wake and memory limits
- Idempotent-pipeline pattern sources (Spark/SQLMesh, dbt incremental patterns, dev.to pipeline articles)
- VCR-style LLM test record/replay pattern sources (dev.to, pytest-llm-vcr on PyPI)
- Portfolio Visualizer, testfol.io, QuantConnect/quantstats, GuruFocus/AnyChart/Macrotrends documentation and galleries (feature-landscape comparison)
- Event-study methodology references (bookdown, Princeton libguide)

### Tertiary (LOW confidence)
- pandas-datareader Stooq-reader-removal reports — consistent across multiple 2026 sources but not independently re-verified against the changelog directly
- uv vs. pip 2026 community tooling comparisons — preference consensus, not a formal spec
- curl_cffi/yfinance TLS-impersonation behavior — community bug-report consensus, not an official yfinance statement

---
*Research completed: 2026-10-07*
*Ready for roadmap: yes*
