# Phase 2: Event Detection & Macro Calendar - Context

**Gathered:** 2026-10-08
**Status:** Ready for planning
**Source:** plan-phase open-question resolution (no discuss-phase run); see 02-RESEARCH.md Open Questions

<domain>
## Phase Boundary

Deterministic detection of SPY shock, gap, drawdown and rally episodes since 1993 (DET-01..07), plus a sourced US macro calendar (FOMC, CPI, payrolls) with each episode tagged by in-window releases (CAL-01, CAL-02). No UI in this phase.

</domain>

<decisions>
## Implementation Decisions

### Episode clustering
- **D-01:** Drawdown and rally episodes are bounded by their steepest leg — drawdown = peak→trough, rally = trough→peak — not the full peak→recovery span. Flags within 3 trading days of a leg merge into that episode. Research measured ~151 episodes on the committed data, with each of the 7 DET-07 known episodes as exactly one cluster (resolves RESEARCH assumption A2).

### Macro calendar sourcing
- **D-02:** The FRED API key is used locally only. The 1993+ calendar is built locally and `data/macro_calendar.parquet` is committed. No new GitHub Actions secret in this phase.
- **D-03:** The calendar builder is idempotent and re-runnable: re-running rebuilds or extends to the current date with stable rows, so the Phase 4 nightly job can call it unchanged.

### Claude's Discretion
- Remaining open items in 02-RESEARCH.md (FOMC meeting vs conference-call classification details, FRED release_id confirmation, file locations) are left to the planner, following CLAUDE.md rules.

</decisions>

<canonical_refs>
## Canonical References

- `docs/SPEC.md` — product spec (what and why)
- `docs/ROADMAP.md` — phase tasks, gates, open questions
- `.planning/phases/02-event-detection-macro-calendar/02-RESEARCH.md` — measured episode counts, sourcing findings
- `CLAUDE.md` — core/ purity, thresholds in `core/config.py`, no network outside `core/data.py`/jobs/scripts

</canonical_refs>

<deferred>
## Deferred Ideas

- Promoting the FRED key to a GitHub Actions secret: Phase 4 (nightly automation), if needed.

</deferred>

---

*Phase: 02-event-detection-macro-calendar*
