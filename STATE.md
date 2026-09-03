# STATE

Live cursor. Update at **every task boundary** — this is a deliverable of every dispatched agent,
not an afterthought. This file, `PLAN.md`, `CLAUDE.md`, and the code are the source of truth —
never the conversation.

**Last updated:** **DEPLOYED + VERIFIED at `$0`** (Claude Code). The project is live and running on
GitHub Actions: `https://github.com/DagiHabtu/job-scout` (PUBLIC). A `workflow_dispatch` run
succeeded end-to-end — real scout (233 jobs → 1 notified), digest artifact uploaded, `data/scout.db`
committed back by the bot, daily schedule active. Phase-2 sources complete (greenhouse + lever +
ashby + known_programs, all live-verified); **`pytest -q` → 85 passed**; spine unchanged. Adzuna
deferred (needs a free API key; also a discovery-layer design piece, not a copy-paste adapter);
hard-logic tuning deferred pending more real-run evidence (per user). See §Phase 3 and §Live
verification for executed evidence.

**Prior passes:** Gate 1 (live model + greenhouse) → Gate 0 (spine frozen) → recovery.

---

## Current position

| Field | Value |
|---|---|
| **Phase** | 3 — Operations (DEPLOYED); Phase-2 sources complete |
| **Gate status** | **Deployed + verified at `$0`** — GitHub Actions run 33754711547 green; artifact + DB commit-back confirmed |
| **Frozen-spine status** | **FROZEN** — unchanged since Gate 0; signatures in `CLAUDE.md` §Frozen spine |
| **Live repo** | `https://github.com/DagiHabtu/job-scout` (PUBLIC, `main`); workflow `scout` state=active (daily 04:00 UTC ≈ 07:00 EAT) |
| **Environment** | Local dev: Python 3.14.6 venv (`.[dev,embeddings]`). CI: ubuntu-latest, Python 3.12, model cached. |

### Frozen spine (FROZEN at Gate 0 — full signatures in `CLAUDE.md` §Frozen spine)

- `Opportunity`, enums, `Eligibility`/`Relevance`/`Provenance`, `content_fingerprint()` — `models.py`
- `Source` protocol — `sources/base.py` — `fetch(cfg: SourceConfig) -> list[Opportunity]`
- Pipeline stage order — `discover → normalize → dedupe → classify_eligibility → hard_filter → score → rank → reconcile/persist → notify` (refined from the drafted order — see Decisions #2)
- SQLite schema — `store.py`

---

## Live verification (Gate 1) — executed evidence, not narrated

**Real end-to-end run executed** via `python -m job_scout -c config/profile.yaml` against GitLab's
public Greenhouse board (`boards-api.greenhouse.io`, no auth), with the real MiniLM model. `$0`:
public API + local model (one-time free HF download) + SQLite + file digest — nothing paid.

- **Fetch (live):** 234 real jobs from board `gitlab`; board display name resolved from board metadata.
- **Dedupe:** 234 → **201** (real within-run duplicates merged; GitLab posts one role across locations).
- **Eligibility gate:** 201 → **23 survivors**. Region-locked / work-auth roles correctly dropped —
  this is constraint #2 (eligibility-first) working on real data.
- **Scoring (real MiniLM):** model loads and cosine-separates cleanly — `backend-intern`≈**0.68** vs
  `sales-exec`≈**0.13** in isolation; on live data, engineering roles rank above sales, and
  senior/manager roles are correctly down-weighted by the title-scoped penalty.
- **Notify:** **1** genuine match surfaced (Intermediate Fullstack Engineer, worldwide-remote,
  score 0.41) — HTML digest written to `data/digest.html`.
- **Persistence / idempotency:** run 1 → 23 NEW, 1 notified; **run 2 → 23 ACTIVE, 0 notified**
  (no re-spam). Diff-driven lifecycle confirmed on real data.

**Three real defects the live run exposed — all fixed in place + regression-tested** (see Decisions
#4–6):
1. `score.py` penalize-keywords matched as substrings across the whole description → fired on nearly
   every posting ("you'll *lead* …", "*senior* engineers"). Now title-scoped + word-boundaried.
2. `score.py` "semantic model unavailable" caveat was counted as a role concern and silently docked
   0.1 off every lexical-mode score. Now excluded from the numeric penalty.
3. `eligibility.py` generic "global / work-from-anywhere" boilerplate in an employer's description
   rescued roles whose LOCATION field was explicitly Canada/US → false `worldwide_remote`. The
   structured location field is now authoritative over prose (dropped survivors 79 → 23).

**Residual (non-blocking) findings for the hard-logic-builder:**
- A location naming a single foreign country NOT in the exclusion list (e.g. "Bangalore, India") plus
  worldwide boilerplate still classifies `worldwide_remote`. Optimistic but uncertain; could tighten
  to UNKNOWN. Genuinely ambiguous (GitLab is all-remote, hires 65+ countries).
- The digest is rewritten every run, so a quiet run (0 notified) overwrites the last populated
  digest. Fine under the commit-DB-back deployment (git keeps history) but worth a conscious choice.
- Relevance threshold: real MiniLM cosines cluster low (~0.33–0.43); the drafted `0.45` default
  suppressed genuine matches, so `config/profile.yaml` is calibrated to **0.40** (library default
  left at 0.45). Calibrate against more boards before changing the shipped default.

---

## Implementation inventory — Gate 0 status (VERIFIED = tested green)

All KEEP/REWORK modules are now **verified by tests** (45 passing). Do **not** recreate any file
below — extend from it.

| File | Status | Notes |
|---|---|---|
| `models.py` | **VERIFIED** | Frozen spine. `test_models.py`: fingerprint stability/distinctness, disqualifier logic, UNKNOWN never disqualifying. |
| `sources/base.py` | **VERIFIED** | `Source` protocol; contract exercised by `FakeSource` + the Gate-0 slice. |
| `config.py` | **VERIFIED** | pydantic config; imports + used across the suite. |
| `eligibility.py` | **VERIFIED + FIXED** | 14 per-category/edge tests. **Fixed:** country-code `in hay` substring match (`"et"` matched inside `"meetings"`, masking a real foreign-auth requirement) → now word-boundary matched. See Decisions #3. |
| `normalize.py` | **VERIFIED** | `test_normalize.py`: tracking-strip (keeps real job tokens), honest remote inference, fingerprint, discovered_date stamp. |
| `score.py` | **VERIFIED** | `test_score.py`: lexical fallback (+concern flag), prioritized-company boost, `hard_filter` (confident-disqualifier / deadline / unwanted-type, UNKNOWN kept), `rank` (eligibility gates relevance). Weight tuning still owned by hard-logic-builder. |
| `store.py` | **VERIFIED** | `test_store.py`: NEW/UPDATED/ACTIVE, ATS-key precedence, `notified_at` preservation, JSON round-trip (enums/dates/nested). GONE detection still deferred (cross-run absence). |
| `dedupe.py` | **VERIFIED (rework proven)** | Rework (merge into stable first-seen object, union provenance, richer content wins) proven by `test_dedupe.py` incl. the richer-second-occurrence regression + company blocking. |
| `pipeline.py` | **DONE** | `run_once` orchestration + `RunSummary`; per-source failure isolation; provenance stamping. Frozen stage order. Green via `test_pipeline.py`. |
| `notify.py` | **DONE** | `select_for_notification` (new/updated ∧ ≥ threshold ∧ not notified) + `render_digest`/`write_digest` (self-contained HTML). |
| CLI (`cli.py` + `__main__.py`) | **DONE** | Idempotent single-run; lazy source registry (empty until adapters land); `job-scout` console script. Clean empty-pass verified. |
| `tests/` + `tests/fixtures/gate0.py` | **DONE** | `FakeSource` + Gate-0 fixtures; e2e slice is `test_pipeline.py`. |
| `sources/greenhouse.py` | **VERIFIED (live)** | Stdlib-only adapter (urllib/json), injectable `fetch_json`, per-board isolation, HTML→text. Recorded fixture `tests/fixtures/greenhouse_board.json`; 9 hermetic tests (`test_greenhouse.py`) incl. pipeline composition. Registered in `cli._REGISTRY`. Ran live against `gitlab`. |
| `sources/known_programs.py` | **VERIFIED (live)** | Curated, offline, date-driven `Source` (Outreachy/GSoC/MLH) → `STIPEND_PROGRAM_GLOBAL`. Injectable `today`; auto-expiry via `deadline`; 8 tests (`test_known_programs.py`). Registered + enabled in `profile.yaml`. Real run today surfaces 0 (honest, between cycles); dated demo surfaces 3 at top tier, all notified. |
| `sources/_http.py`, `sources/_text.py` | **DONE** | Shared stdlib helpers: `get_json` (JSON-or-raise; HTML → total failure) and `html_to_text`. Greenhouse refactored to use both. |
| `sources/lever.py` | **VERIFIED (live)** | Adapter for `api.lever.co/v0/postings/{site}?mode=json` (JSON array; maps `categories`/`workplaceType`/`descriptionPlain`). Defensive: non-array/HTML → total failure. Recorded fixture (`lever_postings.json` from `leverdemo`); 11 tests (`test_lever.py`). Registered in `_REGISTRY`. |
| `.github/workflows/scout.yml` | **DONE** | Daily scheduled run (04:00 UTC ≈ 07:00 EAT) + `workflow_dispatch`; `contents:write`; installs `.[dev]` + optional `.[embeddings]` (graceful $0 fallback); caches HF model; uploads digest artifact; commits `data/scout.db` back (persistence + keepalive). YAML validated. |
| `sources/ashby.py` | **VERIFIED (live)** | Adapter for `api.ashbyhq.com/posting-api/job-board/{org}` (`{"jobs":[...]}`; maps `employmentType`/`workplaceType`+`isRemote`/`location`/`descriptionPlain`; respects `isListed`). Recorded fixture (`ashby_board.json` from `ashby` org); 9 tests (`test_ashby.py`). Registered in `_REGISTRY`. |
| `sources/adzuna.py` | **NEXT (blocked on key)** | Discovery layer (free `app_id`/`app_key`, ~1k calls/mo — a user secret). Used to FIND boards to poll, not as a record source. Cannot be live-verified here without the key. |

**REPLACE (discard): none.**

**KEEP AS-IS (complete documents, no execution needed):** `CLAUDE.md`, `PLAN.md`, this file,
`README.md`, `.claude/agents/*`, `.claude/settings.json`, `pyproject.toml`,
`config/profile.example.yaml`, `.env.example` (this recovery pass updated PLAN.md + STATE.md).

### Correctness target (Gate 0) — executable, not narrated

The vertical slice runs green **on fixtures**, locally, with **no network and no model**:
`FakeSource` (fixtures) → normalize → classify_eligibility → hard_filter → score (lexical fallback)
→ dedupe → upsert_and_reconcile (temp DB) → render digest. Asserts: confident disqualifiers
filtered; the cross-source duplicate merged with **unioned provenance** (this also proves the
`dedupe` rework); a stipend program and a worldwide-remote role outrank an unknown-eligibility one;
a second run marks records ACTIVE, not NEW.

## Single next action

**Deployed + verified at `$0`. The core project is COMPLETE and operating.** Remaining items are
optional and were consciously deferred:

1. **Observe scheduled runs** (no action needed): over the next days confirm the digest evolves and
   NEW→ACTIVE reconciliation holds. The DB commits back each run.
2. **Adzuna discovery layer — DEFERRED.** Blocked on the user's free `app_id`/`app_key` (so no real
   recorded fixture, unlike every other adapter) AND it is a Mode-B *discovery* design piece
   (find companies → feed the ATS adapters), not a record-source adapter (PLAN §4). Build it when a
   key is provided, with a real fixture. Not built on a guessed shape.
3. **Hard-logic tuning — DEFERRED per user** until more real-run evidence: GONE detection; tighten
   single-foreign-city + boilerplate → UNKNOWN; digest-overwrite-on-quiet-run policy; threshold
   calibration across more boards. (All logged in §Known defects / §Live verification residuals.)
4. **More boards/sites/orgs**: the user can widen coverage by editing `config/profile.yaml`
   (`greenhouse_boards`, `lever_sites`, `ashby_orgs`) and pushing — no code change.

Do not edit the frozen spine without a spine-architect pass + a Decisions entry here.

## What was actually run

**Gate 0 (fixtures, offline):** `-e .[dev]` installed; all modules import; CLI empty pass; the
fixtures slice green.

**Gate 1 (live, `$0`) — executed this pass:** installed `.[embeddings]` (torch 2.14.0,
sentence-transformers 6.0.1); verified MiniLM loads and cosine-separates (0.68 vs 0.13); recorded a
real Greenhouse fixture from a live GitLab fetch; ran `python -m job_scout -c config/profile.yaml`
live end-to-end (234→201→23→1 notified; run 2 all-ACTIVE, 0 notified). **`pytest -q` → 57 passed.**
Full numbers + the three defects fixed: §Live verification above.

---

## Verified external facts (researched during planning — do not re-search unless stale)

- **Greenhouse:** `GET boards-api.greenhouse.io/v1/boards/{token}/jobs` — public, no auth, JSON;
  `remote` often null. Used by Stripe, GitLab, Airbnb, Anthropic.
- **Lever:** `GET api.lever.co/v0/postings/{slug}?mode=json` — no auth. **Gotcha:** intermittently
  returns HTML even with `mode=json` → parse defensively (soft failure).
- **Ashby / Workable:** same public-JSON pattern; confirm exact endpoints at build.
- **Adzuna:** free `app_id`/`app_key`, ~1,000 calls/month (~33/day). Truncated descriptions,
  `salary_is_predicted`, aggregator dupes → **discovery layer, not a record source.**
- **Ethiopia eligibility:** EoR *does* support ET (RemoFirst, Remote.com, Safeguard Global,
  Playroll, RemotePeople) — but it's the company's unstated choice → per-posting eligibility is
  usually **uncertain**. No digital-nomad visa; tourist visa ≠ work. Real FX friction. EAT (UTC+3)
  overlaps EU well (~1–2h), US poorly (~8–9h).
- **Outreachy:** worldwide, 18+, next round **Dec 7 2026 – Mar 8 2027**, flat **$5,500**;
  ineligible if you've done GSoC/Outreachy before; 30 hrs/week.
- **GSoC:** all non-embargoed countries (ET fine), fully remote, PPP stipend **$3,000–6,600**; must
  be eligible to work in your country of residence. 2026 deadline (~Mar 31) passed → **next is 2027**.
- **GitHub Actions:** public repo → unlimited free minutes; private → 2,000 free min/month. Cron is
  UTC, best-effort (**15–60 min delays normal**), 5-min minimum. **Public-repo schedules auto-disable
  after 60 days inactivity** → committing the DB back each run keeps it alive. New repo needs one
  `workflow_dispatch`. Per-schedule `timezone:` field since Mar 2026 → pin `Africa/Addis_Ababa`.
  Gmail SMTP app-password is free (requires 2FA).

---

## Decisions that override PLAN.md

*(This section wins where it conflicts with PLAN.md.)*

1. **Onsite-in-user's-own-country stays `UNKNOWN` (conf 0.4)** — RESOLVED at Gate 0. No
   `ELIGIBLE_ONSITE_LOCAL` category was added: it is out of scope for the current international
   sources, and `UNKNOWN` with explicit evidence surfaces the case honestly rather than
   miscategorizing it. `EligibilityCategory` is frozen at its 7 values. Revisit only if a source
   that supplies local onsite roles is added.
2. **Frozen pipeline stage order** = `discover → normalize → dedupe → classify_eligibility →
   hard_filter → score → rank → reconcile/persist → notify`. This refines PLAN §3's drafted order
   (which listed `reconcile` before `score`): `content_hash` — which drives the NEW/UPDATED/ACTIVE
   diff — is independent of the relevance score, so persisting AFTER scoring yields identical
   lifecycle diffing while storing the fully-scored record. `classify_eligibility` is named as its
   own stage between `dedupe` and `hard_filter` (hard_filter reads eligibility).
3. **`eligibility.py` country-code match hardened.** The "already authorized in your own country"
   check matched the ISO code as a bare substring; for `ET` that hit inside ordinary words
   (`"meetings"`, `"get"`), silently masking a genuine foreign work-auth requirement. Now matched on
   a word boundary (`\bet\b`), consistent with the module's existing `\bus\b`/`\buk\b` guards. The
   country *name* stays a plain substring (distinctive enough). Regression:
   `test_eligibility.py::test_work_auth_not_masked_by_country_code_substring`.
4. **`score.py` penalize-keywords are title-scoped + word-boundaried** (live-found). A penalize
   keyword names a KIND of role to avoid (senior/staff/manager/clearance) — a title property; the
   old whole-description substring match fired on almost every posting ("you'll *lead* …"). Positive
   signals (tech/prioritize keywords) still scan title+description, now word-boundaried (so "go" no
   longer matches "category"). Regressions: `test_score.py::test_lexical_signals_reward_matches_and_flag_penalties`,
   `::test_word_boundary_prevents_substring_false_matches`.
5. **`score.py` model-availability caveat no longer penalizes the score** (STATE-flagged review,
   live-confirmed). The "semantic model unavailable" note is kept for transparency but excluded from
   the `-0.1 × concerns` role penalty, so lexical-mode scores are comparable to model-mode.
6. **`eligibility.py`: the structured LOCATION field is authoritative over free-text boilerplate**
   (live-found). Generic "global / work-from-anywhere" prose (ubiquitous in all-remote employers'
   descriptions) no longer rescues a role whose `location_raw` explicitly names excluding regions
   (Canada/US/etc.). Regressions: `test_eligibility.py::test_explicit_excluding_location_beats_worldwide_boilerplate`,
   `::test_multiregion_location_including_user_is_kept`. Live impact: survivors 79 → 23.
7. **`score.py` rewards a wanted employment type** (Phase-2). An opportunity whose `employment_type`
   is one the user explicitly lists (`internship`, `stipend_program`) gets a +0.15 structural-match
   boost — a stipend program IS what a stipend-seeker wants even when its generic description names
   no tech. UNKNOWN never boosts. Regression: `test_score.py::test_wanted_employment_type_boosts_score`.
8. **`notify.py` surfaces the best-fit class on eligibility alone** (Phase-2). A confident
   `STIPEND_PROGRAM_GLOBAL` (≥0.7) notifies whenever it is NEW/UPDATED even if its relevance is below
   threshold — its value is structural eligibility, not keyword overlap (PLAN §1/§5). It still passes
   the not-already-notified gate, so it is announced once. Without this, the single best-fit class
   for a location-constrained user would be silently suppressed. Regression:
   `test_known_programs.py::test_best_fit_stipend_surfaces_below_threshold_but_unknown_does_not`.

## Known defects (open — carry until fixed)

*(None blocking. All recovered + live-found defects to date are FIXED and regression-tested — see
Decisions #3–6.)*

- **GONE detection still unimplemented** (`store.py`): needs cross-run absence tracking against a
  SUCCESSFULLY-fetched source for K consecutive runs (`scoring.gone_after_missing_runs`, default 2).
  Deferred to the hard-logic-builder.
- **Eligibility precision (residual):** a single foreign-country location NOT in the exclusion list
  (e.g. "Bangalore, India") + worldwide boilerplate still classifies `worldwide_remote` (optimistic;
  could tighten to UNKNOWN). See §Live verification.
- **Digest overwrite on a quiet run:** each run rewrites `data/digest.html`, so a 0-notified run
  replaces the last populated digest. Acceptable under commit-DB-back (git keeps history); revisit if
  the file digest is the primary surface.

## Phase 0 checklist — COMPLETE (Gate 0)

- [x] Continuity system; agent roster; spine **FROZEN**; reference stage-logic verified by tests
- [x] Scaffold + deps; `pipeline.py` + `notify.py` + CLI wired; `dedupe` rework proven
- [x] Gate-0 fixtures slice green; signatures in `CLAUDE.md`; **GATE 0 PASSED**

## Phase 1 checklist — COMPLETE (Gate 1)

- [x] Greenhouse adapter (stdlib, injectable HTTP, per-board isolation, HTML→text)
- [x] Recorded real fixture + 9 hermetic tests incl. pipeline composition; registered in `_REGISTRY`
- [x] `.[embeddings]` installed; **real MiniLM verified** (loads, cosine-separates 0.68 vs 0.13)
- [x] Three live-found defects fixed + regression-tested (Decisions #4–6)
- [x] **Real live end-to-end run at `$0`** (234→201→23→1 notified; run 2 idempotent)
- [x] **`pytest -q` → 57 passed**; **GATE 1 PASSED**

## Phase 2 checklist — IN PROGRESS (breadth)

- [x] `known_programs.py` (Outreachy/GSoC/MLH) — STIPEND_PROGRAM_GLOBAL; live-verified
- [x] Scoring/notify made stipend-aware (Decisions #7, #8) so the best-fit class actually surfaces
- [x] Shared `sources/_http.py` + `_text.py`; Greenhouse refactored onto them
- [x] `lever.py` (defensive HTML/non-array handling) — live-verified vs `leverdemo`
- [x] `ashby.py` — live-verified vs `ashby` org
- [x] `.github/workflows/scout.yml` — daily $0 run, commit-DB-back keepalive, digest artifact (YAML validated)
- [x] **Capstone multi-source live run** (greenhouse+lever+ashby+known_programs): 311 discovered →
  265 deduped (cross-source) → 26 eligible → 1 notified, correctly ranked. **85 tests pass.**
- [ ] Adzuna discovery layer (blocked on the user's free API key)
- [ ] Hard-logic follow-ups (GONE detection; eligibility precision; threshold calibration)

## Phase 3 (operations) — DEPLOYED + VERIFIED ($0)

**Live:** `https://github.com/DagiHabtu/job-scout` (PUBLIC, `main`). Deployed and end-to-end verified
2026-09-03.

- [x] Safety audit clean — no secrets/keys/tokens, no personal email in tracked files; committed
  with the GitHub noreply identity `142739733+DagiHabtu`; `.venv`/`.env`/egg-info excluded; seed DB
  dropped so the first CI run started fresh; `.gitattributes` forces LF for the Linux runner.
- [x] Code pushed (53 files); workflow pushed after the user granted the `workflow` OAuth scope
  (`gh auth refresh -s workflow` — was blocked on `repo`-only scope).
- [x] **`workflow_dispatch` run 33754711547 SUCCEEDED in 2m30s.** Executed evidence:
  - Run scout: `greenhouse: board gitlab → 233 jobs; discovered=233 deduped=201 survived=23 new=23
    notified=1` (model loaded in CI — matches the local model-backed result).
  - **Digest artifact** `digest` uploaded (938 bytes).
  - **DB committed back**: commit `scout: run 2026-09-03T12:23Z` by `job-scout[bot]`;
    `data/scout.db` (258 KB) now on remote → persistence + schedule keepalive confirmed.
  - `$0`: public repo (unlimited Actions minutes), local model, no paid services.
- [x] Workflow `state: active` → daily cron (04:00 UTC ≈ 07:00 EAT) is live. Local synced to the
  bot commit.
- [ ] (ongoing) Observe the first few scheduled runs; confirm the digest evolves and NEW→ACTIVE
  reconciliation holds across days.

## Resume note

*(Written only when a checkpoint interrupts work mid-task. Empty = nothing in flight.)*

**Nothing in flight. DEPLOYED + VERIFIED.** The project is live at
`https://github.com/DagiHabtu/job-scout` (PUBLIC) and running on a daily GitHub Actions schedule at
`$0`; a `workflow_dispatch` run (33754711547) succeeded end-to-end (scout ran, digest artifact
uploaded, `data/scout.db` committed back). Local `main` synced to the bot commit; **85 tests pass**;
spine unchanged. Deferred (by choice): Adzuna (needs a key + discovery design), hard-logic tuning
(needs more real-run evidence). Next event is optional — observe scheduled runs, widen coverage via
`config/profile.yaml`, or build Adzuna once a key exists. Spine must not change without a
spine-architect pass + a Decisions entry here.
