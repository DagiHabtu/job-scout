# Job Scout — Project Kernel

**The conversation is NEVER the source of truth.** Four durable artifacts are, in strict order:

1. `CLAUDE.md` — these hard constraints (this file; keep it short)
2. `PLAN.md` — the full plan: phases, gates, the frozen spine, agent roster, risks
3. `STATE.md` — live cursor: current position, gate status, single next action, resume note
4. the code — what actually runs

**After any compaction or context reset, re-read `PLAN.md` and `STATE.md` before doing anything.**

---

## The five hard constraints (never violate)

1. **ZERO COST.** No paid API, hosting, proxy, database, email provider, scheduler, or LLM API
   for ordinary operation. Free tiers only where genuinely sufficient, and their quotas are
   documented in `PLAN.md`. Never design a critical path around "pay for it later." Investigate a
   genuinely free alternative *before* accepting any dependency that could cost money.

2. **ELIGIBILITY IS FIRST-CLASS.** The user is located in Ethiopia (this lives in config, not
   logic). An opportunity that cannot legally or practically hire from the user's location must
   **never outrank** an equally-relevant one that can. Where eligibility cannot be determined
   confidently, **surface the uncertainty** — never silently accept or reject.

3. **DETERMINISTIC CORE, NARROW ML.** The pipeline is deterministic, testable code. The only ML in
   ordinary operation is a **local, free sentence-embedding model** for semantic relevance. There
   is **no agentic "LLM decides the next step" loop.** An optional local LLM (Ollama) MAY enrich
   reasoning but is never a hard dependency; absent it, the system degrades gracefully to
   embeddings + rules.

4. **RESPECT SOURCES.** Public / no-auth APIs, RSS, and legal aggregators only. Honor robots, ToS,
   and rate limits. Do **not** scrape sources that forbid it (LinkedIn, Indeed).

5. **FREEZE BEFORE FAN-OUT.** One serial architect owns the spine — the `Opportunity` schema, the
   `Source` protocol, the pipeline stage signatures, and the SQLite schema — until **Gate 0**. No
   parallel adapter work happens before the spine is frozen. (See `PLAN.md` §Spine and §Agents.)

---

## Compact instructions — preserve the following VERBATIM across any compaction

Working detail may be dropped; these may not.

- The five hard constraints above.
- The FROZEN SPINE below (frozen at Gate 0 — see §Frozen spine).
- The current gate status (read it from `STATE.md`).
- The `$0` operating invariant and the documented free-tier quotas.

Detailed plan → `PLAN.md`. Live status and the single next action → `STATE.md`.

---

## Frozen spine (Gate 0 PASSED — changing any of this needs the spine-architect + a `Decisions that override PLAN` entry in STATE.md)

- **`Opportunity`** (`models.py`): identity (`title`, `company`, `apply_url`, `canonical_url`,
  `ats_provider?`, `ats_job_id?`, `content_fingerprint`) + core (`location_raw?`, `remote_status`,
  `employment_type`, `description`, `technologies[]`, `posting_date?`, `deadline?`, `salary_raw?`,
  `salary_is_estimated`) + derived, pipeline-only (`eligibility?`, `relevance?`) + lifecycle
  (`status`, `provenance[]`, `discovered_date?`, `notified_at?`, `history[]`).
- **Enums, each with first-class `UNKNOWN`**: `EmploymentType`, `RemoteStatus`, `EligibilityCategory`
  (7 values), `Lifecycle`. `DISQUALIFYING_ELIGIBILITY = {REQUIRES_WORK_AUTH, REMOTE_EXCLUDES_USER,
  ONSITE_FOREIGN}` — `UNKNOWN` is NEVER disqualifying. (No `ELIGIBLE_ONSITE_LOCAL` — onsite-in-own-
  country stays `UNKNOWN`@0.4; decided at Gate 0.)
- **Value objects**: `Eligibility{category, confidence, evidence[]}`,
  `Relevance{score, matched_signals[], concerns[], semantic_similarity?}`,
  `Provenance{source, url, first_seen}`.
- **`content_fingerprint(company, title, location)`** = `sha256(canon(company)|canon(title)|
  canon(location))[:16]`; `canon` = lowercase, strip non-alnum, collapse whitespace.
- **`Source` protocol** (`sources/base.py`): `name: str`; `fetch(cfg: SourceConfig) ->
  list[Opportunity]`. Fills only fields the source knows; skip+log one bad record; MAY raise on
  TOTAL failure (never swallow to `[]` — empty means "genuinely nothing").
- **Pipeline stage order** (`pipeline.run_once`): `discover(+provenance) → normalize → dedupe →
  classify_eligibility → hard_filter → score → rank → reconcile/persist → notify`.
- **SQLite schema** (`store.py`): `opportunities(key PK, title, company, canonical_url,
  content_hash, status, first_seen, last_seen, notified_at, raw)` + `runs(run_id PK, started,
  finished, summary)`. Identity key = `"{provider}:{job_id}"` if ATS else `content_fingerprint`;
  `content_hash = sha256(title|description|deadline|canonical_url)[:16]` drives NEW/UPDATED/ACTIVE.
