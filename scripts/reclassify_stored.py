"""S2 acceptance — re-classify every stored row with the current eligibility rules (read-only).

A row FAILS when it gets a positive category although its location names only places outside the
user's scope. The oracle is deliberately independent of the classifier: a location fails it when it
contains none of the user/region/worldwide words and is not a plain "Remote".

Usage:  PYTHONPATH=src python scripts/reclassify_stored.py [path/to/scout.db]
"""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter

from job_scout.config import AppConfig
from job_scout.eligibility import classify_eligibility
from job_scout.models import EligibilityCategory, EmploymentType, Opportunity, RemoteStatus

POSITIVE = {
    EligibilityCategory.STIPEND_PROGRAM_GLOBAL,
    EligibilityCategory.WORLDWIDE_REMOTE,
    EligibilityCategory.REMOTE_REGION_INCLUDES_USER,
}
_OPEN_WORDS = ("ethiopia", "addis", "africa", "emea", "worldwide", "global", "anywhere", "international")


def names_only_elsewhere(location: str | None) -> bool:
    loc = (location or "").lower().strip()
    if loc in ("", "remote"):
        return False
    return not any(w in loc for w in _OPEN_WORDS)


def reclassify(db_path: str) -> tuple[list[dict], Counter]:
    profile = AppConfig.load("config/profile.yaml").profile
    rows = sqlite3.connect(db_path).execute("SELECT raw FROM opportunities").fetchall()
    results, counts = [], Counter()
    for (raw,) in rows:
        d = json.loads(raw)
        o = Opportunity(
            title=d["title"], company=d["company"], apply_url=d["apply_url"], canonical_url=d["canonical_url"],
            ats_provider=d.get("ats_provider"), ats_job_id=d.get("ats_job_id"), location_raw=d.get("location_raw"),
            remote_status=RemoteStatus(d.get("remote_status", "unknown")),
            employment_type=EmploymentType(d.get("employment_type", "unknown")), description=d.get("description", ""),
        )
        e = classify_eligibility(o, profile)
        before = (d.get("eligibility") or {}).get("category")
        bad = e.category in POSITIVE and names_only_elsewhere(o.location_raw)
        counts[(before, e.category.value)] += 1
        results.append({"title": o.title, "company": o.company, "location": o.location_raw, "before": before,
                        "after": e.category.value, "confidence": e.confidence, "bad": bad})
    return results, counts


def main() -> int:
    results, counts = reclassify(sys.argv[1] if len(sys.argv) > 1 else "data/scout.db")
    for (before, after), n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"{n:3d}  {before} → {after}")
    positives = [r for r in results if r["after"] in {c.value for c in POSITIVE}]
    print(f"\nrows={len(results)}  positive after={len(positives)}")
    for r in positives:
        print(f"  + {r['title']} @ {r['company']} | {r['location']} → {r['after']} {r['confidence']}")
    bad = [r for r in results if r["bad"]]
    print(f"positive rows whose location names only non-user places: {len(bad)}")
    for r in bad:
        print(f"  ! {r['title']} | {r['location']} → {r['after']}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
