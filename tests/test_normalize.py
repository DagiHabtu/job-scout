"""Normalization — tracking-strip, honest remote inference, fingerprint, discovered_date stamp."""

from __future__ import annotations

from datetime import datetime, timezone

from job_scout.models import Opportunity, RemoteStatus
from job_scout.normalize import infer_remote_status, normalize, strip_tracking


def _opp(**kw) -> Opportunity:
    base = dict(title="Backend Intern", company="Globex", apply_url="https://x/1", canonical_url="")
    base.update(kw)
    return Opportunity(**base)


def test_strip_tracking_removes_utm_but_keeps_meaningful_query():
    url = "https://jobs.example.com/apply?gh_jid=42&utm_source=news&utm_campaign=x&ref=twitter"
    out = strip_tracking(url)
    assert "gh_jid=42" in out            # a real job token is preserved
    assert "utm_" not in out and "ref=" not in out


def test_strip_tracking_is_stable_when_nothing_to_strip():
    url = "https://jobs.example.com/apply?gh_jid=42"
    assert strip_tracking(url) == url


def test_infer_remote_status_respects_explicit_value():
    # A source that already asserted a status is trusted; inference does not override it.
    assert infer_remote_status(_opp(remote_status=RemoteStatus.ONSITE, description="work from home")) == RemoteStatus.ONSITE


def test_infer_remote_status_from_text():
    assert infer_remote_status(_opp(description="This is a hybrid role.")) == RemoteStatus.HYBRID
    assert infer_remote_status(_opp(description="Fully remote, work from home.")) == RemoteStatus.REMOTE
    assert infer_remote_status(_opp(description="Strictly on-site in our office.")) == RemoteStatus.ONSITE


def test_infer_remote_status_stays_unknown_without_signal():
    assert infer_remote_status(_opp(description="Great team, great mission.")) == RemoteStatus.UNKNOWN


def test_normalize_sets_canonical_url_and_fingerprint_and_date():
    opp = _opp(apply_url="https://x/apply?utm_source=a", location_raw="Remote - EMEA")
    before = datetime.now(timezone.utc)
    out = normalize(opp)
    assert out.canonical_url == "https://x/apply"
    assert out.content_fingerprint  # non-empty, deterministic
    assert out.remote_status == RemoteStatus.REMOTE
    assert out.discovered_date is not None and out.discovered_date >= before


def test_normalize_does_not_overwrite_existing_discovered_date():
    stamped = datetime(2020, 1, 1, tzinfo=timezone.utc)
    out = normalize(_opp(discovered_date=stamped))
    assert out.discovered_date == stamped
