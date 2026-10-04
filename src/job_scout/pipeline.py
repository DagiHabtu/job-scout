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
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

from .config import AppConfig
from .dedupe import dedupe
from .eligibility import classify_eligibility
from .models import EmploymentType, Opportunity, Provenance
from .normalize import normalize
from .notify import (
    gate_reasons,
    render_digest,
    render_funnel_md,
    render_issue_md,
    select_for_notification,
    write_digest,
)
from .score import filter_reason, hard_filter, rank, score_opportunity, stage_of
from .sources.base import Source
from .store import connect, mark_notified, record_run, upsert_and_reconcile

log = logging.getLogger("job_scout.pipeline")

# Types tracked by the internship funnel — the scarce target class whose absence must be explained.
_FUNNEL_TYPES = frozenset({EmploymentType.INTERNSHIP, EmploymentType.STIPEND_PROGRAM})
_MAX_SAMPLES = 5


@dataclass
class RunSummary:
    """A structured account of one run — the return value and what gets recorded in `runs`.

    Every record that does not reach the user carries exactly one reason: `rejects` (hard filter)
    and `gate` (notify gate) are reason → count, so
    `discovered − merged − Σrejects − Σgate = notified` holds for every run.
    """

    run_id: str
    started: str
    finished: str
    sources: dict[str, dict] = field(default_factory=dict)   # name -> {ok, count|error, report?}
    discovered: int = 0
    after_dedupe: int = 0
    after_filter: int = 0
    lifecycle: dict[str, int] = field(default_factory=dict)  # new/updated/active
    notified: int = 0
    digest_path: str | None = None
    rejects: dict[str, int] = field(default_factory=dict)          # hard-filter reason -> count
    gate: dict[str, int] = field(default_factory=dict)             # notify-gate reason -> count
    by_type: dict[str, int] = field(default_factory=dict)          # employment type after normalize
    by_eligibility: dict[str, int] = field(default_factory=dict)   # category after classify
    near_misses: list[dict] = field(default_factory=list)          # top unselected survivors
    internship_funnel: dict = field(default_factory=dict)          # {fetched, outcomes, rejected_samples}
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
            "rejects": self.rejects,
            "gate": self.gate,
            "by_type": self.by_type,
            "by_eligibility": self.by_eligibility,
            "near_misses": self.near_misses,
            "internship_funnel": self.internship_funnel,
        }


def _brief(opp: Opportunity) -> dict:
    """The JSON-safe identifying fields used in near-miss and sample lists."""
    return {
        "title": opp.title,
        "company": opp.company,
        "location": opp.location_raw or "",
        "type": opp.employment_type.value,
        "eligibility": opp.eligibility.category.value if opp.eligibility else "",
    }


_KNOWN = {"not_new", "already_notified"}   # already-seen records are not "rejected"


def _internship_funnel(target_raw: list[Opportunity], kept_ids: set[int], reason_of: dict[int, str | None]) -> dict:
    """Outcome of every fetched internship/stipend record: `merged` (folded into another record by
    dedupe), its filter or gate reason, or `notified`. Few fetched → coverage problem; many fetched
    but rejected → audit the samples before touching any rule."""
    outcomes: Counter[str] = Counter()
    samples: list[dict] = []
    for o in target_raw:
        if id(o) not in kept_ids:
            outcomes["merged"] += 1
            continue
        reason = reason_of.get(id(o))
        outcomes[reason or "notified"] += 1
        if reason and reason not in _KNOWN and len(samples) < _MAX_SAMPLES:   # real rejections only (L4)
            b = _brief(o)
            samples.append({
                "title": b["title"], "company": b["company"], "location": b["location"], "reason": reason,
                # a stage rejection quotes its sentence (§12), so a wrong one is visible in the heartbeat
                "evidence": ("; ".join(stage_of(o)[1]) if reason.startswith("stage:")
                             else "; ".join(o.eligibility.evidence) if o.eligibility else ""),
            })
    return {"fetched": len(target_raw), "outcomes": dict(outcomes), "rejected_samples": samples}


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
        results[src.name] = {"ok": True, "count": len(opps),
                             # malformed records the source skipped (§6) — so "0" is never ambiguous
                             "skipped_records": int(getattr(src, "skipped_records", 0) or 0)}
        # Optional, protocol-free: a source may explain records it deliberately did not emit.
        report = getattr(src, "report", None)
        if isinstance(report, dict) and report:
            results[src.name]["report"] = {str(k): str(v) for k, v in report.items()}
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
    by_type = Counter(o.employment_type.value for o in raw)
    target_raw = [o for o in raw if o.employment_type in _FUNNEL_TYPES]

    # 3. dedupe within the run (unions provenance; richer duplicate wins)
    deduped = dedupe(raw)

    # 4. classify eligibility (honest {category, confidence, evidence}; UNKNOWN first-class)
    for opp in deduped:
        opp.eligibility = classify_eligibility(opp, cfg.profile)
    by_eligibility = Counter(o.eligibility.category.value for o in deduped)

    # 5. hard filter (confident disqualifiers, passed deadlines, unwanted employment types)
    today = today or date.today()
    survivors = hard_filter(deduped, cfg.profile, cfg.scoring, today=today)
    reason_of: dict[int, str | None] = {id(o): filter_reason(o, cfg.profile, cfg.scoring, today) for o in deduped}
    rejects = Counter(r for r in reason_of.values() if r is not None)

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

        # 9. notify (deterministic gate: new/updated, not notified, class ∧ role family ∧ eligibility) → deliver
        threshold = cfg.scoring.relevance_threshold
        to_notify = select_for_notification(ranked, threshold)
        for o, r in zip(ranked, gate_reasons(ranked, threshold)):
            reason_of[id(o)] = r
        gate = Counter(reason_of[id(o)] for o in ranked if reason_of[id(o)] is not None)
        unselected = [o for o in ranked if reason_of[id(o)] is not None]
        near_misses = [
            {**_brief(o), "score": o.relevance.score if o.relevance else 0.0, "gate_reason": reason_of[id(o)]}
            for o in sorted(unselected, key=lambda o: -(o.relevance.score if o.relevance else 0.0))[:_MAX_SAMPLES]
        ]
        digest = render_digest(to_notify, cfg)
        digest_path = write_digest(digest, cfg)
        # The issue body exists only when there is something to deliver; a stale one is removed so
        # the workflow never re-posts a previous run's selection.
        notify_path = Path(digest_path).parent / "notify.md"
        if to_notify:
            notify_path.write_text(render_issue_md(to_notify, cfg), encoding="utf-8")
            mark_notified(conn, to_notify)
        else:
            notify_path.unlink(missing_ok=True)

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
            rejects=dict(rejects),
            gate=dict(gate),
            by_type=dict(by_type),
            by_eligibility=dict(by_eligibility),
            near_misses=near_misses,
            internship_funnel=_internship_funnel(target_raw, {id(o) for o in deduped}, reason_of),
            ranked=ranked,
        )
        _check_invariant(summary)
        record = summary.as_record()
        record_run(conn, run_id, started, record)
        funnel_path = Path(cfg.notify.digest_path).parent / "funnel.md"
        funnel_path.write_text(render_funnel_md(record), encoding="utf-8")
    finally:
        if owns_conn:
            conn.close()

    return summary


def _check_invariant(s: RunSummary) -> bool:
    """`discovered − merged − Σrejects − Σgate = notified`: every lost record has one reason."""
    merged = s.discovered - s.after_dedupe
    ok = s.discovered - merged - sum(s.rejects.values()) - sum(s.gate.values()) == s.notified
    if not ok:
        log.warning(
            "funnel invariant violated: discovered=%d merged=%d rejects=%d gate=%d notified=%d",
            s.discovered, merged, sum(s.rejects.values()), sum(s.gate.values()), s.notified,
        )
    return ok
