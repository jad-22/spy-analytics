# Phase 3: News Enrichment, Backfill & Review - Pattern Map

**Mapped:** 2026-10-09
**Files analyzed:** 9 (core/news/schema.py, core/news/base.py, core/news/null.py,
core/data.py extension, core/config.py extension, jobs/enrich_events.py,
scripts/review_events.py, .github/workflows/backfill.yml, test files for each)
**Analogs found:** 9 / 9

**Module placement note (resolves RESEARCH open question 1):** CONTEXT.md D-02/D-03 lock
the decision research flagged as open: pure logic (schema, Protocol, NullProvider, status
rules, override merging) lives in `core/news/`; the **networked** `ClaudeSearchProvider`
(the actual `import anthropic` + `client.messages.create(...)` call) lives in **`jobs/`**,
not `core/news/claude_search.py` and not `core/data.py`. This is a third option beyond
RESEARCH's two (extend `core/data.py` vs. a new `core/news/claude_search.py` network
file) — CONTEXT.md's own wording is explicit: "No network and no `anthropic` import in
`core/`." Treat `core/data.py` only as the *style* analog for how a network-calling module
should be documented and structured (docstring stating "network calls live here, used
only by jobs"), not as the file the new network code is added to.

**CLI tool naming note:** CONTEXT.md D-05 says the review tool is invoked as
`python -m scripts.review_events`, i.e. the file is `scripts/review_events.py` (matching
the existing `scripts/` package), not `jobs/review_events.py` as RESEARCH's Recommended
Project Structure sketched. Use `scripts/report_phase2.py` as the closest analog (same
package, same "regenerate from committed data, never hand-edit" ethos), adapted for an
interactive accept/edit/reject loop instead of a one-shot report generator.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `core/news/schema.py` | model | transform (validation) | `core/calendar.py` (pure validation module, no network) | role-match |
| `core/news/base.py` | utility (Protocol interface) | transform | `core/signals.py::Strategy` Protocol | exact |
| `core/news/null.py` | service (fixture provider) | transform | `core/signals.py::MACrossoverStrategy` (concrete Protocol implementer) | role-match |
| `core/news/status_rules.py` (or inline in `schema.py`) | utility | transform | `core/validate.py` (pure pre-write gate, raises on rule violation) | exact |
| `core/config.py` (extend) | config | — | `core/config.py` itself, CAL-01/DET-01 blocks | exact |
| `jobs/enrich_events.py` | service/job (orchestrator + network call) | request-response (LLM API) + batch | `jobs/build_macro_calendar.py` (network job: env-var key, retryer, incremental merge, atomic write, exit-1-on-failure) | exact |
| `jobs/enrich_events.py` (API-call internals) | service | request-response | `core/data.py::fetch_fred_release_dates` (key-never-in-error-message pattern) | role-match |
| `scripts/review_events.py` | utility/CLI | event-driven (interactive loop) + file I/O | `scripts/report_phase2.py` (CLI, `python -m scripts.X`, reads committed data, no network) | role-match |
| `.github/workflows/backfill.yml` | config (CI workflow) | event-driven (workflow_dispatch) | `.github/workflows/nightly.yml` | exact |
| `tests/test_news_schema.py` | test | — | `tests/test_calendar.py` (pure-function unit tests, hand-built fixtures) | exact |
| `tests/test_enrich_events.py` | test | — | `tests/test_refresh_prices.py` (monkeypatch network call, assert file untouched on failure, incremental/idempotent) | exact |
| `tests/test_review_events.py` | test | — | `tests/test_refresh_prices.py::test_main_*` style (argparse-driven `main()`, tmp_path files) | role-match |

## Pattern Assignments

### `core/news/base.py` (utility, Protocol interface)

**Analog:** `core/signals.py` lines 46-59

**Core Protocol pattern:**
```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class Strategy(Protocol):
    """... short, stable, filesystem/dict-key-safe identifier ..."""
    name: str
    label: str

    def target(self, prices: pd.DataFrame) -> pd.Series: ...
```
Copy this shape exactly for `NewsProvider`: a `@runtime_checkable` `Protocol` (not ABC —
matches the project's one existing interface convention), a `name: str` attribute, and a
single method (`explain(self, episode) -> EventExplanation`). Put the module docstring
up front stating "no network import here" the way `core/events.py`'s docstring states
"must not import core.data or core.storage."

---

### `core/news/null.py` (service, deterministic fixture)

**Analog:** RESEARCH's own Pattern 1 code example is already aligned with
`core/signals.py`'s dataclass-implementing-Protocol style (`MACrossoverStrategy`, lines
62-96) — no network, deterministic `target`/`explain` method. Use the dataclass-or-plain-
class style from `MACrossoverStrategy` (frozen dataclass with computed `name`/`label`
properties) if `NullProvider` grows beyond a static stub; a plain class with a `name`
class attribute (as RESEARCH sketched) is sufficient for a one-shot "no network" stand-in.

**Imports pattern:** no imports beyond `core.news.schema` — matches `core/events.py`'s
rule of importing only `core.config`, never a networked module.

---

### `core/news/schema.py` (model, pydantic validation)

**No close in-repo analog for pydantic specifically** (this project has never used
pydantic before — `core/calendar.py` and `core/validate.py` do equivalent "deterministic
rule enforcement, raise on violation" work with plain dataclasses/DataFrames instead).
Use `core/validate.py` as the **validation-flow analog** (not syntax):

**Validation-flow pattern** (`core/validate.py` lines 19-45):
```python
def validate_snapshot(new: pd.DataFrame, old: pd.DataFrame | None, cfg: Settings) -> None:
    """Raise ValueError if `new` fails any D-13 check against `old`. No-op on success."""
    if old is not None:
        if len(new) < len(old):
            raise ValueError(f"row count shrank from {len(old)} to {len(new)}")
        ...
```
This is the project's established idiom: a pure function that enforces a rule and raises
a descriptive exception on violation, with **no trust in the caller-supplied "nice"
value** — directly analogous to NEWS-03/NEWS-04's code-enforced status downgrade. For the
actual pydantic model, follow RESEARCH's Pattern 2 code example verbatim
(`EventExplanation` with a `model_validator(mode="after")` that force-downgrades
`status`), since no pydantic precedent exists in-repo to deviate from.

**Settings-driven thresholds pattern** (`core/config.py` lines 64-80, DET block): every
threshold (confidence cutoff 0.5, episode/search caps, model IDs, prompt version) is a
field on the frozen `Settings` dataclass with an inline comment citing the requirement ID,
grouped under a new `# News enrichment (NEWS-01..08)` section heading — copy this exact
style, do not inline any threshold as a literal in `core/news/` or `jobs/enrich_events.py`.

---

### `core/config.py` (extend — News enrichment section)

**Analog:** `core/config.py` lines 64-80 (`# Event detection (DET-01..07)` block) and
82-125 (`# Macro calendar (CAL-01..02)` block)

**Pattern to copy:**
```python
    # Macro calendar (CAL-01..02)
    macro_calendar_path: Path = field(default=DATA_DIR / "macro_calendar.parquet")
    calendar_start: str = "1993-01-01"
    ...
    fred_api_key_env: str = "FRED_API_KEY"  # D-02: local env only, never a CLI arg
    http_timeout_s: float = 20.0
```
Add a parallel `# News enrichment (NEWS-01..08)` block with: `events_path`,
`event_overrides_path`, `news_model` (`"claude-haiku-5-5"`), `news_escalation_model`
(`"claude-sonnet-5-5"`), `news_confidence_threshold: float = 0.5`,
`news_max_episodes_per_run`, `news_max_searches_per_episode`, `news_prompt_version`,
`anthropic_api_key_env: str = "ANTHROPIC_API_KEY"` (same `*_env` naming convention as
`fred_api_key_env`), `web_search_tool_version: str = "web_search_20250305"`. Every field
needs an inline comment citing NEWS-0x, matching the file's existing convention
throughout.

---

### `jobs/enrich_events.py` (service/job, orchestrator + network call)

**Analog:** `jobs/build_macro_calendar.py` (whole file, 171 lines) for job shape;
`jobs/refresh_prices.py` for the retry/exit-1-on-failure pattern.

**Env-var key pattern** (`jobs/build_macro_calendar.py` lines 78-85):
```python
    key = os.environ.get(SETTINGS.fred_api_key_env, "")
    if not key:
        print(
            f"{SETTINGS.fred_api_key_env} is not set; set it in your local shell "
            "(never commit it)",
            file=sys.stderr,
        )
        return 1
```
Copy this exactly for `ANTHROPIC_API_KEY`, adjusting the message since D-04 says the
production backfill reads it as a GitHub Actions secret (local/dev/spike runs may still
read it from the shell env) — message should say "set it in your shell or as the
`ANTHROPIC_API_KEY` repo secret for the workflow_dispatch job," not just "local shell."

**Retry pattern** (`jobs/refresh_prices.py` lines 26-45, identical style in
`jobs/build_macro_calendar.py` lines 37-50):
```python
    retryer = Retrying(
        stop=stop_after_attempt(attempts),
        wait=wait_exponential(multiplier=1, min=wait_min_s, max=wait_max_s),
        reraise=True,
        before_sleep=_log_retry,
    )
    return retryer(fetch_yfinance, ticker, start=start)
```
Use `Retrying(...)` as a **callable, not a decorator** — this is a logged, repeated
project convention (RESEARCH's Don't Hand-Roll table confirms it). Wrap the Claude API
call the same way.

**Incremental/idempotent job skeleton** (`jobs/detect_events.py` lines 44-95, full
`main()`): argparse with `--*-path` overrides defaulting to `SETTINGS.*`, try/except
around the core logic printing to stderr and returning 1 on any failure (never touching
`data/` on failure), a single `_write_*` helper function as "the single call site for the
write path" (see `jobs/detect_events.py` line 36-41 and `jobs/build_macro_calendar.py`
line 53-55 — both have this exact doc comment). Copy this structure for
`jobs/enrich_events.py::main()`, with the incremental filter (episode_id not already in
`events.json`, or in a `--force` list) replacing `jobs/detect_events.py`'s calendar-
coverage check.

**Atomic write pattern** (`core/storage.py` lines 35-47):
```python
def _write_parquet_atomic(df: pd.DataFrame, path: Path) -> None:
    """Write to a temporary sibling, then rename over `path`, so an interrupted run never
    leaves a truncated committed file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)
```
`events.json`/`event_overrides.json` are JSON, not parquet — generalize this exact
tmp-then-`os.replace` idiom to JSON (write to `path.with_name(path.name + ".tmp")` via
`json.dumps`, then `os.replace`), matching `core/storage.py::write_meta`'s simpler
`path.write_text(...)` for small JSON files if atomicity-under-interruption for a single
developer-reviewed file is judged unnecessary — but prefer the atomic version since
`jobs/enrich_events.py` runs unattended in CI.

**Key-never-in-error-message pattern** (`core/data.py` lines 91-124,
`fetch_fred_release_dates`/`fetch_fred_release_name`):
```python
    try:
        resp = requests.get(f"{base_url}/release/dates", params=params, timeout=timeout)
    except requests.RequestException as exc:
        raise ValueError(
            f"FRED request failed for release_id={release_id}: {type(exc).__name__}"
        ) from None

    if resp.status_code != 200:
        raise ValueError(f"FRED returned HTTP {resp.status_code} for release_id={release_id}")
```
Never include `resp.url`, request params, or the exception's own `str(exc)` (which may
embed the URL/key) in a raised message — only `type(exc).__name__` and non-secret
identifiers (`release_id` / `episode_id`). Apply this identically around the Anthropic
API call for NEWS-05's "never leak the key" rule and Pitfall #5.

---

### `scripts/review_events.py` (CLI, local-only)

**Analog:** `scripts/report_phase2.py` (whole file) for the package/invocation shape;
no in-repo analog for an *interactive* accept/edit/reject loop (new pattern, stdlib
`input()`/`argparse` per RESEARCH's Don't Hand-Roll table).

**Package/invocation pattern** (`scripts/report_phase2.py` lines 1-21, 173-183):
```python
"""Generate docs/PHASE2_CALIBRATION.md from the committed Phase 2 artifacts (DET-06).

Usage (from the repo root, no network):
    python -m scripts.report_phase2
...
"""
from __future__ import annotations
...
def main() -> int:
    episodes = load_episodes(SETTINGS.episodes_path)
    ...
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```
Copy the module docstring convention (states "no network" explicitly, cites requirement
IDs), the `core.storage` read functions for loading committed data
(`load_episodes`/add a new `load_events`/`load_event_overrides` to `core/storage.py`),
and the `main() -> int` / `raise SystemExit(main())` entrypoint shape. Replace the
report-generation body with an `argparse` CLI (e.g. `--episode-id` to jump to one record,
default: iterate all `needs_review`/pending records) and a per-record `input()` prompt
loop for accept/edit/reject, writing via the same atomic-JSON-write helper as
`jobs/enrich_events.py`.

---

### `.github/workflows/backfill.yml` (config, workflow_dispatch job)

**Analog:** `.github/workflows/nightly.yml` (whole file, 43 lines)

**Pattern to copy:**
```yaml
name: nightly
on:
  schedule:
    - cron: "30 21 * * 1-5"
  workflow_dispatch: {}
permissions:
  contents: write
concurrency:
  group: nightly-refresh
  cancel-in-progress: false
jobs:
  refresh:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - run: pip install -e ".[dev]"
      - run: python -m jobs.refresh_prices
      - name: Commit data if changed
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add data/prices.parquet data/meta.json
          if git diff --cached --quiet; then
            echo "no data change"
          else
            git commit -m "data: nightly price refresh"
            git push
          fi
```
For `backfill.yml`: drop the `schedule:` trigger (D-04 says manual-only), keep
`workflow_dispatch: {}` as the sole trigger, add
`env: ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}` on the job or the
`python -m jobs.enrich_events` step, raise `timeout-minutes` (LLM calls are slower than a
price fetch — budget per RESEARCH's cost estimate and episode cap), replace the commit
step's `git add` paths with `data/events.json`, and keep the identical
`git diff --cached --quiet` / commit-message-with-no-special-marker pattern (D-15's
no-CI-bypass-tag rule referenced in `nightly.yml`'s own comment applies here too, since
`ci.yml`'s `paths-ignore: ["data/**"]` already excludes `data/events.json`).

---

### `tests/test_news_schema.py` (test)

**Analog:** `tests/test_calendar.py` (pure-function unit tests) — in particular the
secret-leak-hardening block, lines 539-583:
```python
SENTINEL_KEY = "TESTKEY-DO-NOT-LEAK"
...
def test_fetch_fred_release_dates_does_not_leak_key_on_connection_error(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        raise requests.ConnectionError(f"failed hitting {url}?api_key={SENTINEL_KEY}")
    monkeypatch.setattr(requests, "get", fake_get)
    with pytest.raises(ValueError) as exc_info:
        fetch_fred_release_dates(10, SENTINEL_KEY, "1993-01-01", "https://api.stlouisfed.org/fred", 5.0)
    assert SENTINEL_KEY not in str(exc_info.value)
```
Use this identical `SENTINEL_KEY = "TESTKEY-DO-NOT-LEAK"` convention for a new assertion:
grep a rendered `data/events.json` (or the `EnrichmentRecord.raw_response` field in a
unit test) for the sentinel key / `x-api-key` pattern and assert it's never present —
directly implements Pitfall #5 and the "Known Threat Patterns" table's key-leakage
mitigation. Also mirror `test_validate_macro_calendar_raises_on_api_key_in_url` (line 358)
for a hand-built fixture asserting `enforce_status_rules` force-downgrades `status` when
`sources` is empty or `confidence < 0.5`, matching the "every validation rule needs a
unit test with a hand-built fixture" rule from CLAUDE.md.

---

### `tests/test_enrich_events.py` (test)

**Analog:** `tests/test_refresh_prices.py` (whole file) — specifically the
monkeypatch-the-network-call + assert-untouched-on-failure pattern:
```python
def test_main_exits_1_and_leaves_snapshot_on_final_failure(tmp_path, tiny_prices, monkeypatch):
    prices_path = tmp_path / "prices.parquet"
    meta_path = tmp_path / "meta.json"
    write_prices(tiny_prices, prices_path)
    meta_path.write_text('{"existing": true}')
    before_prices = prices_path.read_bytes()
    before_meta = meta_path.read_bytes()

    def always_fail(ticker, start, end=None):
        raise RuntimeError("yahoo is down")
    monkeypatch.setattr(refresh_prices, "fetch_yfinance", always_fail)

    exit_code = refresh_prices.main([...])
    assert exit_code == 1
    assert prices_path.read_bytes() == before_prices
    assert meta_path.read_bytes() == before_meta
```
Copy this shape exactly for `jobs/enrich_events.py`: monkeypatch
`jobs.enrich_events.ClaudeSearchProvider` (or the module-level provider factory) with a
fake that raises, assert `events.json` is byte-identical before/after, and add an
incremental-idempotency test (two episode IDs already in `events.json`, one new one in
`episodes.parquet`; assert only the new one gets an API call and the existing two records
are untouched) — this directly covers NEWS-06. Use `NullProvider` (no monkeypatch needed)
for the happy-path/dry-run tests, since it requires no network.

---

### `tests/test_review_events.py` (test)

**Analog:** `tests/test_refresh_prices.py::test_main_success_writes_prices_and_meta`
style — `argparse`-driven `main()` under `tmp_path`, feeding scripted stdin (use
`monkeypatch.setattr("builtins.input", iter([...]).__next__)` or `capsys`/`io.StringIO`
redirection, a new pattern for this repo since no existing script is interactive) to
drive accept/edit/reject through one record, then assert `event_overrides.json` contains
exactly the expected override and `data/events.json` is never modified (REV-02).

## Shared Patterns

### Settings-driven configuration (no inline literals)
**Source:** `core/config.py` lines 64-125 (DET-01..07 and CAL-01..02 blocks)
**Apply to:** `core/news/schema.py`, `core/news/base.py`, `core/news/null.py`,
`jobs/enrich_events.py`, `scripts/review_events.py` — every threshold, path, model ID,
prompt-version string, and env-var name must be a `Settings` field with an inline
requirement-ID comment, never a literal inside a function body.
```python
confidence_threshold: float = 0.5  # NEWS-04
news_max_episodes_per_run: int = 25  # NEWS-07 hard cap
```

### Atomic file writes (tmp + os.replace)
**Source:** `core/storage.py::_write_parquet_atomic` (lines 35-42)
**Apply to:** `jobs/enrich_events.py` (events.json), `scripts/review_events.py`
(event_overrides.json) — generalize the parquet-specific helper to a JSON variant; both
new writers should route through a single `core/storage.py`-added function
(`write_events`/`write_event_overrides`) the way `write_episodes`/`write_macro_calendar`
each have "single call site" comments pointing at their one caller.

### Env-var-only secret handling, never in error messages
**Source:** `jobs/build_macro_calendar.py` lines 78-85 (read) + `core/data.py` lines
91-124 (never leak in exceptions)
**Apply to:** `jobs/enrich_events.py`'s Anthropic key handling and any error path that
might otherwise stringify an SDK exception containing request details.

### tenacity `Retrying(...)` as a callable, not `@retry` decorator
**Source:** `jobs/refresh_prices.py::fetch_with_retry` (lines 26-45),
`jobs/build_macro_calendar.py::_retryer` (lines 37-50)
**Apply to:** the Claude API call in `jobs/enrich_events.py` — reuse the exact
`Retrying(stop=stop_after_attempt(...), wait=wait_exponential(...), reraise=True,
before_sleep=_log_retry)` shape for consistency with the project's two existing network
jobs.

### Job `main()` shape: argparse + try/except + exit-1-without-writing
**Source:** `jobs/detect_events.py::main` (lines 44-95), `jobs/build_macro_calendar.py::main`
(lines 58-166)
**Apply to:** `jobs/enrich_events.py::main`, `scripts/review_events.py::main` — argparse
with `--*-path` overrides defaulting to `SETTINGS.*`, a single `_write_*` helper as "the
single call site for the write path," any failure prints to stderr and returns 1 without
touching committed files.

### Pure/network boundary docstring convention
**Source:** `core/events.py` lines 1-26, `core/calendar.py` lines 1-12, `core/data.py`
lines 1-14
**Apply to:** every new `core/news/*.py` file — open with a docstring stating what it
must NOT import (no network, no Streamlit, no `anthropic` SDK per CONTEXT.md D-02) and
which requirement IDs it implements, exactly like the three cited files do.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `jobs/enrich_events.py` (Claude API call internals: `output_config` + `web_search` tool, `web_search_tool_result` block extraction) | service | request-response (LLM) | No prior LLM/Anthropic SDK usage anywhere in this codebase — RESEARCH's own Pattern 3/Pattern 4 code examples are the only available reference; follow those directly rather than searching further for an in-repo analog |
| `scripts/review_events.py` (interactive input() loop) | utility/CLI | event-driven | No existing script in `scripts/` or `jobs/` is interactive (all are one-shot batch jobs); build fresh per RESEARCH's Don't Hand-Roll guidance (stdlib `argparse` + `input()`, no new TUI dependency) |
| pydantic model syntax (`BaseModel`, `model_validator`) | model | transform | Project has never used pydantic before this phase (confirmed: not in `pyproject.toml` dependencies); RESEARCH's Pattern 2 code example is the reference, not an in-repo file |

## Metadata

**Analog search scope:** `core/`, `jobs/`, `scripts/`, `tests/`, `.github/workflows/`
**Files scanned:** `core/config.py`, `core/data.py`, `core/events.py`, `core/signals.py`,
`core/storage.py`, `core/validate.py`, `core/calendar.py`, `jobs/detect_events.py`,
`jobs/refresh_prices.py`, `jobs/build_macro_calendar.py`, `scripts/report_phase2.py`,
`tests/conftest.py`, `tests/test_refresh_prices.py`, `tests/test_calendar.py`,
`.github/workflows/nightly.yml`, `.github/workflows/ci.yml`, `pyproject.toml`
**Pattern extraction date:** 2026-10-09
