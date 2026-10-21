"""Iteration 3 §4.3 — role family without bare data/analyst/analytics. Written before the code."""

from __future__ import annotations

import pytest

from job_scout.score import role_family_ok


@pytest.mark.parametrize("title,ok", [
    # Dagi skipped these (Appendix A: xp-video, c1-ta, banco, xp-da)
    ("Video Data Collector (Smartphone)", False),
    ("Teaching Assistant: Supply Chain Analyst", False),
    ("Antifraud Analyst Junior", False),
    ("Data Analyst - Remote, Contact", False),
    # still technical
    ("Data Scientist Intern", True),
    ("Junior Data Engineer", True),
    ("Data Engineering Intern", True),
    ("Data Platform Intern", True),
    ("Data Science Intern", True),
    ("Data Infrastructure Engineer, New Grad", True),
])
def test_role_family(title, ok):
    assert role_family_ok(title) is ok
