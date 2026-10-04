"""E1 — read-only probe of the Himalayas public job search API (spec §5 E1). Never run in CI.

Four queries, pages 1–3, 1 s apart. Prints per query: totalCount, age histogram, role-family
passes, empty-restriction count, 429s; then per-employer target-class counts (input to the narrow
flywheel) and the PASS/FAIL verdict:
  PASS = ≥10 distinct role_family_ok listings published in the last 30 days, and no 429.

Usage:  PYTHONPATH=src python scripts/probe_himalayas.py
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone

from job_scout.score import role_family_ok

BASE = "https://himalayas.app/jobs/api/search"
QUERIES = (
    "employment_type=Intern&worldwide=true",
    "employment_type=Intern&country=ET",
    "seniority=Entry-level&worldwide=true",
    "seniority=Entry-level&country=ET",
)
HEADERS = {"User-Agent": "job-scout/0.1 (+https://github.com/DagiHabtu/job-scout)"}


def _age_bucket(days: float) -> str:
    for limit in (7, 30, 90):
        if days <= limit:
            return f"<={limit}d"
    return ">90d"


def main() -> int:
    now = datetime.now(timezone.utc).timestamp()
    seen: dict[str, dict] = {}
    any_429 = False
    for q in QUERIES:
        jobs: list[dict] = []
        total, got_429 = None, False
        for page in (1, 2, 3):
            url = f"{BASE}?{q}&sort=recent&page={page}"
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=30) as r:
                    data = json.load(r)
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    got_429 = any_429 = True
                    break
                raise
            finally:
                time.sleep(1)
            total = data.get("totalCount")
            jobs += data.get("jobs", [])
            if len(data.get("jobs", [])) < data.get("limit", 20):
                break
        ages = Counter(_age_bucket((now - j.get("pubDate", 0)) / 86400) for j in jobs)
        rf = [j for j in jobs if role_family_ok(j.get("title", ""))]
        empty = sum(1 for j in jobs if not j.get("locationRestrictions"))
        print(f"\n[{q}] totalCount={total} fetched={len(jobs)} 429={got_429}")
        print(f"  age: {dict(sorted(ages.items()))}")
        print(f"  role_family_ok={len(rf)}  empty locationRestrictions={empty}")
        for j in rf:
            print(f"    - {j['title']} @ {j.get('companyName')} | restr={j.get('locationRestrictions')} "
                  f"| age={(now - j.get('pubDate', 0)) / 86400:.0f}d")
        for j in jobs:
            seen.setdefault(j["guid"], j)

    # Per employer: target-class listings open to the user (no restriction, or naming Ethiopia).
    per_employer: Counter[str] = Counter()
    fresh_rf = 0
    for j in seen.values():
        restr = [str(x).lower() for x in j.get("locationRestrictions") or []]
        open_to_user = not restr or any("ethiopia" in x for x in restr)
        recent = (now - j.get("pubDate", 0)) / 86400 <= 30
        if role_family_ok(j.get("title", "")):
            fresh_rf += recent
            if open_to_user and recent:
                per_employer[j.get("companyName", "?")] += 1
    print(f"\ndistinct listings={len(seen)}  distinct role_family_ok ≤30d={fresh_rf}  any 429={any_429}")
    print("employers with target-class listings open to ET (≤30d):", dict(per_employer.most_common()))
    print("flywheel candidates (≥2):", [c for c, n in per_employer.items() if n >= 2])
    verdict = fresh_rf >= 10 and not any_429
    print("E1 VERDICT:", "PASS" if verdict else "FAIL")
    return 0 if verdict else 1


if __name__ == "__main__":
    sys.exit(main())
