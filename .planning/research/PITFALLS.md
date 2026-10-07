# Pitfalls Research

**Domain:** Financial backtest visualization + automated event detection + LLM-sourced news attribution, deployed read-only on Streamlit Community Cloud with a nightly GitHub Actions data pipeline
**Researched:** 2026-10-07
**Confidence:** MEDIUM-HIGH (platform limits and library defaults verified via current docs/community sources; domain judgment on LLM attribution and event detection is MEDIUM, grounded in the project's own SPEC.md risk analysis)

## Critical Pitfalls

### Pitfall 1: Heatmap and robustness charts quietly re-introduce data-snooping / look-ahead that the corrected engine just fixed

**What goes wrong:**
The Strategy Lab's short×long heatmap and rolling-start robustness chart are *presentation* layers over the corrected `core/backtest.py` engine, but they are a common place for subtle leakage to creep back in even when the underlying engine is correct: (a) the heatmap's "best rule" cell is picked by looking at the full test period and then visually anchored as if it were chosen in advance (classic in-sample selection bias, i.e. "I tried 24 rules and highlighted the winner" is not evidence that rule would have been chosen ex ante); (b) the IS/OOS split is computed but the split date is tuned after seeing results, which defeats the purpose; (c) rolling-start windows that all end on the same final date share the back-half of the series, so they are not independent robustness checks — they look like 11 confirmations but are really 1.

**Why it happens:**
The underlying engine (Phase 0) is correct, so it is easy to assume the UI layer built on top of it inherits that correctness automatically. Heatmaps and grids are visually compelling, which makes cherry-picking the best cell feel like "letting the data speak" rather than p-hacking across 24 rules.

**How to avoid:**
- Label the heatmap explicitly: "best cell shown for reference, not a recommendation — see IS/OOS panel for the only forward-looking test."
- Make the IS/OOS split date a config constant chosen *before* looking at results (e.g., a fixed calendar date like 2020-01-01), not a slider the visitor can drag to find a flattering split. If a slider is offered for exploration, caption it as "exploratory, not validation."
- For rolling-start robustness, caption that windows share trailing history and are not independent trials — this is already implicit in Phase 0's findings ("does not depend on the chosen window") but the UI must repeat the caveat, not just the notebook.
- Methodology page should state plainly: 0/24 rules beat buy-and-hold on the full corrected backtest (already true per `docs/PHASE0_FINDINGS.md`), so the heatmap's purpose is to show *risk reduction*, not to help a visitor find a winning rule by eye.

**Warning signs:** Any UI copy that reads like "this rule performed best" without a caveat; a split-date control with no fixed default; marketing language ("optimal strategy") creeping into Strategy Lab captions.

**Phase to address:** Strategy Lab UI phase (whichever phase builds the heatmap + IS/OOS + rolling-start charts). Add an explicit review checklist item: "every chart has a one-line caveat about selection bias."

---

### Pitfall 2: yfinance's adjusted-price behavior silently changes under you (dependency upgrades, Yahoo backend changes)

**What goes wrong:**
yfinance changed `auto_adjust`'s default from `False` to `True` across its 0.2.x releases (deprecation warning landed in 0.2.53), and when `auto_adjust=True` the `Adj Close` column disappears entirely and OHLC columns are pre-adjusted instead. A project that pins `auto_adjust=False` today (as `core/data.py` correctly does) is safe only until someone "cleans up" that explicit kwarg thinking it's redundant, or until yfinance removes the legacy code path for `auto_adjust=False` in a future major version. Separately, Yahoo's backend has a documented history of retroactively restating historical `adj_close` values when new dividends/splits are declared — so a parquet snapshot captured today can silently disagree with the "same" data fetched next week, which matters for total-return calculations and for the 1993 inception-era data (thin 1993 volume, pre-decimalization prices, and occasional stale/zero-volume holiday rows).
Split handling is a related trap: SPY has had no splits since inception, but if the ticker or future tickers added to the app ever split, naive raw-close indicators (SMA/EMA) computed before the adjustment factor is applied will show a fake "crash" at the split date unless `to_total_return()` (or equivalent raw-adjustment) is applied *before* indicators are computed, not after.

**Why it happens:**
yfinance is an unofficial wrapper around a backend Yahoo can change without notice; defaults change between minor versions without most users noticing until returns silently shift. Developers also tend to treat a "successful" fetch as validated data, with no row-count or value-level regression check against the last committed snapshot.

**How to avoid:**
- Keep `auto_adjust=False` pinned explicitly in `fetch_yfinance` with a comment explaining why (already done — preserve this, and add a unit test asserting the yfinance call includes `auto_adjust=False` so a future edit can't silently drop it).
- Pin a yfinance version range in `pyproject.toml` rather than floating to latest; bump deliberately and re-run the Phase 0 acceptance check (`scripts/rerun_notebook_grid`) after any yfinance upgrade.
- In the nightly job, before overwriting `prices.parquet`, diff the new fetch against the last ~30 days of the previous snapshot; if any historical (non-trailing) `adj_close` value changed by more than a tiny tolerance, flag it (log a warning, or write to `meta.json`) rather than silently committing — this catches Yahoo-side restatements.
- For the 1993 start date: add a data-quality check in the nightly job / a Phase 0-style test that asserts no zero-volume or duplicate-date rows in the committed history, and spot-check the 1993-1994 window manually once.
- If `to_total_return()` is applied, apply it once at data-load time before any indicator or signal computation touches the frame — never compute SMA/EMA on raw close and total-return close inconsistently across pages.

**Warning signs:** CI diffing shows `prices.parquet` row values for *old* dates changing between nightly runs (not just new rows appended); Methodology page's Phase 0 numbers drift without a code change; any indicator chart shows a single-day cliff that doesn't correspond to a real market event.

**Phase to address:** Nightly data-refresh job phase. Add a "snapshot diff / anomaly guard" as an explicit acceptance criterion, not just "fetch and commit."

---

### Pitfall 3: Rolling-sigma event detector has warm-up, clustering, and episode-ID churn bugs that silently corrupt the news pipeline downstream

**What goes wrong:**
Three distinct bugs are common in this exact detector design (`|log return| > 2.5 × rolling 60-day σ`, clustering within 3 trading days, drawdown ≥5%/rally ≥8%):
1. **Warm-up window**: the first ~60 trading days of the 1993-start history have no valid rolling σ (or a σ computed on a too-short window that is highly unstable), which can either crash the detector or — worse — silently produce bogus high-severity "shock days" in early 1993 because the rolling window partially includes NaN-padded or artificially low-variance data.
2. **Clustering edge cases**: the spec's "flagged days within 3 trading days merge into one episode" rule is order-dependent and transitive-closure-dependent. A naive pairwise merge can produce different episode boundaries depending on iteration order (e.g., day A merges with B, B merges with C, but a different implementation might not transitively merge A and C). This is exactly the kind of bug that passes small manual tests and then produces wrong episode boundaries at scale (e.g., 2008 or March 2020, where dozens of shock days cluster together) — the "largest single-day move as anchor_date" rule is also ambiguous when two days in a cluster have equal |z|.
3. **Episode ID churn**: if `episode_id` is derived from `anchor_date` + trigger type and the detector re-runs nightly with a *slightly* different σ (because new trading days shift the trailing 60-day window), an episode that was previously `2020-03-09_shock` can have its anchor shift by a day on a later run if a bigger move in the same cluster is found after more data arrives (e.g., during a still-developing crash episode where the detector sees a bigger down day two days after first detecting the cluster). This orphans the previously-enriched `events.json` record (cost already spent) and creates a duplicate under a new ID, or — worse — leaves a stale enriched record under an ID that no longer matches any current episode, which a filterable Event Explorer will either hide or double-count.

**Why it happens:**
Event/episode detection is usually prototyped against a known clean period (e.g., just 2020) where warm-up and ID-stability issues don't show up; the bugs only appear across the full 1993-2026 history and across live nightly re-runs with incrementally new data, which isn't tested until the pipeline is already live.

**How to avoid:**
- Explicitly drop (not zero-fill) the first ~70-80 trading days of history from shock-day detection (buffer past the 60-day warm-up), and document this in `meta.json`/`detector_version` so the Methodology page can state "shock detection begins [date]" rather than silently having unreliable flags in 1993.
- Implement clustering via a graph/union-find (transitive closure) over a day-adjacency graph, not a sequential pairwise scan; add a regression test with a synthetic 5-day cluster where naive order-dependent merging would fail but union-find succeeds.
- Make `episode_id` stable once assigned: derive it from the episode's *first-detected* anchor date and trigger type, and once a cluster exists, only *extend* its date range on later runs rather than re-deriving the anchor — or, simpler, freeze episode boundaries once the episode is more than N days in the past (e.g., 10 trading days) so only recent/in-progress clusters can still shift. Log any boundary change to `meta.json` for auditability.
- Write a "replay" test: run the detector on a fixed historical slice (e.g., Feb-Apr 2020) incrementally (first with data through March 9, then through March 23, then through April 30) and assert episode IDs from the first run still exist and are only *extended*, never renamed, in later runs.

**Warning signs:** `episodes.parquet` row count for a past, closed episode changes between two nightly runs; `events.json` contains enriched records whose `episode_id` no longer appears in the current `episodes.parquet`; any shock-day flags dated in the first three months of 1993.

**Phase to address:** Event detection phase (before news enrichment is built, since enrichment cost is wasted if episode IDs aren't stable). Add "episode ID stability under incremental re-run" as an explicit test in that phase's acceptance criteria.

---

### Pitfall 4: LLM web-search attribution produces confident, well-cited, and wrong explanations — the validation rules in SPEC.md catch *some* but not all failure modes

**What goes wrong:**
SPEC.md already anticipates the main risk ("LLM attributes a move to the wrong story") and has a real mitigation (sources dated inside window, `needs_review` status, overrides file). But three specific failure modes slip past those exact rules:
1. **Post-hoc / retrospective articles that are dated inside the window but written in hindsight.** A web search for "why did SPY drop on 2020-03-09" will surface plenty of retrospective explainer articles and "on this day in markets history" pieces republished or crawled with a *dated* URL that falls inside the search window even though the article's actual claims are a post-hoc narrative assembled weeks later with the benefit of hindsight (oil price war + COVID panic narrative solidified over following days, not known with that framing on the day itself). The date-in-window check does not distinguish "published during the event" from "published about the event, later, but crawled/dated ambiguously."
2. **Confident wrong causality on multi-causal days.** Many large SPY moves have 2-3 plausible simultaneous causes (e.g., a Fed decision *and* a surprise CPI print *and* an earnings miss on the same day); the model will pick one dominant narrative and present it with high confidence, when the honest answer is "multiple contributing factors, relative weight unclear." The schema's single `category` + `drivers` list partially helps but the `confidence` score is self-reported by the same model making the attribution — a model can be consistently overconfident in exactly the cases where it's wrong, since nothing in the pipeline cross-checks confidence against an independent signal.
3. **Hallucinated source metadata that passes schema validation.** The URL can be well-formed and the publisher name plausible (schema validates shape, not that the URL actually resolves or that the article actually says what the summary claims) — pydantic validates structure, not truth. A citation with a real publisher name (e.g., "Reuters") and a plausible-looking URL path can still be a fabricated URL that 404s, especially if the model's web search tool returns a snippet but the model paraphrases/invents the URL rather than using the tool's returned URL verbatim.

**Why it happens:**
The project's validation is schema- and date-level, which catches fabrication-from-nothing but not fabrication-with-real-sounding-details, and not hindsight narratives that technically satisfy "published inside window." This is an inherent limit of LLM-with-tools pipelines: tool use reduces but does not eliminate confident fabrication, and self-reported confidence is not calibrated.

**How to avoid:**
- Require that stored source URLs are exactly the URLs returned by the web search tool's citation metadata (the Claude API's web search tool returns structured citation objects) — never let the model free-type a URL into the JSON; parse citations from the tool-use result, not from the model's prose.
- Add a lightweight link-check step in the enrichment job (HEAD request, cache result) that flags (not necessarily blocks) sources returning 404/non-200 for manual review — cheap, catches the clearest hallucinations.
- For multi-causal days (several scheduled macro releases or several large news items in the search window), force `status: "needs_review"` or require `drivers` to list ≥2 entries with roughly stated contribution rather than letting the model collapse to one clean `category`, when the deterministic macro calendar shows more than one qualifying release in the window.
- Treat the model's self-reported `confidence` as a weak signal only; the real gate is the manual review step (`jobs/review_events.py`) for anything other than the clearest, single-cause, well-sourced moves. Do not let a high self-reported confidence skip human review for episodes above a severity threshold (e.g., the largest ~20% of episodes by severity should always get human eyes regardless of model confidence, since those are the ones most visible on a public portfolio page).
- Explicitly caption retrospective-source risk on the Methodology page: "sources are dated inside the event window, but some may be retrospective analysis published shortly after rather than same-day reporting."

**Warning signs:** A spot-check of 10 "explained" episodes finds any source URL that 404s; two episodes with overlapping dates get contradictory categories; `needs_review` count is suspiciously low (near zero) across the whole backfill, suggesting the model is never flagging its own uncertainty.

**Phase to address:** News enrichment phase. Add "citation URLs verified against tool output, not model prose" and "sample link-check on backfill" as acceptance criteria before the one-off backfill is run (since backfill is the ~$25 one-shot spend — catching this after the fact means re-spending).

---

### Pitfall 5: Claude API web-search cost blowup from uncapped search iterations, retries, and re-enrichment of unchanged episodes

**What goes wrong:**
Web search is billed per search ($10/1,000 searches, i.e. $0.01/search) plus the token cost of search results pulled into context, and a single API turn can trigger *multiple* search iterations (the model can call the search tool several times in one response if not constrained) — SPEC.md's "hard cap on searches per request" is the right control but is easy to under-specify (e.g., capping at the SDK/tool level is different from capping "per episode" if retries on validation failure trigger a fresh call with a fresh search budget). Two concrete blowup scenarios: (a) a transient API error or a pydantic validation failure causes the job to retry the *same* episode, which calls web search again from scratch rather than reusing/caching the first response that may have already returned good search results; (b) the nightly job re-enriches episodes that already have a record in `events.json` because the "only enrich new episodes" check is keyed on something that doesn't survive the episode-ID churn described in Pitfall 3 (if IDs shift, "new" episodes are incorrectly re-triggered, re-spending search budget on episodes already paid for).

**Why it happens:**
Cost controls are usually designed against the happy path (N episodes × M searches each = budget), not against retry/error paths or ID-stability edge cases, which is exactly where uncapped spend sneaks in — nobody budgets for "the same episode gets enriched 3 times because of an upstream bug."

**How to avoid:**
- Cap search iterations *per API call* via the tool configuration (max_uses on the web search tool) in addition to a per-run episode cap — both must be in config, not just one.
- On any retry (API error, validation failure), do not re-call the model+search from scratch by default; log the failure, mark the episode `needs_review` with a note, and let a human/queued re-run decide, rather than auto-retrying in a loop within the same nightly run.
- Key "already enriched" checks on episode content (e.g., anchor_date + trigger + rounded move_pct) rather than solely on `episode_id`, so an ID churn doesn't cause silent re-spend; or fix Pitfall 3 first since it's the root cause.
- Track actual spend: log tokens + search counts to `meta.json` per run and assert against a hard budget ceiling in the nightly job (fail loudly rather than silently overspend) — this also gives an audit trail for the "~$25 backfill" budget claim in SPEC.md.
- Run the backfill once manually with verbose logging and a dry-run count of episodes × expected searches *before* letting it spend real money, to sanity-check the episode count SPEC.md expects ("low hundreds").

**Warning signs:** Anthropic console spend for a single nightly run exceeds the per-run cap you expected; `meta.json` search-count field (if added) shows the same episode enriched more than once; nightly job runtime balloons because retries are looping.

**Phase to address:** News enrichment phase, specifically before the one-off historical backfill is executed (this is the irreversible-spend moment).

---

### Pitfall 6: GitHub Actions nightly workflow silently stops running after 60 days of repo inactivity, and cron timezone/DST mismatches cause off-by-one-hour or off-by-one-day runs

**What goes wrong:**
GitHub automatically disables scheduled workflows in *public* repositories after 60 days with no qualifying repository activity (new commits — not tags, issues, or merged PRs) — and does so silently: no email, no Actions log entry, the workflow simply stops firing. Since this project's nightly job itself creates commits (refresh → detect → enrich → commit), the workflow is normally self-sustaining — but if the nightly job fails *before* its commit step for 60+ consecutive days (e.g., a yfinance outage, an unhandled exception in the detector, or an API key expiring) there's no commit, so the 60-day countdown isn't reset and the workflow disables itself, compounding the original failure into total silence. Separately, GitHub Actions `cron` schedules run in UTC; the spec says "weekday evenings UK time," and UK time is UTC in winter but UTC+1 (BST) in summer — a single fixed UTC cron expression will be off by one hour for roughly half the year unless explicitly handled, and cron-based schedules are also not guaranteed to run at the exact minute under GitHub's load (documented to be delayed, sometimes by tens of minutes, especially at the top of common hours like 00:00 UTC).

**Why it happens:**
60-day auto-disable is an undocumented-feeling GitHub product behavior that most teams only discover after it bites them; DST is a classic "works until the clocks change" bug that passes code review and initial testing done in one season.

**How to avoid:**
- Add a monitoring/alerting mechanism independent of the nightly job's own commit: e.g., a second, trivial scheduled workflow (or an external uptime-style check) that checks `meta.json`'s `last_refresh` timestamp weekly and fails loudly (or a `workflow_run` failure notification to email) if it's stale beyond 2 trading days — this surfaces failures before the 60-day disable window is reached, not after.
- Pick two cron expressions (one for UTC winter-equivalent, one for BST) or — simpler — just run slightly later than needed in both seasons and accept the UK-time will drift by up to an hour depending on DST, documenting that acceptable fuzziness in README rather than fighting it; if same-day timing truly matters, compute the "is it currently BST" check inside the job and have the job itself decide whether to proceed/no-op based on actual UK wall-clock time rather than relying on cron precision.
- Treat GitHub Actions cron timing as "approximate, can be delayed" per GitHub's own documentation — don't build logic that assumes the job runs at exactly the scheduled minute.
- Ensure the nightly job's failure mode still produces *some* commit or heartbeat (even just updating a `last_attempted` field and committing that) so repo activity continues even when the substantive refresh fails, keeping the 60-day clock from ever reaching zero during an extended outage.

**Warning signs:** The Methodology page's "last refresh" timestamp is more than ~2 trading days stale; checking the Actions tab shows the scheduled workflow listed as disabled with no recent runs.

**Phase to address:** Nightly automation / deployment phase. Add "staleness alerting independent of the job's own success" as an explicit acceptance criterion — this is the single most likely way the public app quietly goes stale without the owner noticing.

---

### Pitfall 7: Streamlit Community Cloud's ephemeral filesystem, redeploy-on-commit, and cache invalidation interact badly with a nightly-commit architecture

**What goes wrong:**
Streamlit Community Cloud apps have real, documented resource ceilings (community reports and official guidance put per-app memory in roughly the 1-2.7GB range depending on when provisioned, with apps killed without a clear error when exceeded) and apps hibernate after a period of no visitor traffic (commonly cited around 12 hours), requiring a visitor to "wake" the app with a page load delay. For *this* architecture specifically: (a) every nightly commit to `data/` triggers a full app redeploy, which means `st.cache_data`-decorated loaders need their cache keys tied to file content/mtime, not just function arguments — a naive `@st.cache_data` on `read_prices(path)` with no TTL and no file-hash-based key can serve a *stale in-memory cache* to already-running sessions until the container restarts, so two visitors hitting the app around a redeploy can see different data; (b) five years of daily OHLCV plus thousands of episodes/news JSON records is small, but if Plotly figures are built by holding multiple full-history DataFrames in memory per session (one for Overview, one for Strategy Lab's 24-rule grid, one for Event Explorer) without clearing unused page state, memory can creep toward the ceiling especially since Streamlit multipage apps keep prior page session state alive by default.

**Why it happens:**
Caching bugs are invisible in local dev (one process, one user, no redeploy cycle) and only show up in production with concurrent visitors around a deploy window; memory limits are easy to ignore until the app has been live and gradually accumulating session-state bloat.

**How to avoid:**
- Use `st.cache_data(ttl=...)` or hash-check on file mtime so a redeploy (new container) naturally busts the cache — this is actually the easy case, since redeploy creates a fresh process; the harder case is *long-lived* sessions spanning a redeploy, which Streamlit Cloud handles by restarting the container on new commits anyway, but confirm this behavior rather than assume it.
- Keep `core/` functions pure and cheap to recompute (already a stated principle — "Analytics derived at runtime... are never stored; they are cheap to recompute") — this is the right call specifically *because* it avoids caching staleness bugs; don't undermine it by adding ad hoc `st.session_state` caches of computed DataFrames across pages.
- Load only the date-range-filtered slice of `prices.parquet` needed for the current view rather than the full 30+ year history into every page's memory; Parquet supports predicate pushdown / column selection, use it.
- Budget memory explicitly: the 24-rule grid computed for the heatmap is the single most expensive recurring computation (24 backtests on ~8,000+ rows) — cache its result keyed on (date range, cost bps, price basis) rather than recomputing on every widget interaction, but cap the cache size (`max_entries`) so cache itself doesn't become the memory problem.
- Document app hibernation in the README/Methodology page as SPEC.md already plans ("may take a moment to wake") — this is accepted, not a bug, just confirm it's actually surfaced to visitors.

**Warning signs:** Local testing never reveals this (single session) — watch for visitor reports of "seeing old data" right after a known nightly update, or Streamlit Cloud's own "app over resource limits" banner.

**Phase to address:** MVP deployment phase (initial Streamlit Cloud deploy) for the caching/memory architecture; revisit at the Event Explorer/Event Study phase once the data volume (episodes + news JSON) is non-trivial.

---

### Pitfall 8: News summaries drift into copyright/reproduction risk despite "own words" intent

**What goes wrong:**
SPEC.md's rule ("own-words summaries, links out, no stored article text") is correct policy but easy to violate in practice: a 2-3 sentence LLM-generated summary of a news article can closely paraphrase a distinctive, quotable sentence from the source (especially headlines, which are short and hard to meaningfully paraphrase without losing accuracy) — this is a substantive-similarity risk, not just a verbatim-copying risk, and "the LLM wrote it, not a human copying" doesn't change the legal analysis of the output. Separately, storing the *raw API response* (SPEC.md's enrichment pipeline step 4: "Store the record, the raw response...") risks inadvertently persisting fetched article text if the web search tool's results include fetched page content in the raw response blob, even if the *displayed* summary is clean.

**Why it happens:**
"Own words" is treated as a prompt instruction rather than a verified output property; raw API responses are logged for debugging without considering that the debug log itself might contain the thing you were trying not to store.

**How to avoid:**
- Keep the validated JSON record (schema-defined fields only) as the thing displayed and distributed; if the raw response is stored at all for debugging/audit, store it outside the public repo (not committed to `data/`) or strip search-result content fields before storing, since the public GitHub repo is itself part of the portfolio and publicly readable.
- Add a mechanical check in validation: summary length cap (schema already says ≤90 char headline, 2-3 sentence summary) plus a simple similarity check (e.g., longest-common-substring or n-gram overlap) against any fetched snippet text available in the tool-use result, flagging for review if overlap exceeds a small threshold.
- Headlines: write original short headlines rather than lifting the source's own headline verbatim, since headlines are often the most distinctive phrase and most likely re-publication target.

**Warning signs:** A manual spot-check during review (`jobs/review_events.py`) finds a summary sentence that reads identically to a snippet visible on the cited source page.

**Phase to address:** News enrichment phase — bake the similarity check into the same validation pass as the date-window/confidence checks, not as an afterthought.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Letting `episode_id` be re-derived from current detector output every nightly run instead of persisted/frozen | Simpler detector code, no extra state to manage | Orphaned/duplicated enriched records, wasted LLM spend (Pitfall 3 & 5) | Never past the event-detection phase; acceptable only during initial prototyping before any enrichment spend happens |
| Storing raw Claude API responses verbatim in the committed repo for "debugging" | Easy post-hoc inspection of what the model said | Possible copyright/reproduction exposure if search-result text is embedded (Pitfall 8); repo bloat | Acceptable in a local-only, gitignored debug log; never in the committed public `data/` |
| Floating yfinance to latest with no pin | Always get bugfixes | Silent `auto_adjust` or schema changes break the nightly job or subtly change historical values (Pitfall 2) | Never for the pinned production nightly job; fine for exploratory local notebook work |
| Single fixed UTC cron for a "UK evening" schedule | Simple workflow YAML | Up to 1-hour drift relative to intended UK local time across DST (Pitfall 6) | Acceptable if documented as "approximate" and nothing downstream depends on exact UK time |
| No independent staleness alert, relying on "I'll notice the app looks old" | No extra workflow to write | App can go stale for 60 days before GitHub even disables the workflow, with zero notification (Pitfall 6) | Never for a public portfolio piece where staleness undermines the "every number is honest and traceable" value proposition |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|-------------------|
| yfinance | Assuming `yf.download` defaults are stable across versions; not pinning `auto_adjust` | Explicitly pass `auto_adjust=False`, pin version range, test after upgrades |
| Stooq (fallback) | Assuming Stooq's series is adjusted the same way as yfinance without checking | Verify Stooq vs yfinance total-return numbers overlap on a known historical window before trusting the fallback in production (SPEC.md already flags this as unverified) |
| Claude API web search tool | Letting the model free-type citation URLs into the JSON schema instead of parsing structured citation metadata from the tool-use result | Extract URLs from the tool's citation objects, never from model prose; cap `max_uses` on the search tool explicitly |
| GitHub Actions cron | Assuming cron fires at the exact scheduled minute, and that UTC cron = fixed UK local time | Treat cron timing as approximate; decide BST/GMT handling explicitly in the job, not implicitly in the YAML |
| Streamlit `st.plotly_chart(on_select=...)` on the heatmap | Expecting click-to-select to work on a Plotly heatmap/imshow-style chart the same way it does on scatter/line charts | Verify `on_select` actually fires for the chosen Plotly chart type (heatmaps have documented selection-event gaps in Streamlit) before designing an interaction flow around it; have a fallback (e.g., a dropdown/table row click) if heatmap click-to-select doesn't fire |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|-----------------|
| Recomputing the 24-rule grid backtest on every Strategy Lab widget interaction | Laggy UI, high memory/CPU on Streamlit Cloud | Cache grid results keyed on (date range, cost, price basis) with `st.cache_data` and a bounded `max_entries` | Noticeable once the app has concurrent visitors around the resource-limited Streamlit Cloud container (low thousands of reruns/day is enough to matter on a ~1-2GB container) |
| Loading full 30+ year `prices.parquet` into every page regardless of selected date range | Unnecessary memory per session, slower chart rendering | Filter to selected range at load time, not after computing indicators on the full frame | Becomes visible once Event Explorer/Event Study pages (with hundreds of episodes + JSON) are added on top of price data already in memory |
| Nightly job re-running full historical event detection over all ~33 years every night instead of incrementally | Slow nightly job, higher chance of hitting detector-boundary bugs (Pitfall 3) on every run | Detect only in a trailing window plus explicit re-check of any still-open/recent episode; freeze old episode boundaries | Matters once the job is also calling the LLM — slow detection delays the whole pipeline and risks timeout in GitHub Actions' job time limits |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Anthropic API key accidentally exposed to a fork's PR workflow | A malicious fork PR could exfiltrate secrets if the nightly/CI workflow is configured to run on `pull_request` from forks with secrets available | Never expose the API-key-using workflow to `pull_request_target` or fork PR triggers; keep the nightly job on `schedule`/`push to main` only, and keep `ci.yml` (lint/test) secret-free since it runs on every push including forks |
| Committing the raw Claude API response including any embedded search-result page content | Copyright exposure (Pitfall 8) plus potential accidental exposure of request metadata | Strip to schema-validated fields before committing to the public `data/` directory |
| Key only in GitHub Actions secrets but logged in workflow debug output | A verbose `print()`/debug log of request objects could leak the key into Actions logs, which may be visible depending on repo visibility and log retention settings | Never log full request objects; mask/redact if debug logging is enabled for troubleshooting |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-------------------|
| Heatmap/robustness charts presented without a "this is not a recommendation" caveat | A recruiter/visitor skims the heatmap, sees a green "best" cell, and concludes the opposite of Phase 0's actual finding (0/24 beat B&H) | Caption every Strategy Lab chart with the headline finding, and make the IS/OOS panel — not the heatmap — the visually primary "answer" |
| Event Explorer showing "explained" events with high-confidence styling when the underlying attribution may be a retrospective narrative, not same-day causation | Visitor reads attribution as fact; undermines the "coincident, not causal" principle SPEC.md commits to | Keep the "coincident, not causal" label visually prominent on every event panel, not just in Methodology text; visually distinguish `needs_review` from `explained` with more than just a badge (e.g., different marker styling) |
| App "waking up" delay on first visit after idle hibernation, with no in-app messaging | Visitor thinks the app is broken/slow and leaves before it loads | Streamlit Cloud shows its own wake-up splash, but reinforce in README/landing copy rather than relying solely on Streamlit's default UX |

## "Looks Done But Isn't" Checklist

- [ ] **Corrected backtest engine extended to new UI**: Verify the heatmap/IS-OOS/rolling-start charts actually call the *same* `core/backtest.py` functions validated in Phase 0 — not a re-implemented or simplified version built directly in the Streamlit page for speed.
- [ ] **Event detector**: Verify episode IDs are stable across two consecutive nightly runs on real data (not just unit tests on synthetic data) before wiring up enrichment.
- [ ] **News enrichment backfill**: Verify a random sample of "explained" records' source URLs actually resolve (HTTP 200) and that the summary text doesn't closely match the source's own phrasing — before declaring the one-off backfill complete.
- [ ] **Nightly GitHub Actions job**: Verify it has run successfully, un-aided, for at least one full week with no manual intervention, and that a deliberately-induced failure (e.g., temporarily breaking the yfinance call) still results in a visible signal (not just a quiet skipped run) before trusting it unattended.
- [ ] **Streamlit Cloud deployment**: Verify behavior across an actual redeploy triggered by a nightly commit while a browser tab is already open — does the open session get stale data, an error, or a clean refresh?
- [ ] **Copyright controls**: Verify no raw fetched article text exists anywhere in the committed `data/` directory or git history (check `events.json`, any debug artifacts, and git blame on early commits) — not just that the current schema excludes it.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|----------------|------------------|
| Episode ID churn has already created duplicate/orphaned enriched records | MEDIUM | Write a one-off reconciliation script: match orphaned `events.json` records to current `episodes.parquet` by overlapping date range rather than exact ID match, re-key, and re-run review for any that can't be matched; add the stability fix (Pitfall 3) going forward |
| Yahoo restated historical `adj_close` values after snapshot already committed and used in published Phase 0 findings | MEDIUM | Re-run `scripts/rerun_notebook_grid` against the corrected snapshot, update `docs/PHASE0_FINDINGS.md` numbers, and add a changelog note on the Methodology page rather than silently overwriting — honesty principle requires visible correction, not silent patch |
| Scheduled GitHub Actions workflow found disabled after 60 days of silent failure | LOW | Re-enable via Actions tab or `gh workflow enable`, fix root cause of the original failure, then add the staleness-alert workflow from Pitfall 6 so this doesn't recur silently |
| A published event explanation is found to be a hallucinated/wrong attribution after going live | LOW-MEDIUM | Use the existing `event_overrides.json` mechanism (already designed for exactly this) to correct or mark `unexplained`; this is why the overrides file exists — use it rather than hand-editing `events.json` |
| Streamlit Cloud app repeatedly hits memory limit and gets killed | MEDIUM | Profile which page/computation is heaviest (likely the 24-rule grid or full-history chart rendering), add caching/filtering per Performance Traps above, and reduce default date range shown on first load |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|-------------------|---------------|
| Heatmap/IS-OOS presentation bias (Pitfall 1) | Strategy Lab UI phase | Every chart has a caveat caption; IS/OOS split date fixed in config, not visitor-tunable by default |
| yfinance adjusted-price drift and 1993-era data quality (Pitfall 2) | Nightly data-refresh job phase | Snapshot diff/anomaly guard in nightly job; yfinance version pinned; 1993-1994 window spot-checked |
| Event detector warm-up/clustering/ID-churn (Pitfall 3) | Event detection phase | Replay test across incremental historical slices shows stable, only-extending episode IDs |
| LLM attribution confident-wrong-cause and hallucinated citations (Pitfall 4) | News enrichment phase | Citations parsed from tool-use metadata, not model prose; sample link-check passes before backfill is treated as final |
| Claude API cost blowup from retries/ID churn (Pitfall 5) | News enrichment phase (pre-backfill) | Dry-run episode count vs expected matches SPEC.md's "low hundreds"; spend logged to `meta.json` and asserted against a cap |
| GitHub Actions 60-day disable + cron DST drift (Pitfall 6) | Nightly automation phase | Independent staleness check (separate from the job's own commit) fires if `last_refresh` is stale beyond 2 trading days |
| Streamlit Cloud caching/memory/redeploy interaction (Pitfall 7) | MVP deployment phase | Manual test of a redeploy-while-session-open scenario; memory usage profiled under the full 24-rule grid + full history load |
| Copyright drift in "own words" summaries (Pitfall 8) | News enrichment phase | Similarity check against source snippets included in validation pass; raw responses never committed to public `data/` |

## Sources

- [GitHub Community Discussion: workflows automatically disabled after 60 days of inactivity](https://github.com/orgs/community/discussions/57858)
- [efrecon/gh-action-keepalive — documents the 60-day public-repo auto-disable rule](https://github.com/efrecon/gh-action-keepalive)
- [Streamlit Community: "Is the resource limit 'Unlimited' for public apps?"](https://discuss.streamlit.io/t/is-the-resource-limit-unlimited-for-public-apps/37974)
- [Streamlit Community: "Hitting memory limit of streamlit app"](https://discuss.streamlit.io/t/hitting-memory-limit-of-streamlit-app/68389)
- [Fastero: "Why Your Streamlit App Keeps Sleeping — the 12-Hour Rule"](https://fastero.com/blog/why-your-streamlit-app-keeps-sleeping)
- [yfinance GitHub Issue #687: clarifying auto_adjust/back_adjust semantics](https://github.com/ranaroussi/yfinance/issues/687)
- [softhints.com: "Understanding yfinance auto_adjust=True: What Changed and How to Fix It"](https://softhints.com/understanding-yfinance-auto_adjust-true-what-changed-and-how-to-fix-it/)
- [Claude Platform Docs: Pricing (web search $10/1,000 searches)](https://platform.claude.com/docs/en/about-claude/pricing)
- [Streamlit GitHub Issue #8760: on_select not returning anything for imshow/heatmap](https://github.com/streamlit/streamlit/issues/8760)
- [Streamlit GitHub Issue #8933: Chart Selection not working on Sankey/heatmap/imshow](https://github.com/streamlit/streamlit/issues/8933)
- [Streamlit GitHub Issue #8766: on_select poorly integrated with subplots/hovermodes](https://github.com/streamlit/streamlit/issues/8766)
- Project's own `docs/SPEC.md` Risks table and `docs/PHASE0_FINDINGS.md` (primary source for domain-specific backtest findings already validated in this codebase)
- `core/data.py` (read directly) — confirms `auto_adjust=False` is already correctly pinned, informing Pitfall 2's framing as "preserve this" rather than "fix this"

---
*Pitfalls research for: SPY backtesting + event detection + LLM news attribution on Streamlit Community Cloud with nightly GitHub Actions*
*Researched: 2026-10-07*
