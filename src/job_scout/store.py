"""Persistence + lifecycle diffing — SQLite (embedded, transactional, zero-ops, $0).

The schema is the persistence contract (part of the frozen spine). Reconciliation diffs the current
run against stored state to assign NEW / UPDATED / ACTIVE and to preserve `notified_at` so an
opportunity is never notified twice.

Scope note (Phase 0): GONE detection requires cross-run absence tracking against a
SUCCESSFULLY-fetched source and is deferred to the hard-logic-builder (flagged in STATE). EXPIRED
is handled at filter time from the deadline. NEW/UPDATED/ACTIVE are implemented and tested here.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict
from datetime import date, datetime, timezone
from enum import Enum

from .models import EmploymentType, Lifecycle, Opportunity, Provenance, RemoteStatus

SCHEMA = """
CREATE TABLE IF NOT EXISTS opportunities (
    key           TEXT PRIMARY KEY,      -- ats identity if present, else content fingerprint
    title         TEXT NOT NULL,
    company       TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    content_hash  TEXT NOT NULL,         -- hash of the fields whose change means "updated"
    status        TEXT NOT NULL,
    first_seen    TEXT NOT NULL,
    last_seen     TEXT NOT NULL,
    notified_at   TEXT,
    raw           TEXT NOT NULL          -- full serialized Opportunity (best-effort JSON)
);
CREATE TABLE IF NOT EXISTS runs (
    run_id     TEXT PRIMARY KEY,
    started    TEXT NOT NULL,
    finished   TEXT,
    summary    TEXT
);
"""


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _identity_key(opp: Opportunity) -> str:
    if opp.ats_provider and opp.ats_job_id:
        return f"{opp.ats_provider}:{opp.ats_job_id}"
    return opp.content_fingerprint


def _content_hash(opp: Opportunity) -> str:
    basis = f"{opp.title}|{opp.description}|{opp.deadline}|{opp.canonical_url}"
    return hashlib.sha256(basis.encode()).hexdigest()[:16]


def _serialize(opp: Opportunity) -> str:
    def default(o):
        if isinstance(o, Enum):
            return o.value
        if isinstance(o, datetime):
            return o.isoformat()
        return str(o)

    return json.dumps(asdict(opp), default=default)


def upsert_and_reconcile(conn: sqlite3.Connection, opps: list[Opportunity], run_id: str) -> dict[str, int]:
    """Diff `opps` against stored state; set each opp.status; persist. Returns lifecycle counts."""
    now = datetime.now(timezone.utc).isoformat()
    counts = {"new": 0, "updated": 0, "active": 0}
    for opp in opps:
        key = _identity_key(opp)
        chash = _content_hash(opp)
        row = conn.execute("SELECT content_hash, first_seen, notified_at FROM opportunities WHERE key = ?", (key,)).fetchone()
        if row is None:
            opp.status = Lifecycle.NEW
            counts["new"] += 1
            conn.execute(
                "INSERT INTO opportunities (key,title,company,canonical_url,content_hash,status,first_seen,last_seen,notified_at,raw)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (key, opp.title, opp.company, opp.canonical_url, chash, opp.status.value, now, now, None, _serialize(opp)),
            )
        else:
            if row["notified_at"]:
                opp.notified_at = datetime.fromisoformat(row["notified_at"])
            if row["content_hash"] != chash:
                opp.status = Lifecycle.UPDATED
                counts["updated"] += 1
            else:
                opp.status = Lifecycle.ACTIVE
                counts["active"] += 1
            conn.execute(
                "UPDATE opportunities SET title=?,company=?,canonical_url=?,content_hash=?,status=?,last_seen=?,raw=? WHERE key=?",
                (opp.title, opp.company, opp.canonical_url, chash, opp.status.value, now, _serialize(opp), key),
            )
    conn.commit()
    return counts


def first_seen_of(conn: sqlite3.Connection, opps: list[Opportunity]) -> list[datetime | None]:
    """The stored `first_seen` of each record (None if not stored) — the truth for "first seen", since
    `discovered_date` is re-stamped every run."""
    out = []
    for opp in opps:
        row = conn.execute("SELECT first_seen FROM opportunities WHERE key = ?", (_identity_key(opp),)).fetchone()
        out.append(datetime.fromisoformat(row["first_seen"]) if row else None)
    return out


def _deserialize(raw: str) -> Opportunity:
    """A stored record's source fields (eligibility/relevance are re-derived by the pipeline)."""
    d = json.loads(raw)
    day = lambda v: date.fromisoformat(v[:10]) if v else None  # noqa: E731
    return Opportunity(
        title=d["title"], company=d["company"], apply_url=d["apply_url"], canonical_url=d["canonical_url"],
        ats_provider=d.get("ats_provider"), ats_job_id=d.get("ats_job_id"),
        content_fingerprint=d.get("content_fingerprint") or "", location_raw=d.get("location_raw"),
        remote_status=RemoteStatus(d.get("remote_status") or "unknown"),
        employment_type=EmploymentType(d.get("employment_type") or "unknown"),
        description=d.get("description") or "", technologies=d.get("technologies") or [],
        posting_date=day(d.get("posting_date")), deadline=day(d.get("deadline")), salary_raw=d.get("salary_raw"),
        salary_is_estimated=bool(d.get("salary_is_estimated")),
        provenance=[Provenance(p["source"], p["url"], datetime.fromisoformat(p["first_seen"]) if p.get("first_seen") else None)
                    for p in d.get("provenance") or []],
        history=d.get("history") or [],
    )


def pending_stored(conn: sqlite3.Connection, since: date, fetched: list[Opportunity]) -> list[Opportunity]:
    """Never-notified records first seen on or after `since` that this run did not fetch (status ACTIVE):
    a weekday deferral must still reach Monday's digest when Monday's fetch no longer returns it
    (spec 2026-10-21 §4.6 pending pool; branch review H1)."""
    seen = {_identity_key(o) for o in fetched}
    out = []
    for row in conn.execute("SELECT key, first_seen, raw FROM opportunities WHERE notified_at IS NULL"):
        if row["key"] in seen or datetime.fromisoformat(row["first_seen"]).date() < since:
            continue
        opp = _deserialize(row["raw"])
        opp.status = Lifecycle.ACTIVE
        out.append(opp)
    return out


def mark_notified(conn: sqlite3.Connection, opps: list[Opportunity]) -> None:
    now = datetime.now(timezone.utc)
    for opp in opps:
        opp.notified_at = now
        conn.execute("UPDATE opportunities SET notified_at=? WHERE key=?", (now.isoformat(), _identity_key(opp)))
    conn.commit()


def recent_runs(conn: sqlite3.Connection, n: int = 7) -> list[dict]:
    """The last `n` run records (`RunSummary.as_record()`), newest first."""
    rows = conn.execute("SELECT summary FROM runs ORDER BY started DESC LIMIT ?", (n,)).fetchall()
    return [json.loads(r["summary"]) for r in rows if r["summary"]]


def record_run(conn: sqlite3.Connection, run_id: str, started: str, summary: dict) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO runs (run_id, started, finished, summary) VALUES (?,?,?,?)",
        (run_id, started, datetime.now(timezone.utc).isoformat(), json.dumps(summary)),
    )
    conn.commit()
