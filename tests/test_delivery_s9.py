"""S9 — delivery that does not depend on watch settings: assignee + `cc @owner` (spec §12)."""

from __future__ import annotations

from pathlib import Path

import yaml

from job_scout.config import AppConfig
from job_scout.models import Eligibility, EligibilityCategory, Opportunity
from job_scout.notify import render_heartbeat_md, render_issue_md

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "scout.yml"


def _opp():
    o = Opportunity(title="Software Engineer Intern", company="X", apply_url="https://x/1", canonical_url="https://x/1")
    o.eligibility = Eligibility(EligibilityCategory.WORLDWIDE_REMOTE, 0.85, ["worldwide"])
    return o


def test_issue_and_heartbeat_end_with_cc_owner(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY_OWNER", "DagiHabtu")
    assert render_issue_md([_opp()], AppConfig()).rstrip().endswith("cc @DagiHabtu")
    assert render_heartbeat_md([]).rstrip().endswith("cc @DagiHabtu")


def test_no_cc_line_when_owner_unset(monkeypatch):
    monkeypatch.delenv("GITHUB_REPOSITORY_OWNER", raising=False)
    assert "cc @" not in render_issue_md([_opp()], AppConfig())
    assert "cc @" not in render_heartbeat_md([])


def test_workflow_assigns_owner_on_every_issue_and_seed_mentions_owner():
    text = WORKFLOW.read_text(encoding="utf-8")
    yaml.safe_load(text)
    steps = {s["name"]: s.get("run", "") for s in yaml.safe_load(text)["jobs"]["scout"]["steps"] if "name" in s}
    creates = [r for r in steps.values() if "gh issue create" in r]
    assert len(creates) == 2
    assert all('--assignee "${{ github.repository_owner }}"' in r for r in creates)
    assert "cc @%s" in steps["Seed delivery test item"]
