"""Pipeline orchestration — the single-run spine wiring. See PLAN.md §Spine.

`run_once` is the whole scout in one idempotent pass. It is deterministic and side-effect-honest:
sources are the only I/O in, the SQLite store + the digest file are the only I/O out, and every
source runs inside its own failure boundary so one dead source never aborts the run.

Frozen stage order (Gate 0):

    discover(+provenance) → normalize → dedupe → classify_eligibility → hard_filter
        → score → rank → reconcile/persist → notify

Why this order is load-bearing:
  * normalize before dedupe — dedupe keys on the content fingerprint normalize computes.
  * classify_eligibility before hard_filter — hard_filter drops CONFIDENT disqualifiers, so the
    eligibility judgement must already be attached.
  * hard_filter before score — we never spend scoring compute on dead-on-arrival postings.
  * score before reconcile/persist — the persisted record is the fully-scored one. (content_hash,
    which drives the NEW/UPDATED/ACTIVE diff, is independent of the score, so persisting after
    scoring leaves lifecycle diffing identical to persisting before it.)
  * reconcile/persist before notify — notify reads the lifecycle diff (new/updated) persist emits.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from uuid import uuid4

from .config import AppConfig
from .dedupe import dedupe
from .eligibility import classify_eligibility
from .models import Opportunity, Provenance
from .normalize import normalize
from .notify import render_digest, select_for_notification, write_digest
from .score import hard_filter, rank, score_opportunity
from .sources.base import Source
from .store import connect, mark_notified, record_run, upsert_and_reconcile

log = logging.getLogger("job_scout.pipeline")


@dataclass
class RunSummary:
    """A structured account of one run — the return value and what gets recorded in `runs`."""

    run_id: str
    started: str
    finished: str
    sources: dict[str, dict] = field(default_factory=dict)   # name -> {ok, count|error}
    discovered: int = 0
    after_dedupe: int = 0
    after_filter: int = 0
    lifecycle: dict[str, int] = field(default_factory=dict)  # new/updated/active
    notified: int = 0
    digest_path: str | None = None
    ranked: list[Opportunity] = field(default_factory=list)  # final ranked survivors (in-memory)

    def as_record(self) -> dict:
        """The JSON-safe subset stored in the `runs` table (no live objects)."""
        return {
            "run_id": self.run_id,
            "started": self.started,
            "finished": self.finished,
            "sources": self.sources,
            "discovered": self.discovered,
            "after_dedupe": self.after_dedupe,
            "after_filter": self.after_filter,
            "lifecycle": self.lifecycle,
            "notified": self.notified,
            "digest_path": self.digest_path,
        }


def _discover(sources: list[Source], cfg: AppConfig) -> tuple[list[Opportunity], dict[str, dict]]:
    """Fetch every source inside its own boundary; stamp provenance from the source that saw it.

    A total source failure is isolated and recorded (never allowed to abort the run). An empty
    return is recorded as a genuine "nothing" (ok, count 0) — a different fact from a failure.
    """
    raw: list[Opportunity] = []
    results: dict[str, dict] = {}
    now = datetime.now(timezone.utc)
    for src in sources:
        try:
            opps = src.fetch(cfg.sources)
        except Exception as exc:  # failure isolation — one bad source never kills the run
            log.warning("source %s failed: %r", src.name, exc)
            results[src.name] = {"ok": False, "error": repr(exc)}
            continue
        for opp in opps:
            # Stamp provenance from the source that produced it, unless the source set its own.
            if not opp.provenance:
                opp.provenance = [Provenance(source=src.name, url=opp.apply_url, first_seen=now)]
            raw.append(opp)
        results[src.name] = {"ok": True, "count": len(opps)}
    return raw, results


def run_once(
    cfg: AppConfig,
    sources: list[Source],
    *,
    model=None,
    today: date | None = None,
    conn=None,
) -> RunSummary:
    """Run the whole scout once. Deterministic given the sources, config, and (absent) model.

    `model` is the optional local embedding model (None → lexical scoring, still $0). `conn` lets a
    caller (tests, a long-lived process) inject a connection; when omitted, one is opened from
    `cfg.db_path` and closed before returning.
    """
    run_id = uuid4().hex[:12]
    started = datetime.now(timezone.utc).isoformat()

    # 1. discover (per-source failure isolation) + stamp provenance
    raw, source_results = _discover(sources, cfg)

    # 2. normalize (canonical URL, remote inference, content fingerprint)
    for opp in raw:
        normalize(opp)

    # 3. dedupe within the run (unions provenance; richer duplicate wins)
    deduped = dedupe(raw)

    # 4. classify eligibility (honest {category, confidence, evidence}; UNKNOWN first-class)
    for opp in deduped:
        opp.eligibility = classify_eligibility(opp, cfg.profile)

    # 5. hard filter (confident disqualifiers, passed deadlines, unwanted employment types)
    survivors = hard_filter(deduped, cfg.profile, cfg.scoring, today=today)

    # 6. score survivors (embedding when available, else lexical fallback)
    for opp in survivors:
        opp.relevance = score_opportunity(opp, cfg.profile, cfg.scoring, model=model)

    # 7. rank (eligibility gates rank, then relevance)
    ranked = rank(survivors)

    # 8. reconcile + persist (assign NEW/UPDATED/ACTIVE, preserve notified_at)
    owns_conn = conn is None
    if owns_conn:
        conn = connect(cfg.db_path)
    try:
        lifecycle = upsert_and_reconcile(conn, ranked, run_id)

        # 9. notify (new/updated ∧ ≥ threshold ∧ not already notified) → digest → mark notified
        to_notify = select_for_notification(ranked, cfg.scoring.relevance_threshold)
        digest = render_digest(to_notify, cfg)
        digest_path = write_digest(digest, cfg)
        if to_notify:
            mark_notified(conn, to_notify)

        finished = datetime.now(timezone.utc).isoformat()
        summary = RunSummary(
            run_id=run_id,
            started=started,
            finished=finished,
            sources=source_results,
            discovered=len(raw),
            after_dedupe=len(deduped),
            after_filter=len(survivors),
            lifecycle=lifecycle,
            notified=len(to_notify),
            digest_path=digest_path,
            ranked=ranked,
        )
        record_run(conn, run_id, started, summary.as_record())
    finally:
        if owns_conn:
            conn.close()

    return summary
