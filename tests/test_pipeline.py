"""GATE 0 — the vertical slice, green on fixtures, no network and no model.

FakeSource(s) → normalize → dedupe → classify_eligibility → hard_filter → score(lexical) → rank →
reconcile(temp DB) → digest. This single test IS the Gate-0 correctness target from STATE.md; the
per-module tests support it. Asserts, in one run:
  * a confident disqualifier is filtered out;
  * the cross-source duplicate is merged with UNIONED provenance (also proves the dedupe rework);
  * a stipend program and a worldwide-remote role outrank an unknown-eligibility one;
  * a total source failure is isolated (the run still completes);
  * a digest is rendered; and a SECOND run marks records ACTIVE, not NEW.
"""

from __future__ import annotations

from pathlib import Path

from job_scout.config import AppConfig
from job_scout.pipeline import run_once

from fixtures.gate0 import gate0_sources


def _cfg(tmp_path) -> AppConfig:
    cfg = AppConfig()
    cfg.db_path = str(tmp_path / "scout.db")
    cfg.notify.digest_path = str(tmp_path / "digest.html")
    return cfg


def _by_company(summary, company):
    return next((o for o in summary.ranked if o.company == company), None)


def test_gate0_slice_runs_green(tmp_path):
    cfg = _cfg(tmp_path)
    run1 = run_once(cfg, gate0_sources())

    # --- source failure isolation: the broken source is recorded failed; the run still completes.
    assert run1.sources["broken"]["ok"] is False
    assert run1.sources["greenhouse"]["ok"] is True
    assert run1.sources["lever"]["ok"] is True

    # --- pipeline arithmetic: 6 discovered → 5 after dedupe (one cross-source dup) → 4 after filter.
    assert run1.discovered == 6
    assert run1.after_dedupe == 5
    assert run1.after_filter == 4

    # --- confident disqualifier (REQUIRES_WORK_AUTH) is filtered out entirely.
    assert _by_company(run1, "GovTech") is None

    # --- cross-source duplicate merged, richer content won, provenance unioned (dedupe rework).
    globex = _by_company(run1, "Globex")
    assert globex is not None
    assert {p.source for p in globex.provenance} == {"greenhouse", "lever"}
    assert "pipelines" in globex.description.lower()          # the richer (lever) description

    # --- eligibility gates rank: stipend + worldwide-remote both outrank the unknown-eligibility one.
    titles = [o.company for o in run1.ranked]
    i_stipend = titles.index("Outreachy")
    i_world = titles.index("Zapier")
    i_unknown = titles.index("Acme Corp")
    assert i_stipend < i_unknown
    assert i_world < i_unknown

    # --- a digest was rendered and written.
    digest = Path(run1.digest_path)
    assert digest.exists()
    assert "Job Scout" in digest.read_text(encoding="utf-8")

    # --- at least one genuinely new, relevant opportunity was notified on the first run.
    assert run1.notified >= 1
    assert run1.lifecycle["new"] == 4

    # --- SECOND run over the same store: everything is ACTIVE, nothing NEW, nothing re-notified.
    run2 = run_once(cfg, gate0_sources())
    assert run2.lifecycle["new"] == 0
    assert run2.lifecycle["active"] == 4
    assert run2.notified == 0
