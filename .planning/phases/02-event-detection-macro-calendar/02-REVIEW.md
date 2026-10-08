---
phase: 02-event-detection-macro-calendar
reviewed: 2026-10-09T00:00:00Z
depth: standard
files_reviewed: 14
files_reviewed_list:
  - core/calendar.py
  - core/config.py
  - core/data.py
  - core/events.py
  - core/storage.py
  - jobs/build_macro_calendar.py
  - jobs/detect_events.py
  - scripts/report_phase2.py
  - tests/test_build_macro_calendar.py
  - tests/test_calendar.py
  - tests/test_detect_events.py
  - tests/test_episode_replay.py
  - tests/test_events.py
  - tests/test_macro_calendar_data.py
findings:
  critical: 1
  warning: 4
  info: 7
  total: 12
status: issues_found
---

# Phase 2: Code Review Report

**Reviewed:** 2026-10-09
**Depth:** standard
**Files Reviewed:** 14
**Status:** issues_found

## Summary

I reviewed the Phase 2 detector (`core/events.py`), the macro-calendar parser, merge and validation code (`core/calendar.py`), the FRED/Fed fetchers, both jobs, the calibration report and the tests.

The FRED key handling holds up. The key is read only from the environment, every `requests` error is rewritten with `from None`, and `resp.url` never shows up in an error message. No look-ahead turned up in the shock, gap or drawdown signals. Purity boundaries are respected.

The main defect is in the DET-05 replay-stability contract. A rally episode can be marked `closed` and then change its `end_date`, `move_pct`, `severity` and `status` when more rows are appended. A synthetic series reproduces it under production `SETTINGS`. Phase 3's paid enrichment relies on exactly this contract, so this is a blocker.

The remaining findings are about honesty and robustness:
- Fed conference calls are labelled as unscheduled FOMC "actions".
- A stale calendar quietly produces `surprise` catalysts.
- The calendar stability check ignores the `scheduled` flag.
- The episode job's write path is not atomic.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: A "closed" rally episode changes when new rows are appended (DET-05 contract broken)

**File:** `core/events.py:159-174` (rally merge) and `core/events.py:202-239`, `328-332` (closure)
**Issue:** `rally_legs` sweeps candidate `(trough j, i)` intervals into merged spans, then reports each leg as `(trough_pos, peak_pos)`. `peak_pos` is the earliest argmax inside the span, which can sit well before the span's merged end. `closure_frontier` case (b) only reasons about a future rally's own interval. It ignores that a future candidate whose `j` is at or before an existing span's merged end gets merged into that span inside `rally_legs`, before clustering. That moves the existing leg's `peak_pos`, `end_pos` and `move`.

The cluster check `end_pos + merge_window_days < frontier` uses the peak, not the merged-span end. So the episode is already marked `closed` while its span can still be extended.

Reproduced with production `SETTINGS`, with drawdown, shock and gap disabled to isolate the effect. The series is flat at about 100, jumps once to 110, holds at about 109 for `rally_window_days + 3` bars, then ends at a new high of 111:

```
before: 2024-04-22_rally start 2024-03-12 end 2024-04-22 move 0.1000 status closed
+1 bar: 2024-04-22_rally start 2024-03-12 end 2024-06-10 move 0.1783 status open
```

The episode keeps its `episode_id` but its `end_date`, `move_pct`, `severity` and `status` all change. If the new bar's return were larger than the original jump, the anchor would move and the `episode_id` would change too. A "closed" episode is exactly what Phase 3 will spend API budget on, so this breaks DET-05.

The tests miss it because `tests/test_episode_replay.py` sets `rally_threshold=10.0` (rally disabled) in every synthetic case, and the six real-data cutoffs happen not to land on this pattern.

**Fix:** Carry the merged-span end on the leg and use it for closure. One option:

```python
@dataclass(frozen=True)
class Leg:
    kind: str
    start_pos: int
    end_pos: int
    move: float
    recovery_pos: int | None
    reach_pos: int | None = None  # last position whose data can still change this leg

# rally_legs
legs.append(Leg("rally", trough_pos, peak_pos, move, None, reach_pos=end))

# detect
reach = max((leg.reach_pos if leg.reach_pos is not None else leg.end_pos) for leg in cluster)
status = "closed" if max(end_pos, reach) + settings.merge_window_days < frontier and drawdown_recovered else "open"
```

Also add a synthetic replay test with rally enabled that uses the series above, and fix the `closure_frontier` docstring proof, case (b).

## Warnings

### WR-01: Fed conference calls are recorded and reported as unscheduled FOMC "actions"

**File:** `core/calendar.py:104-106`, `scripts/report_phase2.py:150-151`
**Issue:** Every historical "Conference Call" header becomes `release_type="unscheduled"`, `scheduled=False`, and the module docstring calls these "decision dates". Many calls made no policy decision. The committed calendar has 8 unscheduled FOMC rows in 1993, a year with no change to the funds-rate target. 2008-01-09 and 2008-07-24 were also no-action calls.

`tag_episodes` then lists these calls under `unscheduled_releases` for public episodes. The calibration report prints `Unscheduled FOMC actions: 45`. That number is not true as worded, which conflicts with the project's honesty rule. `catalyst` is unaffected, because only scheduled rows drive it.

**Fix:** Either rename the concept everywhere to "unscheduled FOMC call or meeting" (docstring, the report line, and the future app label), or add a `Settings.fomc_no_action_calls` allow-list, the same way `fomc_non_decision_meetings` works, so only calls that produced a policy action are tagged.

### WR-02: A stale or later-rebuilt calendar silently changes `catalyst`, including on "closed" episodes

**File:** `jobs/detect_events.py:57-69`, `core/calendar.py:333-373`
**Issue:** `detect_events` tags episodes against whatever calendar is committed, with no coverage check. The committed calendar's FRED rows end at CPI 2026-12-10 and payrolls 2026-12-04, and it is only rebuilt by hand because it needs a local FRED key. Any episode whose search window falls after the last FRED date will get `scheduled_releases=[]` and `catalyst="surprise"`, even if a CPI or payrolls print happened in the window. That is a false public claim.

When the calendar is later rebuilt, the `catalyst` of an already-closed episode flips. Yet `catalyst` is in the replay test's `exact_cols` and is treated as stable downstream.

**Fix:** In `detect_events.main`, fail (or at least mark the episode `open`) when any episode's `search_to` is after the last calendar date of any FRED release:

```python
for label, _rid, _ in SETTINGS.fred_releases:
    last = calendar.loc[calendar["release"] == label, "date"].max()
    if pd.isna(last) or episodes["search_to"].max() > last:
        print(f"macro calendar {label} coverage ends {last}; rebuild it", file=sys.stderr)
        return 1
```

### WR-03: The calendar stability check ignores `scheduled` and `release_type`, and accepts newly inserted past rows

**File:** `core/calendar.py:245-258`, `jobs/build_macro_calendar.py:137-140`
**Issue:** `merge_calendar` compares only `(date, release)` pairs. If a past FOMC row flips from `scheduled=True` to `False` (or the reverse), or its `release_type` changes, the check passes and history is rewritten silently. That flip changes `catalyst` for already-closed episodes. New rows dated before `today` (for example a past date FRED newly lists) are also accepted without comment, even though the docstring promises to "fail loudly rather than silently rewrite the past". The job's added/removed summary uses the same coarse key, so such changes never show up in its output either.

There is also no escape hatch. A legitimately vanished past row, such as a release postponed after the calendar was built, blocks every rebuild until someone deletes the committed file by hand.

**Fix:** Compare past rows on the full `(date, release, release_type, scheduled)` tuple, and raise on both removals and additions dated before `today`. Add an explicit `--accept-history-change` flag that prints the diff and proceeds, so maintainers can apply a correction deliberately.

### WR-04: `detect_events` write path is not atomic and can leave data/ inconsistent

**File:** `jobs/detect_events.py:35-40`, `81-85`
**Issue:** `_write_episodes` writes `episodes.parquet` first, then loads `meta.json`. If `meta.json` is missing or corrupt, the episodes are already overwritten, `detector_version` in meta is stale, and the job dies with a traceback. The module docstring promises "exits 1 without touching data/".

Separately, if `detect` returns zero episodes (for example on a short price file), the file is written and then `df['start_date'].iloc[0]` raises `IndexError` after the write.

**Fix:** Load and validate meta before writing anything. Reject an empty frame before the write. Write to a temporary path and `os.replace` it into place:

```python
meta = load_meta(meta_path)              # before any write
if df.empty:
    print("episode detection produced zero episodes", file=sys.stderr); return 1
write_episodes(df, episodes_path)        # ideally tmp + os.replace
meta["detector_version"] = SETTINGS.detector_version
write_meta(meta, meta_path)
```

## Info

### IN-01: Zero rolling sigma gives `inf` z-scores and `inf` severity

**File:** `core/events.py:77-78`, `300-302`
**Issue:** If the lagged rolling std is 0 (for example a stuck feed repeating a close), `ret / sigma` is `inf` or `nan`, and `max_z` and `severity` become `inf` and get written to parquet. This was seen with a flat synthetic series.
**Fix:** `sigma = sigma.where(sigma > 0)` before dividing.

### IN-02: `detect_events` only catches `ValueError`

**File:** `jobs/detect_events.py:67-72`
**Issue:** `next(...)` at `core/events.py:276` raises `StopIteration` if `trigger_precedence` is missing a kind. Malformed parquet raises `ArrowInvalid` or `KeyError`. Either one escapes as a raw traceback.
**Fix:** Pass a default to `next` and raise `ValueError`, or catch `Exception` and exit 1, as `build_macro_calendar` does.

### IN-03: Gap legs store a close-to-close return as `move`

**File:** `core/events.py:262-264`
**Issue:** `Leg("gap", ..., float(ret.loc[date]))` records the log close-to-close return, not the gap `open/prev_close - 1`. It is currently unused, but it is misleading.
**Fix:** Store the gap value, or document that `move` is ignored for single-day legs.

### IN-04: Misleading "future rows" summary

**File:** `jobs/build_macro_calendar.py:151`
**Issue:** `added` and `removed` count all keys, past included, but the message says "future rows".
**Fix:** Filter to `date >= today` or reword the message.

### IN-05: Parquet writes are not atomic

**File:** `core/storage.py:34-50`
**Issue:** `to_parquet` writes in place, so an interrupted run can leave a truncated committed artifact.
**Fix:** Write to `path.with_suffix(".tmp")`, then `os.replace`.

### IN-06: Weak or inconsistent tests

**File:** `tests/test_calendar.py:93`, `tests/test_detect_events.py:29-42`, `tests/test_episode_replay.py:169-171`
**Issue:**
- Line 93's `... or "September 15" in html` makes the precondition assertion almost tautological.
- The detector and replay tests hard-require `data/macro_calendar.parquet`, while `test_macro_calendar_data.py` skips when it is missing, so a fresh clone fails in a different way per module.
**Fix:** Assert the exact header text. Use one consistent skip or fail policy for missing committed artifacts.

### IN-07: The closure proof relies on unstated config coupling

**File:** `core/events.py:226-230`, `311-318`
**Issue:** The docstring says every closed-episode field comes from positions inside `[start_pos, end_pos]`. That is not quite true: `search_to` reaches `end_pos + search_post_days`, and `structural_search_half_width` also extends the window. Stability currently holds only because `search_post_days` and `structural_search_half_width` are small compared with `merge_window_days + rally_window_days`. Nothing enforces that.
**Fix:** Correct the docstring, and add a config assertion (or a test) that `max(search_post_days, structural_search_half_width) <= merge_window_days`.

---

_Reviewed: 2026-10-09_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
