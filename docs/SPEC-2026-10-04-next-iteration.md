# Job Scout — Diagnosis and Next-Iteration Spec (2026-10-04)

Audience: Claude Code (implementer) and Dagi (owner). Investigated against repo HEAD `a2f685b`
(31 runs, Sep 3 – Oct 3), the committed `data/scout.db`, and live sources on 2026-10-04.

**Revision 2 (2026-10-04, same day).** Two corrections after re-checking my own evidence: the
supply claim in §1 is rescoped to what the inspected sources show, and the MLH entry and its
acceptance criterion in S6 are replaced (the live application form is for a batch whose deadline
passed on 2026-08-31, so revision 1 would have notified a closed round). Consequent edits are in
§3, S0, S2, S5, S6, E1, §7, §8 and §10. §11 (execution mode) was added afterwards; its current form is
one session, one pass, resumable from `STATE.md`. Where §5's per-step gates say to wait for Dagi,
§11 overrides them. Diagnosis C1–C8, architecture and step order are otherwise
unchanged.

Labels used throughout: **FACT** = observed directly (code, DB, live fetch, reproduced locally).
**INFERENCE** = strongly supported, not directly measured. **HYPOTHESIS** = unverified.

Verification limits of this investigation: the sandbox shell could not reach the ATS APIs, so the
full pipeline was not replayed on live data. Live checks went through a fetch tool that returns a
model-written summary of each page, so counts taken from those summaries are approximate and dates
it converted from epochs are unreliable (flagged where used). Everything from the repo, the DB, and
the SimplifyJobs dataset was computed directly.

---

## 1. Diagnosis

### Answer in one paragraph

Zero happens **before the pipeline starts**: the four boards being monitored contain no
internships, and the curated-programs source is silent by construction until mid-December. The
pipeline then adds three defects that would suppress or mis-rank a real opportunity if one did
arrive (eligibility verdicts driven by company boilerplate, a relevance score that mostly measures
the employer rather than the job, and a type filter that discards entry-level roles from the
better-labelled sources). Finally, the one thing it did find was never pushed to you: the digest is
a gitignored file inside an Actions artifact zip. The September 8 diagnostic was right that the
scraper is "healthy" and wrong that no change was warranted — a healthy pipeline over an empty
input is still an empty product.

### Confirmed causes (FACT)

**C1 — The input contains zero internships.**
- Live boards, 2026-10-04: GitLab — no title containing intern / co-op / new grad / apprentice;
  Sourcegraph — 7 jobs, none; PostHog — 6 jobs, all `employmentType: FullTime`; Deel — 0 jobs.
- DB, all 31 runs: 50 distinct rows ever persisted, **all 50** `employment_type = unknown`. No row
  is an internship or a stipend program.
- `known_programs` returned 0 on all 31 runs.

**C2 — `known_programs` is silent until ~Dec 13 and its table is stale.**
- `_active_round` surfaces a round only from 45 days before `apply_opens`. Earliest future round in
  the table is Outreachy `2027-01-27` → first surfaced ~2026-12-13.
- The Dec 2026 Outreachy round took initial applications in early–mid August (outreachy.org), i.e.
  before the Sep 3 deployment. It was missed, not filtered.
- Table errors vs. outreachy.org today: stipend is **$7,000** (table: ~$5,500); the May 2026
  application window was **Feb 6–13, 2026 — one week** (table models ~4-week windows). A one-week
  window with approximate dates is easy to miss entirely.
- LFX Mentorship (three terms a year) is not in the table.

**C3 — The relevance score is mostly a per-employer constant.**
- `embed_similarity` encodes `f"{title}. {description}"`. All 36 stored GitLab descriptions share an
  identical **206-word prefix** (company boilerplate). 
- Stored `semantic_similarity`: GitLab mean 0.342, sd 0.022, range 0.273–0.393; Sourcegraph mean
  0.235, sd 0.014, range 0.219–0.259. "Enterprise Account Executive – Singapore" = 0.344; "Senior
  Backend Engineer" = 0.364. The between-company gap (0.107) is ~5× the within-company spread.
- The 0.40 threshold is above the highest similarity ever observed (0.393). The single notification
  (Sep 3) crossed it only through the +0.0375 eligibility nudge.
- INFERENCE on mechanism: `all-MiniLM-L6-v2` truncates input at 256 word-pieces, so the embedded
  text is the title plus boilerplate; the job-specific body never reaches the model. Confirming
  test: embed title-only vs. title+description for 10 GitLab jobs and compare spread (step S5).
- Consequence: the threshold was "calibrated" on boilerplate. Whether an internship notifies depends
  on its employer's boilerplate plus the +0.15 wanted-type boost, not on the role.

**C4 — Every positive eligibility verdict in the DB comes from description boilerplate.**
- Of 50 stored rows, **0** have an include-token (`africa`, `emea`, `worldwide`, `global`,
  `anywhere`) in the location field. 37 verdicts rest on the bare word `global` (GitLab's
  "Remote-Global" benefits header), 13 on `emea`/`africa` in team descriptions ("the Europe, Middle
  East, and Africa sales team").
- Reproduced locally: with a body containing "Remote-Global", locations `Bangalore, India`,
  `Remote, France`, `Remote, Germany` all classify as `worldwide_remote @ 0.75`. Only
  `Remote, United States` is rejected.
- Root cause: step 2b's `_EXCLUDES_ET` is a deny-list of a handful of names (US, Canada, UK, EU,
  Australia…). Any location naming another country falls through to full-text rules, where a
  single generic word rescues it.
- Consequence: the ranked survivors are false positives (sales roles in Singapore/Netherlands,
  engineering roles pinned to Bangalore). Rule 2 of CLAUDE.md (eligibility is first-class) is
  currently violated in the permissive direction.

**C5 — The employment-type filter is asymmetric and the secondary target is unreachable.**
- `hard_filter` drops a *known* type not in `employment_types: [internship, stipend_program]` and
  keeps `UNKNOWN`. Greenhouse always emits `UNKNOWN`; Ashby/Lever emit `FULL_TIME`.
- So every PostHog job is dropped (8–11 fetched per run, 0 ever persisted), while every Greenhouse
  job passes the type gate regardless of level. The survivor set is "Greenhouse jobs the system
  knows least about".
- `EmploymentType.NEW_GRAD` exists in the enum and is assigned by nothing (`grep`: one hit, the
  definition). Entry-level/junior roles — the stated secondary target — cannot be represented, so
  they cannot be wanted.

**C6 — "Found" does not reach the user.**
- `notify.mode: file` writes `data/digest.html`; `.gitignore` excludes it; the workflow uploads it
  as an Actions artifact. Seeing it means opening the run page and downloading a zip. Nothing is
  pushed. The digest is also overwritten with an empty one on every quiet run.
- `mark_notified` fires as soon as the file is written, so an item is recorded as delivered whether
  or not a human saw it.

**C7 — Same-title postings in different locations are merged before eligibility runs.**
- Reproduced: two Greenhouse jobs titled "Software Engineer Intern", one `Remote, United States`
  (longer description), one `Remote, EMEA`, dedupe to a single record with the US location. Tier-3
  fuzzy matching blocks on company only; `_merge` promotes the longer record wholesale.
- An eligible regional variant can therefore be swallowed by an ineligible one and then rejected.
  ~24–33 records are merged per run; how many are cross-location is unmeasured.

**C8 — A zero-result run cannot explain itself.**
- `hard_filter` returns one count. Rejected records are not persisted. The notify gate records no
  reasons. The Sep 8 diagnostic already named this gap; it was not closed.
- 20 of the 50 stored rows were absent from the latest run but remain `active`/`new` (no GONE
  handling). Harmless to notifications; makes the table unreliable as "currently open".

### Likely causes (INFERENCE)

- The ~85% hard-filter loss (Oct 3: 205 → 30) is mostly rule 2b rejecting US/Canada/UK locations
  (GitLab's largest location buckets) plus the Ashby type drop. Not measured per reason — S0 does.
- Role mismatch: `target_roles` are backend-centred while the stated long-term target is not
  backend/web. This does not cause the zeros but would mis-rank once supply exists.

### Supply: what was observed, and how far it reaches

Revision 1 said the company-internship market is "structurally closed" to a resident of Ethiopia.
That overreached, and one of my own probes contradicts it as a universal claim (Himalayas returned
internships with no location restriction). The scoped version:

| # | Observation (directly established) | Inference | Boundary — what this does not show | Decision consequence |
|---|---|---|---|---|
| 1 | The 4 monitored boards produced 0 internship-typed records in 31 runs; live titles on 2026-10-04 contain none. | These 4 employers are not a source of internships in this period. | Nothing about other employers, or these employers in other seasons. The store holds only survivors, so interns rejected before persistence in earlier runs would be invisible (S0 closes this). | Keep the boards (cost is nil); do not expect internships from them. |
| 2 | SimplifyJobs `listings.json`, 2026-10-04: 4,453 active internship listings; 0 with a worldwide or African location; all 72 remote ones name US, Canada, UK or Australia. New-Grad list: same pattern. | A pipeline seeded from this list, or from the employers on it, would fetch thousands of records and reject nearly all on location. | The list is curated around US/Canada roles (my understanding of its stated scope — confirm in its README), so its location mix reflects its scope as much as the market. It does not show what employers outside it do, and it does not establish any employer's hiring policy. | Do not use it for acquisition or to seed board discovery. |
| 3 | Himalayas search, 2026-10-04: 29 results for Intern ∧ worldwide (mostly non-technical; at least 2 technical, e.g. a Software Engineer Intern); 29 for Entry-level ∧ country=ET ∧ "engineer", including junior data, DevOps and kernel roles. | Internships and junior roles with no stated location restriction exist and are queryable through a structured field. | "No restriction listed" is the aggregator's field, not the employer's confirmed policy. Freshness is unverified (the fetch tool's date conversions were unreliable). One day's sample. | Probe it (E1) and build the adapter if the probe passes. This is the evidence against "closed". |
| 4 | HN "Who is hiring" October 2026: 20 comments match "intern", about 7 are real internships, all onsite in the US/EU. | That thread is a poor internship source this month. | One thread, internship query only. Junior or worldwide-remote roles in the thread were not examined. | Not now. Not a permanent rejection. |
| 5 | RemoteOK `?tag=internship`: 16 results, non-technical onsite roles with spam tag lists, newest dated 2026-07-31. | That tag is unusable. | Says nothing about RemoteOK's untagged feed. | Do not use the tag. Whole-feed evaluation: later. |
| 6 | Outreachy states it is "open to applicants around the world"; GSoC and MLH state the rule "not residing in a U.S.-embargoed country"; LFX states "eligible to work in the country … where you will be participating". | For a resident of Ethiopia these are open on geography, provided Ethiopia is not on the US comprehensive-embargo list (my understanding is that it is not — verify once against OFAC and date the check). | Each program has personal conditions the system cannot check (see S6). Dates for 2027 rounds are not published. | Programs are the class with the strongest eligibility evidence; treat the calendar as first-class. |

**Strongest conclusion the evidence supports:** in every US-centric source inspected, reachable
internship supply was zero or near zero against thousands of listings, and in the one
worldwide-oriented source it was small but non-zero. So scaling ATS-board monitoring or US-list-seeded
discovery is the wrong investment, and sources that expose location restriction as a structured
field are the right one. **Not established:** that no Ethiopia-accessible company internships exist,
how many exist across the wider market, or what supply will look like in other seasons.

Reachable supply was seen in three places:

| Class | Shape | Evidence |
|---|---|---|
| A. Stipend programs (Outreachy, GSoC, LFX, MLH) | A few dated application windows per year | Row 6 above |
| B. Worldwide-remote junior roles and internships | Unknown volume; small in one sample | Row 3 above |
| C. Local Addis roles | Unknown | Afriwork's public Telegram preview carries consistently structured posts. Tech-internship density unmeasured. |

HYPOTHESIS, not a finding: yield will be a few items per week with bursts at program windows. The
system must measure this (S0's internship funnel) instead of assuming it in either direction.

### Unresolved hypotheses

- H1: Himalayas listings are fresh enough to act on, and `country=ET` returns
  worldwide-plus-Ethiopia jobs. (Experiment E1.)
- H2: Afriwork posts ≥4 tech intern/junior roles per month. (Experiment E2.)
- H3: Greenhouse token `canonical` resolves and Canonical's graduate/junior roles are open
  worldwide. (Verify with `scripts/verify_boards.sh`.)
- H4: GitHub emails/pushes the repo owner for issues opened by `github-actions[bot]`. (Step S1
  acceptance test.)

---

## 2. Pipeline-loss table

Run `f521db260732`, 2026-10-03 09:30 UTC (from `runs.summary` and the `opportunities` table).

| Stage | In | Out | Loss / reason | Confidence |
|---|--:|--:|---|---|
| fetch | — | 229 | greenhouse 221, ashby 8, lever 0 (no sites), known_programs 0 (no round in window) | FACT |
| parse | 229 | 229 | no source failure recorded; per-record skips are logged, not counted | FACT (count) / unmeasured (skips) |
| normalize | 229 | 229 | no loss by design | FACT |
| internships recognized | 229 | **0** | no title matches the intern regex; no source types anything as internship | FACT post-filter; live-title check for pre-filter |
| dedupe | 229 | 205 | 24 merged; some are cross-location merges (C7) | FACT (count) / unmeasured (split) |
| eligibility + hard filter | 205 | 30 | 175 dropped; reason split not recorded. All 8 Ashby jobs are among them. | FACT (count) / INFERENCE (reasons) |
| score | 30 | 30 | no loss; max score this run < 0.40 | FACT |
| rank | 30 | 30 | order only | FACT |
| reconcile | 30 | 1 new, 29 active | 29 already known | FACT |
| notify gate | 1 | 0 | the 1 new row ("Account Executive – France", 0.356) is below 0.40 | FACT |
| delivered to user | 0 | 0 | — (and no push channel exists) | FACT |

30-day totals: 50 distinct survivors persisted; 1 ever scored ≥ 0.40; 1 ever "notified" (to a file);
0 internships; 0 stipend programs.

---

## 3. Source strategy

| Source | Role | Evidence (2026-10-04) | Complexity | Decision |
|---|---|---|---|---|
| `known_programs` (Outreachy, GSoC, MLH, **+LFX**) | authoritative acquisition (class A) | Only class structurally open to ET. Table stale (C2). MLH is batch-based: its live form is for Fall 2026, deadline 2026-08-31 (closed). LFX docs: Spring Mar 1–May 31 (posted mid-Jan), Summer Jun 1–Aug 31 (mid-Apr), Fall Sep 1–Nov 30 (mid-Jul), applications ~4 weeks | low (data edit + small logic) | **now** |
| Himalayas API (`/jobs/api/search`) | authoritative acquisition (class B) | Public, no auth. Filters: `employment_type=Intern`, `seniority=Entry-level`, `worldwide`, `country`. Structured `locationRestrictions`, `seniority`, `employmentType`. 20/page, rate-limited (429). Terms: link back, name Himalayas, do not resubmit to other job platforms | medium (new adapter) | **experiment (E1) → now if it passes** |
| Greenhouse `gitlab`, `sourcegraph91`; Ashby `posthog`, `deel` | acquisition, low yield | 0 internships in 31 runs; becomes useful for junior roles once C4/C5 are fixed | none | keep as is |
| Greenhouse `canonical` | acquisition | Canonical junior/graduate roles appear as worldwide in Himalayas results; token unverified | low | **now, after token verification** |
| Afriwork Telegram public preview (`t.me/s/freelance_ethio`) | acquisition (class C) | Structured posts; Addis-based; tech intern density unknown; Telegram ToS for automated reading unreviewed | medium + needs a spine decision | **experiment (E2)** |
| Jobicy API | acquisition (class B) | Works, no auth, attribution required. Sample of 50 dev jobs: 1 "Anywhere", 0 junior/intern | low | later |
| We Work Remotely RSS | acquisition (class B) | Not verified in this pass | low | later |
| Remotive API | acquisition | API path disallowed by robots.txt for fetchers; conflicts with CLAUDE.md rule 4 unless their API terms say otherwise | low | later (read terms first) |
| HN "Who is hiring" (Algolia API) | discovery | Oct 2026 thread: 267 comments; 20 match "intern", ~7 real internships, all onsite US/EU | medium (free-text) | not now (one thread, internship query only) |
| SimplifyJobs lists | discovery | 4,453 active internships, 0 with a worldwide/African location; list is US/Canada-scoped | low | reject for acquisition and for seeding discovery |
| RemoteOK API | — | `?tag=internship` returns bartender / assembler / store-manager posts with spam tag lists; newest dated 2026-07-31 | low | reject the tag; whole feed not evaluated |
| ethiojobs.net | — | Listing page is JS-rendered; `/api/*` disallowed by robots | high | reject |
| LFX Mentorship site scrape | enrichment | robots-disallowed to fetchers | — | reject (use the calendar instead) |
| Bluesky | discovery | Not evaluated | high | not evaluated — no decision |

### Company-discovery flywheel: not from US-centric lists; a narrow version is conditional on E1

The flywheel's value depends on its seed. Seeded from SimplifyJobs-style lists it would add boards
whose internships are, on the observed data, located in the US/Canada (row 2 of the supply table).
That version is rejected on evidence.

A narrow version is supported by row 3: employers that repeatedly post worldwide target-class roles.
E1 therefore also outputs, per employer, the count of target-class listings with no location
restriction (or including Ethiopia) in the last 30 days. An employer with ≥2 becomes a candidate:
resolve its ATS token by hand, verify with `scripts/verify_boards.sh`, add to config with a
provenance comment. No crawler, no automatic resolution. If E1 shows no such employers, nothing is
built.

---

## 4. Target architecture

Stage order and all signatures stay as frozen. Changes are inside stages.

```
ACQUISITION   known_programs (calendar with dated evidence per program and per round, +LFX)
              himalayas (structured: seniority, employmentType, locationRestrictions)   [if E1 passes]
              greenhouse / ashby / lever (unchanged adapters; +canonical board)
DISCOVERY     none
ENRICHMENT    none
      │
NORMALIZE     canonical URL · remote inference · type/level inference (INTERNSHIP, NEW_GRAD) · fingerprint
DEDUPE        ATS id → fingerprint → fuzzy title blocked by (company, location)      ← was company only
ELIGIBILITY   location field decides first (gazetteer); description may not rescue a named-elsewhere
              location; bare "global"/"africa"/"emea" in body no longer count
HARD FILTER   every rejection carries a reason code; adds title-seniority rejection
SCORE         role-fit from TITLE only (embedding or lexical) + body tech hits; used for ordering
RANK          unchanged
PERSIST       unchanged schema; run summary gains reason histograms
NOTIFY        deterministic gate: class ∧ role family ∧ eligibility; GitHub Issue delivery;
              weekly heartbeat with funnel + near-misses
```

Two departures from the brief, with reasons:

1. **The relevance threshold stops being the notification gate.** Evidence: C3 — it was calibrated
   on boilerplate, and 50 rows from two employers cannot calibrate anything. A rule gate (class,
   title role family, eligibility) is testable without a model, explains itself, and is simpler.
   The embedding stays, for ordering items within a digest. Self-check: the risk is recall loss on
   roles with unusual titles; mitigated by the near-miss list in the weekly heartbeat, which is
   where a missed pattern would show up.
2. **Sources come after delivery and instrumentation, not first.** A new source feeding a pipeline
   that mislabels eligibility and cannot deliver would produce confident wrong notifications that
   nobody receives.

---

## 5. Implementation plan (ordered by dependency)

Constants and regexes below are exact unless marked "tune".

### S0 — Reason-coded funnel (no behaviour change)

- **Files:** `score.py`, `pipeline.py`, `notify.py`.
- **Current:** `hard_filter` returns survivors only; `select_for_notification` returns the selected
  list only; `RunSummary` has scalar counts.
- **Desired:** every dropped or unselected record has exactly one reason; reasons are counted in
  the run record.
- **Logic:**
  - `score.py`: add `filter_reason(opp, profile, cfg, today) -> str | None` returning the first
    matching of `"eligibility:<category>"`, `"deadline_passed"`, `"type_unwanted:<type>"`, else
    `None`. Re-implement `hard_filter` as `[o for o in opps if filter_reason(...) is None]`
    (signature unchanged).
  - `notify.py`: add `gate_reason(opp, threshold) -> str | None` returning `"not_new"`,
    `"already_notified"`, `"below_threshold"`, else `None`; `select_for_notification` uses it
    (signature unchanged).
  - `pipeline.py`: `RunSummary` gains `rejects: dict[str,int]`, `gate: dict[str,int]`,
    `by_type: dict[str,int]` (after normalize), `by_eligibility: dict[str,int]` (after classify),
    `near_misses: list[dict]` (top 5 unselected survivors by score: title, company, location, type,
    eligibility, score, gate reason). All added to `as_record()`. `runs.summary` is already a JSON
    text column — no schema change.
  - `internship_funnel`: for records typed `INTERNSHIP` or `STIPEND_PROGRAM` after normalize —
    `fetched` (count), `outcomes` (reason → count, using the same filter and gate reasons, plus
    `notified`), and `rejected_samples` (up to 5: title, company, location, reason, evidence).
    This is the standing check against false scarcity: "few fetched" means a coverage problem,
    "many fetched, rejected for eligibility" means the rules need a hand audit of the samples.
  - Sources may expose an optional `report: dict[str, str]` attribute (read with `getattr`, no
    protocol change) explaining records they deliberately did not emit; the pipeline copies it into
    `sources[name]["report"]`.
  - Write the same data as a Markdown table to `data/funnel.md`; in the workflow, append it to
    `$GITHUB_STEP_SUMMARY`.
- **Tests:** `sum(rejects.values()) == after_dedupe - after_filter`;
  `sum(gate.values()) == after_filter - notified`; all 89 existing tests unchanged.
- **Acceptance:** one `workflow_dispatch` run shows the funnel table on the run page with the
  hard-filter loss split by reason. Record the table in `STATE.md`. This either confirms or refutes
  the INFERENCE in §1 about the 85% loss before anything else changes.
- **Depends on:** nothing.

### S1 — Delivery by GitHub Issue

- **Files:** `notify.py`, `.github/workflows/scout.yml`, `.gitignore`.
- **Current:** HTML file → artifact; marked notified on file write.
- **Desired:** items reach Dagi's inbox/phone; a delivery failure causes a replay, not a silent loss.
- **Logic:**
  - `notify.py`: add `render_issue_md(opps, cfg) -> str` — one task-list line per item:
    `- [ ] [Title](url) — Company · type · location`, followed by indented eligibility category,
    confidence, evidence, and matched signals. Two sections: "Actionable" and "Check eligibility".
    Each Himalayas item ends with "via Himalayas" linking to its Himalayas listing URL. Pipeline
    writes `data/notify.md` only when the selection is non-empty (delete a stale one otherwise).
  - Workflow: `permissions: contents: write, issues: write`. Steps in this order:
    run scout → `if [ -s data/notify.md ]; then gh issue create --title "Job Scout: $N new — $(date -u +%F)" --body-file data/notify.md --label scout; fi`
    (env `GH_TOKEN: ${{ github.token }}`) → commit state. Because "commit state" runs after issue
    creation, a failed issue step leaves `notified_at` uncommitted and the next run re-selects the
    same items.
  - Heartbeat: when the run date is a Monday, also create an issue "Job Scout weekly funnel" whose
    body is `data/funnel.md` aggregated over the last 7 run records plus the near-miss list. This
    makes silence distinguishable from failure and gives Dagi the data to judge the gate.
  - Add `data/notify.md` and `data/funnel.md` to `.gitignore`. Keep the HTML digest artifact.
- **Tests:** renderer unit test (sections, links, attribution line); pipeline test that
  `notify.md` is absent when nothing is selected.
- **Acceptance:** a manual run with one seeded item produces an issue, and Dagi confirms a
  notification arrived (email or GitHub mobile). If it does not arrive, fall back to a Telegram bot
  (`sendMessage`, token in Actions secrets, $0) before proceeding — delivery is a gate for S2+.
- **Note for Dagi:** the repo is public, so issues are public. They contain only public job
  listings. If that is unwanted, make the repo private (≈1 min/run against 2,000 free min/month).
- **Depends on:** S0 (funnel file).

### S2 — Eligibility: the location field decides first

- **Files:** new `src/job_scout/_geo.py`; `eligibility.py`.
- **Current:** C4.
- **Desired:** a location that names only places outside the user's scope is a confident exclusion
  that description text cannot override; generic words in the body are not positive evidence.
- **Logic:**
  - `_geo.py`: `COUNTRIES: frozenset[str]` (lower-case names of all countries plus common variants:
    "usa", "u.s.", "uk", "uae", "south korea", "czechia"…), `REGIONS_EXCLUDING_AFRICA` ("americas",
    "north america", "latam", "apac", "europe", "eu", "eea", "dach", "nordics", "anz"),
    `REGIONS_INCLUDING_AFRICA` ("africa", "emea", "mea", "middle east and africa", "east africa",
    "sub-saharan africa"), `WORLDWIDE_TOKENS` ("worldwide", "global", "anywhere", "international"),
    `CITIES: dict[str,str]` for cities seen in practice (bangalore/bengaluru→india, london→uk, …;
    extend from S0's reject samples), and a US-state pattern `r",\s*[A-Z]{2}$"`.
  - `eligibility.py`: add `_classify_location(loc_raw, title, profile) -> tuple[str, str] | None`.
    Split `loc_raw` on `;`, `|`, `/`, ` or `, ` and `. For each segment, lower-case and strip the
    word "remote", hyphens and commas at the edges, then label it:
    `USER` (contains the user's country, city, or a `REGIONS_INCLUDING_AFRICA` token) ·
    `WORLD` (a `WORLDWIDE_TOKENS` token) · `BARE` (empty after stripping, i.e. plain "Remote") ·
    `ELSEWHERE` (matches `COUNTRIES` other than the user's, `REGIONS_EXCLUDING_AFRICA`, `CITIES`, or
    the US-state pattern) · `OTHER`.
    Also extract a trailing region marker from the title (`r"[-,(]\s*(US|USA|UK|EU|EMEA|APAC|LATAM|AMER|[A-Z][a-z]+)\)?\s*(\[.*\])?$"`)
    and label it the same way; an `ELSEWHERE` title marker counts as an `ELSEWHERE` segment.
  - Decision order inside `classify_eligibility`, replacing step 2b and constraining steps 3–6
    (steps 1 and 2 — stipend program, work-authorization — stay first and unchanged):
    1. any `USER` → `REMOTE_REGION_INCLUDES_USER`, 0.8, evidence quotes the location field.
    2. any `WORLD` → `WORLDWIDE_REMOTE`, 0.85.
    3. at least one `ELSEWHERE` and no `BARE`/`OTHER` → `REMOTE_EXCLUDES_USER` 0.85 if
       `remote_status == REMOTE`, else `ONSITE_FOREIGN` 0.8. Return immediately.
    4. otherwise (only `BARE`/`OTHER`, or no location): look at the body for an explicit phrase
       from `_WORLDWIDE` extended with "anywhere in the world", "hire anywhere", "any country" →
       `WORLDWIDE_REMOTE` 0.7 (minus the existing US-hours penalty). Else `UNKNOWN` — 0.5 for
       `BARE`, 0.3 for none.
  - Step 1 (stipend program) no longer assumes "stipend ⇒ worldwide". New rule: if
    `opp.ats_provider == "known_programs"`, call
    `known_programs.geo_verdict(opp.ats_job_id, profile.location.country_name)` (defined in S6):
    `"eligible"` → `STIPEND_PROGRAM_GLOBAL` 0.9 with the quoted rule, URL and check date as
    evidence; `"excluded"` → `REMOTE_EXCLUDES_USER` 0.85; `"unknown"` → `UNKNOWN` 0.5 with evidence
    "geographic eligibility not verified for <country>". A `STIPEND_PROGRAM` record from any other
    source goes through the location rules below like any other record. Delete the text-mention
    path (`_has(hay, _STIPEND_PROGRAMS)`): a posting that mentions GSoC is not a GSoC round — this
    is the same boilerplate defect as C4.
  - Remove `"global"`, `"africa"`, `"emea"`, `"anywhere"` as bare full-text positives
    (`_INCLUDES_AFRICA` and `names_user_region` now apply to the location field only). Keep the
    existing full-text *exclusion* rule (step 3) only for the case in (4).
- **Tests (new, table-driven):** body containing "Remote-Global" with locations
  `Bangalore, India` → `ONSITE_FOREIGN` or `REMOTE_EXCLUDES_USER`; `Remote, France` →
  `REMOTE_EXCLUDES_USER`; `Remote, EMEA` → `REMOTE_REGION_INCLUDES_USER`;
  `Remote, Germany; Remote, EMEA` → includes; `Remote` + title "…, US [IC5]" → excludes;
  `Remote` + body "work from anywhere" → `WORLDWIDE_REMOTE`; `Remote` + neutral body → `UNKNOWN 0.5`;
  `Addis Ababa, Ethiopia` → includes. Existing eligibility tests must still pass or be updated with
  a one-line justification each.
- **Acceptance:** re-classifying the 50 stored rows (script over `raw`) yields **0** rows with a
  positive category whose location names only non-user places. Expected: GitLab rows drop to the
  handful with location `Remote`; Sourcegraph rows become `UNKNOWN 0.5` or excluded by title marker.
- **Depends on:** S0 (to see the before/after reason histogram).

### S3 — Type and level inference

- **Files:** `normalize.py`, `config/profile.yaml`, `profile.example.yaml`.
- **Current:** only `INTERNSHIP` from a title token; `NEW_GRAD` never assigned.
- **Logic:**
  - `_INTERN_TITLE = r"\b(intern(ship)?s?|co-?ops?|working student|werkstudent(in)?|trainee|apprentice(ship)?)\b"`.
  - `_ENTRY_TITLE = r"\b(junior|jr\.?|entry[- ]level|new[- ]grad(uate)?|graduate|early[- ]career|associate (software|data|ml|machine learning|devops|platform|cloud|security|qa|site reliability) (engineer|developer|analyst|scientist))\b"`.
  - `_SENIOR_TITLE = r"\b(senior|sr\.?|staff|principal|lead|head|director|manager|vp|chief|architect)\b"`.
  - `infer_employment_type`: if type is `UNKNOWN` and `_INTERN_TITLE` matches → `INTERNSHIP`.
    Else if type is `UNKNOWN` **or `FULL_TIME`**, `_ENTRY_TITLE` matches and `_SENIOR_TITLE` does
    not → `NEW_GRAD`. Refining `FULL_TIME` to `NEW_GRAD` is consistent with the enum's own comment
    ("entry-level / early-career full-time"); update the docstring, which currently says a
    structured value is never overridden.
  - `profile.yaml`: `employment_types: ["internship", "stipend_program", "new_grad"]`.
  - `target_roles` (decision for Dagi; default to ship):
    `["data engineer intern", "software engineer intern", "machine learning engineer intern", "junior data engineer", "junior software engineer", "junior platform engineer"]`.
- **Tests:** title table for each regex incl. negatives ("Internal Tools Engineer",
  "International Sales", "Associate Renewals Manager", "Graduate Partner Marketing Manager" →
  `NEW_GRAD` by level, later vetoed by role family in S5 — assert both).
- **Acceptance:** `by_type` in the funnel shows non-zero `new_grad` on a run that includes
  Himalayas or Canonical data.
- **Depends on:** none (S0 makes it visible).

### S4 — Hard filter: title seniority, and dedupe by location

- **Files:** `score.py`, `dedupe.py`.
- **Logic:**
  - `filter_reason`: after the type check, add: if `employment_type` not in
    `{INTERNSHIP, STIPEND_PROGRAM}` and `_SENIOR_TITLE` matches the title →
    `"seniority_title:<token>"`.
    Why hard and not a penalty: a title seniority token is high-precision, a senior role is never
    actionable for this profile, and as a penalty these rows currently make up 35 of 50 persisted
    survivors (measured with the regex above) and occupy the ranked list. Of the 15 that remain,
    the role-family check in S5 passes 5 engineering titles and vetoes the 10 sales/support ones.
  - `UNKNOWN` type with no level signal stays (not dropped) — it is persisted, counted at the notify
    gate as `not_target_class`, and eligible for the near-miss list.
  - `dedupe.py` tier 3: bucket key becomes `(canon(company), canon(location_raw or ""))`. Tier 1
    and 2 unchanged.
- **Tests:** the C7 reproduction (same title, `Remote, United States` vs `Remote, EMEA`) now yields
  two records; a same-location near-duplicate still merges; "Senior Backend Engineer" → rejected
  with reason; "Intern, Engineering Manager's Office" → kept.
- **Depends on:** S0, S3 (shares `_SENIOR_TITLE`; define it once in `normalize.py` and import).

### S5 — Scoring from the title; deterministic notify gate

- **Files:** `score.py`, `notify.py`, `scripts/calibrate.py` (new), `tests/fixtures/golden_titles.csv` (new).
- **Logic:**
  - `embed_similarity`: encode `opp.title` against each string in `profile.target_roles`; return
    the max cosine. (Was: one profile blob vs. title+description.)
  - `score_opportunity`: `base = sim if model else lexical`; add `0.03 × (target technologies found
    in body)`, capped at 0.15; keep the prioritized-company, wanted-type, and eligibility nudges.
    Drop the per-concern 0.1 damping for seniority (now a hard filter).
  - `score.py`: `role_family_ok(title) -> bool` =
    matches `r"\b(engineer(ing)?|developer|programmer|software|data|machine learning|ml|ai|devops|sre|site reliability|platform|infrastructure|cloud|backend|back-end|full[- ]?stack|analyst|analytics|scientist|security|qa|research)\b"`
    and does not match
    `r"\b(sales|account executive|marketing|recruit(er|ing)|talent|legal|counsel|finance|accounting|customer success|people|hr|designer?|content|community|partnerships?|curriculum|renewals|support)\b"`.
  - `notify.gate_reason` (replaces S0's interim version), first match wins:
    `not_new` → `already_notified` → stipend program (type `STIPEND_PROGRAM`: category `STIPEND_PROGRAM_GLOBAL` → select, "Actionable"; `UNKNOWN` → select, "Check eligibility", outside the cap; never dropped for uncertainty) → `not_target_class` (type not in
    `{INTERNSHIP, NEW_GRAD}`) → `role_family` → eligibility:
    category in `{WORLDWIDE_REMOTE, REMOTE_REGION_INCLUDES_USER}` → select, section "Actionable";
    `UNKNOWN` and type `INTERNSHIP` → select, section "Check eligibility", at most 5 per run
    (overflow reason `unknown_cap`); `UNKNOWN` and `NEW_GRAD` → `eligibility_unknown`.
    `UNKNOWN` is surfaced with its uncertainty for the scarce class and never treated as eligible.
    The `threshold` parameter stays in the signature and is no longer consulted for these classes.
  - `scripts/calibrate.py`: loads `golden_titles.csv` (columns `title,label`; ~60 rows drawn from
    the 50 DB titles, the Himalayas probe output, and hand-written positives), prints
    precision/recall of `role_family_ok`, and — if the model loads — title-only similarity
    quantiles for positives vs. negatives. This is also the confirming test for C3's mechanism.
- **Tests:** `role_family_ok` ≥ 0.9 precision and ≥ 0.8 recall on the golden file (pure regex, runs
  in CI); gate table test covering every reason; ordering test (higher title similarity first
  within a section).
- **Depends on:** S2, S3, S4.

### S6 — Programs calendar (revised)

- **File:** `sources/known_programs.py` (curated data; nothing is fetched at run time — application
  state is established by a dated human/implementer check recorded in the table, and the system
  must say so in each record).
- **Why revised:** revision 1 marked MLH `rolling` because the landing page shows "Apply Now", and
  required "exactly one notification (MLH)" on the first run. The application form that button
  leads to is for **Fall 2026, deadline August 31, 2026, program start September 14, 2026** — closed
  five weeks ago. The criterion would have been satisfied by notifying a closed round.
- **Data model:**
  - `_Program` gains: `geo_scope: Literal["worldwide", "unknown"]`; `geo_exclusions: tuple[str, ...]`
    (places the program itself says are excluded or have no projects); `geo_quote: str` (verbatim);
    `geo_url: str`; `geo_checked_on: date`; `conditions: tuple[str, ...]` (requirements the system
    cannot check — rendered in every notification).
  - `_Round` gains: `state: Literal["open", "announced", "expected"]`; `state_url: str`;
    `state_checked_on: date`. `open` = the official page shows applications open with this deadline.
    `announced` = official dates published, not yet open. `expected` = dates extrapolated from a
    previous cycle.
  - Drop `rolling`. A program with no dated round emits nothing and reports `no_published_round`.
  - Staleness: an `open`/`announced` round whose `state_checked_on` is more than 45 days before
    today is treated as `expected` (title says so). A `geo_checked_on` older than 365 days makes
    `geo_verdict` return `"unknown"`.
- **Functions:**
  - `geo_verdict(ats_job_id, country) -> "eligible" | "excluded" | "unknown"`: `"excluded"` if
    `country` is in `geo_exclusions` or in `US_EMBARGOED` when the program's rule is the US-embargo
    rule; `"eligible"` if `geo_scope == "worldwide"` and the check is fresh; else `"unknown"`.
    `US_EMBARGOED` is a module constant with its own `checked_on` date and source URL (OFAC);
    until the implementer has verified it, programs relying on that rule return `"unknown"`.
  - Timing: a round is emitted iff `today <= apply_deadline` and (`state == "open"` or
    `today >= apply_opens - lead`), with `lead = 30` days for `announced` and `51` days for
    `expected` (Outreachy's last window was 7 days long; extrapolated dates need slack).
  - Identity: `ats_job_id = f"{round.key}@{effective_state}"`. A round is therefore announced at
    most once per state — a heads-up while `expected`, again when it becomes `open` with confirmed
    dates. Without this, `notified_at` from the heads-up would suppress the "now open" notice.
  - Title: `open` → "… — applications open (deadline Feb 12, 2027)"; `announced` → "… — opens
    Feb 5, 2027"; `expected` → "… — expected around Feb 2027 (dates not published; last checked
    2026-10-04)". Description carries `geo_quote`, `geo_url`, `conditions`, `state_url`.
  - `KnownProgramsSource.report`: for every round not emitted, `key → "deadline_passed" |
    "outside_lead_window"`, and for every program without a future round, `name →
    "no_published_round (last checked <date>)"`.
- **Table (verified 2026-10-04 unless marked):**
  - **Outreachy** — `geo_scope="worldwide"`, quote: "Outreachy is open to applicants around the
    world." (`https://www.outreachy.org/docs/applicant/`). Stipend "$7,000 USD". Conditions:
    "30 hours/week"; "university students need 42 consecutive days free from school and exams
    during the internship"; "students in the Northern Hemisphere may apply only to the May–August
    cohort". Rounds: `outreachy-2027-05`, `expected`, opens ~2027-02-05, deadline ~2027-02-12
    (pattern from Feb 6–13, 2026). **Do not add December rounds**: Ethiopia is in the Northern
    Hemisphere, so for a university student that cohort is excluded by Outreachy's own rule.
  - **Google Summer of Code** — rule: "Not residing in a U.S. embargoed country"; "Eligible to work
    in your country of residence"; "18+". Uses `US_EMBARGOED`. Round `gsoc-2027`, `expected`,
    existing dates (2027 timeline not published).
  - **LFX Mentorship** (new) — rule: "Be eligible to work in the country and jurisdiction where you
    will be participating"; not residing where participation is prohibited under US law; 18+; not a
    prior LF mentee. `geo_scope="worldwide"` is an inference from that wording, so set
    `geo_scope="unknown"` unless the implementer finds an explicit statement. Rounds, all
    `expected`: spring opens ~2027-01-15 → ~2027-02-12; summer ~2027-04-15 → ~2027-05-13;
    fall ~2027-07-15 → ~2027-08-12.
  - **MLH Fellowship** — rule: "Reside in a country not embargoed by the United States"; 18+.
    `geo_exclusions`: the 29 countries the form lists as having no anticipated projects (Ethiopia is
    not among them); the Production Engineering track is US/Canada/Mexico only. Conditions: "must
    have participated in at least one MLH Hackathon or Global Hack Week event"; "20 hours/week";
    "30 Mbps internet". URL `https://fellowship.mlh.com/`. **No round**: Fall 2026 closed
    2026-08-31 and no later batch is published. Add a round only when the official form shows one.
- **Decision on uncertain eligibility** (the three options, decided on evidence): geographic
  eligibility is (3) treated as eligible only when the table holds the program's own quoted rule,
  a URL, a check date, and — for embargo-rule programs — a verified embargo list; otherwise (2)
  surfaced as `UNKNOWN` under "Check eligibility" with the gap stated. Never (1) excluded for
  uncertainty alone: these programs are few and high-value, and the cost of a wrong "check this" is
  one click. Personal conditions are always shown, never assumed met.
- **Acceptance test** (`tests/test_known_programs_acceptance.py`; `today` injected; synthetic
  programs for A/C so the test does not depend on the calendar):

  ```python
  # Acquisition — applies to the shipped table
  assert validate_table(_PROGRAMS) == []          # every program: geo_* fields or geo_scope=="unknown";
                                                  # every round: state, state_url, state_checked_on
  KnownProgramsSource(today=T).fetch(cfg)         # does not raise

  # Case A — a qualifying round exists
  # program: geo_scope="worldwide", exclusions=(), geo_checked_on=T; round: state="open",
  # opens T-3d, deadline T+10d, state_checked_on=T
  s = run_once(cfg, [KnownProgramsSource(today=T, programs=A)], today=T, conn=db)
  o = s.ranked[0]
  assert s.sources["known_programs"]["count"] == 1
  assert o.ats_job_id == "a-r1@open" and o.employment_type == EmploymentType.STIPEND_PROGRAM
  assert o.eligibility.category == EligibilityCategory.STIPEND_PROGRAM_GLOBAL
  assert A[0].geo_quote in " ".join(o.eligibility.evidence) and A[0].geo_url in " ".join(o.eligibility.evidence)
  assert o.deadline == T + timedelta(days=10)
  assert s.notified == 1
  md = Path("data/notify.md").read_text()
  assert all(x in md for x in (o.title, A[0].url, A[0].geo_quote, *A[0].conditions))
  assert md.index("Actionable") < md.index(o.title)
  s2 = run_once(cfg, [KnownProgramsSource(today=T, programs=A)], today=T, conn=db)
  assert s2.notified == 0 and s2.gate["already_notified"] == 1

  # Case B — nothing qualifies; zero notifications, each with a recorded reason
  # B1: the real MLH Fall 2026 facts (deadline 2026-08-31) at T = 2026-10-04
  s = run_once(cfg, [KnownProgramsSource(today=date(2026,10,4), programs=B1)], ...)
  assert s.notified == 0 and s.sources["known_programs"]["count"] == 0
  assert s.sources["known_programs"]["report"]["mlh-2026-fall"] == "deadline_passed"
  # B2: round opens T+90d → report == "outside_lead_window", notified == 0
  # B3: program with no rounds → report startswith "no_published_round", notified == 0
  # B4: profile country in geo_exclusions, round open →
  assert s.sources["known_programs"]["count"] == 1 and s.notified == 0
  assert s.rejects["eligibility:remote_excludes_user"] == 1

  # Case C — open round, geography not verified: surfaced as uncertain, never as eligible
  s = run_once(cfg, [KnownProgramsSource(today=T, programs=C)], ...)   # geo_scope="unknown"
  o = s.ranked[0]
  assert o.eligibility.category == EligibilityCategory.UNKNOWN
  assert "not verified" in " ".join(o.eligibility.evidence)
  assert s.notified == 1
  md = Path("data/notify.md").read_text()
  assert md.index("Check eligibility") < md.index(o.title)

  # State change is announced once per state
  # same round, state "expected" at T0 then "open" at T1 → notified == 1 on each of the two runs,
  # with ats_job_id "…@expected" then "…@open"

  # Shipped table, today = 2026-10-04 (the live expectation, Case B)
  s = run_once(cfg, [KnownProgramsSource(today=date(2026,10,4))], ...)
  assert s.notified == 0
  assert "no_published_round" in s.sources["known_programs"]["report"]["MLH Fellowship"]
  assert s.sources["known_programs"]["report"]["outreachy-2027-05"] == "outside_lead_window"
  ```
- **Live acceptance after deploy:** the run page shows `known_programs` count 0 with the per-round
  reasons above, and no program notification. That is a pass. The first program notification is
  expected when a round enters its lead window (~2026-12-16 for Outreachy May 2027, ~2026-11-25 for
  LFX spring) or when someone records a newly published round.
- **Maintenance:** `TABLE_VERIFIED_ON`; the weekly heartbeat lists every program whose
  `state_checked_on`/`geo_checked_on` is older than 30 days as "re-check: <url>", and every
  `no_published_round` program. A test fails when no round has a deadline more than 60 days ahead.
- **Depends on:** S0 (source `report`), S1, S2 (step-1 rule), S5 (gate routing).

### E1 → S7 — Himalayas adapter (build only if the probe passes)

- **E1 probe:** `scripts/probe_himalayas.py`, run locally or by `workflow_dispatch`. Four queries
  against `https://himalayas.app/jobs/api/search`, `sort=recent`, pages 1–3, 1 s apart:
  `employment_type=Intern&worldwide=true`; `employment_type=Intern&country=ET`;
  `seniority=Entry-level&worldwide=true`; `seniority=Entry-level&country=ET`. Print per query:
  `totalCount`, age histogram from `pubDate` (epoch seconds), count passing `role_family_ok`,
  count with empty `locationRestrictions`, any 429s, and per employer the number of target-class
  listings with no restriction or including Ethiopia (input to the narrow flywheel in §3).
  **Pass:** ≥10 distinct `role_family_ok` listings published within the last 30 days across the
  four queries, and no 429 at this request volume. Record the output in `STATE.md` either way.
- **S7 adapter (`sources/himalayas.py`, registered in `cli._REGISTRY`, name `"himalayas"`):**
  same four queries; stop a query on 429 and log it; raise only if all four fail. Mapping:
  `title`; `company=companyName`; `apply_url=applicationLink`; `ats_provider="himalayas"`;
  `ats_job_id=guid`; `location_raw = "; ".join(locationRestrictions) or "Worldwide"`;
  `remote_status=REMOTE`; `employment_type`: "Intern" → `INTERNSHIP`, else if `seniority`
  contains "Entry-level" → `NEW_GRAD`, "Full Time" → `FULL_TIME`, "Contractor" → `CONTRACT`, else
  `UNKNOWN`; `description`; `posting_date` from `pubDate`; `deadline` from `expiryDate` if present.
  `SourceConfig` gains `himalayas_queries` with those four as the default. Terms compliance: the
  issue line links to the Himalayas listing and names Himalayas; nothing is resubmitted elsewhere.
- **Tests:** recorded fixture `tests/fixtures/himalayas_search.json`; mapping; 429 handling;
  empty-restrictions → "Worldwide" → `WORLDWIDE_REMOTE` through S2.
- **Depends on:** S2, S3, S5; E1 pass.

### S8 — Add the `canonical` Greenhouse board

- Verify the token with `scripts/verify_boards.sh`; add to `greenhouse_boards` with a provenance
  comment. No other boards.

### E2 — Local source probe (decision point, not a build)

- Read 30 days of `t.me/s/freelance_ethio` (paginate with `?before=`), count posts whose "Job
  Title" passes `role_family_ok` and whose title or type marks intern/junior/trainee. Review
  Telegram's terms for automated reading of public previews.
- **Pass:** ≥4 such posts in 30 days and no terms conflict. If it passes, write a
  `Decisions that override PLAN` entry proposing a new `EligibilityCategory` for onsite/hybrid in
  the user's own country (currently folded into `UNKNOWN @ 0.4`) — that is a frozen-spine change
  and needs Dagi's sign-off before any adapter work.

---

## 6. Observability (minimum)

Per run, in `runs.summary` and on the Actions run page:

- `sources`: per source `ok`, `count`, `error`, plus `skipped_records`.
- `by_type` after normalize; `by_eligibility` after classify.
- `rejects`: reason → count (`eligibility:*`, `deadline_passed`, `type_unwanted:*`,
  `seniority_title:*`).
- `gate`: reason → count (`not_new`, `already_notified`, `not_target_class`, `role_family`,
  `eligibility_unknown`, `unknown_cap`).
- `near_misses`: top 5 unselected survivors with their gate reason.
- `notified`, and whether the issue was created (the workflow step's exit status).

Invariant, enforced by a test and asserted at runtime with a warning:
`discovered − merged − Σrejects − Σgate = notified`.

With this, every zero-result run reads as one of: source returned nothing · all rejected for
reason X · survivors all already known · survivors not in a target class · delivery failed.

---

## 7. Verification

- **Unit:** tables for `_classify_location`, the three title regexes, `role_family_ok`,
  `filter_reason`, `gate_reason`, known-programs windows, Himalayas mapping.
- **Integration:** `run_once` with fixture sources → asserts the funnel invariant and the exact
  reason histogram; a fixture mixing an EMEA intern, a US intern with the same title, a senior
  role, a sales intern, and a stipend program → exactly the EMEA intern and the program are
  selected.
- **Regression:** the C4 and C7 reproductions as permanent tests; a re-classification script over
  the 50 stored rows asserting 0 boilerplate-rescued positives.
- **Live source:** `scripts/verify_boards.sh` for ATS tokens; `scripts/probe_himalayas.py`;
  both run by hand or `workflow_dispatch`, never in CI.
- **End to end:** one manual run after S1 with a seeded item → issue exists → Dagi confirms the
  notification arrived → `notified_at` committed. Then one manual run after S6 → funnel visible, invariant
  holds, `known_programs` reports a reason for every round it did not emit, and program notifications
  number exactly as many as rounds satisfying the S6 predicates (zero on 2026-10-04).

---

## 8. Acceptance criteria

1. Every run record satisfies the funnel invariant; no run ends with an unattributed zero.
2. Re-classification of the stored rows: 0 positive-eligibility rows whose location names only
   non-user places.
3. Delivery confirmed by Dagi on a real device.
4. Golden set: `role_family_ok` precision ≥ 0.9, recall ≥ 0.8.
5. Notifications are a consequence of qualifying records, never a target. The S6 acceptance test
   passes in all of Case A, B and C. On the first post-deploy run, the number of delivered items
   equals the number of records passing the gate, each carries its eligibility evidence and
   unchecked conditions, and a run with zero delivered items shows a reason for every fetched
   target-class record in `internship_funnel`. With the table as verified on 2026-10-04, zero
   program notifications is the correct result.
6. 14-day observation after S7 (or after S6 if E1 fails): Dagi ticks the items worth applying to in
   each issue. Review thresholds (targets for judging the system, not forecasts of supply):
   **≥3 delivered items per week on average and ≥60% ticked.** Below 1 per week, read
   `internship_funnel` before changing anything: if few target-class records were *fetched*, the
   constraint is coverage → run E2 and evaluate the "later" sources; if many were fetched and
   *rejected for eligibility*, hand-audit the rejected samples from the weekly heartbeat for false
   rejections before touching any rule. Below 60% ticked, read the unticked items' reasons and
   tighten `role_family_ok` or the eligibility rules.
7. All pre-existing tests pass or carry a one-line justification for the change.

---

## 9. Boundaries

Do not change without new evidence and a `Decisions that override PLAN` entry:

- The `Opportunity` schema, enums, value objects, `Source` protocol, stage order, stage signatures,
  SQLite schema. Everything above fits inside them (`NEW_GRAD` already exists; `runs.summary` is
  free-form JSON).
- `DISQUALIFYING_ELIGIBILITY`, and the rule that `UNKNOWN` is never disqualifying and never
  auto-eligible.
- $0: no paid service, no LLM API. GitHub Issues, Actions, and the Himalayas public API are free;
  respect its rate limit and attribution terms.
- No scraping of LinkedIn, Indeed, robots-disallowed paths (Remotive API path, LFX site,
  ethiojobs `/api`).
- No new ATS boards beyond `canonical`; no discovery crawler; no GONE detection in this iteration.
- Do not retune `relevance_threshold` — it leaves the critical path instead.

This spec ends the observation freeze recorded in `STATE.md`; the implementer's first write is a
STATE entry saying so and pointing here.

---

## 10. Final sequence

1. **S0** funnel → one manual run → record the reason table in `STATE.md`. Run the **E1** probe
   now as well: it is read-only, depends on nothing, and with no program round in its window until
   late November it decides whether anything can be delivered before then.
2. **S1** issue delivery → seeded test → Dagi confirms receipt. (Gate.)
3. **S2** eligibility by location field → re-classify stored rows.
4. **S3 + S4** type/level inference, seniority filter, dedupe by location.
5. **S5** title scoring + deterministic gate + golden set.
6. **S6** programs calendar with dated evidence → Case A/B/C test passes; live result today is
   zero program notifications with reasons.
7. **S7** Himalayas adapter if E1 passed; **S8** `canonical` board; any employers E1 flagged.
8. Observe 14 days against criterion 6. Run **E2** only if supply is the measured constraint.

Steps 1–2 make every later result visible and delivered. Steps 3–5 make the verdicts correct.
Steps 6–7 are the only ones that add supply, and they come last so that what they bring in is
judged by a pipeline that can be trusted.

---

## 11. Execution mode: one session, one pass, resumable

Revised 2026-10-04 (third version; supersedes the subagent roster and the four-session handoff).
One Claude Code session, one model (the one Dagi launches — Opus 5.5), started from the `job-scout`
folder. It implements every step in §10 order without waiting for Dagi, and keeps `STATE.md`
current so the context can be cleared at any time and the work resumed from the files alone.

Why this replaced the earlier versions:

- Subagents under an orchestrator pay a cold start and a review per step. The plan is mostly serial
  (steps share `score.py`, `notify.py`, `eligibility.py`), so that overhead buys almost no
  parallelism, and model pinning failed in practice.
- Four model-specific sessions removed the orchestrator but required three manual restarts with
  model switches and three stops for Dagi. The only saving was running a cheaper model on the
  mechanical steps (S3, data files, fixtures), which are a small share of the work.
- A single session has no handoff loss and no pinning problem, and the strongest available model
  writes every step, including the hard ones. Tiering exists to save cost; it does not raise
  quality, and Dagi has said cost is not the constraint.
- What a single session lacks is independent review. That is added back below as fresh-context
  reviewers, which is the one place extra tokens buy quality.

No implementer subagents and no model switching: the main session writes all code. Run at the
highest reasoning effort the session offers.

### Independent review

After the acceptance criteria pass for **S2, S5 and S6** (the steps where a wrong rule looks like a
pass), and once more for the whole branch at the end, spawn one reviewer subagent: the built-in
general-purpose agent on the same model as the main session (no pinned agent definitions needed),
read-only.

- Give it only: the spec section for the step, §9 (boundaries), the diff (`git diff <base>..HEAD`
  for that step), and the test files. Do not give it your reasoning or your summary of the change.
- Ask it for: places the code departs from the spec; inputs that would be classified wrongly, with
  a concrete example each; reason codes that can overlap or be skipped; tests that pass without
  testing the stated behaviour. Findings ranked by severity, each with a failing input.
- For every finding: turn it into a test first. If the test fails, fix the code. If it passes,
  record the finding as refuted with the test name.
- Record in `STATE.md`: findings, which were confirmed, which were refuted, the commits that fixed
  them. A step is "done and verified" only after its review is closed.
- The final whole-branch review also checks the funnel invariant end to end and that §8 criteria
  1, 2, 4, 5 and 7 hold.

### Branch and commits

- All work on one branch, `next-iteration`. `main` is not touched in this pass, so the daily
  scheduled run keeps its current behaviour until Dagi merges.
- One or more commits per step, each message prefixed with the step id (`S0: ...`). Commit before
  every `STATE.md` update so that `git log` and `STATE.md` never disagree.

### The resume block

`STATE.md` starts with a block in exactly this shape, rewritten (not appended) at every checkpoint:

```
## RESUME — next-iteration
Branch: next-iteration      Last commit: <hash> <subject>
Step in progress: <S-id or "none">
  Sub-progress: [x] done item  [ ] remaining item ...
Steps done and verified: S0 (<hash>), S1 (<hash>), ...
Reviews: S2 <open|closed>, S5 <open|closed>, S6 <open|closed>, final <open|closed>
Next action: <one sentence>
Pending human checks: <list, see below>
Deviations from spec: <list or "none">
Unverified facts still in code: <list or "none">
```

Checkpoints, all mandatory:

1. When a step starts: set "Step in progress" and write its sub-progress checklist.
2. After each commit inside a step: tick the checklist.
3. When a step's acceptance criteria pass: move it to "done and verified" with the commit hash and
   the evidence (numbers) in the step log below the block; set the next action.

### Resuming after a cleared context

Read CLAUDE.md, PLAN.md, STATE.md and this spec. Run `git status`, `git log -8` and the tests. If
the resume block and `git log` disagree, git is the truth: fix the block first. Re-run the
acceptance check of the last step marked done; if it fails, that step is reopened. Then continue
from "Next action". Uncommitted changes found on resume belong to the step in progress: inspect
them, then either finish and commit them or discard them, and say which in the step log.

### What does not stop the pass

These were gates in earlier versions. They are now recorded under "Pending human checks" and the
pass continues:

- **Funnel reason split (S0).** Produce it with a local run against a copy of `data/scout.db`
  (never the committed file), record the table in `STATE.md`, continue. S2 does not depend on it:
  S2 rests on C4, which was reproduced directly.
- **Delivery confirmation (S1).** Implement and unit-test S1. Dagi confirms on a real device after
  the pass, by dispatching the workflow on the branch. If it fails, the Telegram fallback is the
  first follow-up.
- **`target_roles` (S3).** Ship the default list in S3; Dagi may edit it later. It is config.
- **E1 probe.** Run it at the start. Pass → build S7. Fail, or the network is unavailable → skip
  S7, record why, continue.
- **Live facts** (OFAC list, programs table, `canonical` token). Verify if the session has network
  access. Anything it could not verify stays in the conservative state the spec already defines
  (`UNKNOWN`, round not added, board not added) and is listed under "Unverified facts".
- **E2** is not part of this pass.

### What does stop the pass

- A step appears to need a frozen-spine change.
- The repo contradicts the spec in a way that changes a decision (not merely a fact).
- Anything that would cost money.
- A step fails its acceptance criteria after two honest attempts: stop, leave the evidence in
  `STATE.md`.

### When to clear the context

Safe at any checkpoint. Recommended at step boundaries, after a step is marked done and verified:
in particular after S1, after S4 (before the gate work in S5), and after S6. A fresh context that
re-reads the spec section for the next step works from the source text, not from a compacted memory
of it.

### End of the pass

`STATE.md` lists every step with its evidence, the pending human checks in the order Dagi should
do them, and the exact commands for each (dispatch the workflow on the branch, confirm the issue
arrived, merge). Nothing is merged to `main` and nothing is reported as pushed unless it was.

---

## Sources

- Repo `DagiHabtu/job-scout` at `a2f685b`; `data/scout.db` (31 run records, 50 opportunity rows).
- https://boards-api.greenhouse.io/v1/boards/gitlab/jobs · https://boards-api.greenhouse.io/v1/boards/sourcegraph91/jobs
- https://api.ashbyhq.com/posting-api/job-board/posthog · https://api.ashbyhq.com/posting-api/job-board/deel
- https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships/dev/.github/scripts/listings.json
- https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/.github/scripts/listings.json
- https://himalayas.app/api · https://himalayas.app/jobs/api/search
- https://jobicy.com/api/v2/remote-jobs · https://remoteok.com/api?tag=internship
- https://hn.algolia.com/api/v1/search?tags=comment,story_49922569&query=intern
- https://www.outreachy.org/docs/applicant/ · https://developers.google.com/open-source/gsoc/faq · https://docs.linuxfoundation.org/lfx/mentorship/mentee-guide/am-i-eligible · https://www.tfaforms.com/4956119 (MLH application form)
- https://www.outreachy.org/ · https://docs.linuxfoundation.org/lfx/mentorship/mentorship-program-timelines · https://fellowship.mlh.com/
- https://t.me/s/freelance_ethio · https://ethiojobs.net/robots.txt
