"""Tests for scripts/report_news_budget.py (NEWS-07, success criterion 1, D-01) and
scripts/report_phase3.py (NEWS-07, NEWS-08, REV-02). No network; every number traces
back to core/config.py's SETTINGS, a hand-built episodes/ledger fixture, or committed
data read through core/storage.py.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from core.config import SETTINGS
from core.news.cost import estimate_backfill_usd
from scripts import report_news_budget


def _write_episodes(path: Path, statuses: list[str]) -> None:
    df = pd.DataFrame(
        {
            "episode_id": [f"2020-01-0{i + 1}_shock" for i in range(len(statuses))],
            "status": statuses,
        }
    )
    df.to_parquet(path, index=False)


# ---------------------------------------------------------------------------
# render_budget
# ---------------------------------------------------------------------------


def test_render_budget_empty_ledger_contains_verified_pricing_and_estimates():
    report = report_news_budget.render_budget(142, [], SETTINGS)

    for name, in_price, out_price in SETTINGS.news_model_prices_usd_per_mtok:
        assert name in report
        assert f"{in_price:.2f}" in report
        assert f"{out_price:.2f}" in report
    assert f"{SETTINGS.news_web_search_usd_per_1k:.2f}" in report
    assert SETTINGS.news_pricing_verified_on in report
    for url in SETTINGS.news_pricing_sources:
        assert url in report
    assert "142" in report

    haiku_estimate = estimate_backfill_usd(
        142,
        SETTINGS.news_model,
        SETTINGS,
        SETTINGS.news_estimate_searches_per_episode,
        SETTINGS.news_estimate_input_tokens_per_episode,
        SETTINGS.news_estimate_output_tokens_per_episode,
    )
    assert f"{haiku_estimate:.2f}" in report

    worst_case_search = (
        142 * SETTINGS.news_max_searches_per_request * SETTINGS.news_web_search_usd_per_1k / 1000
    )
    worst_case_reserve = 142 * SETTINGS.news_episode_cost_reserve_usd
    assert f"{worst_case_search:.2f}" in report
    assert f"{worst_case_reserve:.2f}" in report

    n_escalate = round(142 * 0.2)
    escalation_estimate = estimate_backfill_usd(
        n_escalate,
        SETTINGS.news_escalation_model,
        SETTINGS,
        SETTINGS.news_estimate_searches_per_episode,
        SETTINGS.news_estimate_input_tokens_per_episode,
        SETTINGS.news_estimate_output_tokens_per_episode,
    )
    assert f"{escalation_estimate:.2f}" in report
    assert f"{SETTINGS.news_budget_usd:.2f}" in report
    assert "No paid runs recorded yet" in report


def test_render_budget_with_ledger_lists_runs_and_remaining_budget():
    ledger = [
        {
            "run_id": "run-a",
            "provider": "claude",
            "model": "claude-haiku-5-5",
            "prompt_version": "v1",
            "mode": "backfill",
            "episodes_attempted": 10,
            "episodes_written": 10,
            "failures": 0,
            "input_tokens": 1000,
            "output_tokens": 100,
            "web_search_requests": 15,
            "cost_usd": 1.0,
        },
        {
            "run_id": "run-b",
            "provider": "claude",
            "model": "claude-sonnet-5-5",
            "prompt_version": "v1",
            "mode": "escalation",
            "episodes_attempted": 2,
            "episodes_written": 2,
            "failures": 0,
            "input_tokens": 200,
            "output_tokens": 20,
            "web_search_requests": 3,
            "cost_usd": 0.5,
        },
    ]
    report = report_news_budget.render_budget(142, ledger, SETTINGS)

    assert "No paid runs recorded yet" not in report
    for entry in ledger:
        assert entry["run_id"] in report
        assert entry["mode"] in report
        assert entry["model"] in report
        assert str(entry["episodes_written"]) in report
        assert str(entry["web_search_requests"]) in report
        assert f"{entry['cost_usd']:.2f}" in report

    assert "1.50" in report  # total spent
    remaining = SETTINGS.news_budget_usd - 1.5
    assert f"{remaining:.2f}" in report


def test_render_budget_is_deterministic():
    first = report_news_budget.render_budget(142, [], SETTINGS)
    second = report_news_budget.render_budget(142, [], SETTINGS)
    assert first == second


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------


def test_main_writes_file_and_returns_0(tmp_path: Path):
    episodes_path = tmp_path / "episodes.parquet"
    ledger_path = tmp_path / "enrichment_spend.json"
    out_path = tmp_path / "PHASE3_BUDGET.md"
    _write_episodes(episodes_path, ["closed", "closed", "open"])

    exit_code = report_news_budget.main(
        [
            "--episodes-path", str(episodes_path),
            "--ledger-path", str(ledger_path),
            "--out", str(out_path),
        ]
    )

    assert exit_code == 0
    assert out_path.exists()
    content = out_path.read_text()
    assert "Closed episodes: 2" in content
    assert report_news_budget.HEADER in content


def test_main_is_deterministic_across_reruns(tmp_path: Path):
    episodes_path = tmp_path / "episodes.parquet"
    ledger_path = tmp_path / "enrichment_spend.json"
    out_path = tmp_path / "PHASE3_BUDGET.md"
    _write_episodes(episodes_path, ["closed"])

    argv = [
        "--episodes-path", str(episodes_path),
        "--ledger-path", str(ledger_path),
        "--out", str(out_path),
    ]
    report_news_budget.main(argv)
    first = out_path.read_text()
    report_news_budget.main(argv)
    second = out_path.read_text()
    assert first == second
