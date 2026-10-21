"""Iteration 3 §4.7 — small fixes. Written before the code."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from job_scout.config import UserProfile
from job_scout.models import EmploymentType as ET, Opportunity
from job_scout.score import stage_fit
from job_scout.sources.himalayas import _employment

ROOT = Path(__file__).resolve().parents[1]
_FX = json.loads((ROOT / "tests" / "fixtures" / "labels_2026-10-21_records.json").read_text(encoding="utf-8"))
REC = {r["label_id"]: r["record"] for r in _FX["records"]}


@pytest.mark.parametrize("label", ["ewor-dev", "ewor-cmo"])
def test_ewor_cofounder_titles_are_not_internships(label):
    assert _employment({"employmentType": "Intern", "title": REC[label]["title"]}) != ET.INTERNSHIP


def test_intern_still_internship():
    assert _employment({"employmentType": "Intern", "title": "Software Engineer Intern"}) == ET.INTERNSHIP


def test_company_age_is_not_an_experience_requirement():
    # Mimidentalclinic (heartbeat): a wrong stage:experience on company age
    o = Opportunity(title="Junior Software Engineer", company="Mimidentalclinic", apply_url="u", canonical_url="u",
                    employment_type=ET.NEW_GRAD, description="Stage: Established, 20+ years operational. Build our app.")
    assert stage_fit(o, UserProfile())[0] != "experience_required"
