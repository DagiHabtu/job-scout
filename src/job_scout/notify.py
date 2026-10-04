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

from html import escape
from pathlib import Path

from .config import AppConfig
from .models import EligibilityCategory, EmploymentType, Lifecycle, Opportunity
from .score import role_family_ok

# Statuses that are worth telling the user about. ACTIVE (seen again, unchanged) is deliberately
# excluded — re-announcing an unchanged posting is exactly the noise we are avoiding.
_NOTIFIABLE = frozenset({Lifecycle.NEW, Lifecycle.UPDATED})

UNKNOWN_INTERN_CAP = 5     # "Check eligibility" internships per run (stipend programs are outside it)
_TARGET_CLASS = frozenset({EmploymentType.INTERNSHIP, EmploymentType.NEW_GRAD})


def gate_reason(opp: Opportunity, threshold: float) -> str | None:
    """Why `opp` is NOT notified, or None if it is selected. Deterministic rules, first match wins,
    so every unselected record carries exactly one reason (spec S5):

    already_notified → not_new → stipend program (positive or UNKNOWN eligibility → selected; never
    dropped for uncertainty) → not_target_class (not INTERNSHIP/NEW_GRAD) → role_family (title is not
    a technical role) → eligibility: positive → selected; UNKNOWN internship → selected under "Check
    eligibility" (capped per run by `gate_reasons`); UNKNOWN new-grad → eligibility_unknown.

    `threshold` stays in the signature (frozen) but is no longer consulted: relevance orders items,
    it does not gate them (C3).
    """
    # already_notified is checked first (spec lists not_new first): the reason label only — selection is
    # identical — but a record seen again after delivery reads as delivered, which S6's Case A asserts.
    if opp.notified_at is not None:
        return "already_notified"
    if opp.status not in _NOTIFIABLE:
        return "not_new"
    cat = opp.eligibility.category if opp.eligibility else EligibilityCategory.UNKNOWN
    if opp.employment_type == EmploymentType.STIPEND_PROGRAM:
        return None if cat in _POSITIVE or cat == EligibilityCategory.UNKNOWN else "eligibility_negative"
    if opp.employment_type not in _TARGET_CLASS:
        return "not_target_class"
    if not role_family_ok(opp.title):
        return "role_family"
    if cat in _POSITIVE:
        return None
    if cat == EligibilityCategory.UNKNOWN:
        return None if opp.employment_type == EmploymentType.INTERNSHIP else "eligibility_unknown"
    return "eligibility_negative"   # a low-confidence disqualifier that survived the hard filter


def gate_reasons(opps: list[Opportunity], threshold: float) -> list[str | None]:
    """`gate_reason` for each record in order, plus the per-run cap on UNKNOWN-eligibility
    internships: the best title matches are kept, the overflow gets `unknown_cap`."""
    out = [gate_reason(o, threshold) for o in opps]
    capped = [
        i for i, (o, r) in enumerate(zip(opps, out))
        if r is None and o.employment_type == EmploymentType.INTERNSHIP
        and (o.eligibility is None or o.eligibility.category == EligibilityCategory.UNKNOWN)
    ]
    for i in sorted(capped, key=lambda i: -_title_fit(opps[i]))[UNKNOWN_INTERN_CAP:]:
        out[i] = "unknown_cap"
    return out


def select_for_notification(opps: list[Opportunity], threshold: float) -> list[Opportunity]:
    """The records `gate_reasons` selects. Order preserved."""
    return [o for o, r in zip(opps, gate_reasons(opps, threshold)) if r is None]


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
    matched = "".join(f"<li>{escape(x)}</li>" for x in r.matched_signals)
    concerns = "".join(f"<li class='concern'>{escape(x)}</li>" for x in r.concerns)
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

ACTIONABLE = "Actionable"
CHECK_ELIGIBILITY = "Check eligibility"
_POSITIVE = frozenset({
    EligibilityCategory.STIPEND_PROGRAM_GLOBAL,
    EligibilityCategory.WORLDWIDE_REMOTE,
    EligibilityCategory.REMOTE_REGION_INCLUDES_USER,
})


def section_of(opp: Opportunity) -> str:
    """A positive eligibility verdict is actionable; anything else is surfaced with its doubt."""
    return ACTIONABLE if opp.eligibility and opp.eligibility.category in _POSITIVE else CHECK_ELIGIBILITY


def _issue_item(opp: Opportunity) -> str:
    url = opp.canonical_url or opp.apply_url
    meta = " · ".join(x for x in (opp.company, opp.employment_type.value, opp.location_raw) if x)
    lines = [f"- [ ] [{opp.title}]({url}) — {meta}"]
    if opp.deadline:
        lines.append(f"  - deadline: {opp.deadline.isoformat()}")
    e = opp.eligibility
    if e is not None:
        lines.append(f"  - eligibility: **{e.category.value}** (confidence {e.confidence:.2f})")
        lines += [f"    - {x}" for x in e.evidence]
    if opp.relevance and opp.relevance.matched_signals:
        lines.append(f"  - matched: {', '.join(opp.relevance.matched_signals)}")
    if opp.ats_provider == "himalayas":
        listing = opp.ats_job_id if (opp.ats_job_id or "").startswith("http") else url
        lines.append(f"  - via [Himalayas]({listing})")
    return "\n".join(lines)


def _title_fit(opp: Opportunity) -> float:
    """Ordering key within a section: title-to-target-role similarity, else the relevance score."""
    r = opp.relevance
    if r is None:
        return 0.0
    return r.semantic_similarity if r.semantic_similarity is not None else r.score


def render_issue_md(opps: list[Opportunity], cfg: AppConfig) -> str:
    """One task-list line per item (tick the ones worth applying to), grouped into "Actionable" and
    "Check eligibility", each with its eligibility evidence and matched signals."""
    out = [f"Job Scout — {len(opps)} new for {cfg.profile.location.country_name}. "
           "Tick the items worth applying to.\n"]
    for section in (ACTIONABLE, CHECK_ELIGIBILITY):
        items = sorted((o for o in opps if section_of(o) == section), key=_title_fit, reverse=True)
        if items:
            out.append(f"## {section}\n")
            out.append("\n".join(_issue_item(o) for o in items) + "\n")
    return "\n".join(out)


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
        src_rows += f"| {_md(name)} | {_md(status)} | {s.get('count', '—')} | {_md(report)} |\n"
    out.append("| source | status | fetched | report |\n|---|---|--:|---|\n" + src_rows)

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
    out.append(f"**Internship / stipend-program funnel:** fetched {f.get('fetched', 0)}\n")
    if f.get("outcomes"):
        out.append(_counts_table("Internship outcomes", f["outcomes"]))
    if f.get("rejected_samples"):
        rows = "".join(
            f"| {_md(s['title'])} | {_md(s['company'])} | {_md(s['location'])} | {_md(s['reason'])} | {_md(s['evidence'])} |\n"
            for s in f["rejected_samples"]
        )
        out.append("| title | company | location | reason | evidence |\n|---|---|---|---|---|\n" + rows)

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


def _sum_counts(dicts) -> dict[str, int]:
    total: dict[str, int] = {}
    for d in dicts:
        for k, v in (d or {}).items():
            total[k] = total.get(k, 0) + v
    return total


def render_heartbeat_md(records: list[dict], extra: list[str] | None = None) -> str:
    """Weekly heartbeat: the funnel summed over the given run records (newest first) plus their
    near misses, so silence is distinguishable from failure. `extra` lines are appended verbatim."""
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
        out.append(f"**Internship / stipend-program records fetched (7 runs):** {f_fetched}\n")
        out.append(_counts_table("Internship outcomes (7 runs)",
                                 _sum_counts(r.get("internship_funnel", {}).get("outcomes") for r in records)))
        best: dict[tuple, dict] = {}
        for r in records:
            for n in r.get("near_misses", []):
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
