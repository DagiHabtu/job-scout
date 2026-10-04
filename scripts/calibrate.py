"""S5 calibration report — role_family_ok on the golden set, and (if the model loads) title-only
similarity for positives vs negatives, plus C3's confirming test: title-only vs title+description
spread on stored GitLab rows. Read-only; never run in CI.

Usage:  PYTHONPATH=src python scripts/calibrate.py
"""

from __future__ import annotations

import csv
import json
import sqlite3
import statistics
from pathlib import Path

from job_scout.config import AppConfig
from job_scout.score import load_model, role_family_ok

ROOT = Path(__file__).resolve().parents[1]


def _q(xs: list[float]) -> str:
    xs = sorted(xs)
    pick = lambda p: xs[min(len(xs) - 1, int(p * len(xs)))]  # noqa: E731
    return f"n={len(xs)} p10={pick(.1):.3f} p50={pick(.5):.3f} p90={pick(.9):.3f}"


def main() -> None:
    rows = list(csv.DictReader((ROOT / "tests/fixtures/golden_titles.csv").open(encoding="utf-8")))
    tp = sum(role_family_ok(r["title"]) and r["label"] == "1" for r in rows)
    fp = sum(role_family_ok(r["title"]) and r["label"] == "0" for r in rows)
    fn = sum((not role_family_ok(r["title"])) and r["label"] == "1" for r in rows)
    print(f"role_family_ok on {len(rows)} golden titles: precision={tp / (tp + fp):.3f} recall={tp / (tp + fn):.3f}")
    for r in rows:
        if role_family_ok(r["title"]) != (r["label"] == "1"):
            print(f"  miss (label={r['label']}): {r['title']}")

    cfg = AppConfig.load(ROOT / "config/profile.yaml")
    model = load_model(cfg.scoring.embedding_model)
    if model is None:
        print("model unavailable — similarity section skipped")
        return
    import numpy as np

    roles = model.encode(cfg.profile.target_roles, normalize_embeddings=True)

    def sim(texts):
        v = model.encode(texts, normalize_embeddings=True)
        return (v @ roles.T).max(axis=1)

    pos = [r["title"] for r in rows if r["label"] == "1"]
    neg = [r["title"] for r in rows if r["label"] == "0"]
    print(f"title-only similarity  positives: {_q(list(sim(pos)))}")
    print(f"title-only similarity  negatives: {_q(list(sim(neg)))}")

    db = sqlite3.connect(ROOT / "data/scout.db")
    gl = [json.loads(r[0]) for r in db.execute("SELECT raw FROM opportunities WHERE company='GitLab'")][:10]
    if gl:
        blob = " ".join([*cfg.profile.target_roles, *cfg.profile.target_technologies])
        b = model.encode([blob], normalize_embeddings=True)[0]
        full = model.encode([f"{d['title']}. {d['description']}" for d in gl], normalize_embeddings=True) @ b
        title = sim([d["title"] for d in gl])
        print(f"C3 check on {len(gl)} GitLab rows:")
        print(f"  old (profile blob vs title+description): sd={statistics.pstdev(full):.3f} range={np.ptp(full):.3f}")
        print(f"  new (title vs target roles, max):        sd={statistics.pstdev(title):.3f} range={np.ptp(title):.3f}")
        for d, f, t in zip(gl, full, title):
            print(f"    {f:.3f} → {t:.3f}  {d['title']}")


if __name__ == "__main__":
    main()
