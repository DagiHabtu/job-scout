# Job Scout — Iteration 3: reviewable delivery, honest aggregator eligibility, labels (2026-10-21)

Audience: Claude Code (implementer) and Dagi (owner). Written against `main` at `06dc4c6`
(scheduled run 2026-10-21), the committed `data/scout.db`, delivery issues #1–#19, and Dagi's labels
for all 35 delivered items, given on 2026-10-21.

Labels: **FACT** = observed directly (issues, DB, code run). **INFERENCE** = supported, not measured.
**HYPOTHESIS** = unverified.

**Authority.** Dagi asked for this pass on 2026-10-21. It ends the observation period recorded in
`STATE.md` (2026-10-04 → 2026-10-18; this is that review, three days late). It authorizes exactly the
changes in §4, nothing else. The frozen spine (CLAUDE.md §Frozen spine) is not touched; if any step
appears to need a spine change, stop (see §7).

---

## 1. What the review found

### 1.1 The label channel produced nothing (FACT)

Spec 2026-10-04 §8 criterion 6 measures the system by Dagi ticking "Apply" checkboxes in each issue.
In 17 days, across 18 delivery issues, **zero checkboxes were ticked.** Dagi then reviewed all 35 items in
one sitting on 2026-10-21, but only through a separate triage page that showed, for each item, a plain
summary of what the job is, what it asks for, and what it pays. He said why: he did not want to open
each posting. So the blocker was the cost of judging an item from the issue, not the cost of ticking.
The issue shows the system's evidence (category, confidence, matched signals), not the facts a person
decides on.

### 1.2 Dagi's decisions (FACT)

Apply 6 · Maybe 5 · Skip 24 (full table in Appendix A; seeded as data in §4.8).

| Delivered in the top section | Items | Picked (apply or maybe) | Apply only |
|---|--:|--:|--:|
| Oct 4 backlog run ("Actionable") | 9 | 5 (56%) | 4 |
| Oct 5–19 daily runs ("Apply") | 23 | 6 (26%) | 2 (9%) |

Criterion 6's target is 60%. The ongoing feed is the problem. Skipped items in "Apply", by cause:

| Cause | Items skipped | Mechanism |
|---|---|---|
| Invented "Worldwide" | Talent Journey ×2 (body: "Remote (Europe; Middle East; North America)"), micro1 (body: "US-based"), Xperteez ×2 (body: "Based in an English-speaking country", under Preferred), EWOR ×2 ("based in Europe or the Americas") | `sources/himalayas.py:69` writes `location_raw = "Worldwide"` when `locationRestrictions` is empty. The October fix made the location field authoritative over body text, so a field the adapter invented outranks what the employer wrote. This is constraint #2 failing in the permissive direction, and is `STATE.md` "Still open (2)" ("We are hiring only US-based candidates …" with location Worldwide → still wrongly passed). |
| Over-broad role words | Video Data Collector (`data`), Teaching Assistant: Supply Chain Analyst, Antifraud Analyst Junior (`analyst`) | Verified by running `role_family_ok` on `main`. |
| Unpaid | Holiday World, Flowai, Makerble DevOps Volunteer, Bridges Cyber Security Volunteer | Pay is not a dimension. Dagi skipped all four. |
| Mislabelled type | EWOR "co-founder" fellowships typed INTERNSHIP | Himalayas `employmentType: "Intern"` trusted over a title naming a founder/head role. |

**Pay drives choices (FACT, Dagi 2026-10-21).** His one pick outside his stated interests (Vantum QA
Tester, USD 500–1,000/month, part-time) was chosen because it pays. So: unpaid roles are not wanted;
paid part-time work is wanted even outside his interests.

### 1.3 Recall is not the constraint (FACT)

The three Monday heartbeats (#6, #11, #19) list rejected target-class samples and near-misses. Every
rejected sample is a correct rejection (Canonical HR/sales graduate roles in the Americas/APAC/UK). Every
high-scoring near-miss had already been delivered. One wrong rejection was found: "Junior Software
Engineer — Mimidentalclinic" → `stage:experience` on "Stage: Established, 20+ years operational" (company
age read as a requirement).

Consequence: after this pass the feed will be smaller, roughly one strong item a week from current
sources (INFERENCE from 14 days). That is the supply, not a defect. Loosening filters is not a remedy.
Adding sources is the volume lever and is out of scope here (§6).

### 1.4 Delivery cadence (decided by Dagi, 2026-10-21)

Daily issues of 1–6 items went unread for 17 days; Dagi reviews in batches. **Decision:** one weekly
issue on Mondays (Africa/Addis_Ababa date), merged with the heartbeat; an immediate issue only for
urgent items (§4.6). The daily scheduled run itself stays daily (fetching, persistence, lifecycle).

---

## 2. Outcome this pass must produce

On Dagi's 35 labelled items (Appendix A), evaluated with the new rules as if new, `today = 2026-10-21`,
uncapped:

| Section | Items | Dagi's labels |
|---|---|---|
| Apply | Canonical Junior Kernel, Canonical Junior Ubuntu, CloudCops (both records) | all picked |
| Check eligibility | Ritual SWE Intern, Ritual Research Intern, Emetlab, Avary, GitLab EOI ×2, Affidea Innovation, Affidea DevOps, ArchWell | 7 of 9 picked |
| Aspirational | Tether | skipped (known residual, by design) |
| Outside your stated interests | Vantum (first, shows its pay), Makerble Automated Tester, NightOwl CRM, Affidea QA/UAT, Resilio | Vantum picked; others are one-line entries (known residuals) |
| Not selected | the other 17 | all skipped |

No picked item is dropped. Apply is 3/3 and Apply + Check is 10/12 on this sample. **These numbers are
in-sample:** the rules in §4 were written with these 35 items in view, so they show the rules do what they
say, not how well they generalise. §5 criterion 5 is the real test.

---

## 3. Boundaries

- Frozen spine unchanged: `Opportunity` fields, enums (`EligibilityCategory` stays at 7 values),
  value objects, `Source` protocol, stage order and stage signatures, SQLite schema. Everything below
  fits inside: new facts ride in `location_raw` strings, `Eligibility.confidence/evidence`, and
  prefixed strings in `Relevance.matched_signals/concerns` (as `stage:` and `interest:` already do).
- $0. GitHub Actions and Issues only. No LLM (constraint #3): all summarisation in §4.5 is
  deterministic text extraction.
- Do not retune `relevance_threshold`, `max_required_years`, or the stage rules beyond §4.7.
- No new sources, no cross-run dedupe, no GONE detection.
- Employer-stated location fields (Greenhouse/Ashby/Lever `location_raw`) stay authoritative over body
  text, as decided in October (Decision #6). The new body rules in §4.1 apply only where the location
  field is absent, bare "Remote", or the aggregator marker.

---

## 4. Changes, in dependency order

Read the named code before changing it; earlier iterations added review fixes (deviations i2-a…i2-s in
`STATE.md`) that this spec does not restate. Where this spec's suggested mechanism conflicts with how
the code is built, **the outcomes in §2 and the tests below win over the mechanism**; record the
deviation. Where they conflict with the spine, stop.

### 4.1 Honest eligibility for aggregator listings

**Files:** `sources/himalayas.py`, `_geo.py`, `eligibility.py`.

1. `_geo.py`: add `NO_RESTRICTION_LISTED = "Remote (no location restriction listed)"`. Add
   `"middle east"` and `"english-speaking country"`/`"english speaking country"` to the places that are
   not the user's (`REGIONS_EXCLUDING_AFRICA` or the module's equivalent). `"middle east and africa"`
   must still count as including the user.
2. `himalayas.py:69`: `location_raw="; ".join(restrictions) or NO_RESTRICTION_LISTED`. Update the module
   docstring: an empty `locationRestrictions` means the aggregator lists no restriction, not that the
   employer hires worldwide.
3. `eligibility.py`, `_classify_location`: the marker is its own label (call it `UNSTATED`). It is
   treated like `BARE` (the body decides), except its no-evidence result is `UNKNOWN` **0.6** with
   evidence `"Himalayas lists no location restriction; the posting states none"`.
4. Body rules for `BARE` / `UNSTATED` / no location (extend the existing step 4; reuse the existing
   body-exclusion code, including the "position/role … based in" pattern from c54fe46, rather than
   duplicating it). First match wins:
   - **(a) Required location naming only other places** → `REMOTE_EXCLUDES_USER` **0.75** (at the
     disqualify threshold, so the hard filter rejects it with reason `eligibility:remote_excludes_user`).
     Shapes: `(based|located|resid(e|ing|ent)|living) in (the )?<place>`; `<place>[- ]based` not
     preceded within three words by `a|an|our|the` (so "a US-based company" is not a requirement);
     `Remote \(<list>\)` where every list item is a non-user place. Places are labelled with `_geo` as in
     S2. If the same sentence mentions relocation (`relocat`), the result is `UNKNOWN` 0.5 instead, with
     the sentence as evidence.
   - **(b) Preferred location naming only other places** — same shapes, but within 250 characters after
     `preferred|nice to have|bonus|a plus` → `UNKNOWN` **0.45**, evidence `"states a location
     preference: '<sentence>'"`.
   - **(c) Explicit worldwide phrase** (existing `_WORLDWIDE` plus `"no geographic restrictions"`,
     `"no geographical restrictions"`, `"remote (global)"`) → `WORLDWIDE_REMOTE` 0.7, as now.
   - **(d)** otherwise → `UNKNOWN`: 0.6 for `UNSTATED`, 0.5 for `BARE`, 0.3 for no location.

   (a) and (b) are checked before (c): an explicit region list beats benefit boilerplate ("Remote work
   flexibility from anywhere in the world" in Talent Journey's benefits), the same principle as Decision #6.

**Tests** (table-driven; bodies are the stored texts where named):

| location_raw | body | expected |
|---|---|---|
| marker | Talent Journey backend body | `REMOTE_EXCLUDES_USER` 0.75 |
| marker | micro1 body ("… US-based …") | `REMOTE_EXCLUDES_USER` 0.75 |
| marker | "We are a US-based company. Work from anywhere." | `WORLDWIDE_REMOTE` 0.7 |
| marker | Xperteez Junior SWE body | `UNKNOWN` 0.45, evidence quotes the preference |
| marker | EWOR body ("based in Europe or the Americas or open to relocate") | `UNKNOWN` 0.5 |
| marker | CloudCops body ("work from anywhere") | `WORLDWIDE_REMOTE` 0.7 |
| marker | Bridges body ("no geographical restrictions") | `WORLDWIDE_REMOTE` 0.7 |
| marker | Ritual SWE body | `UNKNOWN` 0.6, evidence names the marker |
| marker | "Remote (Middle East and Africa)" | `REMOTE_REGION_INCLUDES_USER` |
| `Home based - Worldwide` | "We are hiring only US-based candidates" | unchanged: `WORLDWIDE_REMOTE` (employer field authoritative; record the case in STATE as accepted) |

All existing eligibility tests pass or carry a one-line justification. Update `STATE.md` "Still open (2)".

### 4.2 Gate: an "unverified" tier

**File:** `notify.py`.

Define unverified = category `UNKNOWN` and confidence ≥ 0.6. In `gate_reason`'s eligibility branch:
positive → selected (unchanged); unverified → selected for `INTERNSHIP` **and** `NEW_GRAD`, section
"Check eligibility"; `UNKNOWN` < 0.6 → internship selected (unchanged), new-grad `eligibility_unknown`
(unchanged). This keeps rule 2: aggregator-only evidence is surfaced as uncertain, never as eligible.

In "Check eligibility", each item's eligibility line reads, for the marker case: "No location
restriction listed on Himalayas or in the posting. Confirm before applying."

### 4.3 Role family

**File:** `score.py` (`_ROLE_FAMILY`).

Remove bare `data`, `analyst`, `analytics`. Add `data (engineer(ing)?|scien(ce|tist)s?|platform|
infrastructure)`. Expected: "Video Data Collector (Smartphone)", "Teaching Assistant: Supply Chain
Analyst", "Antifraud Analyst Junior", "Data Analyst - Remote, Contact" → `role_family`; "Data Scientist
Intern", "Junior Data Engineer" → pass.

Re-run `scripts/calibrate.py` on `golden_titles.csv`. If a golden row labelled positive now fails, list it.
Relabel only rows that contradict Dagi's 2026-10-21 decisions, and cite Appendix A in the commit; for any
other conflict, stop and record it. Report precision/recall before and after (they are in-sample).

### 4.4 Pay

**Files:** `score.py` (or new `pay.py`), `notify.py`, `config.py`, `config/profile.yaml`.

- Profile: `pay: { accept_unpaid: false }` with comment `# Dagi 2026-10-21: unpaid not wanted; paid
  part-time work is wanted even outside stated interests`. Defaults in `UserProfile` match.
- `pay_of(opp) -> tuple[str, str | None]`, verdict + quoted snippet, carried as `pay:` entries in
  `Relevance.concerns`/`matched_signals` (like `stage:`):
  - `unpaid`: title matches `\b(unpaid|volunteer)\b`, or body matches
    `\b(this|it)\s+(is|will be)\s+an?\s+(unpaid|volunteer)\b`, `\bunpaid\s+(internship|role|position)\b`,
    or `\bvolunteer\s+(role|position)\b`.
  - `contingent`: `\b(goal|performance)[- ]based\b` within 80 chars of `compensation|paid`.
  - `stipend`: `\bstipend\b` (and not unpaid).
  - `stated`: a currency amount with a period — prefix form `(US\$|\$|USD\s?|€|EUR\s?|£)\s?\d[\d,.]*k?`
    with an optional range (`-`, `–`, `to`) and a period (`/|per|a` + `hour|hr|week|month|mo|year|yr`), or
    suffix form `\d[\d,.]*\s?\$\s?/\s?(hr|hour)`. Snippet = the match.
  - `unstated` otherwise.
- Gate: after `role_family`, before stage: `unpaid` and not `accept_unpaid` → reason `pay:unpaid`.
  Stipend programs are exempt.
- "Outside your stated interests": order items with a `stated` or `stipend` pay first, then by title fit;
  each line shows company and the pay snippet when present.
- `config/profile.yaml`: add `"tester"` to `not_interested`.

**Tests** (stored bodies): Holiday World, Flowai, Makerble DevOps, Bridges → `unpaid`; Makerble Automated
Tester → `contingent`; Vantum → `stated` "$500 to $1,000 USD per month"; Flowmingo → `stipend`; Resilio →
`stated` "35$/hr"; a negative: "Our team volunteers at local food banks" → `unstated`.

### 4.5 Decision facts on every item (the summary Dagi asked for)

**New file:** `src/job_scout/facts.py` (not spine). Deterministic, no model.

`key_facts(opp) -> dict` with:
- `role`: up to 250 chars after the first heading in `About the role|The role entails|What you'll do|
  What You'll Do|What You Will Do|Responsibilities|Key Responsibilities|Role Overview|Scope of Work|
  Job Summary|Position Overview|Your tasks|deine aufgaben`, cut at a word boundary with "…".
- `asks`: up to 350 chars after the first heading in `Requirements|Qualifications|What we are looking
  for|What We're Looking For|What we're looking for in you|About you|What You'll Need|What You'll Have|
  Required Skills|Skills, Knowledge and Expertise|Who We're Looking For|Who You Are|dein profil`,
  stopping at the next known heading (include `Nice to have|Nice-to-have|Preferred|Bonus|Benefits|What we
  offer|Why join|Extras|Perks|Compensation|About`).
- `pay`: from §4.4.
- `hours`: `\d+\s*(?:[-–]|to)?\s*\d*\s*\+?\s*(hours|hrs)\s*(/|per|a)\s*week` (first match).
- `location`: up to 2 sentences matching the §4.1 shapes or `timezone|time zone|overlap|GMT|UTC|CET`.

Headings arrive flattened by `html_to_text`; match them as substrings, case-sensitively where the list
gives a case, and take the earliest occurrence. Missing fields are omitted, never invented.

**Acceptance** on the 34 stored Appendix A descriptions (`xp-da`'s may be empty): `asks` found for ≥ 80%,
`role` for ≥ 70%; print the coverage table and the extracted facts for the 11 picked items into the step
log so Dagi can judge them.

### 4.6 Delivery: weekly digest, urgent-only daily, numbered items

**Files:** `notify.py`, `pipeline.py`, `.github/workflows/scout.yml`.

- **Pending pool.** A record is deliverable when the gate selects it and either its status is NEW/UPDATED,
  or it was never notified (`notified_at` is null) and was first seen within the last 14 days. Use the
  store's `first_seen` as the truth (check whether `discovered_date` is re-stamped each run before relying
  on it). `today` must be injectable for tests. A keyword-only `today` parameter on non-stage helpers is
  acceptable; changing a frozen stage signature is not.
- **Urgent** = a selected stipend-program record, or a selected record whose `deadline` is within 14 days
  of today.
- **Daily (not Monday):** deliver only urgent items. Everything else selected stays undelivered, reason
  `deferred:weekly` in the run's gate histogram, `notified_at` untouched.
- **Monday (Africa/Addis_Ababa date):** deliver every deliverable item in one issue
  `Job Scout weekly — <N> new — <date>`. Body: the digest sections first (Apply, Check eligibility,
  Aspirational, Outside your stated interests), then the funnel inside `<details><summary>Weekly
  funnel</summary>…</details>`. This replaces the separate heartbeat issue.
- **Per-digest caps** (the weekly pool is larger than a day's): Check eligibility 10, Aspirational 2,
  Outside interests 5. Overflow keeps its cap reason and appears in near-misses.
- **Item format** (Markdown, numbered continuously across sections):
  ```
  1. [Title](url) — Company · type · location
     - **Role:** …            (facts.role)
     - **Asks:** …            (facts.asks)
     - **Pay:** …  · **Hours:** …
     - **Location:** …        (facts.location, else omitted)
     - **Eligibility:** <category> (<confidence>) — <first evidence line>
     - **Stage:** <verdict> — <quote>   (as now)
     - via Himalayas (link)   (as now, for Himalayas items)
  ```
  Drop the "matched:" signal line from the issue (keep it in the HTML artifact). Under "Outside your
  stated interests", keep one line per item, plus company and pay.
- **End of body:** `Reply with a comment such as: apply 1,4 · maybe 2 · skip rest` and a hidden map
  `<!-- scout-items {"1": "<record key>", "2": …} -->`.
- **Heartbeat near-misses:** exclude reasons `already_notified`, `not_new`, `deferred:weekly`.
- **Workflow:** the scout job runs daily as now. Create the issue when `data/notify.md` is non-empty
  (existing pattern); the pipeline decides weekly vs urgent and the title. Keep "commit state after issue
  creation" so a failed issue step re-delivers next run.

**Tests:** pending pool (NEW; ACTIVE + never notified + first seen 10 days ago → deliverable; 20 days ago →
not; notified → not); Tuesday run with one urgent + two normal → issue contains only the urgent item, two
`deferred:weekly`; Monday run → all three, numbered 1–3, hidden map parses as JSON with three keys; the
funnel invariant still holds with `deferred:weekly` counted in the gate histogram.

### 4.7 Small fixes

- `himalayas.py` `_employment`: `"Intern"` → `INTERNSHIP` only when the title does not match
  `co-?founder` or `normalize._SENIOR_TITLE`; otherwise fall through to the other rules. Test: both EWOR
  titles are not `INTERNSHIP`.
- `score.py` `_NOT_REQUIREMENT`: add `operational|operating|established`. Test: the Mimidentalclinic
  sentence is not an experience requirement.

### 4.8 Labels channel

**Files:** new `src/job_scout/labels.py`, new `.github/workflows/labels.yml`, new `data/labels.jsonl`.

- **Seed:** convert Appendix A (also attached as `labels_2026-10-21.json`) into `data/labels.jsonl`, one
  line per record key: `{"key", "title", "company", "decision", "labelled_at": "2026-10-21", "source":
  "triage-page"}`. CloudCops has two keys; both get `maybe`.
- **Parser:** `parse_label_comment(comment: str, item_map: dict[str, str]) -> list[tuple[key, decision]]`.
  Grammar, case-insensitive, separators `·`, `;`, `,`, newlines: `(apply|maybe|skip)` followed by item
  numbers, ranges `2-4`, or `rest`/`all`; `rest` means every item not yet named. Unknown numbers or no
  recognised verb → error listing what was not understood. A later comment on the same issue replaces
  earlier decisions for the items it names.
- **Workflow** `labels.yml`: `on: issue_comment: types: [created]`; run only if
  `github.event.comment.user.login == github.repository_owner` and the issue has label `scout`.
  `permissions: contents: write, issues: write`. Steps: checkout; run
  `python -m job_scout.labels` reading the issue body and comment **from the event JSON file
  (`$GITHUB_EVENT_PATH`) or from `env:` variables, never interpolated into a shell command** (comment text
  is untrusted input); append to `data/labels.jsonl`; commit; then add a `+1` reaction to the comment on
  success (no email), or reply with the parse error on failure. Both workflows use
  `concurrency: { group: scout-state, cancel-in-progress: false }`, and both pull with rebase before
  pushing.
- **Tests:** grammar table (`apply 1,4 · maybe 2 · skip rest`, `skip all`, `apply 2-3`, `Apply 1\nskip 2`,
  an unknown number, empty text); injection-shaped comment text (`$(rm -rf /)`, backticks) is stored as
  data and nothing executes.
- **Measurement:** `scripts/label_report.py` prints, from `data/labels.jsonl` joined with the store, the
  share of each section's items labelled apply/maybe. This replaces checkbox counting for criterion 6.

---

## 5. Acceptance

1. **Appendix A regression test** (`tests/test_labels_2026_10_21.py`): load the 36 records for the 35 labels
   from a fixture built from `data/scout.db` (`raw` JSON), reset lifecycle to NEW, run normalize →
   eligibility → hard filter → score → `gate_reason` (uncapped) → `section_of` with `today = 2026-10-21`,
   and assert the §2 placement of every record, with the expected reason code for each unselected one
   (Appendix A column "expected"). If a placement differs because the mechanism differed, record it as a
   deviation; if a picked item is dropped, that is a failure.
2. All pre-existing tests pass or carry a one-line justification each. Report the new total.
3. `facts.py` coverage meets §4.5, with the picked items' facts printed in the step log.
4. A `workflow_dispatch` run on the branch with `seed=true` (existing seed path) on a Monday-mocked date
   produces one weekly issue with numbered items and a parseable hidden map. **Pending human check:** Dagi
   replies `apply 1 · skip rest` on that issue and confirms the reaction appears and `data/labels.jsonl`
   gains the lines on the branch.
5. **Real test, after merge:** four Monday digests. Review threshold, not a forecast: ≥ 60% of items in
   "Apply" + "Check eligibility" labelled apply or maybe, measured by `label_report.py`. If fewer than
   ~2 items a week are delivered, read the target-class funnel first: few fetched means coverage (sources,
   a later decision); many fetched and rejected means hand-audit the rejected samples before changing a
   rule.

---

## 6. Out of scope, recorded

- More sources (supply is the volume constraint, §1.3) — decide after criterion 5.
- Cross-run duplicates across company slugs (CloudCops seen as `cloudcops` and `cloudcops-gmbh`): needs a
  store identity change (spine). One instance so far.
- Stale content (Talent Journey says hiring was planned for Q4 2024); scam signals (Resilio): one instance
  each.
- `max_required_years` (ArchWell and Bridges both read "2 years"): the skipped items had other reasons.
- `STATE.md` "Still open (1)" (Addis onsite = UNKNOWN 0.4) and the CET-timezone wording gap: unchanged.

---

## 7. Execution mode

Same as spec 2026-10-04 §11: one session, the model Dagi launches, highest reasoning effort; no
implementer subagents.

- **Branch** `iteration-3` cut from `main`. Do not merge to `main` and do not push to `main`; Dagi merges.
- **First writes:** copy this file to `docs/SPEC-2026-10-21-iteration-3.md`; add an Observation-log entry to
  `STATE.md` (§8 text); rewrite the RESUME block for this pass.
- **Order:** 4.1 → 4.2 → 4.3 → 4.4 → 4.7 → 4.5 → 4.6 → 4.8 → acceptance 5.1–5.4.
- **Commits:** one or more per step, prefixed `I3-4.1: …`; commit before each `STATE.md` update.
- **Fresh-context review** (built-in general-purpose agent, read-only, same model): after 4.1+4.2, after
  4.6, and once over the whole branch. Give it only the relevant spec sections, §3, the diff and the test
  files. Every finding becomes a test first; fix if it fails, record as refuted if it passes.
- **Stop** if: a step needs a spine change; anything would cost money; a picked item in Appendix A cannot
  be kept selected without contradicting this spec; a step fails its acceptance after two honest attempts.
  Leave the evidence in `STATE.md`.
- **End:** `STATE.md` lists each step with commit and evidence, deviations, the pending human checks in
  order (dispatch on branch → reply to the test issue → merge), and the exact commands.

---

## 8. Text for the STATE.md Observation log

```
- 2026-10-21 — **Observation-period review (due 2026-10-18), with Dagi's labels for all 35 delivered
  items.** Apply 6 · maybe 5 · skip 24 (docs/SPEC-2026-10-21-iteration-3.md Appendix A;
  data/labels.jsonl). Zero issue checkboxes ticked in 17 days: the checkbox label channel produced no data;
  the review happened through a triage page with per-item summaries. Ongoing feed: 2 of 23 "Apply" items
  picked as apply (6 of 23 apply or maybe); Oct 4 backlog run: 5 of 9. Causes of skipped "Apply" items:
  Himalayas adapter writes "Worldwide" for an empty locationRestrictions (Still open (2)); bare
  data/analyst role words; unpaid roles (Dagi: pay matters; his one off-interest pick was chosen for pay);
  EWOR co-founder roles typed Intern. Recall checked against heartbeats #6/#11/#19: rejected samples all
  correct; near-misses all already delivered; one wrong stage:experience ("20+ years operational").
  Supply after precision fixes ≈ 1 strong item/week (inference, 14 days). Cadence decided: weekly Monday
  digest + urgent-only daily. Next: iteration 3 (docs/SPEC-2026-10-21-iteration-3.md).
```

---

## Appendix A — Dagi's labels, 2026-10-21, and expected outcome

`expected` = section, or the reason code for an unselected record, under §4.

| label_id | decision | title — company | record key(s) | expected |
|---|---|---|---|---|
| canon-kernel | apply | Junior Linux Kernel Engineer - Ubuntu — Canonical | greenhouse:5370815 | Apply |
| canon-ubuntu | apply | Junior Ubuntu Software Engineer — Canonical | greenhouse:6707669 | Apply |
| ritual-research | apply | Research Intern — Ritual | himalayas:…/ritual-net/jobs/research-intern-1464631102 | Check eligibility |
| emetlab | apply | Junior Software Engineer — Emetlab | himalayas:…/emetlab/jobs/junior-software-engineer | Check eligibility |
| avary | apply | Data Scientist Intern — Avary.ai | himalayas:…/avary-ai/jobs/data-scientist-intern | Check eligibility |
| vantum | apply | QA Tester — Vantum | himalayas:…/vantum/jobs/qa-tester | Outside interests, first, pay shown |
| ritual-swe | maybe | Software Engineer Intern — Ritual | himalayas:…/ritual-net/jobs/software-engineer-intern-9031169445 | Check eligibility |
| gitlab-eoi | maybe | Backend, Frontend, and Fullstack Engineering EOI — GitLab | himalayas:…/gitlab-com/jobs/backend-frontend-and-fullstack-engineering-expression-of-interest-form | Check eligibility |
| gitlab-sec | maybe | Security Engineer EOI — GitLab | himalayas:…/gitlab-com/jobs/security-engineer-expression-of-interest-form | Check eligibility |
| cloudcops | maybe | Junior DevOps / Cloud Engineer — CloudCops | himalayas:…/cloudcops/jobs/junior-devops-cloud-engineer; himalayas:…/cloudcops-gmbh/jobs/junior-devops-cloud-engineer | Apply (both) |
| affidea-innov | maybe | Junior Digital Innovation Engineer — Affidea BV | himalayas:…/affidea-bv/jobs/junior-digital-innovation-engineer | Check eligibility |
| affidea-devops | skip | Junior DevOps Engineer — Affidea BV | himalayas:…/affidea-bv/jobs/junior-devops-engineer | Check eligibility (residual) |
| archwell | skip | Jr. Network Engineer — ArchWell Health | himalayas:…/archwell-health/jobs/it-analyst-network-engineer-jr-network-engineer | Check eligibility (residual) |
| tether | skip | Research Engineer Intern (Video/Multimodal LLM) — Tether | himalayas:…/tether-operations-limited/jobs/research-engineer-intern-video-multimodal-llm | Aspirational (residual) |
| makerble-test | skip | Automated Tester — Makerble | himalayas:…/makerble/jobs/automated-tester | Outside interests (residual) |
| crm | skip | CRM Developer — NightOwl Consulting | himalayas:…/nightowl-consulting/jobs/crm-developer | Outside interests (residual) |
| affidea-qa | skip | QA and UAT Tester — Affidea BV | himalayas:…/affidea-bv/jobs/qa-and-uat-tester | Outside interests (residual) |
| resilio | skip | Remote UI/UX Reviewer & QA — Resilio Partners | himalayas:…/resilio-partners/jobs/remote-ui-ux-reviewer-quality-assurance-qa | Outside interests (residual) |
| tj-backend | skip | Junior Backend Developer - Future Position — Talent Journey | himalayas:…/talent-journey/jobs/junior-backend-developer-future-position | `eligibility:remote_excludes_user` |
| tj-frontend | skip | Junior Frontend Developer - Future Position — Talent Journey | himalayas:…/talent-journey/jobs/junior-frontend-developer-future-position | `eligibility:remote_excludes_user` |
| micro1 | skip | Usability Tester — micro1 | himalayas:…/micro1/jobs/usability-tester | `role_family` or `eligibility:remote_excludes_user` |
| xp-swe | skip | Junior Software Engineer, Remote - Contract — Xperteez | himalayas:…/xperteez-technology/jobs/junior-software-engineer-remote-contract | `eligibility_unknown` (0.45) |
| xp-ds | skip | Junior Data Scientist, Remote - Contract — Xperteez | himalayas:…/xperteez-technology/jobs/junior-data-scientist-remote-contract | `eligibility_unknown` (0.45) |
| xp-da | skip | Data Analyst - Remote, Contact — Xperteez | himalayas:…/xperteez-technology/jobs/data-analyst-remote-contact | `role_family` |
| xp-video | skip | Video Data Collector (Smartphone) — Xperteez | himalayas:…/xperteez-technology/jobs/video-data-collector-smartphone | `role_family` |
| c1-ta | skip | Teaching Assistant: Supply Chain Analyst — Correlation One | himalayas:…/correlation-one/jobs/teaching-assistant-supply-chain-analyst | `role_family` |
| banco | skip | Antifraud Analyst Junior — Banco Plata | himalayas:…/banco-plata-s-a-institucion-de-banca-multiple/jobs/antifraud-analyst-junior | `role_family` |
| holiday | skip | Software Engineer Internship (UNPAID) — Holiday World | himalayas:…/holiday-world/jobs/software-engineer-internship-unpaid | `pay:unpaid` |
| flowai | skip | Senior Back-End Engineer Intern — Flowai | himalayas:…/flowai/jobs/senior-back-end-engineer-intern | `pay:unpaid` |
| makerble-devops | skip | DevOps Volunteer — Makerble | himalayas:…/makerble/jobs/devops-volunteer | `pay:unpaid` |
| bridges | skip | Cyber Security Volunteer — Bridges for Enterprise | himalayas:…/bridges-for-enterprise/jobs/cyber-security-volunteer | `pay:unpaid` |
| ewor-dev | skip | DevTools Co-Founder / Head of Engineering — EWOR | himalayas:…/ewor-gmbh/jobs/devtools-co-founder-head-of-engineering-100-remote-m-f-d-4866789568 | any non-selection (`type_unwanted:*`, `not_target_class`, or eligibility) |
| ewor-cmo | skip | AI Research Lab Co-Founder / CMO — EWOR | himalayas:…/ewor-gmbh/jobs/ai-research-lab-co-founder-cmo-100-remote-m-f-d-5545667816 | any non-selection |
| canon-grad | skip | Graduate Software Engineer, Open Source and Linux — Canonical | greenhouse:8142329 | `stage:graduate_only` |
| flowmingo | skip | QA/QC Intern — Flowmingo | himalayas:…/flowmingo/jobs/qa-qc-intern | `deadline_passed` |

`…` = `https://himalayas.app/companies`. Full keys are in the attached `labels_2026-10-21.json`.

Note on `canon-grad`: Dagi skipped it, but it hires "2025 and 2026 graduates". Whether it fits depends on
his graduation year, which this spec does not know; `accept_graduate_programs` stays false until he says
otherwise.
