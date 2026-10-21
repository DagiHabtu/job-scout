"""Notification — selection + digest rendering. File-first, $0, zero external dependency.

Two responsibilities, kept separate so both are testable:
  * `select_for_notification` — the gate: NEW/UPDATED, not already notified, and passing the
    deterministic class ∧ role-family ∧ eligibility rules in `gate_reason`. This is the
    load-bearing anti-spam rule (over-notification is the real product risk, PLAN §9).
  * `render_digest` / `write_digest` — turn the selected opportunities into a legible HTML digest
    and write it where the config says. The digest shows the *reasoning* (eligibility evidence,
    matched signals, concerns), never a bare number, so a human can audit every call.

Email (Gmail SMTP + app password) is the optional free upgrade and is intentionally NOT a hard
dependency; the file digest is the always-available default.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from html import escape
from pathlib import Path

from .config import AppConfig
from .eligibility import UNSTATED_EVIDENCE
from .models import EligibilityCategory, EmploymentType, Lifecycle, Opportunity
from .facts import key_facts
from .score import interest_of, pay_verdict, role_family_ok, stage_of
from .store import _identity_key

# Statuses that are worth telling the user about. ACTIVE (seen again, unchanged) is deliberately
# excluded — re-announcing an unchanged posting is exactly the noise we are avoiding.
_NOTIFIABLE = frozenset({Lifecycle.NEW, Lifecycle.UPDATED})

# Per-digest caps (spec 2026-10-21 §4.6: the weekly pool is larger than a day's)
UNKNOWN_INTERN_CAP = 10    # "Check eligibility" items per digest (stipend programs are outside it)
ASPIRATIONAL_CAP = 2       # advanced-degree (MSc/PhD) roles per digest (§12 S10)
OUTSIDE_INTERESTS_CAP = 5  # title-and-link lines for eligible roles outside the stated interests (§12 S11)
PENDING_DAYS = 14          # a never-notified record first seen this recently is still deliverable (§4.6)
URGENT_DAYS = 14           # a deadline this close makes an item urgent: delivered on any day (§4.6)
DEFERRED = "deferred:weekly"
_TARGET_CLASS = frozenset({EmploymentType.INTERNSHIP, EmploymentType.NEW_GRAD})
UNVERIFIED_CONFIDENCE = 0.6  # UNKNOWN at/above this = "unverified" (spec 2026-10-21 §4.2)


def gate_reason(opp: Opportunity, threshold: float, *, pending: bool = False) -> str | None:
    """Why `opp` is NOT notified, or None if it is selected. Deterministic rules, first match wins,
    so every unselected record carries exactly one reason (spec S5):

    already_notified → not_new → stipend program (positive or UNKNOWN eligibility → selected; never
    dropped for uncertainty) → not_target_class (not INTERNSHIP/NEW_GRAD) → role_family (title is not
    a technical role) → eligibility: positive → selected; unverified (UNKNOWN ≥ 0.6, spec 2026-10-21 §4.2)
    → selected under "Check eligibility" for internships and new-grad roles; other UNKNOWN internship →
    selected under "Check eligibility"; other UNKNOWN new-grad → eligibility_unknown. "Check eligibility"
    is capped per run by `gate_reasons`.

    `threshold` stays in the signature (frozen) but is no longer consulted: relevance orders items,
    it does not gate them (C3). `pending` (spec 2026-10-21 §4.6): the record is in the pending pool
    (`in_pending_pool`), so an ACTIVE one is not `not_new`.
    """
    # already_notified is checked first (spec lists not_new first): the reason label only — selection is
    # identical — but a record seen again after delivery reads as delivered, which S6's Case A asserts.
    if opp.notified_at is not None:
        return "already_notified"
    if opp.status not in _NOTIFIABLE and not pending:
        return "not_new"
    cat = opp.eligibility.category if opp.eligibility else EligibilityCategory.UNKNOWN
    if opp.employment_type == EmploymentType.STIPEND_PROGRAM:
        return None if cat in _POSITIVE or cat == EligibilityCategory.UNKNOWN else "eligibility_negative"
    if opp.employment_type not in _TARGET_CLASS:
        return "not_target_class"
    # Role family before interest: a non-technical title is never selected, whatever its taste verdict
    # ("CRM Assistant" → role_family); a technical not-interested one goes to its own section (§12 S11).
    if not role_family_ok(opp.title, opp.description):
        return "role_family"
    # Pay (spec 2026-10-21 §4.4): unpaid roles are not wanted unless the profile accepts them (recorded
    # at score time as "unpaid_accepted"). Stipend programs returned above, so they are exempt.
    if pay_verdict(opp)[0] == "unpaid":
        return "pay:unpaid"
    # Stage fit (§12 S10): stated conditions a current student cannot meet now. An advanced-degree
    # role with positive eligibility is selected into "Aspirational" (capped in `gate_reasons`).
    stage, _ = stage_of(opp)
    if stage == "graduate_only":
        return "stage:graduate_only"
    if stage == "experience_required":
        return "stage:experience"
    if cat in _POSITIVE:
        return None
    if cat == EligibilityCategory.UNKNOWN:
        if opp.eligibility is not None and opp.eligibility.confidence >= UNVERIFIED_CONFIDENCE:
            return None   # unverified: aggregator-only evidence, surfaced as uncertain (never as eligible)
        return None if opp.employment_type == EmploymentType.INTERNSHIP else "eligibility_unknown"
    return "eligibility_negative"   # a low-confidence disqualifier that survived the hard filter


def in_pending_pool(opp: Opportunity, first_seen: datetime | None, today: date) -> bool:
    """Deliverable if selected (spec 2026-10-21 §4.6): never notified, and NEW/UPDATED or first seen
    (the store's `first_seen`) within `PENDING_DAYS` of `today`."""
    if opp.notified_at is not None:
        return False
    if opp.status in _NOTIFIABLE:
        return True
    return first_seen is not None and (today - first_seen.date()).days <= PENDING_DAYS


def is_urgent(opp: Opportunity, today: date) -> bool:
    """A stipend program, or a deadline within `URGENT_DAYS` of `today` — delivered on any day (§4.6)."""
    if opp.employment_type == EmploymentType.STIPEND_PROGRAM:
        return True
    return opp.deadline is not None and (opp.deadline - today).days <= URGENT_DAYS


def gate_reasons(opps: list[Opportunity], threshold: float, *, pending: list[bool] | None = None,
                 urgent_only: date | None = None) -> list[str | None]:
    """`gate_reason` for each record in order, plus the per-digest caps, one per section: UNKNOWN-eligibility
    internships in "Check eligibility" (`unknown_cap`), "Aspirational" (`stage:advanced_cap`), "Eligible,
    outside your stated interests" (`interest:cap`). The best title matches are kept.

    `pending`: per record, whether it is in the pending pool (§4.6). `urgent_only` (a weekday that is not
    the weekly digest's, as `today`): only urgent records stay selected, the rest are `deferred:weekly`
    — before the caps, so a deferred record never reads as capped."""
    out = [gate_reason(o, threshold, pending=p) for o, p in zip(opps, pending or [False] * len(opps))]
    if urgent_only is not None:
        out = [DEFERRED if r is None and not is_urgent(o, urgent_only) else r for o, r in zip(opps, out)]
    # unverified new-grad roles share the "Check eligibility" cap with UNKNOWN internships (§4.2)
    capped = [
        i for i, (o, r) in enumerate(zip(opps, out))
        if r is None and o.employment_type in _TARGET_CLASS and section_of(o) == CHECK_ELIGIBILITY
    ]
    for i in sorted(capped, key=lambda i: -_title_fit(opps[i]))[UNKNOWN_INTERN_CAP:]:
        out[i] = "unknown_cap"
    aspirational = [i for i, (o, r) in enumerate(zip(opps, out)) if r is None and section_of(o) == ASPIRATIONAL]
    for i in sorted(aspirational, key=lambda i: -_title_fit(opps[i]))[ASPIRATIONAL_CAP:]:
        out[i] = "stage:advanced_cap"
    outside = [i for i, (o, r) in enumerate(zip(opps, out)) if r is None and section_of(o) == OUTSIDE_INTERESTS]
    for i in sorted(outside, key=lambda i: -_title_fit(opps[i]))[OUTSIDE_INTERESTS_CAP:]:
        out[i] = "interest:cap"
    return out


def select_for_notification(opps: list[Opportunity], threshold: float, **kw) -> list[Opportunity]:
    """The records `gate_reasons` selects (same keywords). Order preserved."""
    return [o for o, r in zip(opps, gate_reasons(opps, threshold, **kw)) if r is None]


# --------------------------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------------------------- #


def _fmt_eligibility(opp: Opportunity) -> str:
    e = opp.eligibility
    if e is None:
        return "<span class='elig unknown'>eligibility: not assessed</span>"
    cls = "good" if e.category.value in {
        "stipend_program_global", "worldwide_remote", "remote_region_includes_user"
    } else ("unknown" if e.category.value == "unknown" else "bad")
    ev = "".join(f"<li>{escape(x)}</li>" for x in e.evidence)
    return (
        f"<div class='elig {cls}'>eligibility: <b>{escape(e.category.value)}</b> "
        f"(confidence {e.confidence:.2f})<ul>{ev}</ul></div>"
    )


def _fmt_relevance(opp: Opportunity) -> str:
    r = opp.relevance
    if r is None:
        return ""
    matched = "".join(f"<li>{escape(x)}</li>" for x in r.matched_signals if not x.startswith("stage:"))
    concerns = "".join(f"<li class='concern'>{escape(x)}</li>" for x in r.concerns if not x.startswith("stage:"))
    stage, stage_ev = stage_of(opp)
    if stage and opp.employment_type != EmploymentType.STIPEND_PROGRAM:
        quotes = "; ".join(stage_ev)
        concerns += f"<li class='concern'>stage: <b>{escape(stage)}</b> — {escape(quotes)}</li>"
    sim = f" · semantic {r.semantic_similarity:.2f}" if r.semantic_similarity is not None else ""
    return (
        f"<div class='rel'>relevance: <b>{r.score:.2f}</b>{sim}"
        f"<ul>{matched}{concerns}</ul></div>"
    )


def _fmt_provenance(opp: Opportunity) -> str:
    if not opp.provenance:
        return ""
    seen = ", ".join(sorted({p.source for p in opp.provenance}))
    return f"<div class='prov'>seen via: {escape(seen)}</div>"


def _fmt_opp(opp: Opportunity) -> str:
    url = escape(opp.canonical_url or opp.apply_url or "")
    badge = escape(opp.status.value)
    return (
        "<article class='opp'>"
        f"<h2><a href='{url}'>{escape(opp.title)}</a> "
        f"<span class='co'>@ {escape(opp.company)}</span> "
        f"<span class='badge {badge}'>{badge}</span></h2>"
        f"<div class='meta'>{escape(opp.remote_status.value)} · "
        f"{escape(opp.employment_type.value)}"
        + (f" · {escape(opp.location_raw)}" if opp.location_raw else "")
        + "</div>"
        f"{_fmt_eligibility(opp)}"
        f"{_fmt_relevance(opp)}"
        f"{_fmt_provenance(opp)}"
        "</article>"
    )


_STYLE = """
body{font:15px/1.5 system-ui,sans-serif;max-width:820px;margin:2rem auto;padding:0 1rem;color:#1a1a1a}
h1{font-size:1.4rem} .opp{border:1px solid #e2e2e2;border-radius:8px;padding:1rem;margin:1rem 0}
.opp h2{font-size:1.1rem;margin:.2rem 0} .co{color:#555;font-weight:400}
.meta{color:#666;font-size:.85rem;margin:.3rem 0} ul{margin:.3rem 0 .3rem 1.1rem;padding:0}
.elig.good b{color:#137333} .elig.bad b{color:#b00020} .elig.unknown b{color:#8a6d00}
.rel b{color:#0b57d0} .concern{color:#8a6d00}
.badge{font-size:.7rem;padding:.1rem .4rem;border-radius:4px;background:#eee}
.badge.new{background:#d7f0d7} .badge.updated{background:#fde8c8}
.empty{color:#666} .prov{color:#888;font-size:.8rem;margin-top:.3rem}
""".strip()


def render_digest(opps: list[Opportunity], cfg: AppConfig) -> str:
    """Render the selected opportunities as a standalone, self-contained HTML digest."""
    loc = cfg.profile.location.country_name
    if opps:
        body = "".join(_fmt_opp(o) for o in opps)
    else:
        body = "<p class='empty'>No new or updated opportunities cleared the threshold this run.</p>"
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>Job Scout digest</title><style>{_STYLE}</style></head><body>"
        f"<h1>Job Scout — {len(opps)} opportunit{'y' if len(opps) == 1 else 'ies'} "
        f"for {escape(loc)}</h1>{body}</body></html>"
    )


def write_digest(digest_html: str, cfg: AppConfig) -> str:
    """Write the digest to the configured path (creating parent dirs). Returns the path written."""
    path = Path(cfg.notify.digest_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(digest_html, encoding="utf-8")
    return str(path)


# --------------------------------------------------------------------------------------------- #
# Issue body (Markdown) — the push channel: the workflow posts it as a GitHub Issue
# --------------------------------------------------------------------------------------------- #

ACTIONABLE = "Apply"       # §12 S11 (was "Actionable")
CHECK_ELIGIBILITY = "Check eligibility"
ASPIRATIONAL = "Aspirational"
OUTSIDE_INTERESTS = "Eligible, outside your stated interests"
SECTIONS = (ACTIONABLE, CHECK_ELIGIBILITY, ASPIRATIONAL, OUTSIDE_INTERESTS)
_POSITIVE = frozenset({
    EligibilityCategory.STIPEND_PROGRAM_GLOBAL,
    EligibilityCategory.WORLDWIDE_REMOTE,
    EligibilityCategory.REMOTE_REGION_INCLUDES_USER,
})


_UNCONFIRMED = "eligibility not confirmed — check it before applying"
UNSTATED_LINE = "No location restriction listed on Himalayas or in the posting. Confirm before applying."


def _unstated(opp: Opportunity) -> bool:
    """The aggregator marker with a silent body (spec 2026-10-21 §4.2)."""
    e = opp.eligibility
    return bool(e and e.category == EligibilityCategory.UNKNOWN and UNSTATED_EVIDENCE in e.evidence)


def _positive(opp: Opportunity) -> bool:
    return bool(opp.eligibility and opp.eligibility.category in _POSITIVE)


def section_of(opp: Opportunity) -> str:
    """The least actionable section wins (Dagi, 2026-10-04): a title naming a not-interested direction →
    "Eligible, outside your stated interests"; an MSc/PhD requirement → "Aspirational" — both whatever
    the eligibility (UNKNOWN is noted on the item). "Check eligibility" holds only roles that would
    otherwise be in "Apply". Stipend programs: positive → "Apply", else "Check eligibility"."""
    if opp.employment_type != EmploymentType.STIPEND_PROGRAM:
        if interest_of(opp)[0]:
            return OUTSIDE_INTERESTS
        if stage_of(opp)[0] == "advanced_degree":
            return ASPIRATIONAL
    return ACTIONABLE if _positive(opp) else CHECK_ELIGIBILITY


_CONDITION = "condition (not checked): "   # known_programs evidence prefix


def _issue_item(opp: Opportunity, n: int) -> str:
    """One numbered item (spec 2026-10-21 §4.6): the decision facts, eligibility, stage and the notes."""
    url = opp.canonical_url or opp.apply_url
    meta = " · ".join(x for x in (opp.company, opp.employment_type.value, opp.location_raw) if x)
    lines = []
    facts = key_facts(opp)
    if "role" in facts:
        lines.append(f"- **Role:** {facts['role']}")
    if "asks" in facts:
        lines.append(f"- **Asks:** {facts['asks']}")
    pay_hours = [f"**{k.title()}:** {facts[k]}" for k in ("pay", "hours") if k in facts]
    if pay_hours:
        lines.append("- " + " · ".join(pay_hours))
    if "location" in facts:
        lines.append(f"- **Location:** {facts['location']}")
    if opp.deadline:
        lines.append(f"- **Deadline:** {opp.deadline.isoformat()}")
    e = opp.eligibility
    if e is not None and _unstated(opp):
        lines.append(f"- **Eligibility:** {UNSTATED_LINE}")
    elif e is not None:
        lines.append(f"- **Eligibility:** {e.category.value} ({e.confidence:.2f})"
                     + (f" — {e.evidence[0]}" if e.evidence else ""))
    # a known program's personal conditions are not eligibility reasoning: only the user can check them
    conditions = [x.split(": ", 1)[1] for x in (e.evidence if e else []) if x.startswith(_CONDITION)]
    if conditions:
        lines.append(f"- **Check yourself:** {'; '.join(conditions)}")
    if not _positive(opp) and section_of(opp) != CHECK_ELIGIBILITY:
        lines.append(f"- {_UNCONFIRMED}")
    stage, stage_ev = stage_of(opp)
    if stage and opp.employment_type != EmploymentType.STIPEND_PROGRAM:
        lines.append(f"- **Stage:** {stage}" + (f" — {'; '.join(stage_ev)}" if stage_ev else ""))
    veto, note = interest_of(opp)
    if veto:
        lines.append(f"- outside your stated interests ('{veto}')")
    if note:
        lines.append(f"- interest: {note}")
    if opp.ats_provider == "himalayas":
        listing = opp.ats_job_id if (opp.ats_job_id or "").startswith("http") else url
        lines.append(f"- via [Himalayas]({listing})")
    return "\n".join([f"{n}. [{opp.title}]({url}) — {meta}"] + [f"    {x}" for x in lines])


_PAID = frozenset({"stated", "stipend"})


def _outside_line(opp: Opportunity, n: int) -> str:
    """'<n>. [Title](url) — Company · pay: <snippet>' (+ the unconfirmed-eligibility note)."""
    snippet = pay_verdict(opp)[1] if pay_verdict(opp)[0] in _PAID else None
    meta = " · ".join(x for x in (opp.company, f"pay: {snippet}" if snippet else None) if x)
    line = f"{n}. [{opp.title}]({opp.canonical_url or opp.apply_url})" + (f" — {meta}" if meta else "")
    return line + ("" if _positive(opp) else f" — {_UNCONFIRMED}")


def _title_fit(opp: Opportunity) -> float:
    """Ordering key within a section: title-to-target-role similarity, else the relevance score."""
    r = opp.relevance
    if r is None:
        return 0.0
    return r.semantic_similarity if r.semantic_similarity is not None else r.score


REPLY_HINT = "Reply with a comment such as: `apply 1,4 · maybe 2 · skip rest`"


def render_issue_md(opps: list[Opportunity], cfg: AppConfig, *, funnel: str | None = None) -> str:
    """The issue body (spec 2026-10-21 §4.6): items numbered continuously across the sections "Apply"
    (ordered by relevance score) · "Check eligibility" · "Aspirational" · "Eligible, outside your
    stated interests" (one line per item); each detailed item with its decision facts, eligibility and
    stage evidence. Empty sections are omitted. Then the weekly `funnel` (folded), the reply hint, and
    a hidden map from item number to record key for the labels channel (§4.8)."""
    out = [f"Job Scout — {len(opps)} new for {cfg.profile.location.country_name}.\n"]
    keys: dict[str, str] = {}
    for section in SECTIONS:
        key = (lambda o: o.relevance.score if o.relevance else 0.0) if section == ACTIONABLE else _title_fit
        if section == OUTSIDE_INTERESTS:      # paid roles first (spec 2026-10-21 §4.4), then title fit
            key = lambda o: (pay_verdict(o)[0] in _PAID, _title_fit(o))  # noqa: E731
        items = sorted((o for o in opps if section_of(o) == section), key=key, reverse=True)
        if not items:
            continue
        out.append(f"## {section}\n")
        render = _outside_line if section == OUTSIDE_INTERESTS else _issue_item
        lines = []
        for o in items:
            keys[str(len(keys) + 1)] = _identity_key(o)
            lines.append(render(o, len(keys)))
        out.append("\n".join(lines) + "\n")
    if funnel:
        out.append(f"<details><summary>Weekly funnel</summary>\n\n{funnel.rstrip()}\n\n</details>\n")
    if keys:
        out.append(REPLY_HINT + "\n")
    out.append(f"<!-- scout-items {json.dumps(keys)} -->")
    return _with_cc("\n".join(out))


def issue_title(n: int, today: date, *, weekly: bool, urgent: bool) -> str:
    """The issue title the workflow posts (§4.6)."""
    if weekly:
        return f"Job Scout weekly — {n} new — {today.isoformat()}"
    return f"Job Scout: {n} {'urgent' if urgent else 'new'} — {today.isoformat()}"


def _with_cc(body: str) -> str:
    """End an issue body with `cc @<owner>` (S9): a mention is a "participating" notification, which
    GitHub sends even when the owner does not watch the repository. Omitted when the env var is
    unset (local runs)."""
    owner = os.environ.get("GITHUB_REPOSITORY_OWNER", "").strip()
    return f"{body.rstrip()}\n\ncc @{owner}\n" if owner else body


# --------------------------------------------------------------------------------------------- #
# Funnel report (Markdown) — the run's reason-coded account, for the Actions step summary
# --------------------------------------------------------------------------------------------- #


def _md(s) -> str:
    """Make a value safe inside a Markdown table cell."""
    return str(s).replace("|", "\\|").replace("\n", " ")


def _counts_table(title: str, counts: dict, head: str = "reason") -> str:
    if not counts:
        return f"**{title}:** none\n"
    rows = "".join(f"| {_md(k)} | {v} |\n" for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
    return f"**{title}**\n\n| {head} | count |\n|---|--:|\n{rows}"


def render_funnel_md(rec: dict) -> str:
    """Render one run record (`RunSummary.as_record()`) as Markdown: sources, stage counts, and the
    reason histograms, so a zero-result run reads as a specific cause rather than a bare zero."""
    out = [f"## Job Scout funnel — run `{rec['run_id']}` ({rec['started'][:16]}Z)\n"]

    src_rows = ""
    for name, s in rec.get("sources", {}).items():
        status = "ok" if s.get("ok") else f"FAILED: {s.get('error', '')}"
        report = "; ".join(f"{k}: {v}" for k, v in (s.get("report") or {}).items())
        src_rows += (f"| {_md(name)} | {_md(status)} | {s.get('count', '—')} | {s.get('skipped_records', 0)} "
                     f"| {_md(report)} |\n")
    out.append("| source | status | fetched | skipped | report |\n|---|---|--:|--:|---|\n" + src_rows)

    merged = rec["discovered"] - rec["after_dedupe"]
    out.append(
        "| stage | count |\n|---|--:|\n"
        f"| discovered | {rec['discovered']} |\n"
        f"| merged by dedupe | {merged} |\n"
        f"| rejected by hard filter | {sum(rec.get('rejects', {}).values())} |\n"
        f"| survived | {rec['after_filter']} |\n"
        f"| not selected at notify gate | {sum(rec.get('gate', {}).values())} |\n"
        f"| **notified** | **{rec['notified']}** |\n"
    )
    out.append(_counts_table("Hard-filter rejects", rec.get("rejects", {})))
    out.append(_counts_table("Notify-gate reasons", rec.get("gate", {})))
    out.append(_counts_table("Employment type (after normalize)", rec.get("by_type", {}), "type"))
    out.append(_counts_table("Eligibility (after classify)", rec.get("by_eligibility", {}), "category"))

    f = rec.get("internship_funnel", {})
    out.append(f"**Target-class funnel (internship / new grad / stipend program):** fetched {f.get('fetched', 0)}\n")
    if f.get("outcomes"):
        out.append(_counts_table("Internship outcomes", f["outcomes"]))
    if f.get("rejected_samples"):
        out.append(_samples_table(f["rejected_samples"]))

    nm = rec.get("near_misses", [])
    if nm:
        rows = "".join(
            f"| {_md(n['title'])} | {_md(n['company'])} | {_md(n['location'])} | {_md(n['type'])} | "
            f"{_md(n['eligibility'])} | {n['score']} | {_md(n['gate_reason'])} |\n"
            for n in nm
        )
        out.append(
            "**Near misses** (top unselected survivors by score)\n\n"
            "| title | company | location | type | eligibility | score | gate reason |\n"
            "|---|---|---|---|---|--:|---|\n" + rows
        )
    return "\n".join(out)


MAX_SAMPLES = 5
STAGE_SAMPLE_RESERVE = 2
_STAGE_REJECTIONS = frozenset({"stage:graduate_only", "stage:experience"})   # judgements, not cap overflows


def pick_samples(cands: list[dict], n: int = MAX_SAMPLES, reserve: int = STAGE_SAMPLE_RESERVE) -> list[dict]:
    """Up to `n` rejected samples in their original order, at least `reserve` of them stage rejections
    when that many exist, so a wrong stage rejection is visible (§12; final review M6)."""
    stage = [i for i, c in enumerate(cands) if c["reason"] in _STAGE_REJECTIONS][:reserve]
    rest = [i for i in range(len(cands)) if i not in stage][: n - len(stage)]
    return [cands[i] for i in sorted(stage + rest)]


def _samples_table(samples: list[dict]) -> str:
    rows = "".join(
        f"| {_md(s['title'])} | {_md(s['company'])} | {_md(s['location'])} | {_md(s['reason'])} | {_md(s['evidence'])} |\n"
        for s in samples
    )
    return "| title | company | location | reason | evidence |\n|---|---|---|---|---|\n" + rows


def _sum_counts(dicts) -> dict[str, int]:
    total: dict[str, int] = {}
    for d in dicts:
        for k, v in (d or {}).items():
            total[k] = total.get(k, 0) + v
    return total


_NOT_NEAR_MISS = frozenset({"already_notified", "not_new", DEFERRED})   # seen or waiting, not "missed"


def render_heartbeat_md(records: list[dict], extra: list[str] | None = None) -> str:
    """Weekly heartbeat: the funnel summed over the given run records (newest first) plus their
    near misses, so silence is distinguishable from failure. `extra` lines are appended verbatim."""
    return _with_cc(heartbeat_body(records, extra))


def heartbeat_body(records: list[dict], extra: list[str] | None = None) -> str:
    """`render_heartbeat_md` without the `cc` line — also the weekly digest's folded funnel (§4.6)."""
    out = [f"## Job Scout weekly funnel — {len(records)} run(s)\n"]
    if not records:
        out.append("No run records found — the scout has not run. Check the Actions tab.\n")
    else:
        rows = "".join(
            f"| {r['started'][:10]} | {r['discovered']} | {r['after_filter']} | {r['notified']} | "
            f"{_md(', '.join(n for n, s in r.get('sources', {}).items() if not s.get('ok')) or '—')} |\n"
            for r in records
        )
        out.append("| run | discovered | survived | notified | failed sources |\n|---|--:|--:|--:|---|\n" + rows)
        out.append(_counts_table("Hard-filter rejects (7 runs)", _sum_counts(r.get("rejects") for r in records)))
        out.append(_counts_table("Notify-gate reasons (7 runs)", _sum_counts(r.get("gate") for r in records)))
        f_fetched = sum(r.get("internship_funnel", {}).get("fetched", 0) for r in records)
        out.append(f"**Target-class records fetched — internship / new grad / stipend program (7 runs):** {f_fetched}\n")
        out.append(_counts_table("Internship outcomes (7 runs)",
                                 _sum_counts(r.get("internship_funnel", {}).get("outcomes") for r in records)))
        seen: dict[tuple, dict] = {}
        for r in records:
            for s in r.get("internship_funnel", {}).get("rejected_samples", []):
                seen.setdefault((s["title"], s["company"]), s)
        if seen:
            out.append("**Rejected target-class samples (7 runs)**\n\n" + _samples_table(pick_samples(list(seen.values()))))
        best: dict[tuple, dict] = {}
        for r in records:
            for n in r.get("near_misses", []):
                if n.get("gate_reason") in _NOT_NEAR_MISS:
                    continue
                k = (n["title"], n["company"])
                if k not in best or n["score"] > best[k]["score"]:
                    best[k] = n
        nm = sorted(best.values(), key=lambda n: -n["score"])[:10]
        if nm:
            rows = "".join(
                f"| {_md(n['title'])} | {_md(n['company'])} | {_md(n['location'])} | {_md(n['type'])} | "
                f"{_md(n['eligibility'])} | {n['score']} | {_md(n['gate_reason'])} |\n"
                for n in nm
            )
            out.append(
                "**Near misses (7 runs)**\n\n| title | company | location | type | eligibility | score | gate reason |\n"
                "|---|---|---|---|---|--:|---|\n" + rows
            )
    if extra:
        out.append("\n".join(extra) + "\n")
    return "\n".join(out)
