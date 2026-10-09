"""Static text checks on .github/workflows/backfill.yml (D-04/OPS-03, T-03-16/T-03-17)
and .github/workflows/nightly.yml. Reads the YAML as plain text -- no pyyaml dependency
-- since every assertion here is about textual shape (trigger keywords, where a secret
or an input is referenced), not full YAML semantics.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKFILL = (ROOT / ".github" / "workflows" / "backfill.yml").read_text()
NIGHTLY = (ROOT / ".github" / "workflows" / "nightly.yml").read_text()


def test_workflow_dispatch_only_no_schedule():
    assert "workflow_dispatch" in BACKFILL
    assert "schedule" not in BACKFILL


def test_secret_referenced_exactly_once_in_env_mapping():
    assert BACKFILL.count("secrets.ANTHROPIC_API_KEY") == 1
    lines_with_secret = [
        line for line in BACKFILL.splitlines() if "secrets.ANTHROPIC_API_KEY" in line
    ]
    assert len(lines_with_secret) == 1
    assert re.match(r"^\s+ANTHROPIC_API_KEY:\s", lines_with_secret[0])


def test_every_inputs_reference_is_in_an_env_mapping_line():
    lines_with_inputs = [line for line in BACKFILL.splitlines() if "${{ inputs." in line]
    assert lines_with_inputs, "expected at least one ${{ inputs. reference"
    for line in lines_with_inputs:
        assert re.match(r"^\s+[A-Z_]+:\s\$\{\{ inputs\.", line), (
            f"inputs reference outside an env mapping line: {line!r}"
        )


def test_calls_enrich_events_with_claude_provider():
    assert "jobs.enrich_events" in BACKFILL
    assert "--provider claude" in BACKFILL


def test_commits_both_data_files():
    assert "data/events.json" in BACKFILL
    assert "data/enrichment_spend.json" in BACKFILL


def test_commit_step_runs_even_after_a_failed_enrich_step():
    assert "!cancelled()" in BACKFILL


def test_no_debug_tracing_or_env_dumps():
    assert "set -x" not in BACKFILL
    assert "printenv" not in BACKFILL
    assert "env |" not in BACKFILL


def test_nightly_workflow_has_no_key_and_no_enrich_events():
    assert "ANTHROPIC_API_KEY" not in NIGHTLY
    assert "enrich_events" not in NIGHTLY
