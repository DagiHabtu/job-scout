"""S5 independent-review findings, each as a test (spec §11: finding → test → fix or refute)."""

from __future__ import annotations

from datetime import datetime

import pytest

from job_scout.config import AppConfig
from job_scout.models import Eligibility, EligibilityCategory as EC, EmploymentType as ET
from job_scout.models import Lifecycle, Opportunity, Relevance
from job_scout.notify import UNKNOWN_INTERN_CAP, gate_reason, gate_reasons
from job_scout.score import role_family_ok


# H1 — vetoes must not reject real technical internships …
@pytest.mark.parametrize("title", [
    "Software Engineer Intern, Customer Platform",
    "Social Computing Research Intern",
    "AI Research Intern - Social Impact",
    "Package Manager Engineer Intern",
])
def test_h1_technical_titles_with_veto_words_pass(title):
    assert role_family_ok(title)


# … and non-software engineer/analyst/research titles must not pass.
@pytest.mark.parametrize("title", [
    "Financial Analyst Intern", "Business Analyst Intern", "Operations Analyst Intern",
    "Mechanical Engineering Intern", "Civil Engineer Intern", "Chemical Engineering Intern",
    "Policy Research Intern", "Research Assistant (Psychology)", "Data Center Technician Intern",
    "Mac Users Needed for AI Security Research | $25 USD | Work From Home",
])
def test_h1_non_software_titles_fail(title):
    assert not role_family_ok(title)


def _o(title="Software Engineer Intern", etype=ET.INTERNSHIP, cat=EC.UNKNOWN, status=Lifecycle.NEW,
       score=0.5, sim=0.5, elig=True):
    o = Opportunity(title=title, company="C", apply_url=f"https://x/{title}", canonical_url=f"https://x/{title}",
                    employment_type=etype, status=status)
    o.eligibility = Eligibility(cat, 0.8, ["ev"]) if elig else None
    o.relevance = Relevance(score=score, semantic_similarity=sim)
    return o


# M3 — the unknown-internship cap keeps the best TITLE matches, not the highest nudged scores
def test_m3_cap_keeps_highest_title_similarity():
    opps = [_o(title=f"Software Engineer Intern {i}", score=0.9 - i * 0.01, sim=0.1) for i in range(UNKNOWN_INTERN_CAP)]
    best = _o(title="Data Engineer Intern", score=0.2, sim=0.95)          # lowest score, best title
    rs = gate_reasons([*opps, best], 0.4)
    assert rs[-1] is None and rs.count("unknown_cap") == 1


# L3 — gate table gaps
def test_l3_missing_eligibility_is_unknown():
    assert gate_reason(_o(elig=False), 0.4) is None                    # UNKNOWN intern → check eligibility
    assert gate_reason(_o(etype=ET.NEW_GRAD, title="Junior Data Engineer", elig=False), 0.4) == "eligibility_unknown"


def test_l3_new_grad_role_family():
    assert gate_reason(_o(etype=ET.NEW_GRAD, title="Junior Account Executive", cat=EC.WORLDWIDE_REMOTE), 0.4) == "role_family"


def test_l3_stipend_negative():
    assert gate_reason(_o(etype=ET.STIPEND_PROGRAM, title="Prog", cat=EC.REMOTE_EXCLUDES_USER), 0.4) == "eligibility_negative"


def test_l3_known_unknown_intern_does_not_use_a_cap_slot():
    old = [_o(title=f"Old Intern {i}", status=Lifecycle.ACTIVE) for i in range(UNKNOWN_INTERN_CAP)]
    fresh = [_o(title=f"Software Engineer Intern {i}") for i in range(UNKNOWN_INTERN_CAP)]
    rs = gate_reasons([*old, *fresh], 0.4)
    assert rs.count("not_new") == UNKNOWN_INTERN_CAP and rs.count(None) == UNKNOWN_INTERN_CAP


def test_l3_pipeline_exercises_target_class_unknown_and_cap_codes(tmp_path):
    from job_scout.pipeline import run_once

    from fixtures.gate0 import FakeSource

    cfg = AppConfig()
    cfg.db_path = str(tmp_path / "scout.db")
    cfg.notify.digest_path = str(tmp_path / "digest.html")
    cfg.profile.employment_types = [ET.INTERNSHIP, ET.STIPEND_PROGRAM, ET.NEW_GRAD]

    def gh(i, title, loc="Remote"):
        return Opportunity(title=title, company="Globex", apply_url=f"https://gh/{i}", canonical_url="",
                           ats_provider="greenhouse", ats_job_id=str(i), location_raw=loc, description="We build tools.")
    # "QA Automation" → "Cloud": a QA title now goes to its own section, never a Check-eligibility slot (final review M3)
    roles = ["Software Engineer", "Data Engineer", "Machine Learning", "Platform", "Security", "Cloud"]
    opps = [gh(i, f"{r} Intern") for i, r in enumerate(roles[: UNKNOWN_INTERN_CAP + 1])]   # distinct: no fuzzy merge
    opps += [gh(90, "Backend Engineer"), gh(91, "Junior Data Engineer")]
    s = run_once(cfg, [FakeSource("mix", opps)])
    assert s.gate == {"unknown_cap": 1, "not_target_class": 1, "eligibility_unknown": 1}
    assert s.notified == UNKNOWN_INTERN_CAP
    merged = s.discovered - s.after_dedupe
    assert s.discovered - merged - sum(s.rejects.values()) - sum(s.gate.values()) == s.notified
