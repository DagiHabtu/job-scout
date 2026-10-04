"""S1 — delivery by GitHub Issue: the Markdown body, its sections, and the notify.md lifecycle."""

from __future__ import annotations

from pathlib import Path

from job_scout.cli import write_heartbeat
from job_scout.config import AppConfig
from job_scout.models import Eligibility, EligibilityCategory, EmploymentType, Opportunity, Relevance
from job_scout.notify import render_heartbeat_md, render_issue_md
from job_scout.pipeline import run_once

from fixtures.gate0 import FakeSource, gate0_sources


def _cfg(tmp_path) -> AppConfig:
    cfg = AppConfig()
    cfg.db_path = str(tmp_path / "scout.db")
    cfg.notify.digest_path = str(tmp_path / "digest.html")
    return cfg


def _opp(title, cat, provider=None, job_id=None):
    o = Opportunity(title=title, company="Co", apply_url=f"https://x/{title}", canonical_url=f"https://x/{title}",
                    location_raw="Remote", employment_type=EmploymentType.INTERNSHIP,
                    ats_provider=provider, ats_job_id=job_id)
    o.eligibility = Eligibility(cat, 0.85, [f"evidence for {title}"])
    o.relevance = Relevance(score=0.5, matched_signals=["tech: python"])
    return o


def test_issue_md_sections_links_and_attribution():
    good = _opp("Good Intern", EligibilityCategory.WORLDWIDE_REMOTE, "himalayas", "https://himalayas.app/companies/co/jobs/good")
    doubt = _opp("Doubt Intern", EligibilityCategory.UNKNOWN)
    md = render_issue_md([doubt, good], AppConfig())
    # "Actionable" renamed "Apply" (§12 S11)
    assert md.index("## Apply") < md.index("Good Intern") < md.index("## Check eligibility") < md.index("Doubt Intern")
    assert "- [ ] [Good Intern](https://x/Good Intern) — Co · internship · Remote" in md
    assert "eligibility: **worldwide_remote** (confidence 0.85)" in md
    assert "evidence for Good Intern" in md and "matched: tech: python" in md
    assert "via [Himalayas](https://himalayas.app/companies/co/jobs/good)" in md
    assert md.count("via [Himalayas]") == 1                      # only the Himalayas item


def test_notify_md_written_when_selected_and_removed_when_not(tmp_path):
    cfg = _cfg(tmp_path)
    s1 = run_once(cfg, gate0_sources())
    notify = Path(tmp_path) / "notify.md"
    assert s1.notified >= 1 and notify.exists()
    assert notify.read_text(encoding="utf-8").count("- [ ] ") == s1.notified
    s2 = run_once(cfg, gate0_sources())                          # nothing new → no stale body left
    assert s2.notified == 0 and not notify.exists()


def test_notify_md_absent_on_an_empty_run(tmp_path):
    run_once(_cfg(tmp_path), [FakeSource("empty", [])])
    assert not (Path(tmp_path) / "notify.md").exists()


def test_heartbeat_aggregates_runs(tmp_path):
    cfg = _cfg(tmp_path)
    s1 = run_once(cfg, gate0_sources())
    run_once(cfg, gate0_sources())
    md = Path(write_heartbeat(cfg)).read_text(encoding="utf-8")
    assert "2 run(s)" in md
    assert "eligibility:requires_work_auth | 2" in md            # summed over both runs
    assert "Near misses" in md
    assert "MLH Fellowship: no_published_round" in md             # S6 programs maintenance lines
    assert "has not run" in render_heartbeat_md([])
    assert s1.run_id                                             # sanity
