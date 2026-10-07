import pandas as pd
import pytest

from core.indicators import MASpec, ema, sma


def test_sma_needs_full_window():
    s = pd.Series([1.0, 2, 3, 4])
    assert sma(s, 3).isna().sum() == 2
    assert sma(s, 3).iloc[-1] == pytest.approx(3.0)


def test_ema_uses_span_not_centre_of_mass():
    s = pd.Series([10.0, 20, 30, 40, 50])
    n = 3
    alpha = 2 / (n + 1)
    manual = [10.0]
    for x in s.iloc[1:]:
        manual.append(alpha * x + (1 - alpha) * manual[-1])
    got = ema(s, n)
    assert got.iloc[-1] == pytest.approx(manual[-1])
    # The notebook's ewm(period) is a much slower average
    assert s.ewm(n).mean().iloc[-1] != pytest.approx(manual[-1])


def test_maspec_label():
    assert MASpec("ema", 10).label == "ema10"
