# Job Scout — Plan

An autonomous, **$0**, single-user agent that periodically discovers internship / entry-level
opportunities, evaluates them for **relevance** AND **eligibility** (the user is in Ethiopia),
deduplicates, ranks, persists, and presents a digest — repeatedly, without babysitting.

It is a **deterministic pipeline with a narrow local-ML component**, not an agentic loop.

---

## 1. The two things that shaped this design

- **Zero cost is a hard constraint**, including no paid LLM API. → Relevance judgment comes from a
  **local sentence-embedding model** (semantic similarity beyond keyword overlap), not an LLM.
  Reasoning is legible from **deterministic signals**, not narrated by a model. An optional local
  LLM enriches but is never required.
- **Location (Ethiopia) makes eligibility the real axis.** "Remote" rarely means "remote from
  anywhere." Eligibility is usually *undeterminable from the posting*, so it is modeled as
  `{category, confidence, evidence}` with `unknown` first-class. Eligibility **gates rank**.

The single highest-value insight: for someone in Ethiopia the best-fit class is **global
open-source stipend programs** (Outreachy, GSoC), which *structurally* bypass work-authorization,
EoR, and FX problems (stipend, not employment). These are a small set of **known recurring
programs**, encoded as a first-class source — not scraped.

---

## 2. Phases and gates

| Phase | Goal | Exit gate |
|---|---|---|
| **0 — Spine** | Define + freeze the shared interface; make one vertical slice run end-to-end on **fixtures**, locally. | **Gate 0** — spine frozen; slice (one source → normalize → eligibility → embed-score → dedupe → persist → digest) runs green on fixtures. Fan-out FORBIDDEN before this. |
| **1 — Live** | Run the slice against **real** ATS APIs + the real embedding model in the user's environment; confirm `$0`. | **Gate 1** — live end-to-end run produces a real, correctly-ranked digest at `$0`. (This gate cannot be crossed inside the web sandbox — no live net, no model download. It runs in Claude Code / locally.) |
| **2 — Breadth** | Fan out: more source adapters, the aggregator discovery layer, the known-programs source, notification polish. | Coverage + freshness targets in STATE. |
| **3 — Operate** | Scheduling + persistence on free infra; observability; failure isolation hardened. | `$0` operating mode verified end-to-end (see §Definition of done). |

**Freeze-before-fan-out is the load-bearing rule.** Only the spine-architect touches the spine
until Gate 0. After it freezes, adapters and the hard-logic pieces fan out in parallel.

---

## 3. Spine (the frozen interface) — the alphabet everything else is written in

Defined in code; **changing any of these after Gate 0 requires the spine-architect + a
`Decisions that override PLAN` entry in STATE.md.**

- **`Opportunity`** (`src/job_scout/models.py`) — the canonical record every source normalizes into
  and every stage reads. Identity fields (`ats_provider`, `ats_job_id`, `canonical_url`,
  `content_fingerprint`), core fields, and *derived* fields (`eligibility`, `relevance`,
  lifecycle, provenance). Honest nulls: `remote_status`/`employment_type` carry `UNKNOWN` as a real
  value; `salary_is_estimated` marks aggregator-predicted pay.
- **`Source` protocol** (`src/job_scout/sources/base.py`) — one adapter per source. `fetch(cfg)
  -> list[Opportunity]`, filling only the fields THAT source knows; derived fields are the
  pipeline's job. Never raises on one bad record (skip + log); MAY raise on total source failure
  (the pipeline isolates it). Uses only free endpoints.
- **Pipeline stage signatures** (`src/job_scout/pipeline.py`), FROZEN order:
  `discover → normalize → dedupe(within-run) → classify_eligibility → hard_filter → score(survivors)
   → rank → reconcile/persist → notify(new/changed only)`.
  Order is load-bearing: eligibility is classified before hard-filter (which drops confident
  negatives); hard-filter precedes the embedding step so we never spend compute on dead-on-arrival
  postings; persist runs after scoring so the stored record is fully scored (the content-hash diff
  is score-independent, so lifecycle is unaffected); notify reads the diff persist emits. (This is
  a small refinement of the originally-drafted order — `reconcile` moved to sit with `persist`
  after `score`; see STATE §Decisions #2.)
- **SQLite schema** (`src/job_scout/store.py`) — the persistence + lifecycle-diff contract.

---

## 3.1 Implementation status (authoritative live detail in STATE.md)

**Gate 1 is PASSED** (real live run at `$0`, correctly ranked, idempotent) **and the spine is
FROZEN** (unchanged since Gate 0). `pytest -q` → 57 passing. The Greenhouse adapter is live-verified
and the MiniLM model is wired. See STATE.md §Live verification for executed evidence. Summary:

- **Verified by tests (the deterministic core + spine):** `models.py`, `sources/base.py`,
  `config.py`, `eligibility.py`, `normalize.py`, `score.py`, `store.py`, `dedupe.py`. Two recovered
  defects were fixed in place and regression-tested: the `dedupe` merge-propagation bug (richer
  second occurrence now wins with unioned provenance) and an `eligibility` country-code substring
  bug (`"et"` matched inside words, masking a foreign-auth requirement → now word-boundary matched).
- **Built and wired:** `pipeline.py` (`run_once` + `RunSummary`, per-source failure isolation),
  `notify.py` (`select_for_notification` + HTML digest), the CLI (`cli.py`/`__main__.py`, lazy
  source registry, `job-scout` console script), `tests/` + `tests/fixtures/gate0.py` (`FakeSource`).
- **Sources (Phase 2, all live-verified):** `greenhouse`, `lever`, `ashby` (each with a recorded
  fixture + hermetic tests, sharing `sources/_http.py` + `_text.py`), and the curated
  `known_programs` (Outreachy/GSoC/MLH). Registered in `cli._REGISTRY`.
- **Operations (Phase 3, written):** `.github/workflows/scout.yml` — daily $0 run, commit-DB-back
  keepalive, digest artifact. Awaits activation on a real GitHub repo.
- **Next:** Adzuna discovery layer (needs a free API key); hard-logic follow-ups (GONE detection,
  eligibility precision, threshold calibration).
- **Replace (discard):** none.

The freeze-before-fan-out rule has now been satisfied: the spine is frozen, so adapters and the
hard-logic pieces may proceed in parallel against the frozen `Source` protocol.

---

## 4. Discovery strategy (two modes + known programs)

Verified facts live in STATE §Verified external facts so a fresh session need not re-search.

- **Mode A — deep, company-scoped, high quality:** poll **ATS public JSON APIs** (Greenhouse,
  Lever, Ashby, Workable). No auth for reads, stable IDs, full descriptions, `$0`. Coverage bounded
  by a curated company list (an asset the system maintains).
- **Mode B — broad, keyword-searchable discovery:** a **legal aggregator** (Adzuna free key,
  ~1,000 calls/month). Thin records + dupes + predicted salary, so it is a **discovery / market
  signal** layer, not a record source.
- **The hybrid move:** spend Mode B's quota on *finding new companies*, then poll their ATS board
  for the clean record (free). Discovery finds the door; the ATS API gives the data behind it.
- **Known global programs:** Outreachy, GSoC, and kin — encoded as a small curated source with
  their windows + eligibility, surfaced when a window opens. Not scraped.

---

## 5. Scoring (no paid ML)

Deterministic, three layers, all `$0`:

1. **Hard-constraint filter** (binary, disqualifying): confident work-auth-required, wrong
   employment type, deadline passed, geographically impossible. Runs first.
2. **Lexical signal extraction** (skill/keyword dictionaries, seniority regex): cheap, and the
   source of *legible* match reasons.
3. **Embedding similarity** (local sentence-transformer, MiniLM-class, CPU): the semantic relevance
   an LLM used to provide. Deterministic, testable.

`Relevance = {score, matched_signals, concerns, semantic_similarity}` — a composite with legible
components, never a bare number. **Eligibility gates rank**: a confident can't-hire-you opportunity
never outranks an equally-relevant can-hire-you one; timezone overlap (EAT ≈ EU, far from US) and
confident worldwide-remote are boosts. Optional local LLM adds prose reasoning when present.

Cost control: hard-filter before embedding; cache embedding verdicts by
`(content_hash, profile_version)`.

---

## 6. Zero-cost operations (definition of done)

- **Scheduling + hosting:** GitHub Actions scheduled workflow (public repo → unlimited free
  minutes; private → 2,000 free min/month; a daily job is trivial either way) **or** local
  cron / systemd timer. The DB is committed back to the repo each run — which also keeps the
  schedule alive (Actions auto-disables inactive public-repo schedules at 60 days). Cron is UTC and
  best-effort (15–60 min delays are normal, fine for a daily scout); pin `Africa/Addis_Ababa` via
  the per-schedule timezone field; activate a new repo's schedule once via `workflow_dispatch`.
- **Notifications:** file-first — an HTML/Markdown digest committed to the repo (viewable on
  GitHub) or written locally, zero external dependency. Gmail SMTP with an app password is the
  optional free email upgrade (requires 2FA + app password).
- **Discovery quota:** Adzuna free key ~1,000 calls/month, spent on discovery not records → capped
  and documented, not hidden.
- **Model:** the embedding weights download once from HuggingFace (fine locally / in Actions;
  **not reachable from the web sandbox** — see STATE).

---

## 7. Agent roster (model tiering + least privilege)

Definitions in `.claude/agents/`. Models are **pinned to exact versions** (the `opus`/`sonnet`
aliases drift to newest). Reviewers are read-only. Every agent STOPs and escalates rather than
guessing past a subtle question.

| Agent | Model | Effort | Tools | Scope |
|---|---|---|---|---|
| `spine-architect` | `claude-opus-4-8` | high | Read/Write/Edit/Bash/Glob/Grep | Owns the spine. **Serial, Phase 0 only.** |
| `hard-logic-builder` | `claude-opus-4-8` | high | Read/Write/Edit/Bash/Glob/Grep | Genuinely subtle correctness: eligibility classifier, dedup / entity-resolution, embedding scorer. |
| `source-adapter-builder` | `claude-opus-4-6` | medium | Read/Write/Edit/Bash/Glob/Grep | ONE source adapter against the frozen `Source` protocol + fixtures. Parallel after Gate 0. Does not touch the spine. |
| `fixtures-and-scaffolding` | `claude-sonnet-5` | low | Read/Write/Edit/Glob/Grep | Recorded fixtures, config schemas, docs, mechanical refactors, **test stubs only**. No design decisions. |
| `pipeline-reviewer` | `claude-opus-4-6` | high | Read/Grep/Glob | Read-only review; escalates cross-cutting / subtle correctness → Opus 4.8. |

**Before each phase decide:** (1) what needs strong reasoning; (2) what is delegable; (3) which
model suffices; (4) what must stay serial because of shared state. Do not have two agents redesign
the same component. **Every dispatched agent's acceptance criteria include writing back to
`STATE.md`** — this is a deliverable, not an expectation.

---

## 8. Testing

- **Unit** on the deterministic core where bugs hide: normalization (date/location edge cases),
  dedupe (fuzzy cases, blocking-by-company), eligibility classification, lifecycle transitions,
  ranking order.
- **Adapters** against **recorded real fixtures** (saved JSON) — hermetic, catch parser regressions.
- **Embedding component**: test the contract (valid output, graceful handling of degenerate input);
  a few golden real-model checks run manually, out of CI (nondeterminism + no CI model download).
- **End-to-end**: one integration test running the whole pipeline over fixture sources into a temp
  DB, asserting dedupe + digest render. This is Gate 0's executable target.

---

## 9. Risks (ranked)

1. **Discovery fragility** → structured public APIs; any HTML scraping is quarantined, expected to
   break, isolated per-adapter.
2. **Over-notification kills usefulness** (the real *product* risk) → relevance+eligibility
   threshold, new/changed gating, `notified_at` state.
3. **Eligibility mislabeling** → confidence + `unknown` first-class; hard-exclude only confident
   negatives; surface uncertainty.
4. **Bad dedupe merges** → conservative fuzzy threshold, block by company, retain all provenance.
5. **Stale `gone` detection** → only mark gone when the *source succeeded* but the posting was
   absent, for K consecutive successful runs.
