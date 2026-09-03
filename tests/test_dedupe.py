"""Within-run dedupe — the three tiers, company blocking, and the merge-propagation regression.

The regression test (richer SECOND occurrence wins, provenance unioned) is the executable proof of
the REWORK flagged in STATE: the previous merge dropped a richer second occurrence's content and
its provenance from the output.
"""

from __future__ import annotations

from datetime import datetime, timezone

from job_scout.dedupe import dedupe
from job_scout.models import Opportunity, Provenance

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _opp(source, url, *, title, company, location="Remote - EMEA", description="", provider=None, job_id=None):
    return Opportunity(
        title=title,
        company=company,
        apply_url=url,
        canonical_url=url,
        location_raw=location,
        description=description,
        ats_provider=provider,
        ats_job_id=job_id,
        provenance=[Provenance(source=source, url=url, first_seen=NOW)],
    )


def _sources(opp) -> set[str]:
    return {p.source for p in opp.provenance}


def test_richer_second_occurrence_wins_with_unioned_provenance():
    thin = _opp("greenhouse", "https://gh/1", title="Data Engineer Intern", company="Globex", description="Short.")
    rich = _opp("lever", "https://lever/2", title="Data Engineer Intern", company="Globex",
                description="A much longer, richer description of the Data Engineer Intern role at Globex.")
    out = dedupe([thin, rich])   # greenhouse first, richer lever second
    assert len(out) == 1
    assert out[0].description == rich.description          # richer content won
    assert _sources(out[0]) == {"greenhouse", "lever"}     # no provenance lost


def test_richer_first_occurrence_also_keeps_both_provenance():
    rich = _opp("lever", "https://lever/2", title="Data Engineer Intern", company="Globex",
                description="A much longer, richer description of the role.")
    thin = _opp("greenhouse", "https://gh/1", title="Data Engineer Intern", company="Globex", description="Short.")
    out = dedupe([rich, thin])   # richer first this time
    assert len(out) == 1
    assert out[0].description == rich.description
    assert _sources(out[0]) == {"greenhouse", "lever"}


def test_tier1_exact_ats_identity_merges():
    a = _opp("greenhouse", "https://gh/a", title="Backend Intern", company="Globex",
             provider="greenhouse", job_id="42", description="short")
    b = _opp("aggregator", "https://agg/b", title="Backend Intern", company="Globex",
             provider="greenhouse", job_id="42", description="a richer aggregator copy of the same posting")
    out = dedupe([a, b])
    assert len(out) == 1
    assert _sources(out[0]) == {"greenhouse", "aggregator"}


def test_tier3_fuzzy_title_merges_within_company():
    a = _opp("greenhouse", "https://gh/a", title="Backend Engineer Intern", company="Globex")
    b = _opp("lever", "https://lever/b", title="Backend Engineer Interns", company="Globex")  # near-identical
    out = dedupe([a, b])
    assert len(out) == 1
    assert _sources(out[0]) == {"greenhouse", "lever"}


def test_blocking_by_company_prevents_cross_employer_merge():
    a = _opp("greenhouse", "https://gh/a", title="Backend Engineer Intern", company="Globex")
    b = _opp("lever", "https://lever/b", title="Backend Engineer Intern", company="Initech")
    out = dedupe([a, b])                 # identical title, different employers → never merged
    assert len(out) == 2


def test_distinct_roles_are_not_merged():
    a = _opp("greenhouse", "https://gh/a", title="Backend Engineer Intern", company="Globex")
    b = _opp("greenhouse", "https://gh/b", title="Frontend Designer", company="Globex")
    assert len(dedupe([a, b])) == 2
