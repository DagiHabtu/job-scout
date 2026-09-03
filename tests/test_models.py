"""Tests for the frozen spine's value semantics — fingerprint identity and disqualifier logic."""

from __future__ import annotations

from job_scout.models import (
    DISQUALIFYING_ELIGIBILITY,
    Eligibility,
    EligibilityCategory,
    content_fingerprint,
)


def test_fingerprint_is_stable_across_cosmetic_differences():
    # Same role, differently punctuated/cased/spaced → same fingerprint (that is the whole point).
    a = content_fingerprint("Stripe, Inc.", "Software Engineer  Intern", "Remote - EMEA")
    b = content_fingerprint("stripe inc", "software engineer intern", "remote  emea")
    assert a == b


def test_fingerprint_distinguishes_real_differences():
    base = content_fingerprint("Globex", "Data Engineer Intern", "Remote - EMEA")
    assert base != content_fingerprint("Globex", "Data Engineer Intern", "Remote - US")
    assert base != content_fingerprint("Initech", "Data Engineer Intern", "Remote - EMEA")
    assert base != content_fingerprint("Globex", "Backend Intern", "Remote - EMEA")


def test_fingerprint_handles_missing_location():
    assert content_fingerprint("Globex", "Intern", None) == content_fingerprint("Globex", "Intern", "")


def test_confident_disqualifier_respects_threshold_and_category():
    hi = Eligibility(EligibilityCategory.REQUIRES_WORK_AUTH, 0.85)
    assert hi.is_confident_disqualifier(0.75) is True
    # Same disqualifying category but low confidence → NOT a hard fail (surface the uncertainty).
    lo = Eligibility(EligibilityCategory.REQUIRES_WORK_AUTH, 0.5)
    assert lo.is_confident_disqualifier(0.75) is False
    # A positive category at high confidence is never a disqualifier.
    good = Eligibility(EligibilityCategory.WORLDWIDE_REMOTE, 0.99)
    assert good.is_confident_disqualifier(0.75) is False


def test_disqualifying_set_is_exactly_the_three_negatives():
    assert DISQUALIFYING_ELIGIBILITY == frozenset(
        {
            EligibilityCategory.REQUIRES_WORK_AUTH,
            EligibilityCategory.REMOTE_EXCLUDES_USER,
            EligibilityCategory.ONSITE_FOREIGN,
        }
    )
    # UNKNOWN must never be disqualifying — that would silently drop uncertain postings.
    assert EligibilityCategory.UNKNOWN not in DISQUALIFYING_ELIGIBILITY
