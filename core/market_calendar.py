"""NYSE trading-session calendar (DATA-03, D-13 gap check).

Pure module: no network calls, no Streamlit import. Recurring closures come from
`pandas.tseries.holiday` rules (pandas is already a dependency, so no new package
is needed). One-off closures that don't fit a recurring rule (funerals, 9/11,
Hurricane Sandy) live in NYSE_SPECIAL_CLOSURES, verified against a cited source.
"""
from __future__ import annotations

from typing import ClassVar

import pandas as pd
from pandas import DateOffset
from pandas.tseries.holiday import (
    MO,
    AbstractHolidayCalendar,
    GoodFriday,
    Holiday,
    USLaborDay,
    USMemorialDay,
    USPresidentsDay,
    USThanksgivingDay,
    nearest_workday,
    sunday_to_monday,
)

# Each entry is a trading day NYSE was fully closed that does not fit a recurring
# rule. Sources: NYSE/SEC closure notices and contemporaneous news reports.
NYSE_SPECIAL_CLOSURES: tuple[str, ...] = (
    "1994-04-27",  # Nixon funeral
    "2001-09-11",  # September 11 attacks
    "2001-09-12",  # September 11 attacks
    "2001-09-13",  # September 11 attacks
    "2001-09-14",  # September 11 attacks
    "2004-06-11",  # Reagan funeral
    "2007-01-02",  # Ford funeral
    "2012-10-29",  # Hurricane Sandy
    "2012-10-30",  # Hurricane Sandy
    "2018-12-05",  # G.H.W. Bush funeral
    "2025-01-09",  # Carter funeral
)


class NYSEHolidayCalendar(AbstractHolidayCalendar):
    """Recurring NYSE holiday rules used for the D-13 gap check.

    Special one-off closures are not recurring rules and live in
    NYSE_SPECIAL_CLOSURES instead of here.
    """

    rules: ClassVar[list[Holiday]] = [
        # NYSE does not close the prior Friday when Jan 1 falls on a Saturday —
        # sunday_to_monday only shifts a Sunday Jan 1 to the following Monday.
        Holiday("New Year's Day", month=1, day=1, observance=sunday_to_monday),
        Holiday(
            "Birthday of Martin Luther King, Jr.",
            month=1,
            day=1,
            offset=DateOffset(weekday=MO(3)),
            start_date="1998-01-01",  # NYSE added MLK Day to its calendar in 1998
        ),
        USPresidentsDay,
        GoodFriday,
        USMemorialDay,
        Holiday(
            "Juneteenth National Independence Day",
            month=6,
            day=19,
            start_date="2022-01-01",  # First observed as an NYSE holiday in 2022
            observance=nearest_workday,
        ),
        Holiday("Independence Day", month=7, day=4, observance=nearest_workday),
        USLaborDay,
        USThanksgivingDay,
        Holiday("Christmas Day", month=12, day=25, observance=nearest_workday),
    ]


def nyse_holidays(start, end) -> pd.DatetimeIndex:
    """NYSE holidays (recurring rules plus special closures) inside [start, end]."""
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    calendar_holidays = NYSEHolidayCalendar().holidays(start=start_ts, end=end_ts)
    special = pd.DatetimeIndex(
        [d for d in NYSE_SPECIAL_CLOSURES if start_ts <= pd.Timestamp(d) <= end_ts]
    )
    return calendar_holidays.union(special)


def nyse_sessions(start, end) -> pd.DatetimeIndex:
    """Trading sessions (business days minus NYSE holidays) inside [start, end]."""
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    return pd.bdate_range(start_ts, end_ts).difference(nyse_holidays(start_ts, end_ts))
