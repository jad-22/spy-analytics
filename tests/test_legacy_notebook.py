"""Documents why the 2022 notebook's strategy returns cannot be trusted.

`legacy_returns_loop` is a faithful copy of the notebook's evaluation loop.
"""
import pandas as pd
import pytest


def legacy_returns_loop(data: pd.DataFrame, column_name: str, starting_value: float = 100):
    temp_df = data[data[column_name] != 0][[column_name, "Close", "next_open"]]
    price = data["Close"].values[0]
    value = starting_value
    position = True
    for _, row in temp_df.iterrows():
        value = value * row["next_open"] / price
        price = row["next_open"]
        if row[column_name] == -1:
            position = False
        elif row[column_name] == 1:
            position = True
    if position:
        value = data["Close"].values[-1]
    return value


def test_legacy_loop_disagrees_with_hand_calculation():
    closes = [100.0, 110.0, 99.0, 99.0, 120.0, 132.0]
    df = pd.DataFrame({"Close": closes, "Open": closes})
    df["next_open"] = df["Open"].shift(-1)
    df["sig"] = [0, -1, 0, 1, 0, 0]  # sell filled at 99, buy filled at 120

    # Correct: 100 -> 99 (sell) -> cash -> buy at 120 -> worth 132  =>  99 * 132 / 120
    correct = 100 * (99 / 100) * (132 / 120)
    legacy = legacy_returns_loop(df, "sig")

    assert correct == pytest.approx(108.9)
    assert legacy == pytest.approx(132.0)  # a share price, not a portfolio value
    assert legacy != pytest.approx(correct)
