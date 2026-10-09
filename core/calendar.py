"""Macro-release calendar: FOMC/CPI/payrolls parsing, merge and validation (CAL-01).

Pure: no network call, no Streamlit import, must not import core.data or core.storage.
This is the macro-*release* calendar (FOMC decisions, CPI, payrolls) -- a different
concept from core/market_calendar.py's NYSE trading-session calendar; keep the two
separate.

HTML is parsed with stdlib `re` + `html.unescape` only (no new dependency, no
pandas.read_html). jobs/build_macro_calendar.py owns all network I/O and calls these
functions with already-fetched text/JSON.
"""
from __future__ import annotations

import calendar as _calendar_module
import html as html_lib
import re

import pandas as pd

from core.config import Settings

CALENDAR_COLUMNS = ["date", "release", "release_type", "scheduled", "source_url"]

# Appended to EPISODE_COLUMNS by tag_episodes (CAL-02). Not imported from core.events --
# core/calendar.py must stay decoupled from core/events.py (no cross-import required; both
# are pure siblings called by jobs/detect_events.py).
TAG_COLUMNS = ("scheduled_releases", "unscheduled_releases", "catalyst")

# "January 6 Conference Call - 1993", "February 2-3 Meeting - 1993",
# "March 2 (unscheduled) Meeting - 2020", "March 17-18 (cancelled) Meeting - 2020"
_HISTORICAL_ENTRY_RE = re.compile(
    r"(?P<mon>[A-Za-z]+)\s+(?P<day1>\d{1,2})(?:-(?P<day2>\d{1,2}))?"
    r"(?:\s*\((?P<note>[a-z]+)\))?\s*(?P<kind>Conference Call|Meeting)\s*-\s*(?P<year>\d{4})"
)

# "2021 FOMC Meetings" section headers on the current calendars page.
_YEAR_SECTION_RE = re.compile(r"(?P<year>\d{4})\s+FOMC Meetings")

# "January 26-27 Statement", "March 16-17* Statement", "Jan/Feb 31-1 Statement",
# "August 22 (notation vote) Statement". Future meetings have no Statement link yet
# ("October 27-28 December 8-9* * Meeting associated..."), so an entry may instead be
# followed by the next entry, the footnote asterisk or the end of its year section.
# Prose dates ("Released February 18, 2026", "January 25-26, 2028") are followed by a
# comma and never match.
_CALENDAR_ENTRY_RE = re.compile(
    r"(?:(?P<mon1>[A-Za-z]{3,9})/)?(?P<mon2>[A-Za-z]{3,9})\s+(?P<day1>\d{1,2})"
    r"(?:-(?P<day2>\d{1,2}))?\*?\s*(?:\((?P<note>[a-z ]+)\))?"
    r"(?=\s*(?:Statement|\*|[A-Z][a-z]+(?:/[A-Z][a-z]+)?\s+\d{1,2}(?:-\d{1,2})?\*?(?:\s|$)|$))"
)


def _strip_html(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw)
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text)


_MONTH_NAMES = {name.lower(): i for i, name in enumerate(_calendar_module.month_name) if name}
_MONTH_ABBRS = {abbr.lower(): i for i, abbr in enumerate(_calendar_module.month_abbr) if abbr}


def _parse_month(name: str) -> int:
    key = name.lower()
    if key in _MONTH_NAMES:
        return _MONTH_NAMES[key]
    if key in _MONTH_ABBRS:
        return _MONTH_ABBRS[key]
    raise ValueError(f"unrecognized month name: {name!r}")


def _frame(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=CALENDAR_COLUMNS)
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    df["scheduled"] = df["scheduled"].astype(bool)
    return df.sort_values(["date", "release", "release_type"]).reset_index(drop=True)


def parse_fomc_historical(
    html: str, year: int, url: str, non_decision: tuple[str, ...] = ()
) -> pd.DataFrame:
    """Scheduled/unscheduled FOMC decision dates from one federalreserve.gov per-year page.

    Header classification: "Conference Call" or an "(unscheduled)" annotation ->
    release_type "unscheduled", scheduled False. A plain "Meeting" header -> "meeting",
    scheduled True. A "(cancelled)" meeting is dropped entirely -- no decision was made
    on that date (RESEARCH Pitfall 2; the cancelled slot is replaced by the emergency
    unscheduled meetings that appear as their own rows). Dates in `non_decision`
    (Settings.fomc_non_decision_meetings) are dropped for the same reason.
    """
    text = _strip_html(html)
    skip = {pd.Timestamp(d) for d in non_decision}
    rows: list[dict] = []
    for m in _HISTORICAL_ENTRY_RE.finditer(text):
        if int(m.group("year")) != year:
            continue
        note = (m.group("note") or "").lower()
        if note == "cancelled":
            continue
        day = int(m.group("day2") or m.group("day1"))
        month = _parse_month(m.group("mon"))
        date = pd.Timestamp(year=year, month=month, day=day)
        if date in skip:
            continue
        kind = m.group("kind")
        if kind == "Conference Call" or note == "unscheduled":
            release_type, scheduled = "unscheduled", False
        else:
            release_type, scheduled = "meeting", True
        rows.append(
            {
                "date": date,
                "release": "FOMC",
                "release_type": release_type,
                "scheduled": scheduled,
                "source_url": url,
            }
        )
    if not rows:
        raise ValueError(f"parsed zero FOMC rows from {url} (year {year})")
    return _frame(rows)


def parse_fomc_calendars(html: str, url: str) -> pd.DataFrame:
    """Scheduled FOMC decision dates from the current federalreserve.gov calendars page.

    The page groups entries under "<year> FOMC Meetings" section headers. A
    "(notation vote)" entry (e.g. a vote on the Longer-Run Goals strategy statement) is
    not a rate-decision meeting and is dropped. An "(unscheduled)" entry, if the page
    ever carries one, is tagged scheduled False -- the current (2021-2027) page has none,
    but the rule mirrors parse_fomc_historical's for consistency.
    """
    text = _strip_html(html)
    year_matches = list(_YEAR_SECTION_RE.finditer(text))
    if not year_matches:
        raise ValueError(f"parsed zero FOMC year sections from {url}")

    rows: list[dict] = []
    for i, ym in enumerate(year_matches):
        year = int(ym.group("year"))
        chunk_start = ym.end()
        chunk_end = year_matches[i + 1].start() if i + 1 < len(year_matches) else len(text)
        chunk = text[chunk_start:chunk_end]
        for m in _CALENDAR_ENTRY_RE.finditer(chunk):
            note = (m.group("note") or "").lower()
            if "notation vote" in note:
                continue
            month = _parse_month(m.group("mon2"))
            day = int(m.group("day2") or m.group("day1"))
            date = pd.Timestamp(year=year, month=month, day=day)
            if "unscheduled" in note:
                release_type, scheduled = "unscheduled", False
            else:
                release_type, scheduled = "meeting", True
            rows.append(
                {
                    "date": date,
                    "release": "FOMC",
                    "release_type": release_type,
                    "scheduled": scheduled,
                    "source_url": url,
                }
            )
    if not rows:
        raise ValueError(f"parsed zero FOMC rows from {url}")
    return _frame(rows)


def parse_fred_release_dates(
    payload: dict, label: str, release_id: int, url_template: str
) -> pd.DataFrame:
    """CPI/payrolls release dates from a FRED `release/dates` JSON payload.

    Raises on a pagination mismatch (`count` larger than the returned rows -- the job
    always requests limit=10000, but a future FRED change shouldn't silently truncate
    a backfill) or an unparseable date.
    """
    release_dates = payload.get("release_dates", [])
    count = payload.get("count", len(release_dates))
    if count > len(release_dates):
        raise ValueError(
            f"FRED release_id={release_id} payload is paginated: count={count} "
            f"but only {len(release_dates)} release_dates present"
        )
    if not release_dates:
        raise ValueError(f"FRED release_id={release_id} returned zero release_dates")

    rows: list[dict] = []
    for entry in release_dates:
        try:
            date = pd.Timestamp(entry["date"])
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError(
                f"FRED release_id={release_id} has an unparseable date: {entry!r}"
            ) from exc
        source_url = url_template.format(rid=release_id, year=date.year)
        rows.append(
            {
                "date": date,
                "release": label,
                "release_type": "release",
                "scheduled": True,
                "source_url": source_url,
            }
        )
    return _frame(rows)


def drop_non_release_dates(
    df: pd.DataFrame, non_release: tuple[tuple[str, str], ...]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Remove FRED dates that are not scheduled prints; return (kept, dropped).

    `non_release` is Settings.fred_non_release_dates: (release label, ISO date) pairs.
    FRED's release/dates also lists revision and seasonal-factor publication days, and
    no position rule (first or last in the month) separates them from the print, so
    they are listed explicitly. validate_macro_calendar's one-per-month check catches
    any new one.
    """
    skip = {(label, pd.Timestamp(d)) for label, d in non_release}
    is_skip = pd.Series(
        [(r, d) in skip for r, d in zip(df["release"], df["date"], strict=True)],
        index=df.index,
        dtype=bool,
    )
    return df[~is_skip].reset_index(drop=True), df[is_skip].reset_index(drop=True)


# The columns a past calendar row must keep across rebuilds: tag_episodes reads all of them.
_HISTORY_KEY = ["date", "release", "release_type", "scheduled"]


def past_calendar_changes(
    existing: pd.DataFrame, fresh: pd.DataFrame, today
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(removed, added) rows dated before `today`, compared on the full _HISTORY_KEY.

    A row whose release_type or scheduled flag changed shows up in both frames.
    """
    today_ts = pd.Timestamp(today)

    def _past_keys(df: pd.DataFrame) -> pd.DataFrame:
        past = df.loc[df["date"] < today_ts, _HISTORY_KEY].copy()
        past["scheduled"] = past["scheduled"].astype(bool)
        return past.drop_duplicates()

    old, new = _past_keys(existing), _past_keys(fresh)
    both = old.merge(new, on=_HISTORY_KEY, how="outer", indicator=True)
    removed = both.loc[both["_merge"] == "left_only", _HISTORY_KEY]
    added = both.loc[both["_merge"] == "right_only", _HISTORY_KEY]
    return removed.reset_index(drop=True), added.reset_index(drop=True)


def merge_calendar(
    existing: pd.DataFrame | None,
    fresh: pd.DataFrame,
    today,
    accept_history_change: bool = False,
) -> pd.DataFrame:
    """Combine a freshly rebuilt calendar with the previously committed one (D-03).

    `fresh` is produced by a full rebuild each run (job fetches calendar_start..horizon
    every time), so it is always the authoritative superset: fresh wins on any
    (date, release, release_type) key. The only role of `existing` is the stability
    check on rows dated before `today`, compared on date, release, release_type and the
    scheduled flag (tag_episodes reads all four, so any change would rewrite closed
    episodes' tags). A past row that vanished or changed, or a new past scheduled row,
    fails loudly unless `accept_history_change` is set by a maintainer who has checked
    it (e.g. a print postponed by a shutdown). A new past unscheduled row is accepted: an
    emergency FOMC action between rebuilds is expected.
    """
    fresh = fresh.drop_duplicates(subset=["date", "release", "release_type"], keep="last")
    fresh = fresh.sort_values(["date", "release", "release_type"]).reset_index(drop=True)

    if existing is None or accept_history_change:
        return fresh

    removed, added = past_calendar_changes(existing, fresh, today)
    added_scheduled = added[added["scheduled"]]
    if len(removed) or len(added_scheduled):

        def _show(df: pd.DataFrame) -> list[str]:
            return [
                f"{r.date.date()} {r.release} {r.release_type} scheduled={r.scheduled}"
                for r in df.head(10).itertuples()
            ]

        raise ValueError(
            "past calendar rows changed (rerun with --accept-history-change after "
            f"checking): missing or changed {_show(removed)}, new scheduled "
            f"{_show(added_scheduled)}"
        )

    return fresh


def validate_macro_calendar(df: pd.DataFrame, settings: Settings, today) -> None:
    """Raise ValueError on any structural defect. No-op on a well-formed frame."""
    today_ts = pd.Timestamp(today)

    if df["date"].isna().any():
        raise ValueError("macro calendar has NaT date(s)")

    dup_mask = df.duplicated(subset=["date", "release", "release_type"], keep=False)
    if dup_mask.any():
        dups = df.loc[dup_mask, ["date", "release", "release_type"]].drop_duplicates()
        raise ValueError(f"duplicate calendar row(s): {dups.to_dict('records')[:10]}")

    bad_url = ~df["source_url"].str.startswith("https://") | df["source_url"].str.contains(
        "api_key", case=False
    )
    if bad_url.any():
        raise ValueError(f"source_url not public/https-safe on {int(bad_url.sum())} row(s)")

    start_ts = pd.Timestamp(settings.calendar_start)
    horizon_ts = today_ts + pd.Timedelta(days=settings.calendar_horizon_days)
    out_of_range = (df["date"] < start_ts) | (df["date"] > horizon_ts)
    if out_of_range.any():
        raise ValueError(
            f"{int(out_of_range.sum())} row(s) outside "
            f"[{start_ts.date()}, {horizon_ts.date()}]"
        )

    fred_labels = [label for label, _rid, _name in settings.fred_releases]
    fred = df[df["release"].isin(fred_labels)]
    months = fred["date"].dt.strftime("%Y-%m")
    per_month = fred.groupby([fred["release"], months])["date"].agg(list)
    allowed = set(settings.fred_double_release_months)
    extra = {
        key: [str(d.date()) for d in dates]
        for key, dates in per_month.items()
        if len(dates) > 1 and key not in allowed
    }
    if extra:
        raise ValueError(
            f"more than one release in a month (add the non-print date to "
            f"fred_non_release_dates after checking it): {extra}"
        )

    first_release_by = pd.Timestamp(settings.calendar_first_release_by)
    for label, _rid, _name in settings.fred_releases:
        rows = df[df["release"] == label]
        if len(rows) and rows["date"].min() > first_release_by:
            raise ValueError(
                f"{label}'s first date {rows['date'].min().date()} is after "
                f"calendar_first_release_by {first_release_by.date()}"
            )

    first_year = start_ts.year
    last_complete_year = today_ts.year - 1
    fomc_lo, fomc_hi = settings.fomc_scheduled_per_year
    mon_lo, mon_hi = settings.monthly_releases_per_year
    for year in range(first_year, last_complete_year + 1):
        year_df = df[df["date"].dt.year == year]
        fomc_scheduled = int(
            ((year_df["release"] == "FOMC") & year_df["scheduled"]).sum()
        )
        if not (fomc_lo <= fomc_scheduled <= fomc_hi):
            raise ValueError(
                f"{year}: {fomc_scheduled} scheduled FOMC meetings, expected "
                f"{fomc_lo}-{fomc_hi}"
            )
        for label, _rid, _name in settings.fred_releases:
            count = int((year_df["release"] == label).sum())
            if not (mon_lo <= count <= mon_hi):
                raise ValueError(f"{year}: {count} {label} releases, expected {mon_lo}-{mon_hi}")


def check_calendar_coverage(
    episodes: pd.DataFrame, calendar: pd.DataFrame, releases: tuple[str, ...]
) -> None:
    """Raise ValueError if any release's last calendar date is before the latest episode
    search_to. Past a release's last date, tag_episodes would see an empty window and call
    a move a "surprise" even if a print happened, and a later rebuild would flip it."""
    if episodes.empty:
        return
    through = episodes["search_to"].max()
    short = []
    for release in releases:
        last = calendar.loc[calendar["release"] == release, "date"].max()
        if pd.isna(last) or last < through:
            short.append(f"{release} ends {'never' if pd.isna(last) else last.date()}")
    if short:
        raise ValueError(
            f"macro calendar does not cover episodes through {through.date()} "
            f"({', '.join(short)}); rebuild it with jobs.build_macro_calendar"
        )


def tag_episodes(episodes: pd.DataFrame, calendar: pd.DataFrame) -> pd.DataFrame:
    """Tag each episode with in-window macro releases, scheduled vs surprise (CAL-02).

    For every episode, selects calendar rows whose date falls in
    [search_from, search_to] inclusive on calendar dates (including non-trading days --
    this is a calendar-date window, not a trading-day one). Each match is formatted as
    f"{release} {date:%Y-%m-%d}", sorted by (date, release). Rows with scheduled=True go
    to scheduled_releases; scheduled=False rows go to unscheduled_releases. catalyst is
    "scheduled" iff scheduled_releases is non-empty, else "surprise" -- an
    unscheduled-only or empty window still counts as a surprise, since only a scheduled
    release makes a move explainable by the calendar (RESEARCH Pitfall 2).

    Pure: does not mutate either input, preserves episodes' row order and columns,
    appends TAG_COLUMNS at the end. Raises ValueError if calendar is missing a
    CALENDAR_COLUMNS column.
    """
    missing = [c for c in CALENDAR_COLUMNS if c not in calendar.columns]
    if missing:
        raise ValueError(f"calendar is missing column(s): {missing}")

    cal = calendar.sort_values(["date", "release"]).reset_index(drop=True)
    cal_dates = cal["date"]
    cal_scheduled = cal["scheduled"].astype(bool)
    cal_labels = cal["release"].astype(str) + " " + cal_dates.dt.strftime("%Y-%m-%d")

    scheduled_col: list[list[str]] = []
    unscheduled_col: list[list[str]] = []
    catalyst_col: list[str] = []
    for search_from, search_to in zip(episodes["search_from"], episodes["search_to"], strict=True):
        in_window = (cal_dates >= search_from) & (cal_dates <= search_to)
        scheduled = cal_labels[in_window & cal_scheduled].tolist()
        unscheduled = cal_labels[in_window & ~cal_scheduled].tolist()
        scheduled_col.append(scheduled)
        unscheduled_col.append(unscheduled)
        catalyst_col.append("scheduled" if scheduled else "surprise")

    tagged = episodes.copy(deep=True)
    tagged["scheduled_releases"] = scheduled_col
    tagged["unscheduled_releases"] = unscheduled_col
    tagged["catalyst"] = catalyst_col
    return tagged
