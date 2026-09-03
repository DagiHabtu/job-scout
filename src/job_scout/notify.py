"""Notification — selection + digest rendering. File-first, $0, zero external dependency.

Two responsibilities, kept separate so both are testable:
  * `select_for_notification` — the gate: an opportunity is worth surfacing iff it is NEW or
    UPDATED this run, clears the relevance threshold, and has not already been notified. This is
    the load-bearing anti-spam rule (over-notification is the real product risk, PLAN §9).
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
from .models import EligibilityCategory, Lifecycle, Opportunity

# Statuses that are worth telling the user about. ACTIVE (seen again, unchanged) is deliberately
# excluded — re-announcing an unchanged posting is exactly the noise we are avoiding.
_NOTIFIABLE = frozenset({Lifecycle.NEW, Lifecycle.UPDATED})

# Confidence at/above which the best-fit class is surfaced regardless of relevance score.
_STIPEND_SURFACE_CONFIDENCE = 0.7


def _is_best_fit_class(opp: Opportunity) -> bool:
    """A confident, structurally-worldwide stipend program — the single best-fit class for a
    location-constrained user (PLAN §1/§5). Its value is its eligibility, not keyword overlap, so it
    is surfaced whenever it appears even if its generic description scores modest relevance. It still
    passes through NEW/UPDATED + not-already-notified gating, so it is announced once, not repeatedly.
    """
    e = opp.eligibility
    return (
        e is not None
        and e.category == EligibilityCategory.STIPEND_PROGRAM_GLOBAL
        and e.confidence >= _STIPEND_SURFACE_CONFIDENCE
    )


def select_for_notification(opps: list[Opportunity], threshold: float) -> list[Opportunity]:
    """new/updated ∧ not already notified ∧ (relevance ≥ threshold OR best-fit class). Order preserved."""
    out: list[Opportunity] = []
    for o in opps:
        if o.status not in _NOTIFIABLE:
            continue
        if o.notified_at is not None:
            continue
        relevant = o.relevance is not None and o.relevance.score >= threshold
        if relevant or _is_best_fit_class(o):
            out.append(o)
    return out


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
