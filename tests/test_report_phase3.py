"""Tests for scripts/report_news_budget.py (NEWS-07, success criterion 1, D-01) and
scripts/report_phase3.py (NEWS-07, NEWS-08, REV-02). No network; every number traces
back to core/config.py's SETTINGS, a hand-built episodes/ledger fixture, or committed
data read through core/storage.py.
"""
from __future__ import annotations

import copy
from pathlib import Path

import pandas as pd

from core.config import SETTINGS
from core.news.cost import estimate_backfill_usd
from core.news.overrides import Override
from core.storage import write_event_overrides, write_events, write_spend_ledger
from scripts import report_news_budget, report_phase3


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


# ---------------------------------------------------------------------------
# report_phase3: render_enrichment_report / render_episode_table / main
# ---------------------------------------------------------------------------


def _record(**overrides_) -> dict:
    base = {
        "episode_id": "2020-01-01_shock",
        "status": "explained",
        "headline": "Headline A",
        "summary": "s",
        "category": "other",
        "region": "US",
        "scheduled": False,
        "drivers": [],
        "sources": [
            {"title": "t", "url": "https://a.example", "publisher": "p", "published": "2020-01-01"}
        ],
        "confidence": 0.9,
        "conflicting_sources": False,
        "reviewed": False,
        "rejected": False,
        "provider": "claude",
        "model": "claude-haiku-5-5",
        "prompt_version": SETTINGS.news_prompt_version,
        "web_search_tool": SETTINGS.web_search_tool_type,
        "enriched_at": "2026-10-09T00:00:00Z",
        "search_from": "2019-12-30",
        "search_to": "2020-01-02",
        "usage": {"input_tokens": 100, "output_tokens": 50, "web_search_requests": 2},
        "cost_usd": 0.01,
        "stop_reasons": ["end_turn"],
        "dropped_sources": [{"url": "https://x.example", "reason": "outside_window"}],
        "raw_response": None,
    }
    base.update(overrides_)
    return base


def _three_records() -> list[dict]:
    record_a = _record()
    record_b = _record(
        episode_id="2020-02-01_gap",
        status="needs_review",
        headline="Headline B",
        confidence=0.3,
        sources=[],
        dropped_sources=[],
        usage={"input_tokens": 80, "output_tokens": 40, "web_search_requests": 1},
        cost_usd=0.02,
    )
    record_c = _record(
        episode_id="2020-03-01_drawdown",
        status="needs_review",
        headline="Headline C",
        confidence=0.4,
        category="geopolitics",
        region="Europe",
        scheduled=True,
        model="claude-sonnet-5-5",
        sources=[
            {
                "title": "t2", "url": "https://b.example", "publisher": "p2",
                "published": "2020-03-01",
            }
        ],
        dropped_sources=[{"url": "https://y.example", "reason": "no_page_age"}],
        stop_reasons=["pause_turn", "end_turn"],
        usage={"input_tokens": 120, "output_tokens": 60, "web_search_requests": 3},
        cost_usd=0.03,
    )
    return [record_a, record_b, record_c]


def _episodes() -> list[dict]:
    return [
        {"episode_id": "2020-01-01_shock", "status": "closed"},
        {"episode_id": "2020-02-01_gap", "status": "closed"},
        {"episode_id": "2020-03-01_drawdown", "status": "closed"},
        {"episode_id": "2020-04-01_rally", "status": "closed"},
    ]


def test_render_enrichment_report_coverage_and_missing_ids():
    report = report_phase3.render_enrichment_report(_episodes(), _three_records(), [], [], SETTINGS)
    assert "Closed episodes: 4" in report
    assert "Current records: 3" in report
    assert "2020-04-01_rally" in report


def test_render_enrichment_report_raw_vs_effective_status_after_override():
    override = Override(
        episode_id="2020-03-01_drawdown", action="accept", fields={},
        reviewed_at="2026-10-09T00:00:00Z",
    )
    report = report_phase3.render_enrichment_report(
        _episodes(), _three_records(), [override], [], SETTINGS
    )
    # raw: 1 explained, 2 needs_review
    # effective: 2020-03-01_drawdown's accept promotes it to explained (it has a source)
    assert "2020-02-01_gap" in report  # the still-unresolved needs_review id
    assert "Reviewed: 1" in report


def test_render_enrichment_report_tallies_and_search_usage():
    report = report_phase3.render_enrichment_report(_episodes(), _three_records(), [], [], SETTINGS)
    assert "outside_window" in report
    assert "no_page_age" in report
    assert "end_turn" in report
    assert "pause_turn" in report
    assert "claude-haiku-5-5" in report
    assert "claude-sonnet-5-5" in report
    # total searches 2+1+3=6, max 3
    assert "Total requests: 6" in report
    assert "Max per episode: 3" in report


def test_render_enrichment_report_spend_vs_budget():
    ledger = [{"run_id": "r1", "cost_usd": 1.0}]
    report = report_phase3.render_enrichment_report(_episodes(), _three_records(), [], ledger, SETTINGS)
    assert "1.00" in report
    assert f"{SETTINGS.news_budget_usd:.2f}" in report


def test_render_enrichment_report_leak_scan_passes_on_clean_input():
    report = report_phase3.render_enrichment_report(_episodes(), _three_records(), [], [], SETTINGS)
    assert "PASS" in report
    assert "FAIL" not in report


def test_render_enrichment_report_leak_scan_fails_on_leaked_pattern():
    leaked = copy.deepcopy(_three_records())
    leaked[0]["raw_response"] = [{"encrypted_content": "zzz"}]
    report = report_phase3.render_enrichment_report(_episodes(), leaked, [], [], SETTINGS)
    assert "FAIL" in report


def test_render_episode_table_rows_and_missing():
    table = report_phase3.render_episode_table(
        _three_records(), ["2020-01-01_shock", "2099-01-01_missing"]
    )
    assert "Headline A" in table
    assert "explained" in table
    assert "missing" in table


def test_main_stdout_prints_table_and_writes_no_file(tmp_path: Path):
    events_path = tmp_path / "events.json"
    overrides_path = tmp_path / "event_overrides.json"
    episodes_path = tmp_path / "episodes.parquet"
    ledger_path = tmp_path / "enrichment_spend.json"
    out_path = tmp_path / "PHASE3_ENRICHMENT.md"

    write_events(_three_records(), events_path)
    write_event_overrides([], overrides_path)
    write_spend_ledger([], ledger_path)
    pd.DataFrame(_episodes()).to_parquet(episodes_path, index=False)

    exit_code = report_phase3.main(
        [
            "--events-path", str(events_path),
            "--overrides-path", str(overrides_path),
            "--episodes-path", str(episodes_path),
            "--ledger-path", str(ledger_path),
            "--out", str(out_path),
            "--stdout",
            "--episode-ids", "2020-01-01_shock,2099-01-01_missing",
        ]
    )

    assert exit_code == 0
    assert not out_path.exists()


def test_main_default_writes_file(tmp_path: Path):
    events_path = tmp_path / "events.json"
    overrides_path = tmp_path / "event_overrides.json"
    episodes_path = tmp_path / "episodes.parquet"
    ledger_path = tmp_path / "enrichment_spend.json"
    out_path = tmp_path / "PHASE3_ENRICHMENT.md"

    write_events(_three_records(), events_path)
    write_event_overrides([], overrides_path)
    write_spend_ledger([], ledger_path)
    pd.DataFrame(_episodes()).to_parquet(episodes_path, index=False)

    exit_code = report_phase3.main(
        [
            "--events-path", str(events_path),
            "--overrides-path", str(overrides_path),
            "--episodes-path", str(episodes_path),
            "--ledger-path", str(ledger_path),
            "--out", str(out_path),
        ]
    )

    assert exit_code == 0
    assert out_path.exists()
    assert report_phase3.HEADER in out_path.read_text()


def test_main_with_no_events_file_reports_zero_records(tmp_path: Path):
    events_path = tmp_path / "events.json"  # never written
    overrides_path = tmp_path / "event_overrides.json"
    episodes_path = tmp_path / "episodes.parquet"
    ledger_path = tmp_path / "enrichment_spend.json"
    out_path = tmp_path / "PHASE3_ENRICHMENT.md"

    pd.DataFrame(_episodes()).to_parquet(episodes_path, index=False)

    exit_code = report_phase3.main(
        [
            "--events-path", str(events_path),
            "--overrides-path", str(overrides_path),
            "--episodes-path", str(episodes_path),
            "--ledger-path", str(ledger_path),
            "--out", str(out_path),
            "--stdout",
        ]
    )

    assert exit_code == 0
