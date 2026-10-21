"""Label report (spec 2026-10-21 §4.8, criterion 5.5): from data/labels.jsonl joined with the store, the
share of each section's items labelled apply or maybe. A key's latest label counts; the section is read
from the stored record (its eligibility and title as last scored).

    PYTHONPATH=src python scripts/label_report.py [--since 2026-10-26] [--db data/scout.db] [--labels data/labels.jsonl]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter

from job_scout.labels import latest, read_labels
from job_scout.models import Eligibility, EligibilityCategory, EmploymentType, Opportunity, Relevance
from job_scout.notify import ACTIONABLE, CHECK_ELIGIBILITY, SECTIONS, section_of


def _opp(d: dict) -> Opportunity:
    o = Opportunity(title=d["title"], company=d["company"], apply_url=d["apply_url"], canonical_url=d["canonical_url"],
                    description=d.get("description") or "", employment_type=EmploymentType(d["employment_type"]),
                    location_raw=d.get("location_raw"))
    if e := d.get("eligibility"):
        o.eligibility = Eligibility(EligibilityCategory(e["category"]), e["confidence"], e["evidence"])
    if r := d.get("relevance"):
        o.relevance = Relevance(r["score"], r["matched_signals"], r["concerns"], r.get("semantic_similarity"))
    return o


def report(labels: list[dict], db_path: str) -> str:
    conn = sqlite3.connect(db_path)
    by_section: dict[str, Counter] = {s: Counter() for s in SECTIONS}
    missing = 0
    for key, ln in latest(labels).items():
        row = conn.execute("SELECT raw FROM opportunities WHERE key = ?", (key,)).fetchone()
        if row is None:
            missing += 1          # e.g. the seeded delivery-test item
            continue
        by_section[section_of(_opp(json.loads(row[0])))][ln["decision"]] += 1
    out = ["| section | labelled | apply | maybe | skip | apply+maybe |", "|---|--:|--:|--:|--:|--:|"]

    def row_of(name: str, c: Counter) -> str:
        n = sum(c.values())
        share = f"{(c['apply'] + c['maybe']) / n:.0%}" if n else "—"
        return f"| {name} | {n} | {c['apply']} | {c['maybe']} | {c['skip']} | {share} |"

    out += [row_of(s, by_section[s]) for s in SECTIONS]
    out.append(row_of(f"**{ACTIONABLE} + {CHECK_ELIGIBILITY}**", by_section[ACTIONABLE] + by_section[CHECK_ELIGIBILITY]))
    if missing:
        out.append(f"\n{missing} labelled key(s) not in the store (not counted).")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/scout.db")
    ap.add_argument("--labels", default="data/labels.jsonl")
    ap.add_argument("--since", help="only labels on or after this date (YYYY-MM-DD)")
    args = ap.parse_args()
    labels = [ln for ln in read_labels(args.labels) if not args.since or ln["labelled_at"] >= args.since]
    print(report(labels, args.db))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
