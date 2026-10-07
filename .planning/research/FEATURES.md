# Feature Research

**Domain:** Backtesting dashboard + market-event explorer (public analytics portfolio app)
**Researched:** 2026-10-07
**Confidence:** MEDIUM-HIGH

This research compares the planned SPY Market Lens pages (`docs/SPEC.md`) against conventions
in established backtesting tools (Portfolio Visualizer, testfol.io, QuantConnect/LEAN tear
sheets, quantstats) and market-event timeline tools (AnyChart/amCharts event markers, GuruFocus,
Macrotrends, academic event-study methodology), plus what recruiters/hiring managers scan for
in a 3-minute review of a portfolio app. The engine (Phase 0) is done; this file is scoped to
**user-facing features** for Phases 1-4.

## Feature Landscape

### Table Stakes (Users Expect These)

Features every credible backtesting/market tool has. Missing these makes the Strategy Lab or
Event Explorer look unfinished next to free tools visitors have likely already used.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Equity curve vs. buy-and-hold benchmark, same chart | Every backtester (Portfolio Visualizer, testfol.io, QuantConnect) leads with this; it's the single chart a recruiter screenshots | LOW | Already in spec (Strategy Lab). Log-scale toggle is a near-free addition quantstats always offers — add it. |
| Core metrics table: CAGR, max drawdown, Sharpe, time in market | Universal across all four reference tools; quantstats ships 50+, but these four are the floor | LOW | Already in spec. Add Sortino and Calmar cheaply alongside Sharpe — they're one-line pandas calcs and a quant reviewer will look for them since Sharpe alone reads as basic. |
| Drawdown periods table (peak, trough, recovery date, depth, days underwater) | Portfolio Visualizer's signature table; this is the detail that makes "−18.5% vs −32%" (Phase 0 headline) concrete rather than abstract | LOW-MED | Spec only has "drawdown regime shading" on Overview — a true drawdown table belongs on Overview or Strategy Lab, not just shading. See Differentiators below for the stronger version. |
| Parameter heatmap (short × long grid, color = excess return) | Standard on every "24-rule grid" style backtester; readers expect to see the whole rule space, not just the best one | MED | Already in spec (Strategy Lab). Must show a *plateau vs. spike* visually (per walk-forward/overfitting best practice) — annotate or caption that a lone bright cell is a red flag, which directly supports the Phase 0 "0/24 beat B&H" honesty story. |
| Rolling-start / walk-forward robustness view | Core to "does this depend on the window" — exactly Phase 0's finding; every serious backtester has some rolling or walk-forward view | MED | Already in spec and already computed in Phase 0 findings (11 start years, 2011-2021). Render as a small-multiples or box/strip chart of excess return by start year. |
| In-sample / out-of-sample split | Textbook anti-overfitting control; "Sharpe > 3" and "OOS drop > 50%" are named industry red flags for a reason — a public page with only IS results invites exactly that criticism | MED | Already in spec. Needs a visible split marker on the equity curve (shaded or vertical line) so a recruiter doesn't have to infer where IS ends. |
| KPI strip (YTD return, distance from ATH, current drawdown, realised vol) | Bloomberg-terminal-style convention now standard on retail dashboards (Finviz, GuruFocus) and cheap to compute | LOW | Already in spec (Overview). |
| Cost/slippage control (bps slider) | Every credible backtester lets you stress-test costs; Phase 0 already tested 0 vs 5 bps — surfacing the slider makes that rigor visible and interactive | LOW | Already in spec. |
| Event markers on price chart with click-through detail | Direct analogue to GuruFocus/AnyChart event markers (dividends, earnings, ±5% days) — users expect clicking a flagged point to reveal context, not just a tooltip | MED | Already in spec (`on_select="rerun"`). Marker **size by severity, color by category** (as spec'd) matches the AnyChart/GuruFocus convention exactly — keep it. |
| Filterable event table (category, direction, year, confidence) | Standard companion to any marker-based timeline; without it users can't audit coverage or find a specific crash | LOW | Already in spec. |
| Sourced citations with publish dates on every event | Non-negotiable given the project's own Core Value ("every explanation... cited... or marked unexplained") — this is the credibility floor for an LLM-sourced claim | LOW (engine does the work; UI just renders it) | Already in spec (detail panel). |
| Methodology / about page (definitions, disclaimer, data sources, last-refresh timestamp) | Recruiters spend ~3 minutes; a visible disclaimer + "corrected notebook findings" page is what turns "nice chart" into "shows rigor" — matches hiring-manager research showing documented process beats a bare dashboard | LOW | Already in spec. This is probably the single highest ROI page for the stated audience — don't let it ship thin. |

### Differentiators (Competitive Advantage)

Features that go beyond "another backtester" or "another crash timeline" and align with the
project's Core Value: **honesty and traceability**, demonstrated for a recruiter audience rather
than a trading audience.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| "0/24 rules beat buy-and-hold" framed as the headline finding, not buried | Most portfolio backtest demos implicitly sell "look, I found alpha." Leading with a rigorously *negative* result, shown with full methodology, is rare and signals analytical honesty over cherry-picking — exactly what a hiring manager for an analyst/quant role wants to see | LOW (data exists; this is a framing/IA decision) | Put this on Strategy Lab's default view and restate it on Methodology. This is the app's strongest differentiator and costs nothing new to build. |
| Risk-reduction framing: drawdown-reduction vs return-tradeoff chart (scatter of CAGR vs max DD across all 24 rules, B&H as reference point) | Reframes "strategies lose" into "here's what they actually buy you" (−18.5% vs −32% DD) — a single scatter plot communicates the Phase 0 conclusion better than a table of 24 rows | LOW-MED | Not in spec yet. One Plotly scatter (return on y, |max DD| on x, B&H highlighted) sitting on Strategy Lab. High value/cost ratio — recommend adding explicitly. |
| Overfitting-awareness callout tied to the heatmap | Quant-aware reviewers specifically look for whether the author understands overfitting (per the "red flags" literature: Sharpe > 3, lone-spike heatmap, big IS/OOS gap). Explicitly annotating "look for plateaus, not spikes" on the heatmap, and showing the IS/OOS gap number next to it, is a credibility signal few retail dashboards bother with | LOW | Caption/annotation only — reuses existing heatmap and split data. Cheap differentiator with high audience-fit payoff. |
| Event Study: average cumulative return path by category (day −5 to +60) with a confidence band | This is genuine event-study methodology (CAAR curves), rarely seen outside academic papers or institutional research notes — doing it for a public SPY timeline is unusual and demonstrates statistical literacy beyond typical "crash timeline" sites (Macrotrends, Finviz) which only show raw annotated charts, no aggregated study | MED-HIGH | Already in spec (Event Study page). This is the single most differentiating page relative to the competitive set — Macrotrends/GuruFocus/AnyChart stop at annotated markers; none do cross-event aggregation. Worth the complexity. |
| Recovery-time distribution (histogram/strip of days-to-recover by category) | Turns "the market always recovers" folklore into an actual distribution with categorized evidence (e.g., geopolitics vs. monetary policy recover differently) — no retail tool in the comparison set shows this | MED | Already in spec. Pair with a simple statistic (median days to recover by category) in the KPI area of the page, not just the chart. |
| Scheduled vs. surprise catalyst tagging (macro calendar overlay) | Differentiates "the market dropped and here's a story" (common) from "the market dropped on a *scheduled* release vs *surprise* news" (rare) — directly useful for a recruiter assessing whether the candidate understands market microstructure, not just NLP/news scraping | LOW-MED (calendar already scoped; UI is a filter/badge) | Already in spec. Keep as a filter chip on Event Explorer and Event Study, not just a field in the detail panel — otherwise the distinction is invisible unless you open every event. |
| Explicit confidence/status badges ("explained" / "needs_review" / "unexplained") shown in the UI, not just stored | Nearly every competing "news + chart" tool (GuruFocus, AnyChart) implicitly presents every annotation as fact. Visibly surfacing uncertainty (a yellow "needs_review" badge, a grey "unexplained" marker) is the project's stated differentiator ("honest... or marked unexplained") and should be visually unmissable, not a tooltip detail | LOW | Already implied by schema; make sure Event Explorer's marker styling (not just the detail panel) encodes status — e.g., hollow marker for unexplained — so the honesty signal is visible at the chart level, matching the Core Value statement. |
| "Oracle" hindsight bound shown once, clearly labeled, as a cautionary lesson | Nobody else in the comparison set deliberately shows an unreachable "best possible" line and explains why it's fake — most retail tools either don't have one or present optimized backtests uncritically. Explicitly showing and debunking it (per Key Decisions) reinforces the honesty thesis | LOW | Already scoped as Methodology text per `docs/SPEC.md`. Consider a single faint dashed line on the Strategy Lab equity chart captioned "unattainable hindsight bound — see Methodology" rather than only prose — more memorable for a 3-minute scan. |

### Anti-Features (Commonly Requested, Often Problematic)

Features that look impressive on competing platforms but would hurt this project's specific
goals (public portfolio piece, honest/traceable, zero runtime API cost, Streamlit Cloud
ephemeral hosting).

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|------------------|-------------|
| General multi-asset / multi-strategy portfolio builder (à la Portfolio Visualizer's full asset-allocation suite) | Portfolio Visualizer and testfol.io both let you backtest arbitrary ticker baskets, glide paths, withdrawals — feels like "more features = more impressive" | Already explicitly out of scope in PROJECT.md ("scope creep that weakens the events story"); diffuses the honest-SPY-strategy narrative and multiplies data/testing surface for no portfolio payoff | Keep the `Strategy` interface extensible (already planned) but ship only MA-crossover + 200D filter; mention extensibility in Methodology text, don't build it |
| Live/intraday price updates or "refresh now" button in the app | Users of real trading tools expect live quotes; feels incomplete without it | Spec is explicitly daily-bar, nightly-refresh, read-only app with no runtime API calls (cost/abuse risk on Streamlit Cloud); a "refresh" button would either lie (no-op) or violate the architecture | Show `last_refresh` timestamp prominently (already planned) with a one-line note that this is a daily-batch app by design |
| Runtime LLM Q&A ("ask the AI why SPY dropped") or chatbot over events | Feels like a natural, impressive extension of the news-enrichment pipeline; LLM chat UIs are currently fashionable | Reintroduces exactly the runtime-API-cost/abuse-risk the architecture was designed to avoid (public app, no secrets, no live calls); also reopens hallucination risk on a page whose entire value proposition is "cited or marked unexplained" | All LLM work stays offline in the nightly job; the app only ever renders pre-validated JSON |
| Parameter auto-optimizer ("find me the best MA pair") with a "Run Optimization" button | Natural ask once a heatmap exists — "just pick the best cell for me" | Directly produces the overfit, cherry-picked result the project is explicitly debunking (0/24 beat B&H); an optimizer button invites visitors to "find the winning rule," undermining the Core Value and inviting exactly the Sharpe>3/spike-picking anti-pattern the research flags | Heatmap is read-only/exploratory; pair it with the overfitting-awareness callout (above) instead of an action button |
| Causal language or causal scoring for events ("this news caused the drop") | Readers (and some LLM summaries) naturally phrase explanations causally; feels more satisfying than hedged language | Explicitly out of scope ("Claims of causation... shown as coincident context only"); also a bigger legal/credibility exposure for a public page attributed to a named author | Enforce "coincident, not causal" language in the enrichment prompt and repeat the caveat in every detail panel and the Methodology page |
| User accounts, saved backtests, or shareable permalinks for custom rule configs | Common in bigger backtesting SaaS (save a run, share a link); "pro" feel | Adds auth, state persistence and a write path — directly conflicts with the "read-only app, ephemeral filesystem, no secrets, no database" architecture decision | Rely on Streamlit widget state only (session-local); if sharing matters later, encode params in URL query string (cheap, no backend) rather than accounts |
| Real-time or near-real-time news ingestion (polling a news API continuously) | Feels "more alive" than a nightly batch; competitors' event tools (Stock Catalysts) advertise real-time calendars | Reopens the cost/rate-limit risk the architecture avoided, and daily granularity is explicitly sufficient per PROJECT.md non-goals | Keep nightly batch; the 1-trading-day staleness is already an accepted tradeoff |
| Candlestick/intraday OHLC micro-detail zoom with tick-level tooltips | Visually "richer" than a daily line/candle chart; some stock-chart libraries (amCharts) support deep intraday drill-down | Out of scope data granularity (daily bars only); building deep zoom UX for data that doesn't exist below the daily bar is wasted complexity | Daily candlestick with a range slider (already spec'd) is the ceiling for this dataset |
| Exhaustive quantstats-style 50+ metric dump on every page | quantstats offers a huge metric list; "more numbers = more rigorous" is tempting to copy wholesale | For a 3-minute recruiter scan, a 50-row metrics table reads as noise, not rigor, and dilutes the honest-headline-result framing that is the actual differentiator | Keep the curated table (CAGR, max DD, Sharpe, Sortino, Calmar, time in market, trades) and put a "full metrics" expander only if asked — don't make it the default view |

## Feature Dependencies

```
[Nightly price refresh + data/prices.parquet]
    └──requires──> [Overview: price chart, KPI strip, drawdown shading]
                       └──requires──> [Strategy Lab: equity curve vs B&H]
                                          └──requires──> [Parameter heatmap]
                                          └──requires──> [Rolling-start robustness view]
                                          └──requires──> [In-sample/out-of-sample split]
                                          └──enhances──> [Risk-reduction scatter (CAGR vs max DD)]

[Event detection (episodes.parquet)]
    └──requires──> [Macro calendar tagging (scheduled vs surprise)]
    └──requires──> [News enrichment (events.json)]
                       └──requires──> [Manual review / overrides]
                       └──requires──> [Event Explorer: markers + detail panel + filter table]
                                          └──requires──> [Event Study: category paths, recovery distribution]

[Overfitting-awareness callout] ──enhances──> [Parameter heatmap]
[Confidence/status badges at marker level] ──enhances──> [Event Explorer markers]
[Oracle hindsight line] ──enhances──> [Strategy Lab equity curve] (requires Methodology page text to explain it)
[Scheduled vs surprise filter chip] ──enhances──> [Event Explorer] AND [Event Study]

[User accounts / saved runs] ──conflicts──> [Read-only Streamlit Cloud architecture]
[Runtime LLM Q&A] ──conflicts──> [No-runtime-API-calls constraint]
[Parameter auto-optimizer action] ──conflicts──> [Honest "0/24 beat B&H" headline / overfitting-awareness goal]
```

### Dependency Notes

- **Strategy Lab's advanced views (heatmap, rolling-start, IS/OOS) require the equity-curve-vs-B&H
  view to exist first:** all three are elaborations on the same backtest engine output; building
  them before the baseline curve risks shipping confusing detail without the headline comparison
  users need to interpret it.
- **Event Explorer requires both event detection and news enrichment to be complete**, including
  manual review: showing markers before enrichment is done means empty or "unexplained"-only
  detail panels, which undercuts the Event Explorer's demo value. Event Study additionally
  requires enough enriched, categorized episodes to make category-level averaging meaningful
  (a handful of events per category produces a noisy, unconvincing average path).
- **Overfitting-awareness callout and confidence/status badges are pure UI enhancements** — no
  new data pipeline needed, so they can be added cheaply in the same phase as their parent
  feature (heatmap, markers) rather than deferred.
- **User accounts/saved runs and runtime LLM Q&A conflict with the architecture's core
  constraints** (read-only app, ephemeral FS, no secrets, no runtime API calls) — these aren't
  just lower priority, they're structurally incompatible with Phase 0-established decisions and
  should not resurface as "nice to have" without revisiting the architecture decision itself.
- **A parameter auto-optimizer action conflicts with the Core Value and the Phase 0 headline
  finding:** any UI that invites "pick the best rule" works against the deliberately negative,
  honest result the whole app is built to showcase.

## MVP Definition

### Launch With (v1)

Everything already in `docs/SPEC.md`'s Active requirements is the MVP — it is already scoped
tightly and should not be cut further:

- [ ] Overview: price chart (line/candle), MA overlays, drawdown regime shading, KPI strip — gives a visitor instant market context, the cheapest page to build
- [ ] Strategy Lab: rule picker, costs, equity vs B&H, metrics table, heatmap, rolling-start chart, IS/OOS split — this is the Phase 0 payoff; the "0/24 beat B&H" finding only lands with the full comparison visible
- [ ] Event Explorer: markers, detail panel, filterable table — the other half of the portfolio story; without it this is "just another backtester"
- [ ] Event Study: average path by category, recovery times, events per year — the differentiator that separates this from every annotated-chart competitor
- [ ] Methodology page — essential for the stated audience; this is what converts "nice charts" into "rigorous analyst," the highest-leverage page for recruiters specifically

### Add After Validation (v1.x)

Low-cost enhancements layered onto the MVP once the core four pages are live and deployed —
add these if time remains before milestone close, triggered by "the MVP works and I have a
little more budget before calling this done":

- [ ] Risk-reduction scatter (CAGR vs max DD across all 24 rules) on Strategy Lab — one chart, reuses existing grid output, strong narrative payoff
- [ ] Overfitting-awareness caption/annotation on the heatmap — text + maybe a computed IS/OOS gap number, no new pipeline
- [ ] Marker-level status encoding (hollow/grey for unexplained, distinct style for needs_review) on Event Explorer — styling change to existing marker code
- [ ] Oracle hindsight dashed line on the Strategy Lab equity chart, captioned — one trace plus a caption
- [ ] Sortino/Calmar added to the metrics table — one-line calcs next to existing Sharpe

### Future Consideration (v2+)

Defer until the current milestone's core pages are validated as working end-to-end in
production (deployed on Streamlit Community Cloud, nightly job green for a few runs):

- [ ] Additional `Strategy` implementations beyond MA crossover/200D filter (e.g., RSI, breakout rules) — defer until the interface has proven itself with one strategy family; adding more before that risks the "general backtester" scope creep PROJECT.md explicitly rejects
- [ ] Non-US macro calendar (ECB, BoE) — defer per PROJECT.md's explicit "can be added later" note; US releases already drive most SPY moves
- [ ] Additional `NewsProvider` implementation (e.g., GDELT) — defer until the Claude-search provider's event coverage/cost profile is understood from the real backfill
- [ ] URL-query-string-encoded shareable Strategy Lab configs — nice for sharing a specific finding, but not needed for a recruiter who arrives at the page directly

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Equity curve vs B&H + metrics table | HIGH | LOW | P1 |
| Drawdown regime shading + KPI strip | MEDIUM | LOW | P1 |
| Parameter heatmap | HIGH | MEDIUM | P1 |
| Rolling-start robustness view | HIGH | MEDIUM | P1 |
| In-sample/out-of-sample split | HIGH | MEDIUM | P1 |
| Event markers + detail panel | HIGH | MEDIUM | P1 |
| Filterable events table | MEDIUM | LOW | P1 |
| Event Study category paths + recovery distribution | HIGH | MEDIUM-HIGH | P1 |
| Methodology page | HIGH | LOW | P1 |
| Risk-reduction scatter (CAGR vs max DD) | HIGH | LOW | P2 |
| Overfitting-awareness callout | MEDIUM-HIGH | LOW | P2 |
| Marker-level confidence/status styling | MEDIUM | LOW | P2 |
| Oracle hindsight line on chart | MEDIUM | LOW | P2 |
| Sortino/Calmar metrics | LOW-MEDIUM | LOW | P2 |
| Additional strategies beyond MA/200D | MEDIUM | HIGH | P3 |
| Non-US macro calendar | LOW | MEDIUM | P3 |
| Additional NewsProvider (GDELT) | LOW | MEDIUM | P3 |
| Shareable URL-encoded configs | LOW | LOW-MEDIUM | P3 |
| Parameter auto-optimizer action | — | — | **Do not build (anti-feature)** |
| Runtime LLM Q&A / chatbot | — | — | **Do not build (anti-feature)** |
| User accounts / saved runs | — | — | **Do not build (anti-feature)** |

**Priority key:**
- P1: Must have for launch (already in `docs/SPEC.md` Active requirements)
- P2: Should have, add when possible (cheap, high narrative payoff, no new pipeline)
- P3: Nice to have, future consideration (real cost, defer until core is proven)

## Competitor Feature Analysis

| Feature | Portfolio Visualizer / testfol.io | QuantConnect / quantstats | Event-timeline tools (GuruFocus, AnyChart, Macrotrends) | Our Approach |
|---------|-----------------------------------|----------------------------|----------------------------------------------------------|--------------|
| Equity curve vs benchmark | Yes, with log-scale toggle, core feature | Yes, "Strategy Returns" section | N/A (not a backtester) | Match: equity vs B&H, add log-scale toggle |
| Metrics table | Rolling returns, CAGR, Sharpe, Sortino, std dev | 50+ metrics in quantstats; curated set in LEAN report header | N/A | Curated 6-7 metric table (CAGR, max DD, Sharpe, Sortino, Calmar, time in market, trades) — avoid quantstats' sprawl for a 3-min scan |
| Drawdown detail | Drawdown periods table (peak/trough/recovery dates) | Drawdown chart with top-5 periods marked | N/A | Drawdown regime shading (spec'd) + consider adding a compact drawdown table as a P2 enhancement |
| Parameter sensitivity | Not a feature (fixed-allocation tool) | Not typical in LEAN reports; found in dedicated optimizer tools | N/A | Short×long heatmap (spec'd), annotated for plateau-vs-spike reading — differentiates from both reference sets |
| Walk-forward / IS-OOS | Rare in retail backtesters | Present in dedicated walk-forward tooling, not standard LEAN report | N/A | IS/OOS split + rolling-start view (spec'd) — stronger rigor signal than most retail competitors |
| Event markers on chart | N/A | N/A | Core feature: dividends/earnings/±5% days, click for detail | Match pattern (marker size/color by severity/category) but apply to macro/news events rather than corporate actions |
| Event aggregation/study | N/A | N/A | None of the reference tools aggregate across events (each marker is standalone) | Event Study page (CAAR-style average path, recovery distribution) — this is the clearest differentiation vs. every event-marker competitor |
| Citations/sourcing per event | N/A | N/A | Headlines linked, but rarely validated against a date window or confidence-scored | Validated date-window sourcing + explicit confidence/status — stronger honesty guarantee than any reference tool |
| Methodology/about transparency | FAQ pages exist but assumptions not always foregrounded | LEAN docs are technical, not aimed at a lay/recruiter reader | Minimal — these are data tools, not analysis narratives | Methodology page with corrected-notebook findings front and center — unique to this project's "show your work" framing |

## Sources

- [Portfolio Visualizer backtest documentation and FAQ](https://www.portfoliovisualizer.com/faq)
- [Portfolio Visualizer feature overview](https://www.datasavvyfinance.com/portfolio-visualizer-features/)
- [testfol.io help and methodology guides](https://testfol.io/help/)
- [testfol.io portfolio backtester guide](https://testfol.io/guides/portfolio-backtester/)
- [QuantConnect/LEAN backtest report documentation](https://www.quantconnect.com/docs/v2/cloud-platform/backtesting/report)
- [QuantConnect backtest results documentation](https://www.quantconnect.com/docs/v2/cloud-platform/backtesting/results)
- [quantstats GitHub repository (ranaroussi/quantstats)](https://github.com/ranaroussi/quantstats)
- [AnyChart stock event markers gallery](https://www.anychart.com/products/anystock/gallery/Stock_Event_Markers/)
- [GuruFocus interactive chart with stock events](https://www.gurufocus.com/news/2416953/visualize-stock-events-with-our-enhanced-interactive-chart)
- [Macrotrends historical crash charts](https://www.macrotrends.net/2484/dow-jones-crash-1929-bear-market)
- [Event study methodology overview (bookdown)](https://bookdown.org/mike/data_analysis/sec-event-studies.html)
- [Princeton event study / abnormal returns guide](https://libguides.princeton.edu/eventstudy)
- [Walk-forward optimization and overfitting red flags](https://www.luxalgo.com/blog/stress-test-your-algorithmic-trading-strategy-guide-to-avoiding-overfitting/)
- [Backtesting without overfitting: red flags and best practices](https://backtrex.com/en/blog/backtest-strategy-avoid-overfitting-red-flags)
- [What hiring managers look for in data analyst portfolio projects](https://www.noetify.app/blog/data-analyst-portfolio-projects-that-get-interviews)
- [Project repo: `docs/SPEC.md`, `.planning/PROJECT.md`, `docs/PHASE0_FINDINGS.md`]

---
*Feature research for: Backtesting dashboard + market-event explorer portfolio app (SPY Market Lens)*
*Researched: 2026-10-07*
