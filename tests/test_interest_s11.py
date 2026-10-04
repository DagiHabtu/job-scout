"""S11 — interest: taste in the profile, sections in the issue (spec §12). Written before the code.

Includes the §12 acceptance: the 9 records delivered on 2026-10-04 (tests/fixtures/first_run_2026-10-04.json,
copied from data/scout.db with Dagi's labels) each land in the section Dagi confirmed. Fitted to these nine
items — a regression guard, not a measure of generalisation.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from job_scout.config import AppConfig, ScoringConfig, UserProfile
from job_scout.models import Eligibility, EligibilityCategory as EC, EmploymentType as ET, Lifecycle, Opportunity, RemoteStatus
from job_scout.notify import gate_reasons, render_issue_md, section_of
from job_scout.score import interest_veto, role_family_ok, score_opportunity

from fixtures.gate0 import FakeSource

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "first_run_2026-10-04.json").read_text(encoding="utf-8"))
PROFILE = AppConfig.load(ROOT / "config" / "profile.yaml").profile
APPLY, CHECK, ASPIRATIONAL, OUTSIDE = "Apply", "Check eligibility", "Aspirational", "Eligible, outside your stated interests"


# --- profile ------------------------------------------------------------------------------------- #
def test_profile_interests_and_alias():
    assert "Linux, kernel or open source engineering" in PROFILE.interests
    assert {"qa", "crm", "salesforce"} <= set(PROFILE.not_interested)
    assert "kernel" in PROFILE.strong_interest_terms
    assert UserProfile(target_roles=["backend intern"]).interests == ["backend intern"]   # alias still loads


# --- role family no longer encodes taste ------------------------------------------------------------ #
def test_qa_removed_from_role_family():
    assert not role_family_ok("QA Tester")
    assert role_family_ok("QA Automation Engineer")          # "engineer" is a family word


# --- interest_veto ---------------------------------------------------------------------------------- #
@pytest.mark.parametrize("title,veto,note", [
    ("QA/QC Intern", "qa", None),
    ("CRM Developer", "crm", None),
    ("Salesforce Developer Intern", "salesforce", None),
    ("QA Automation Engineer, Linux Kernel", None, "matches 'qa' but also 'linux'"),
    ("Software Engineer Intern", None, None),
    ("Quality Assurance Engineer Intern", "quality assurance", None),
    ("Aquatic Systems Intern", None, None),                  # word boundary: no "qa" inside a word
])
def test_interest_veto(title, veto, note):
    o = Opportunity(title=title, company="X", apply_url="u", canonical_url="u")
    v, n = interest_veto(o, PROFILE)
    assert v == veto and n == note


# --- gate and sections -------------------------------------------------------------------------------- #
def _scored(title, etype=ET.INTERNSHIP, cat=EC.WORLDWIDE_REMOTE, body=""):
    o = Opportunity(title=title, company="X", apply_url=f"https://x/{title}", canonical_url=f"https://x/{title}",
                    description=body, employment_type=etype, status=Lifecycle.NEW)
    o.eligibility = Eligibility(cat, 0.85, ["worldwide"])
    o.relevance = score_opportunity(o, PROFILE, ScoringConfig())
    return o


def test_outside_interests_selected_and_capped_at_five():
    # software-QA body: a bare QA title is role_family now (final review M2 — family checked before the veto)
    opps = [_scored(f"QA Intern {i}", body="Test our web app and report bugs.") for i in range(6)]
    r = gate_reasons(opps, 0.4)
    assert r.count(None) == 5 and r.count("interest:cap") == 1
    assert section_of(opps[0]) == OUTSIDE


def test_non_technical_title_still_rejected_even_if_vetoed_by_interest():
    assert gate_reasons([_scored("Salesforce Account Executive Intern")], 0.4) == ["role_family"]


def test_outside_interests_rendered_as_title_and_link_only():
    o = _scored("QA/QC Intern")
    md = render_issue_md([o], AppConfig())
    block = md[md.index(f"## {OUTSIDE}"):]
    item_lines = [l for l in block.splitlines() if l.startswith("- [ ]")]
    assert item_lines == [f"- [ ] [QA/QC Intern]({o.canonical_url})"]
    assert "eligibility:" not in block and "stage:" not in block


def test_sections_order_and_empty_sections_omitted():
    opps = [_scored("QA/QC Intern"), _scored("Software Engineer Intern"),
            _scored("Backend Intern", cat=EC.UNKNOWN)]
    md = render_issue_md(opps, AppConfig())
    heads = re.findall(r"^## (.+)$", md, re.M)
    assert heads == [APPLY, CHECK, OUTSIDE]


def test_apply_ordered_by_relevance_score():
    a, b = _scored("Software Engineer Intern"), _scored("Research Intern")
    a.relevance.score, b.relevance.score = 0.5, 0.9
    md = render_issue_md([a, b], AppConfig())
    assert md.index("Research Intern") < md.index("Software Engineer Intern")


def test_strong_term_note_rendered_in_apply():
    o = _scored("QA Automation Engineer, Linux Kernel")
    md = render_issue_md([o], AppConfig())
    assert section_of(o) == APPLY and "matches 'qa' but also 'linux'" in md


# --- §12 acceptance: the nine delivered records + synthetic cases, through the pipeline ---------------- #
def _fresh(d: dict) -> Opportunity:
    return Opportunity(
        title=d["title"], company=d["company"], apply_url=d["apply_url"], canonical_url="",
        ats_provider=d.get("ats_provider"), ats_job_id=d.get("ats_job_id"), location_raw=d.get("location_raw"),
        remote_status=RemoteStatus(d.get("remote_status", "unknown")),
        employment_type=ET(d.get("employment_type", "unknown")) if d.get("ats_provider") == "himalayas" else ET.UNKNOWN,
        description=d.get("description", ""),
    )


def _synthetic(title, etype):
    return Opportunity(title=title, company="Synth", apply_url=f"https://synth/{title}", canonical_url="",
                       ats_provider="himalayas", ats_job_id=f"https://himalayas.app/synth/{title}",
                       location_raw="Worldwide", remote_status=RemoteStatus.REMOTE, employment_type=etype,
                       description="Build things with a friendly team.")


def _sections(md: str) -> dict[str, str]:
    out, current = {}, None
    for line in md.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
        m = re.match(r"- \[ \] \[(.+?)\]\(", line)
        if m:
            out[m.group(1)] = current
    return out


def test_first_run_regression(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from job_scout.pipeline import run_once

    cfg = AppConfig.load(ROOT / "config" / "profile.yaml")
    cfg.db_path = str(tmp_path / "s.db")
    cfg.notify.digest_path = str(tmp_path / "data" / "digest.html")
    opps = [_fresh(r["record"]) for r in FIXTURE["records"]]
    opps += [_synthetic("Junior Backend Engineer", ET.NEW_GRAD), _synthetic("Frontend Engineer Intern", ET.INTERNSHIP),
             _synthetic("QA Automation Engineer, Linux Kernel", ET.INTERNSHIP)]
    s = run_once(cfg, [FakeSource("fixture", opps)])
    md = (tmp_path / "data" / "notify.md").read_text(encoding="utf-8")
    got = _sections(md)
    for r in FIXTURE["records"]:
        title, expected = r["record"]["title"], r["expected"]
        if expected.startswith("not selected"):
            assert title not in got, title
        else:
            assert got.get(title) == expected, (title, got.get(title), expected)
    assert s.gate.get("stage:graduate_only") == 1
    assert got["Junior Backend Engineer"] == APPLY and got["Frontend Engineer Intern"] == APPLY
    assert got["QA Automation Engineer, Linux Kernel"] == APPLY
    assert "matches 'qa' but also 'linux'" in md
