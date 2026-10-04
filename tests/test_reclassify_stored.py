"""S2 regression — the stored rows (C4's evidence) yield no boilerplate-rescued positive."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "scout.db"
sys.path.insert(0, str(ROOT / "scripts"))


@pytest.mark.skipif(not DB.exists(), reason="no committed scout.db")
def test_no_stored_row_is_positive_on_an_elsewhere_location(monkeypatch):
    from reclassify_stored import names_only_elsewhere, reclassify

    monkeypatch.chdir(ROOT)
    results, _ = reclassify(str(DB))
    assert results
    assert [r for r in results if r["bad"]] == []
    # the oracle itself: a named-elsewhere location fails, "Remote" and EMEA do not
    assert names_only_elsewhere("Bangalore, India") and names_only_elsewhere("Remote, France")
    assert not names_only_elsewhere("Remote") and not names_only_elsewhere("Remote, EMEA")
    assert names_only_elsewhere("Remote, South Africa") and names_only_elsewhere("Remote - Anywhere in the US")


def test_body_residency_oracle():
    from reclassify_stored import body_requires_elsewhere

    assert body_requires_elsewhere("we do require successful candidates to be located in the United States")
    assert not body_requires_elsewhere("Come build with us. Teammates are located in Africa.")
