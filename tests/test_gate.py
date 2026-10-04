"""S5 — deterministic notify gate, golden role-family set, and within-section ordering."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

import pytest

from job_scout.config import AppConfig
from job_scout.models import Eligibility, EligibilityCategory as EC, EmploymentType as ET
from job_scout.models import Lifecycle, Opportunity, Relevance
from job_scout.notify import UNKNOWN_INTERN_CAP, gate_reason, gate_reasons, render_issue_md
from job_scout.score import role_family_ok

GOLDEN = Path(__file__).parent / "fixtures" / "golden_titles.csv"


def _o(title="Software Engineer Intern", etype=ET.INTERNSHIP, cat=EC.WORLDWIDE_REMOTE, status=Lifecycle.NEW,
       notified=None, sim=0.5):
    o = Opportunity(title=title, company="C", apply_url=f"https://x/{title}", canonical_url=f"https://x/{title}",
                    employment_type=etype, status=status, notified_at=notified)
    o.eligibility = Eligibility(cat, 0.8, ["ev"])
    o.relevance = Relevance(score=sim, semantic_similarity=sim)
    return o


@pytest.mark.parametrize("opp,reason", [
    (_o(status=Lifecycle.ACTIVE), "not_new"),
    (_o(notified=datetime(2026, 1, 1)), "already_notified"),
    (_o(etype=ET.STIPEND_PROGRAM, cat=EC.STIPEND_PROGRAM_GLOBAL, title="Outreachy"), None),
    (_o(etype=ET.STIPEND_PROGRAM, cat=EC.UNKNOWN, title="Some Program"), None),        # never dropped for doubt
    (_o(etype=ET.UNKNOWN), "not_target_class"),
    (_o(etype=ET.FULL_TIME), "not_target_class"),
    (_o(title="Marketing Intern"), "role_family"),
    (_o(cat=EC.WORLDWIDE_REMOTE), None),
    (_o(cat=EC.REMOTE_REGION_INCLUDES_USER, etype=ET.NEW_GRAD, title="Junior Data Engineer"), None),
    (_o(cat=EC.UNKNOWN), None),                                                         # check-eligibility intern
    (_o(cat=EC.UNKNOWN, etype=ET.NEW_GRAD, title="Junior Data Engineer"), "eligibility_unknown"),
    (_o(cat=EC.REMOTE_EXCLUDES_USER), "eligibility_negative"),
])
def test_gate_table(opp, reason):
    assert gate_reason(opp, threshold=0.99) == reason        # threshold is not consulted


def test_threshold_is_not_consulted():
    o = _o(sim=0.01)
    assert gate_reason(o, 0.0) == gate_reason(o, 1.0) is None


def test_unknown_internship_cap():
    opps = [_o(title=f"Software Engineer Intern {i}", cat=EC.UNKNOWN) for i in range(UNKNOWN_INTERN_CAP + 2)]
    opps.append(_o(title="Data Engineer Intern", cat=EC.WORLDWIDE_REMOTE))           # not counted in the cap
    opps.append(_o(etype=ET.STIPEND_PROGRAM, cat=EC.UNKNOWN, title="Program"))        # outside the cap
    rs = gate_reasons(opps, 0.4)
    assert rs.count("unknown_cap") == 2
    assert rs[-1] is None and rs[-2] is None


def test_issue_sections_order():
    # §12 S11: "Apply" is ordered by relevance score; other sections keep title similarity (S5 review M2).
    # Score and similarity disagree, so each section's sort key is pinned.
    low = _o(title="Data Engineer Intern", sim=0.3)
    low.relevance.score = 0.9
    high = _o(title="Software Engineer Intern", sim=0.7)
    high.relevance.score = 0.1
    d1 = _o(title="Backend Intern", cat=EC.UNKNOWN, sim=0.9)
    d1.relevance.score = 0.1
    d2 = _o(title="Platform Intern", cat=EC.UNKNOWN, sim=0.2)
    d2.relevance.score = 0.9
    md = render_issue_md([low, d2, d1, high], AppConfig())
    assert md.index("Data Engineer Intern") < md.index("Software Engineer Intern") < md.index("Check eligibility")
    assert md.index("Check eligibility") < md.index("Backend Intern") < md.index("Platform Intern")


def test_role_family_golden_precision_and_recall():
    rows = list(csv.DictReader(GOLDEN.open(encoding="utf-8")))
    assert len(rows) >= 60
    tp = sum(role_family_ok(r["title"]) and r["label"] == "1" for r in rows)
    fp = sum(role_family_ok(r["title"]) and r["label"] == "0" for r in rows)
    fn = sum((not role_family_ok(r["title"])) and r["label"] == "1" for r in rows)
    assert tp / (tp + fp) >= 0.9
    assert tp / (tp + fn) >= 0.8


def test_integration_mix_selects_only_emea_intern_and_program(tmp_path, monkeypatch):
    """§7: EMEA intern, US intern with the same title, a senior role, a sales intern, and a stipend
    program → exactly the EMEA intern and the program are selected."""
    import job_scout.sources.known_programs as kp
    from job_scout.pipeline import run_once

    from fixtures.gate0 import FakeSource

    monkeypatch.setattr(kp, "geo_verdict", lambda job_id, country: "eligible")
    cfg = AppConfig()
    cfg.db_path = str(tmp_path / "scout.db")
    cfg.notify.digest_path = str(tmp_path / "digest.html")
    cfg.profile.employment_types = [ET.INTERNSHIP, ET.STIPEND_PROGRAM, ET.NEW_GRAD]

    def gh(i, title, loc):
        return Opportunity(title=title, company="Globex", apply_url=f"https://gh/{i}", canonical_url="",
                           ats_provider="greenhouse", ats_job_id=str(i), location_raw=loc,
                           description="Python services." + (" Longer US copy." * 5 if "United" in loc else ""))
    program = Opportunity(title="Outreachy — applications open", company="Outreachy", apply_url="https://o/",
                          canonical_url="", ats_provider="known_programs", ats_job_id="o@open",
                          employment_type=ET.STIPEND_PROGRAM)
    src = FakeSource("mix", [
        gh(1, "Software Engineer Intern", "Remote, United States"),
        gh(2, "Software Engineer Intern", "Remote, EMEA"),
        gh(3, "Senior Backend Engineer", "Remote, EMEA"),
        gh(4, "Sales Intern", "Remote, EMEA"),
        program,
    ])
    s = run_once(cfg, [src])
    picked = {(o.title, o.location_raw) for o in s.ranked if o.notified_at is not None}
    assert picked == {("Software Engineer Intern", "Remote, EMEA"), ("Outreachy — applications open", None)}
    assert s.rejects == {"eligibility:remote_excludes_user": 1, "seniority_title:senior": 1}
    assert s.gate == {"role_family": 1}
    merged = s.discovered - s.after_dedupe
    assert s.discovered - merged - sum(s.rejects.values()) - sum(s.gate.values()) == s.notified == 2
