---
phase: 01-foundation-overview-strategy-lab
plan: 06
subsystem: ops
tags: [deployment, streamlit-community-cloud, github-actions, nightly, ci-cd]

# Dependency graph
requires:
  - phase: 01-foundation-overview-strategy-lab
    provides: "Plan 02: jobs/refresh_prices.py with the D-13 validate_snapshot() gate and
      .github/workflows/nightly.yml; Plan 03/05: the full Overview and Strategy Lab app"
provides:
  - "Public GitHub repo (jad-22/spy-analytics) and a deployed Streamlit Community Cloud app"
  - "README.md and docs/ROADMAP.md reflecting Phase 1 as shipped and done"
  - "A real, on-GitHub nightly workflow_dispatch run, proving (and documenting the limit of)
    the D-13 validation gate against live Yahoo data"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "No code changes in this plan — docs-only (README/ROADMAP) plus infrastructure
      (public repo, Streamlit Cloud deploy, a live workflow_dispatch run)"

key-files:
  created: []
  modified:
    - README.md
    - docs/ROADMAP.md

key-decisions:
  - "Did not touch core/config.py's rewrite_tolerance_pct or core/validate.py after the live
    nightly run repeated the exact same D-13 volume-rewrite rejection seen in 01-02's local
    test run — that tolerance is a D-13/CONTEXT.md decision owned by the user, not an
    auto-fixable deviation, so the rejection is recorded here as an open issue instead"
  - "requirements.txt left unchanged: Streamlit Community Cloud's dependency install from
    pyproject.toml succeeded on first deploy, so the plan's explicit-list fallback was never
    needed"

requirements-completed: [OPS-01, OPS-05]

# Metrics
duration: ~20min active (Task 3 only; Tasks 1-2 completed in prior sessions)
completed: 2026-10-08
---

# Phase 1 Plan 06: Ship the Phase — Deploy, Record URL, Verify Nightly Summary

**Public repo and live Streamlit Community Cloud deploy recorded in the README; a real
workflow_dispatch nightly run on GitHub reproduced the known D-13 volume-tolerance rejection
on Yahoo's most-recent-day data, confirming the gate behaves identically to the local repro
in 01-02 and leaving no data commit for the CI-loop guard to need checking against.**

## Performance

- **Started:** This session — resumed at Task 3 after Tasks 1-2 completed in prior sessions
- **Completed:** 2026-10-08T10:12 (nightly run concluded)
- **Tasks:** 3 (1: quality gate + docs, 2: public repo + deploy — human action, 3: URL record +
  live verification + docs close-out)
- **Files modified:** 2 (README.md, docs/ROADMAP.md) across this session's commit; see Task 1's
  prior commit for the first round of doc edits

## Accomplishments

- **Task 1** (prior session, commit `16fbffe`): full quality gate re-confirmed green
  (124 tests passed, ruff clean, `scripts.rerun_notebook_grid` reproduced "0 of 24 rules beat
  buy-and-hold" for both windows, matching `docs/PHASE0_FINDINGS.md`). README and
  `docs/ROADMAP.md` updated to describe what Phase 1 actually built (Stooq removed, module
  table expanded, Phase 1 roadmap items converted to ticked checkboxes).
- **Task 2** (human action, prior session): the GitHub repo
  [jad-22/spy-analytics](https://github.com/jad-22/spy-analytics) is public; `origin` is
  configured and `main` is pushed and tracking. The app is deployed on Streamlit Community
  Cloud at https://spy-market-analytics.streamlit.app/, confirmed working by the user. The
  first CI run on the push (run `37760426220`, workflow `ci`) completed with success.
- **Task 3** (this session):
  - README.md: "Live app" section now contains the real URL, with a one-line note that the
    app may take a moment to wake after a period of inactivity (Community Cloud's documented
    sleep behavior — no keep-alive pinger built, per the plan's explicit scope boundary).
  - docs/ROADMAP.md: Phase 1 item 9 ticked with the live URL; the Phase 1 row in the top
    status table set to "**Done** (2026-10-08)"; the "Public or private GitHub repo?" open
    question resolved to "public (OPS-01)" with the repo URL.
  - Full gate re-run green before committing: `ruff check .` clean, `pytest -q` 124 passed.
  - Committed as `e8528ae` and pushed to `origin/main`.
  - OPS-01 live check: `curl -s -D - https://spy-market-analytics.streamlit.app/` returned
    HTTP **303**, `Location: https://share.streamlit.io/-/auth/app?redirect_uri=...` — this is
    Streamlit Community Cloud's documented auth-free wake/session-cookie redirect chain (it
    issues a session cookie and bounces back to the app URL), not a real login wall; matches
    the plan's explicitly anticipated "303 to an auth-free wake page" outcome. The user had
    already confirmed in-browser that the app renders correctly.
  - Nightly workflow: `gh workflow run nightly.yml` dispatched run
    [`37761824923`](https://github.com/jad-22/spy-analytics/actions/runs/37761824923),
    watched with `gh run watch` to completion. **Conclusion: `failure`** — see Issues
    Encountered below; this is the known D-13 risk, not a new bug.
  - OPS-05 CI-loop check: the nightly run's `jobs.refresh_prices` step exited 1 (rejected
    snapshot) *before* the `git add`/`commit`/`push` step ran, so **no data commit was made**
    by this run. `gh run list --workflow ci.yml --limit 10 --json headSha,event,conclusion`
    shows exactly two recent `ci.yml` runs, both `push` events against this session's own
    doc commits (`e8528ae`, `16fbffe`), neither against any nightly-authored SHA — there is no
    data commit for a CI run to have looped on. The CI-loop guard (`paths-ignore: data/**`
    plus the default-`GITHUB_TOKEN`-push behavior) remains structurally unexercised by an
    actual data commit and needs re-checking once a run successfully writes and commits
    `data/` (either after a D-13 decision, or naturally once Yahoo's volume revision settles
    and a future weekday run produces a clean diff).

## Task Commits

1. **Task 1: Full quality gate, README and docs/ROADMAP.md updates** — `16fbffe` (prior session)
2. **Task 2: Publish repo publicly + deploy on Streamlit Community Cloud** — human action,
   no commit (GitHub repo creation + Streamlit Cloud web UI configuration)
3. **Task 3: Record the URL, verify the live nightly run and CI-loop guard, close out docs**
   — `e8528ae` (docs: README live-app URL, docs/ROADMAP.md Phase 1 status and open question)

## Files Created/Modified

- `README.md` — "Live app" section filled in with the real URL and sleep/wake note (Task 3);
  status line, module table, Stooq removal, run commands (Task 1, `16fbffe`)
- `docs/ROADMAP.md` — Phase 1 item 9 ticked with URL, status table row set to Done, "Public or
  private repo" open question resolved (Task 3); Phase 1 items converted to checkboxes and
  ticked, Methodology stub noted as moved to Phase 4, History-start question resolved (Task 1,
  `16fbffe`)
- `requirements.txt` — unchanged; Streamlit Cloud's `pyproject.toml`-based install succeeded,
  so the plan's explicit-dependency-list fallback was never triggered

## Decisions Made

- Left `core/config.py`'s `rewrite_tolerance_pct` and `core/validate.py` untouched after the
  live nightly run reproduced the exact same volume-only rejection documented in
  `01-02-SUMMARY.md`'s local repro. The plan and `01-02-SUMMARY.md` both flag this as a
  decision for the user (D-13 is a `CONTEXT.md`-owned tolerance), not an in-plan auto-fix.
- `requirements.txt` was left as the single `.` line (installs `pyproject.toml`) since Task 2's
  deploy succeeded without the fallback explicit-dependency-list ever being needed.

## Deviations from Plan

None beyond the pre-existing, explicitly-anticipated D-13 risk (see Issues Encountered) — no
auto-fixes were made, per the resume instructions' explicit prohibition on loosening tolerances
or touching `core/config.py`/`core/validate.py` without the user's decision.

## Issues Encountered

**Live nightly run on GitHub Actions reproduced the known D-13 volume-tolerance rejection
(same root cause as 01-02's local repro, not a new defect).**

Run [`37761824923`](https://github.com/jad-22/spy-analytics/actions/runs/37761824923)
(`workflow_dispatch`, triggered 2026-10-08T10:11:25Z) concluded `failure`. The exact log line
from the `Run python -m jobs.refresh_prices` step:

```
2026-10-08T10:11:49.6220250Z snapshot rejected: volume rewritten beyond tolerance on 1 rows, first 2026-10-07; keeping last snapshot
2026-10-08T10:11:49.6927632Z ##[error]Process completed with exit code 1.
```

This is the identical finding from `01-02-SUMMARY.md`'s "Issues Encountered": Yahoo Finance's
consolidated-tape volume for the most recently completed session (2026-10-07) continues to be
revised for a day or two after close, independent of OHLC prices, and D-13's
`rewrite_tolerance_pct` (0.01%) is tight enough to catch that revision and correctly reject the
write. Per the explicit instruction carried into this plan's resume context, **the tolerance
was not loosened and `core/config.py`/`core/validate.py` were not touched** — that remains an
architectural/CONTEXT.md decision for the user. `data/prices.parquet` and `data/meta.json` on
`main` are unchanged by this run (the job exits before any write, exactly as designed).

Because the run made no data commit, the OPS-05 CI-loop assertion could not be exercised
against a live data commit this session — recorded as a structural (not yet empirically
proven) guarantee; see Next Phase Readiness.

## User Setup Required

None beyond what was already completed in Task 2 (public GitHub repo, Streamlit Community
Cloud deploy, no secrets). No further action needed to use the app as shipped.

## Next Phase Readiness

- **Carried-forward blocker (from `01-02-SUMMARY.md`, now confirmed live):** the nightly job
  will likely keep rejecting on its own most-recent trading day's volume figure until either
  (a) Yahoo's volume-revision window passes before the next scheduled run, or (b) a
  `CONTEXT.md` decision special-cases the single most-recent committed day's volume column
  the same way `drop_incomplete_session` already special-cases *today's* bar. This needs an
  explicit user decision before Phase 2 relies on an unattended nightly refresh.
- **OPS-05 structural-only verification:** the CI-loop guard (`paths-ignore: data/**` +
  default `GITHUB_TOKEN` push) has not yet been exercised against an actual nightly data
  commit, because no run has yet produced one. Re-check `gh run list --workflow ci.yml`
  against the next nightly run that successfully writes and pushes `data/` changes (either a
  future scheduled weekday run once the volume revision settles, or after the D-13 decision
  above is made).
- Phase 1's app, deploy, and docs are otherwise complete: public URL live, Overview and
  Strategy Lab pages functioning (user-confirmed), full gate green, roadmap and README
  reflect what shipped.

---
*Phase: 01-foundation-overview-strategy-lab*
*Completed: 2026-10-08*

## Self-Check: PASSED

All claimed files found on disk (README.md, docs/ROADMAP.md,
.planning/phases/01-foundation-overview-strategy-lab/01-06-SUMMARY.md); both claimed commit
hashes (16fbffe, e8528ae) found in git log.

## Post-Summary Resolution (2026-10-08)

The user chose to exempt volume from the D-13 rewrite check. Volume feeds no backtest
or metric; open/high/low/close and adj_close stay guarded at 0.01%.

- Fix: `99b5953` fix(01-02): exempt volume from the D-13 rewrite tolerance. In it,
  `tests/test_validate_snapshot.py::test_volume_revision_passes` replaces the old
  volume-rejection test. It was confirmed failing before the fix and passing after.
- Live nightly re-run [`37763263924`](https://github.com/jad-22/spy-analytics/actions/runs/37763263924):
  **success**. It committed `f56c43a` "data: nightly price refresh".
- OPS-05 CI-loop guard verified live. No `ci` workflow run was triggered by `f56c43a`.
