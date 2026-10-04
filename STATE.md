# STATE

## RESUME — iteration-2
Branch: iteration-2 (cut from origin/main bc4154c)      Last code commit: 1dc90fd iteration-2: close final review (followed only by STATE-only commits)
Step in progress: none — **PASS COMPLETE** (S9, S10, S11 done; final review CLOSED)
Steps done and verified: S9 (1608ab3 — unit level; email arrival = pending human check 1), S10 (69df1b3, 1213ac8 — review closed), S11 (e6b94e4, 1dc90fd — final review closed). Baseline: spec §12 43422e0; c54fe46.
Reviews: S10 closed (1213ac8), final closed (1dc90fd)
Next action: Dagi does the pending human checks below, in order. Nothing else is in flight. Do not dispatch, do not merge without Dagi.
Pending human checks (in this order; commands run from `job-scout/`):
  (1) S9 delivery — open https://github.com/notifications and look for the 2026-10-04 issue; in Settings → Notifications enable Email for "Participating, @mentions and custom", confirm the default notification email is verified and is the one being checked, search the mailbox (incl. spam) for `notifications@github.com`. Then dispatch on the branch: `gh workflow run scout --ref iteration-2 -f seed=true` → `gh run watch` → confirm the issue exists (`gh issue list --label scout`), is assigned to you, ends with `cc @DagiHabtu`, and an email arrived. If no email arrives after the settings are confirmed: the Telegram fallback (§12 S9) becomes the first follow-up. Note: this run commits `data/scout.db` to `iteration-2`.
  (2) Merge by pull request (never via local main): `gh pr create --base main --head iteration-2 --title "Iteration 2: delivery assignee/mention, stage fit, interest sections" --body "Implements docs/SPEC-2026-10-04-next-iteration.md §12 (S9–S11) plus the final-review fixes. Evidence, reviews and deviations: STATE.md (RESUME — iteration-2 + pass log)."` then `gh pr merge --merge`. If the PR reports a conflict in `data/scout.db`: `git checkout iteration-2 && git pull && git merge origin/main` → `git checkout --ours data/scout.db && git add data/scout.db && git commit --no-edit && git push`, then `gh pr merge --merge`. Afterwards `git checkout main && git pull`.
  (3) DECISION carried over (onsite/hybrid in Addis = UNKNOWN@0.4 → an Addis NEW_GRAD role is never notified; see next-iteration block, check 4).
  (4) After merge: §8 criterion 6 — 14 days of issues, ≥60% of "Apply" items ticked.
Known limits (final review Lows not fixed, and test gaps): L2 `education.status` is recorded config only (no rule in the spec). L3 "Graduate Research Assistant" reads `not_target_class` (the `_GRAD_PROGRAM_TITLE` lookahead keeps it from NEW_GRAD), not `stage:graduate_only` — still unselected. L4 eligibility "position/role … based in" pattern (c54fe46) sits outside §12's file list — 6 probes, no false negative. L5 generic strong terms ("systems", "ai", "research") cancel most vetoes — spec-literal. L6 "2-4 years" → N=2 (stretch) — spec-literal, test-pinned. Test gaps: the first-run regression test does not check the order inside "Apply", runs in lexical mode (no model), and its synthetic cases preset `employment_type`.
Deviations from spec: (i2-a) [WITHDRAWN 1dc90fd — replaced by i2-p]. (i2-b) S10 `advanced_degree` context words accept plurals (internships, students, …) — Tether's own sentence uses them. (i2-c) `accept_graduate_programs` is applied at score time (verdict `graduate_only_accepted`, positive) because `gate_reason(opp, threshold)` has no profile. (i2-d) `profile.education` replaces an unused free-text field of the same name; a string still loads (defaults). (i2-e) [SUPERSEDED 1dc90fd by i2-n] S10 review H1: `experience_required`/`stretch` read only a requirement-shaped phrase "<N>[+][-M] years|yrs [of] [≤3 words] experience|hands-on" (spec: 60-char window with experience|hands-on|working|professional), skipping company-subject phrases ("we bring 25 years…"); numbers may be words (one–ten) or decimals. (i2-f) S10 review M1/M2: MSc/PhD exclusions and context are read within ±60 chars of the degree word (undergraduate/bachelor only as an or/and/'/' alternative within ±40), not across the whole tag-stripped "sentence"; company-blurb phrases (founded, our mission, team of…) are not requirements. (i2-g) S10 review M4: only "graduated by/in/before/between <month> 20xx" is graduate-only (spec regex also "graduating", which describes a current student); "undergraduate(s)" joins the student exception; a negated mention ("students are not eligible") is no exception. (i2-h) S10 review M6: a body sentence is `fits` evidence only when it addresses candidates (you/candidates/applicants/role/hiring/open to/eligible…). (i2-i) S10 review H2: `internship_funnel` now covers NEW_GRAD too (target classes), so stage rejections are sampled with their quote; labelled "Target-class funnel". (i2-j) `_GRAD_PROGRAM_TITLE` lookahead also excludes "graduate research/teaching/assistant" (graduate-student roles). (i2-k) [WITHDRAWN 1dc90fd — replaced by i2-o] S11: a title with an interest veto is checked only for the role-family VETO words, not for a family word ("QA/QC Intern" has none once `qa` leaves the family; §12's acceptance places it in "outside your stated interests"). Side effect seen live: "CRM Assistant (with Insellerate Experience)" is listed there too. (i2-l) [WITHDRAWN 1dc90fd — replaced by i2-p] S11: an interest-vetoed item with UNKNOWN eligibility stays in "Check eligibility" (§12: that section is unchanged), with an "outside your stated interests ('<term>')" line. (i2-m) `not_interested` / `strong_interest_terms` defaults also live in `UserProfile` (same values as §12), so a profile without them behaves the same.
  Final-review deviations (Dagi's decisions D1–D7, 2026-10-04): (i2-n) D1 — every "<N>[+][-M] years|yrs" mention is a requirement unless its sentence names something else: combined/collective, team of, founded/founders, in business, ago, has/have been, our team/company/engineers/clients/customers, we've/we have/we bring/we were, old/older/age/aged, vesting, stock options, equity, contract, lasts, duration; a span before it (within/over/after/every/per/up to/next/past/last/first) is not a requirement; N>1 with a singular "year" is attributive ("a 10 year … commitment"); a "sentence" longer than 200 chars (a merged list block) is read only ±60 chars around the mention. Measured on the 244 stored descriptions: 36 sentences read as requirements, all genuine; 10 skipped, all non-requirements. (i2-o) D4 — `role_family_ok(title, description)` is checked before the interest veto; QA/QC/quality assurance/tester/testing/sdet is a family only when the title or description names software work (software, web, browsers, mobile app/devices, apps, automation, api, bugs, codebase, coding, selenium/cypress/playwright); `inspector` is a discipline veto; D5 — `linux|kernel|compiler` join the family. Golden set still 1.000/1.000 (in-sample). (i2-p) D3 — least actionable section wins: interest veto → "Eligible, outside your stated interests", else MSc/PhD → "Aspirational", whatever the eligibility (UNKNOWN items say "eligibility not confirmed — check it before applying"); "Check eligibility" holds only would-be "Apply" items, and only those use an `unknown_cap` slot. A title both vetoed and MSc/PhD goes to "outside" (the later, less actionable section). Selection is unchanged: an UNKNOWN new-grad is still `eligibility_unknown` (not selected) even when vetoed or MSc/PhD. (i2-q) D2 — internships are exempt from the years rule: the sentence is shown as "years mentioned (not applied to internships): …" under the `fits`/`no_evidence` verdict. (i2-r) D7 — `rejected_samples` keeps 5, at least 2 of them `stage:graduate_only`/`stage:experience` when present (cap overflows are not stage judgements); the weekly heartbeat now lists the samples of its runs (deduplicated by title+company, same reserve) — §12 says a wrong stage rejection must be visible there, and the heartbeat had no sample table. (i2-s) D6 — a softener up to 150 chars after the degree word (60 before) counts, and one softened mention softens the sentence.
Unverified facts still in code: as in the next-iteration block; plus whether the Himalayas API truncates descriptions (§12 "Limit").

### S10 review findings (CLOSED `1213ac8` — outcomes in the pass log entry "S10 review CLOSED")
- H1 `_EXPERIENCE` reads non-requirements: company age ("we bring 25 years of experience", "10+ years working with"), age limits ("18 years old … working"), vesting ("4 years, plus a professional development budget"), decimal "1.5 years" → 5, "within 3 years working", boilerplate max beats the real requirement ("0-1 years of experience. Our founders have 20 years of experience") → `stage:experience` (dropped).
- H2 NEW_GRAD stage rejections never reach `internship_funnel.rejected_samples` (funnel types = INTERNSHIP/STIPEND only) — Graduate SWE and every Junior `stage:experience` invisible in the heartbeat; the pipeline test hid it with an Intern title.
- M1 sentence splitting: merged list blocks attach a far "nice to have" to Tether's real "Requirements MSc/PhD candidate…" (Tether is Aspirational only via blurb); "Currently enrolled in a PhD program … Bachelor's degree" → fits; abbreviations split ("Ph.D. are preferred", "e.g. … Master's or PhD") → false advanced_degree.
- M2 boilerplate triggers advanced_degree ("Founded by a team of PhD scientists, we are looking for candidates…", "help every student get a master's degree").
- M3 "Software Engineering Intern (Undergraduate/Graduate)", "Graduate or Undergraduate Software Intern" → graduate_only.
- M4 "graduating between Dec 2026 and Jun 2027" / "graduating in May 2027" (future = still a student) → graduate_only; "2026 graduates and undergraduates" → graduate_only (exception lacks "undergraduate").
- M5 negation: "current students are not eligible" escapes graduate_only and then yields `fits` quoting it.
- M6 body boilerplate `fits` ("app used by 2 million students") — §12: no evidence must be said, not assumed.
- L1 word numbers ("Five years"), "yrs", keyword-before-number missed. L2 curly apostrophe "Master’s". L3 "Graduate Research/Teaching Assistant" → graduate_only. L4 Junior/early-career title switches off every body graduate rule (spec-literal). L5 `education.status` never read. L6 HTML digest prints raw `stage:` strings (also for stipend programs). L7 MSc/PhD + UNKNOWN intern uses an UNKNOWN-intern cap slot (spec silent). L8 dedupe.py/pipeline.py touched outside S10's file list. L9 fixture not yet read by a test (S11).
- Weak tests: "5 years in business" trivially passes; "PhD preferred" only without dots; empty-body undergrad title; Ritual exclusion never exercised; Junior titles decide before the body; Tether blurb not its Requirements line; Intern-typed pipeline test; no cap-interaction test.

### Final review findings — iteration 2 (CLOSED `1dc90fd` — outcomes in the pass log entry "Final review CLOSED")
Reviewer confirmed: 403 passed; S9 clean (both `gh issue create` carry --assignee; issue/heartbeat/seed end with cc @owner); funnel invariant holds with stage:*/stage:advanced_cap/interest:cap; spine, $0, eligibility honesty clean; three caps act on disjoint groups; word boundaries hold; `test_first_run_regression` genuinely runs the 9 byte-identical records through run_once.
- H1 `_EXPERIENCE`/`_COMPANY_SUBJECT` (score.py ~564-605) miss common requirements → 3–5-year roles land in Apply (title "Junior Backend Engineer", worldwide, NEW_GRAD; expected stage:experience): "We require 3+ years of experience with Go." / "We expect 5 years of hands-on experience." (skip matches "We require/expect ") · "Our ideal candidate has 4+ years of experience building APIs." (skip matches "Our ideal candidate has") · "Minimum 3 years' experience in backend development." (apostrophe) · "You have 3+ years working with Kubernetes in production." (spec's `working` dropped) · "5+ years of professional software development." (spec's `professional` dropped).
- M1 strong term cancels the veto but the title has no family word → `role_family` (notify.py:60): "QA Intern, Linux Kernel", "QA (Linux) Intern" → expected Apply with note "matches 'qa' but also 'linux'".
- M2 any vetoed title skips the family requirement → non-technical roles delivered to "outside your stated interests": "QC Inspector Intern", "Quality Assurance Intern" (pharma GMP), "CRM Intern" (HubSpot sales support), "Junior CRM Specialist" (expected role_family). Live: "CRM Assistant (with Insellerate Experience)". Existing test only covers a _ROLE_VETO-word title.
- M3 UNKNOWN eligibility: vetoed ("QA Intern") and MSc/PhD ("Software Engineer Intern" + "Currently pursuing a Master's or PhD in Computer Science.") interns go to "Check eligibility" as full items and compete for the 5 UNKNOWN-intern slots (offline ordering = score). Spec S10 does not condition Aspirational on eligibility (deviation i2-a; tests test_advanced_degree_with_unknown_eligibility_is_not_aspirational / test_caps_interaction lock it in). Not an honesty problem — a section/cap question.
- M4 company copy with >2 words after the subject → `stage:experience`: "Software Engineering Intern" + "We are a team of 5 with 20 years of combined experience." → expected Apply.
- M5 MSc/PhD window misses a sentence's softener: "PhD students are welcome to apply for this internship on our compiler and runtime team, though a PhD is a plus rather than a requirement." / "Candidates pursuing a PhD in machine learning, statistics, applied mathematics or a related quantitative field are preferred." → advanced_degree; expected fits (spec: the SENTENCE also contains preferred/a plus…).
- M6 `rejected_samples` keeps the first 5 non-known reasons incl. cap overflows → stage rejections not guaranteed (probe: 2× interest:cap, 2× stage:advanced_cap, 1 graduate_only, stage:experience never sampled). §12 acceptance wants stage rejections included.
- L1 stipend program with a not-interested term → Apply but prints "outside your stated interests ('salesforce')" ("Salesforce Trailblazer Fellowship"). L2 `education.status` unread. L3 `_GRAD_PROGRAM_TITLE` extra lookahead → "Graduate Research Assistant" reads not_target_class instead of stage:graduate_only (still unselected). L4 eligibility "position/role … based in" pattern outside §12's file list (6 probes, no false negative). L5 generic strong terms ("systems", "ai", "research") cancel most vetoes — spec-literal. L6 "2-4 years" → N=2 stretch — spec-literal, test-pinned.
- Tests: none cover H1/M1/M2/M4 inputs; experience tests only use working phrasings; regression test does not check Apply ordering, runs without the model, synthetic cases preset employment_type.

### Iteration-2 pass log
- 2026-10-04 — Part A done (Dagi-authorised): PR #2 merged → origin/main `bc4154c`; local `main` realigned with
  `git branch -f main origin/main` (tree was clean — the settings.json edit had already been committed in `12c70a9`).
  Updated spec copied from `D:\Downloads` (contains §12; diff is §12 only, +178 lines) and committed on the new
  branch `iteration-2` (`43422e0`). Baseline on origin/main: **1 failed / 308 passed** — the merged `data/scout.db`
  (bot commit `4c6a095`, the delivery-test run) now holds 244 rows, and the stored-row check found one
  positive: GitLab "Business Development Representative", location "Remote, EMEA; …", body "this position is
  100% remote and will be based in the UK, Ireland, Germany, the Netherlands" → was REMOTE_REGION_INCLUDES_USER.
  Test first (2 failed) → `_BODY_RESTRICTION` also reads "position/role/job … (will be|is) based/located in"
  (`c54fe46`). **311 passed**; re-classification 244 rows, 0 bad. The 9 records delivered on 2026-10-04 are in
  `data/scout.db` with `notified_at 2026-10-04T11:51:55Z` (fixture source for §12 acceptance).
- 2026-10-04 — **S9 done (unit level)** (`1608ab3`): both `gh issue create` calls get `--assignee
  "${{ github.repository_owner }}"`; `render_issue_md` and `render_heartbeat_md` end with `cc @<owner>` from env
  `GITHUB_REPOSITORY_OWNER` (Actions sets it by default; omitted when unset); the seeded test item also ends
  with `cc @owner`. Tests `tests/test_delivery_s9.py` (2 of 3 failed on the old code; the third is the
  "omitted when unset" guard). Workflow YAML parses. Email arrival = pending human check (1).
- 2026-10-04 — **S10 acceptance** (`69df1b3`; review pending). Spec facts verified first: all four §12 quotes are
  in the stored descriptions verbatim. Tests first (`tests/test_stage_s10.py`, collection failed before the
  code existed). `stage_fit` on the 9 delivered records: 7 `fits` (5 by title token, Linux Kernel/Junior Ubuntu
  by title too), Tether `advanced_degree` ("MSc/PhD Internships at Tether aim to provide students…"),
  Graduate SWE `graduate_only` (title + "We are hiring 2025 and 2026 Graduate Software Engineers"), CRM
  `stretch` ("1+ years of hands-on Salesforce…"). Live run `70235d635740` on the PRE-delivery DB
  (`4c6a095~1`, so the 9 are NEW again): 628 → merged 17 → rejects 413 → survived 198 → gate 190 (not_target_class
  100, role_family 85, not_new 4, **stage:graduate_only 1**) → **notified 8**: Actionable 7 (incl. QA/QC and CRM —
  S11's job), Aspirational 1 (Tether). Invariant 628−17−413−190 = 8 ✓. **351 passed.**
- 2026-10-04 — **S10 review CLOSED** (`1213ac8`). Reviewer (general-purpose, Opus, read-only; given §12 S10 +
  acceptance, §9, CLAUDE.md, the diff 1608ab3..69df1b3, the tests, and the 9 stored records). Findings →
  `tests/test_stage_review_s10.py` first: **31 failed → confirmed → fixed** (H1 non-requirement years ×7, decimal,
  boilerplate max; H2 NEW_GRAD stage sample; M1 Tether's real Requirements block, merged-list "enrolled in a PhD",
  "Ph.D. … preferred/a plus", "e.g. … Master's or PhD"; M2 blurbs ×2; M3/L3 titles ×4; M4 ×3; M5; M6 ×2; L1 ×3;
  L2). Passed before the fix (guards, kept): real requirements still caught (3+ years → experience, 1+ → stretch),
  "must have graduated by June 2026" still graduate_only, the Linux-Kernel candidate sentence still `fits` with a
  neutral title, and the cap interaction (3 positive MSc/PhD + 6 UNKNOWN interns → 2 + advanced_cap 1, 5 +
  unknown_cap 1). L6 fixed (readable stage line in the HTML digest; none for programs) with a test. My own S10 row
  "graduating in May 2026 → graduate_only" changed to "graduated in May 2026" (justified inline, M4). Kept: L4
  (Junior/early-career title switches off the body graduate rules — spec-literal), L5 (`education.status` has no
  rule in the spec; it is recorded config only), L7 (MSc/PhD + UNKNOWN intern sits in Check eligibility and uses
  an UNKNOWN-intern slot — spec silent; deviation i2-a), L8 (dedupe gains a "graduate" level so graduate titles
  never fuzzy-merge with entry ones; pipeline carries the stage samples — both needed by S10), L9 (S11). The 9
  records: unchanged verdicts (7 fits, Tether advanced_degree, Graduate SWE graduate_only, CRM stretch). **387 passed.**
- 2026-10-04 — **S11 acceptance** (`e6b94e4`; final review pending). Tests first (`tests/test_interest_s11.py`;
  collection failed before the code existed). Profile: `interests` (§12 list; `target_roles` still loads as an
  alias, read-only `target_roles` property kept), `not_interested`, `strong_interest_terms`. `qa` removed from
  the role family; `interest_veto(opp, profile)` reads the TITLE (word boundary) → `interest:veto: <term>` in
  `Relevance.concerns`, or `interest:note: matches '<t>' but also '<strong>'` in `matched_signals`. Gate:
  vetoed titles are checked for veto words only (deviation i2-k); positive + vetoed → "Eligible, outside your
  stated interests" (title-and-link lines, cap 5, overflow `interest:cap`). Sections Apply (by relevance score)
  · Check eligibility · Aspirational · Eligible, outside your stated interests; empty ones omitted; "Actionable"
  renamed "Apply" (4 older tests updated, one-line justification each: test_delivery, S6 acceptance Case A,
  test_gate ordering → `test_issue_sections_order`, my S10 rendering test). **§12 regression:**
  `test_first_run_regression` runs the 9 fixture records + 3 synthetic ones through `run_once` with
  `config/profile.yaml` (lexical mode): Junior Ubuntu, both Ritual, CloudCops, Junior Linux Kernel → Apply; Tether
  → Aspirational; QA/QC and CRM → outside interests; Graduate SWE not selected (`stage:graduate_only`); Junior
  Backend Engineer, Frontend Engineer Intern → Apply; "QA Automation Engineer, Linux Kernel" → Apply with the note
  — passes. Golden set: with `qa` out, old labels give precision 1.000 / recall 0.966 (QA/QC the one miss);
  QA/QC relabelled 0 for role family → **1.000 / 1.000** (in-sample). Title similarity vs `interests`: positives
  p10/p50/p90 0.42/0.62/0.78, negatives 0.17/0.38/0.66. Live run `a080a4536216` (pre-delivery DB, model loaded):
  628 → merged 17 → rejects 413 → survived 198 → gate 189 (not_target_class 100, role_family 84, not_new 4,
  stage:graduate_only 1) → **notified 9**: Apply 5 (Ritual SWE Intern, Junior Ubuntu, CloudCops, Junior Linux
  Kernel, Ritual Research Intern), Aspirational 1 (Tether), Outside 3 (QA/QC Intern, CRM Developer, CRM
  Assistant (with Insellerate Experience) — new live listing; see i2-k). Invariant 628−17−413−189 = 9 ✓.
  **403 passed.**
- 2026-10-04 — **Resumed after context clear**; git and the resume block agreed, tree clean, 403 passed.
  **Final review CLOSED** (`1dc90fd`), with Dagi's decisions D1–D7 (deviations i2-n…i2-s). Findings →
  `tests/test_final_review_i2.py` first: **25 failed → confirmed → fixed**: H1 ×7 wordings (incl. "At least 4
  years in a backend role") → `stage:experience`; M4 "team of 5 with 20 years of combined experience" (verdict and
  intern → Apply); D2 intern with "3+ years" → Apply with the sentence shown; M3/D3 UNKNOWN MSc/PhD intern →
  Aspirational with the note, UNKNOWN QA intern → outside, per-section caps; M2/D4 ×5 non-technical titles
  ("QC Inspector Intern", pharma "Quality Assurance Intern", "CRM Intern", "Junior CRM Specialist", "CRM Assistant
  (with Insellerate Experience)") → `role_family`; M1/D5 "QA Intern, Linux Kernel", "QA (Linux) Intern" → Apply with
  the note; M5/D6 ×2 softeners; M6/D7 run samples and heartbeat samples carry the stage rejections; L1 stipend
  program prints no interest line. **Passed before the fix (guards, kept):** `test_m4_non_requirement_years` ×3
  ("in business for 15 years", "founded 12 years ago", "our engineers have a track record of 10 years"),
  `test_m2_software_qa_still_reaches_outside_interests`. D1 then measured on the 244 stored descriptions
  (`years_probe`, scratch, read-only): first version suppressed 4 real requirements ("track record" in the same
  list block; "Our engineers are:" in a merged block) and read 4 non-requirements (two ages, "has been helping …
  for 8 years", "a 10 year … commitment") → `test_d1_stored_sentences` (7 verbatim sentences; the "8 years" one
  failed before its fix) → fixed; final: 36 read, all genuine requirements; 10 skipped, all non-requirements.
  Older tests changed (one-line justification each, inline): `test_stage_s10` real-sentence table and
  `max_required_years` typed NEW_GRAD as the stored records are (D2 exempts the INTERNSHIP default);
  `test_advanced_degree_with_unknown_eligibility_is_not_aspirational` inverted to `…_is_aspirational` (D3);
  `test_caps_interaction` → one Aspirational cap over all nine (D3); `test_gate_review_s5` L3 pipeline role "QA
  Automation" → "Cloud" (a QA title is no longer a Check-eligibility slot); `test_interest_s11` cap test gets a
  software-QA body (D4). Lows L2–L6 and the test gaps → "Known limits" in the resume block. **§12 regression
  (`test_first_run_regression`, 9 records + 3 synthetic) passes**; golden set 1.000/1.000 (in-sample). **439 passed.**

  **End of pass (iteration 2).** §12 acceptance: regression fixture ✓; funnel shows `stage:*`, `interest:cap`
  and samples include stage rejections with their sentence (per run and in the weekly heartbeat) ✓; existing
  tests pass or carry a one-line justification ✓; golden set re-reported ✓. S9 email arrival and §8 criterion 6
  (14 days) are pending human checks (1) and (4). No workflow dispatched; nothing merged; `main` untouched.

## RESUME — next-iteration (COMPLETE — merged to main as bc4154c; kept for history)
Branch: next-iteration      Last commit: b911406 Merge origin/main (a39feaa, bot run 2026-10-04) into next-iteration
Step in progress: none — **PASS COMPLETE** + Dagi's follow-ups done (body-restriction rule `5819288`; origin/main merged; branch PUSHED to origin/next-iteration). Not merged to main.
Steps done and verified: S0 (6bcbce7, e4535c9), S1 (49aa593, dfd37ec — unit level; device confirmation pending), S2 (613e2a1, ed728ba — review closed), S3 (ab43dd8; acceptance seen in the S7 live run: new_grad 60), S4 (b34b338), S5 (452e3ed, 5ecb953 — review closed), S6 (5cd289f, 3e7d379 — review closed), S7 (ab4e919, 0ef22b7), S8 (d1f055e)
Reviews: S2 closed, S5 closed, S6 closed, final closed (96c10db)
Next action: Dagi does the pending human checks below, in order. Nothing else is in flight.
Pending human checks (in this order; commands run from `job-scout/`):
  (1) [DONE 2026-10-04] Branch pushed: `git push -u origin next-iteration` (carries origin/main a39feaa's data/scout.db).
  (2) S0 + S1 — dispatch on the branch with a seeded delivery test:
      `gh workflow run scout --ref next-iteration -f seed=true` then `gh run watch` (or the Actions tab).
      Confirm (a) the funnel table is on the run page (step summary), (b) an issue "Job Scout: N new — <date>"
      exists (`gh issue list --label scout`) — on today's data it should list the real items (9 in the local
      run), not just the seeded one — and (c) it reached a real device (email or GitHub mobile). If it did not
      arrive, the Telegram fallback is the first follow-up. Note: this run commits `data/scout.db` to
      `next-iteration`, and the items are then marked notified on that branch's DB.
  (3) Merge by pull request — never via local `main` (local `main` has diverged from `origin/main`: it holds
      the 4 pre-branch commits 80ae5b6..7ec0b85, which are already in next-iteration, and lacks a39feaa):
      `gh pr create --base main --head next-iteration --title "Next iteration: funnel, delivery, eligibility, gate, programs, Himalayas, canonical" --body "Implements docs/SPEC-2026-10-04-next-iteration.md (S0–S8). Evidence, reviews and deviations: STATE.md (RESUME block + pass log)."`
      then `gh pr merge --merge`.
      If the PR reports a conflict in `data/scout.db` (the bot commits it to `main` daily, and step 2's run commits it
      to the branch), keep the branch's copy so items delivered in step 2 are not re-sent:
      `git checkout next-iteration && git pull && git merge origin/main` → on conflict
      `git checkout --ours data/scout.db && git add data/scout.db && git commit --no-edit && git push`, then `gh pr merge --merge`.
      Afterwards, realign local main: `git checkout main && git reset --hard origin/main`.
  (4) DECISION for Dagi (S5 review M1): an onsite/hybrid role in Addis Ababa is UNKNOWN@0.4 (Gate-0 Decision #1), so a NEW_GRAD one is never notified (`eligibility_unknown`) and an INTERNSHIP one lands in "Check eligibility" using a cap slot — though the user can certainly take it. Fixing it needs either a gate rule ("own-country onsite UNKNOWN → select") or E2's proposed new EligibilityCategory (spine change). Not changed in this pass.
Deviations from spec: (a) S0 `internship_funnel.outcomes` adds a `merged` outcome (records folded by dedupe) so outcomes sum to `fetched`. (b) [withdrawn — §6 `skipped_records` now implemented, final review M5]. (c) `role_family_ok` (S5) was added to score.py during S0 because the E1 probe needs it; unchanged regex. (d) S1: `workflow_dispatch` input `seed` (boolean) writes a test item into an empty `notify.md` — needed so the seeded acceptance run can be done without fabricating a DB record; the workflow also runs `gh label create scout --force` because `--label` fails on a missing label. (e) S1 heartbeat is produced by `python -m job_scout --heartbeat` (reads last 7 `runs` records) and posted after "Commit state" on Mondays (UTC). (f) S2 interpretations (i)–(v) and review fixes (step log): body-independent `MIXED` verdict → UNKNOWN 0.5; bare country code not USER; region tokens count only for remote roles; worldwide body phrase must not be followed by a named place; OTHER-only location → UNKNOWN 0.3. (g) S5 `role_family_ok`: the spec's exact regexes measured precision 0.61 on the golden set; family + `embedded|computer vision|database`, veto + `manager|participant(s)|study/studies|annotator/annotation|data entry|keyer|service desk|help desk|business development|social|customer|opportunities|ad quality|professional services` → 0.962 / 1.0. Tuned on the same 67 rows — overfitting risk; §8.6's 14-day observation is the real check. (h) S5 adds gate code `eligibility_negative` (a low-confidence disqualifier that survived the hard filter, or a non-positive program) so every unselected record still has one reason. (i) S3: "Graduate Partner Marketing Manager" stays UNKNOWN (spec's exact regex marks "manager" senior), not NEW_GRAD. (j) S6: gate checks `already_notified` before `not_new` (spec Case A requires it). (k) S6: `US_EMBARGOED` = Cuba, Iran, North Korea, Crimea, Donetsk, Luhansk — composed from OFAC's active program list (which has no single "embargoed countries" list); what is verified is that no Ethiopia program exists. (l) S6: program-level `report` key for a program with no future round is its name; a program's last-checked date in that message is the latest of its geo/round checks. (m) S6 review H1: `ats_job_id = <key>@<recorded state>`, not `@<effective_state>` as the spec writes — otherwise a stale `open` round is re-announced as "expected"; staleness still changes title and lead window. (n) S6 review M3: MLH `geo_scope="worldwide"` with the form's verified no-projects list as `geo_exclusions` (spec gave no scope; the earlier "unknown" was only because the list was not extracted).
  Final-review deviations: (o) M1 — step 2 (work authorization) is no longer "unchanged": a residency phrase naming the user's region/"anywhere" ("must be based in EMEA") is not foreign auth, and a visa-sponsorship line does not count when the location is decisively worldwide or includes the user (a remote hire needs no visa); a foreign right-to-work phrase still disqualifies first. (p) H2 — a body worldwide phrase plus "located/reside/based/live in <place elsewhere>" → UNKNOWN 0.5. (q) M2/L9 — exclusion wording in the location ("Global (excluding US)") labels only the part before it, or excludes when it names the user; a WORLD location next to an ELSEWHERE title marker is MIXED → UNKNOWN 0.5 (spec: "any WORLD" wins). (r) M4 — `role_family_ok` judges the title's role head (before ", " / " - " / "(") alone when it names a family; discipline vetoes (psychology, mechanical, technician, guard, participants, study, data entry, annotation, …) count anywhere; golden set still 1.0/1.0 (in-sample). (s) H3 — dedupe tier 3 never merges titles of different level (intern/entry/senior). (t) Follow-up — a WORLD/USER location plus a body sentence restricting applicants only to places elsewhere → UNKNOWN 0.5 (spec: the location decides first).
Unverified facts still in code: all 2027 round dates are `expected` extrapolations (Outreachy ~Feb 5–12, GSoC Mar 24–Apr 7 kept from the old table, LFX mid-Jan/Apr/Jul + 4 weeks); Himalayas freshness per listing (E1 used pubDate).

### Final review findings (CLOSED `96c10db` — outcomes in the pass log entry "Final review CLOSED")
- H1 `\bus\b` in the step-4 body exclusion matches the pronoun ("join us") → plain "Remote" + neutral body → REMOTE_EXCLUDES_USER 0.8 → hard reject (UNKNOWN made disqualifying).
- H2 Sourcegraph "hire almost anywhere in the world, we do require successful candidates to be located in the United States" → WORLDWIDE 0.7 (place outside the 60-char window) → Actionable for US-only roles; 9 stored rows.
- H3 dedupe tier 3 fuzzy ratio ≥0.90 merges "Junior Data Engineer" into "Senior Data Engineer" (same company+location); the senior survives and is rejected → junior lost.
- M1 work-auth step overrides a decisive WORLD/USER location ("Worldwide" + "We do not sponsor visas" → requires_work_auth; "Remote, EMEA" + "must be based in EMEA" → requires_work_auth). Spec-literal (steps 1–2 unchanged).
- M2 "Remote - Global (excluding US)" → excludes; "Anywhere except the United States" → onsite_foreign (exclusion wording read as restriction).
- M3 gazetteer gaps ("Remote, Ontario" + "work from anywhere" → WORLDWIDE 0.7).
- M4 role_family vetoes team-name suffixes ("Software Engineer Intern, Financial Data Platform", "Backend Engineer Intern, People Platform", "Data Scientist Intern - Sales Analytics"); "Security Guard Trainee" passes; golden set is in-sample.
- M5 §6 `skipped_records` not implemented → a source skipping every record reads as a genuine zero.
- L1 gate order (= deviation j). L2 `eligibility_negative` (= deviation h). L3 identity recorded state (= deviation m). L4 `rejected_samples` filled by not_new/already_notified. L5 invariant tests near-tautological; no test with failing source/skip. L6 lexical mode reads body + tech double count (model mode unaffected). L7 reclassify checker blind to plain "Remote" positives (misses H2). L8 deleted known_programs tests lack one-line-each justification. L9 Himalayas synthetic "Worldwide" beats an ELSEWHERE title marker ("Software Engineer Intern (US)" → WORLDWIDE 0.85). L10 "EMEA, excluding Ethiopia" → includes; "Fully Remote" → OTHER 0.3 not BARE; "Remote (GMT+3)" → UNKNOWN 0.3.

### S6 review findings (CLOSED `3e7d379` — outcomes in the pass log entry "S6 independent review CLOSED")
- H1 stale `open` round re-notified as `@expected` with "dates not published" (round q1 open, opens T-1, deadline T+80, checked T; run at T then T+46 → notified twice). Spec composition issue → choose: keep last-notified state, or staleness changes only the title not `ats_job_id`.
- H2 `_INDEX` keyed by round key only, last write wins; duplicate keys across programs/sources borrow another program's "eligible" + quote. `validate_table` does not reject duplicate keys. Fix: index by (program, round) or reject duplicates.
- M1 `geo_verdict` returns eligible for geo_scope worldwide with empty quote/url (only validate_table catches; fetch never runs it).
- M2 `_lookup` miss reloads `_PROGRAMS` over injected programs with real `date.today()` → call-order-dependent verdicts (injected `gsoc-2027` unknown → later eligible).
- M3 MLH row: geo_exclusions empty + geo_scope unknown (29-country list not extracted) and geo_url tfaforms vs spec's fellowship.mlh.com — needs a recorded decision.
- L1 embargo list never goes stale / not in maintenance_notes. L2 embargo match exact lowercase names only (ISO codes / official names miss). L3 gate order swap made in S6 commit (deviation j) — funnel tests loosened to a set; pin it. L4 tests: maintenance "fresh" case uses future geo date (never exercised); no test pins shipped verdicts for Ethiopia (GSoC eligible, LFX/MLH unknown); no backward-state test.

### Pass log (next-iteration, single pass per spec §11)
- 2026-10-04 — Pass started. Partial work found from earlier session: `.claude/settings.json`
  has an uncommitted edit adding `claude-opus-5-5` to `availableModels` (harness config, not
  spec work) — left uncommitted, untouched. No partial S0 code. Updated spec (§11 rewritten:
  single session, single branch) moved from repo root into `docs/` and committed (`1c086a1`).
  Branch `next-iteration` created from `main` @ `7ec0b85`. Baseline: **89 passed**.
  §11 supersedes the per-step branches (`s0-funnel`, …) described in §Next iteration below.
- 2026-10-04 — **S0 done and verified** (`6bcbce7`, `e4535c9`). `filter_reason` / `gate_reason`;
  `RunSummary` gains `rejects`, `gate`, `by_type`, `by_eligibility`, `near_misses`,
  `internship_funnel`, per-source `report`; runtime invariant check (warning); `data/funnel.md`
  written beside the digest and appended to `$GITHUB_STEP_SUMMARY`. Tests: 89 existing unchanged +
  7 new (`tests/test_funnel.py`) → **96 passed**. Acceptance (per §11: local live run against a
  COPY of `data/scout.db`, model loaded), run `b760ad8582a3`:

  | stage | count |
  |---|--:|
  | discovered (greenhouse 221, ashby 8, lever 0, known_programs 0) | 229 |
  | merged by dedupe | 24 |
  | hard-filter rejects | 175 |
  | — `eligibility:remote_excludes_user` | 169 |
  | — `eligibility:requires_work_auth` | 3 |
  | — `type_unwanted:full_time` | 2 |
  | — `eligibility:onsite_foreign` | 1 |
  | survived | 30 |
  | gate `not_new` | 30 |
  | notified | 0 |

  by_type: unknown 221, full_time 8. by_eligibility: remote_excludes_user 169, worldwide_remote 23,
  remote_region_includes_user 9, requires_work_auth 3, onsite_foreign 1. Internship funnel:
  fetched 0. Near misses include "Intermediate Support Engineer — Bangalore, India →
  remote_region_includes_user" and "Enterprise AE — Remote, Singapore → worldwide_remote" (C4 live).
  **§1 INFERENCE confirmed:** the 85% loss is 97% location exclusion (169/175); 6 of the 8 Ashby
  FT jobs are rejected on eligibility first (filter order), 2 on type.
- 2026-10-04 — **E1 probe: PASS** (`scripts/probe_himalayas.py`, 12 requests, no 429). Intern ∧
  worldwide: totalCount 29 (25 ≤30d); Intern ∧ ET: identical 29; Entry-level ∧ worldwide: 306;
  Entry-level ∧ ET: 333 (one ET-restricted listing seen — H1 supported: `country=ET` returns
  worldwide + ET-scoped). Distinct `role_family_ok` listings ≤30d: **20** (≥10 → pass). Honest
  caveat: by hand, roughly 7 of the 20 are genuine technical roles (Software Engineer Intern and
  Research Intern @ Ritual, QA/QC Intern @ Flowmingo, Junior DevOps/Cloud Engineer @ CloudCops,
  CRM Developer, L1-L2 Service Desk Engineer, Data Annotator); the rest are paid "AI study
  participant" / data-entry posts that the regex admits ("AI", "Research", "Data"), plus
  "Business Development … Intern - Nearby.ai" (matches `\bai\b` in the company suffix). S5's golden
  set includes these as negatives. Paging: `page=N` works (offset advances); `offset=` is ignored;
  no `nextCursor` field returned. Flywheel candidates (≥2 open-to-ET target-class ≤30d): Ritual
  (2, genuine), Your Personal AI / Growe Talents / Xperteez (study / data-entry posts — not
  candidates on inspection). → S7 will be built.
- 2026-10-04 — **S1 done (unit level)** (`49aa593`, `dfd37ec`). `render_issue_md` (task-list
  lines, "Actionable" / "Check eligibility", evidence + matched signals, "via Himalayas" line);
  pipeline writes `data/notify.md` only when the selection is non-empty, deletes a stale one
  otherwise; workflow: `issues: write`, deliver step before "Commit state" (failure → replay),
  Monday heartbeat issue; `.gitignore` adds `notify.md`, `funnel.md`, `heartbeat.md`. Tests: 4 new
  (`tests/test_delivery.py`) → **100 passed**. Workflow YAML parsed OK. Not pushed, not dispatched.
- 2026-10-04 — **S2 acceptance passed** (`613e2a1`; review pending). `_geo.py` (countries,
  regions in/excluding Africa, worldwide tokens, cities, US-state pattern); `_classify_location`
  labels each `;|/ or and`-separated segment USER/WORLD/BARE/ELSEWHERE/OTHER plus a title region
  marker. Re-classification of the 50 stored rows (`scripts/reclassify_stored.py`): 24
  worldwide→excluded, 13 region_includes→excluded, 4 worldwide→unknown, 9 stay worldwide;
  **positive rows whose location names only non-user places: 0** (was 37). The 9 remaining
  positives are all Sourcegraph `Remote` rows whose body says "we hire almost anywhere in the
  world" (the spec's own added phrase) → `WORLDWIDE_REMOTE` 0.7, or 0.5 where US hours are stated.
  The spec predicted UNKNOWN 0.5 for these; the difference is a fact about Sourcegraph's text, not a
  rule change. Tests: 34 new → **134 passed**. Updated existing tests (justified inline):
  `test_stipend_program_is_globally_eligible` (now via `geo_verdict`), text-mention test inverted,
  `test_known_programs::test_program_ranks_top_tier…` pins `geo_verdict="eligible"`, gate0
  stipend fixture gains `location_raw="Worldwide"`.
  Interpretations: (i) a named place beats a worldwide word in the SAME segment ("Anywhere in the
  US" → excluded); (ii) an ELSEWHERE title marker qualifies a bare "Remote" (needed for the spec's
  "`Remote` + '…, US [IC5]' → excludes" case); (iii) the step-4 body exclusion rule is kept verbatim
  incl. its old guard (the spec's own `us-hours` test needs it); (iv) USER + ONSITE/HYBRID in the
  user's own country/city stays `UNKNOWN 0.4` (Gate-0 Decision #1); (v) "remote" in the location
  field counts as remote for REMOTE_EXCLUDES_USER vs ONSITE_FOREIGN (both disqualifying).
- 2026-10-04 — **S2 independent review CLOSED** (`ed728ba`). Reviewer (general-purpose, Opus,
  read-only, given only S2 + §9 + diff `ef3615d..613e2a1` + tests). Every finding became a test in
  `tests/test_eligibility_review_s2.py` first; 19 of those tests FAILED → confirmed → fixed:
  H1 "South/North/West Africa" read as USER via "africa" (masked; sub-regions added as excluding);
  H2 onsite foreign city + "EMEA"/"East Africa" → included (region tokens now count only for a
  remote role); H3 "ET" (Eastern Time) read as Ethiopia (bare code dropped from USER, per spec);
  H4 "work from anywhere within the US" → worldwide (a worldwide phrase now needs no named place in
  the next 60 chars; US-hours phrases ignored there); M1 "Remote; Remote, Canada; Remote, US" decided
  by body words → now a body-independent `MIXED` verdict → UNKNOWN 0.5; M2 "Remote, California"
  rescued (US state names added) / "Germany; Cologne" → MIXED; M3 " and " split broke "Bosnia and
  Herzegovina" (protected); M4 "EMEA (Europe only)" → now excluded; L2 onsite-own-city from body →
  UNKNOWN 0.4 restored. Refuted/kept: H4's guard tests (`test_h4_us_hours_stays_a_penalty…`,
  `test_m4_unqualified_multi_region_still_includes`, `test_m3_middle_east_and_africa_still_includes`)
  passed before the fix — behaviour already right. L1 (OTHER-only → 0.3; "remote" in the location
  counts as remote) kept and listed as deviations. L3 (title marker misses "…, US (Remote)") is the
  spec's exact regex — kept; such rows become MIXED/UNKNOWN, not positive. Test-quality findings
  fixed: oracle in `scripts/reclassify_stored.py` no longer blind to "South Africa"/"Anywhere in the";
  GSoC text test pinned to UNKNOWN 0.3; empty `geo_evidence` for eligible programs → S6 (tested there).
  Re-classification after fixes: still **0 bad**, 9 Sourcegraph rows worldwide (0.7/0.5). **187 passed.**
- 2026-10-04 — **S3 done** (`ab43dd8`): `_INTERN_TITLE`, `_ENTRY_TITLE`, `_SENIOR_TITLE` (exact
  spec regexes) in `normalize.py`; UNKNOWN/FULL_TIME + entry token and no senior token → NEW_GRAD;
  profiles: `employment_types` + `new_grad`, default `target_roles` shipped. 22 title-table tests.
  Spec conflict (fact, not decision): "Graduate Partner Marketing Manager → NEW_GRAD by level" is
  impossible with the spec's exact regexes ("manager" is a senior token) → stays UNKNOWN; the S5
  role-family veto also rejects it; both asserted. Acceptance (`by_type` shows new_grad on a run with
  Himalayas/Canonical data) → checked after S7/S8.
- 2026-10-04 — **S4 done** (`b34b338`): `filter_reason` adds `seniority_title:<token>` after the
  type check (not for INTERNSHIP/STIPEND_PROGRAM); dedupe tier 3 blocked by
  `(canon(company), canon(location))`. Tests: C7 reproduction → 2 records (EMEA one included, US one
  excluded); same-location near-dup merges; "Senior Backend Engineer" → `seniority_title:senior`;
  "Intern, Engineering Manager's Office" kept.
- 2026-10-04 — **S5 acceptance passed** (`452e3ed`; review pending). `embed_similarity` = max
  cosine(title, each target role); score = base + 0.03×body tech hits (cap 0.15) + existing nudges;
  per-concern damping dropped. Gate (`notify.gate_reason` / `gate_reasons`): not_new →
  already_notified → stipend program (positive/UNKNOWN → select) → not_target_class → role_family →
  eligibility (positive → Actionable; UNKNOWN intern → Check eligibility, cap 5 → `unknown_cap`;
  UNKNOWN new-grad → `eligibility_unknown`). Threshold no longer consulted. Golden set 67 titles
  (31 stored DB titles, 19 Himalayas probe titles, 17 hand-written incl. 3 hard positives):
  precision **0.962**, recall **1.000** (spec regex alone: 0.61 / 0.88 — see deviation g).
  `scripts/calibrate.py` with the real model: title-only similarity positives p10/p50/p90 =
  0.47/0.67/1.00, negatives 0.19/0.36/0.65. **C3 confirmed** on 10 GitLab rows: old (profile blob
  vs title+description) sd 0.021, range 0.081; new (title vs roles) sd 0.198, range 0.583 — sales
  titles fall to 0.09–0.21, backend titles rise to 0.59–0.68. §7 integration test: EMEA intern +
  same-title US intern + senior + sales intern + program → exactly the EMEA intern and the program
  are selected; invariant holds. Tests → **203 passed**.
- 2026-10-04 — **S5 independent review CLOSED** (`5ecb953`). Findings → `tests/test_gate_review_s5.py`
  (16 failed → confirmed → fixed): H1 my broad vetoes (`customer`, `social`, `manager`) rejected
  real technical internships ("Software Engineer Intern, Customer Platform", "Package Manager
  Engineer Intern", …) → narrowed to phrases; non-software titles passed ("Financial/Business/
  Operations Analyst Intern", "Mechanical/Civil/Chemical Engineering Intern", "Policy Research
  Intern", "Data Center Technician Intern", "Mac Users Needed … $25") → vetoed; these 13 rows were
  added to the golden set (now 80 rows: precision 1.0 / recall 1.0 — **in-sample, so not evidence of
  generalisation**; §8.6's ticked-item observation is the real measure). M3 cap kept top-5 by
  nudged score → now by title similarity. M2 ordering test did not discriminate score vs
  similarity → fixed. L3 gate gaps (None eligibility, NEW_GRAD role_family, stipend negative, ACTIVE
  intern not using a cap slot, pipeline run producing `unknown_cap`/`not_target_class`/
  `eligibility_unknown` with the invariant) → tests added, passed after the fixes. L5 stale comment
  fixed. Kept/refuted: L1 `eligibility_negative` (deviation h); L2 obsolete test removed in S6's
  rewrite; L4 lexical-mode double count of body tech (spec-literal; model mode unaffected). M1 →
  Pending human checks (3), a decision not a bug. **236 passed.**
- 2026-10-04 — **PAUSED by Dagi** (context clear requested) mid-S7 after committing WIP `ab4e919`.
  S6 review report received and recorded above (OPEN). Tests at pause: 247 passed, 1 failed
  (`test_himalayas.py::test_mapping_from_recorded_fixture`). Nothing pushed; `main` untouched.
  `.claude/settings.json` edit (adds `claude-opus-5-5`) committed at Dagi's request (`12c70a9`).
- 2026-10-04 — **S6 acceptance passed** (`5cd289f`; review pending). `known_programs.py` rewritten:
  `_Program` (geo_scope, geo_quote, geo_url, geo_checked_on, geo_exclusions, embargo_rule,
  conditions), `_Round` (state, state_url, state_checked_on); `rolling` dropped; leads 30
  (announced) / 51 (expected); staleness 45 d (state) / 365 d (geo); identity `<key>@<state>`;
  titles per state; `report` (deadline_passed / outside_lead_window / no_published_round);
  `geo_verdict` / `geo_evidence` (quote, URL, date, embargo check, every condition);
  `validate_table`; `maintenance_notes` in the Monday heartbeat. **Live facts verified 2026-10-04**:
  Outreachy "open to applicants around the world", $7,000, 42-day and Northern-Hemisphere rules;
  GSoC "Not residing in a U.S. embargoed country" (2027 timeline not published); LFX eligibility
  wording (no explicit worldwide statement → `unknown`) and term timeline; MLH form: Fall 2026
  deadline Aug 31, 2026, no later batch, embargo rule; OFAC active-program list has no Ethiopia
  program (Cuba, Iran, North Korea comprehensive; Syria now targeted PAARSS). Spec acceptance test
  `tests/test_known_programs_acceptance.py`: Case A, B1–B4, C, state change once per state, shipped
  table on 2026-10-04 → **0 program notifications** with a reason per round — all pass. Old
  `test_known_programs.py` rewritten for the new model (justified in its docstring). Spec conflict
  (fact): Case A asserts `gate["already_notified"] == 1` on a re-run, but the record is ACTIVE and
  the spec's gate lists `not_new` first → `already_notified` is now checked first (label only;
  selection identical). **236 passed** (after the S5 review fixes).
- 2026-10-04 — **Resumed after context clear.** git and the resume block agreed; tree clean; 247
  passed / 1 failed as recorded. **S7 done and verified** (`ab4e919`, `0ef22b7`). Failing test
  cause: the recorded fixture truncates each description at 1,500 chars, leaving a dangling `</li`;
  `_text.html_to_text` now also strips a tag cut off at the end of the string (only `</?letter…`,
  so a literal "a < b" stays). **248 passed.** Live acceptance (local, copy of `data/scout.db` in
  the scratchpad, model loaded), run `b98c1c4d89a3`: discovered 318 (greenhouse 221, ashby 8,
  himalayas 89, known_programs 0 with a reason per round) → merged 7 → rejects 219 (remote_excludes
  201, requires_work_auth 6, seniority_title 8, onsite_foreign 2, type_unwanted 2) → survived 92 →
  gate role_family 80, not_new 4, not_target_class 2 → **notified 6**, all Himalayas and all
  genuine technical roles: Software Engineer Intern + Research Intern @ Ritual, Research Engineer
  Intern (Video/Multimodal LLM) @ Tether, Junior DevOps / Cloud Engineer @ CloudCops, QA/QC Intern @
  Flowmingo, CRM Developer @ NightOwl. by_type: unknown 221, new_grad 60, internship 29, full_time 8
  (**S3 acceptance: new_grad non-zero ✓**). Invariant holds (318−7−219−86 = 6). Observations, not
  changed: entry-level queries hit the 3-page cap (60 of totalCount ~306); title similarity is
  ~0.8–0.9 for any "… Intern" title (UX/Recruiting interns top the near-miss list) — the
  role_family gate, not the score, is what separates them. Himalayas' feed now says cursor
  pagination is preferred and `offset` is deprecated; `page=N` (what we use) still worked live.
- 2026-10-04 — **S6 independent review CLOSED** (`3e7d379`). Findings → `tests/test_known_programs_review_s6.py`
  first; **15 failed → confirmed → fixed**: H1 stale `open` round re-announced as `@expected` →
  `ats_job_id` now uses the RECORDED state; staleness changes only the title and lead window
  (deviation m; `test_known_programs::test_stale_open_state…` updated to `r1@open`, justified
  inline). H2 duplicate round keys → `validate_table` reports them and `fetch` raises (a broken
  curated table is a total failure, not a silent borrow). M2 → each fetch replaces `_INDEX`; a miss
  reads the shipped table without mutating the index. M1 → `eligible` also requires `geo_quote` and
  `geo_url` in `geo_verdict` itself. L1 → embargo list older than 365 d → embargo-rule programs
  `unknown`; heartbeat asks for its re-check after 30 d. L2 → ISO codes / official names added
  (CU, IR, KP, DPRK, "Islamic Republic of Iran", …). **Passed before any fix (behaviour already
  right, now pinned):** `test_h1_forward_state_change_is_still_announced`,
  `test_l3_gate_order_already_notified_before_not_new` (+ `test_funnel` now pins
  `gate == {"already_notified": 4}` instead of a subset), `test_l4_shipped_verdicts_for_ethiopia`
  (Outreachy/GSoC eligible, LFX unknown), `test_l4_maintenance_fresh_checks_are_quiet`. M3 decided:
  the MLH "no anticipated projects" list was extracted live from the form (29 countries — Ethiopia not
  among them) → `geo_exclusions` filled (+ "South Korea" alias for the form's "Korea"),
  `geo_scope="worldwide"` (same treatment as GSoC: embargo rule + verified list); `geo_url` stays the
  form (where the quote and list live), program `url` is fellowship.mlh.com. No round → no output
  change. **268 passed.**
- 2026-10-04 — **S8 done** (`d1f055e`). `scripts/verify_boards.sh` (needs a `python3` on PATH — on
  this Windows box a scratch shim to the venv python) → `canonical` VERIFIED, 310 jobs (gitlab 211,
  sourcegraph91 10, posthog 8, deel 0 also verified). Added to `greenhouse_boards` with a provenance
  comment; no other boards. Live run `c10ee16c1d62` (copy of the DB): discovered 628 → merged 19 →
  rejects 413 (remote_excludes 269, seniority_title 128, onsite_foreign 9, work_auth 6, type 2+…)
  → survived 196 → gate not_target_class 98, role_family 85, not_new 4 → **notified 9**: the 6
  Himalayas items from S7 plus 3 Canonical — Junior Ubuntu Software Engineer, Junior Linux Kernel
  Engineer - Ubuntu, Graduate Software Engineer, Open Source and Linux (all "Home based -
  Worldwide"). by_type new_grad 73. Invariant 628−19−413−187 = 9 ✓. **268 passed.**
- 2026-10-04 — **Final review CLOSED** (`96c10db`). Reviewer (general-purpose, Opus, read-only, given
  only §5–§9, CLAUDE.md, the diff 7ec0b85..48745df and the tests). Findings → `tests/test_final_review.py`
  (+ `test_reclassify_stored::test_body_residency_oracle`); every fix-targeting test was run against the
  pre-fix code and **failed** (eligibility 14 written first; H3/M4/M5/L4/L7 tests written alongside the
  fix and then confirmed failing on the stashed old code). Fixed: H1 "US" matched case-sensitively in
  the body rule (pronoun "us" no longer excludes); H2 body residency requirement elsewhere cancels a
  worldwide phrase → UNKNOWN 0.5; H3 no cross-level fuzzy merge; M1 work-auth vs decisive location
  (deviation o); M2 exclusion wording; M3 `_geo.SUBNATIONAL` (Canadian provinces, Australian/Indian
  states, UK nations, Bay Area, …); M4 role head + discipline vetoes; M5 `skipped_records` per source in
  the run record and a "skipped" column in `funnel.md` (deviation b withdrawn); L4 `rejected_samples`
  exclude not_new/already_notified; L7 checker also flags a positive whose body requires residence in a
  named non-user country; L8 one-line justification per deleted pre-S6 known_programs test; L9 WORLD +
  ELSEWHERE title marker → MIXED; L10 "Fully Remote" → BARE 0.5 and "EMEA, excluding Ethiopia" → excluded.
  Guard tests that passed before the fixes (kept): `test_h1_country_us_still_restricts`,
  `test_h2_worldwide_phrase_alone_still_worldwide`, `test_m1_foreign_right_to_work_still_disqualifies`,
  `test_m1_sponsorship_still_disqualifies_without_decisive_location`, "New South Wales" (already via
  "wales"), M4's three must-veto titles. Refuted / kept as recorded deviations: L1 (= j), L2 (= h),
  L3 (= m). Kept, not changed: L5 — the invariant is algebraic by construction (one reason per record
  from one map); the new M5 test covers a source whose records are all skipped; L6 — lexical-mode body
  reading only matters without the model (same as S5 review L4); "Remote (GMT+3)" stays UNKNOWN 0.3
  (spec has no time-zone rule for the location field). H2 on the stored rows: the real Sourcegraph text
  is "we have a **preference** … welcome to apply regardless of location", not a requirement, so 7 stored
  Sourcegraph rows stay worldwide (0.5 where US/EST hours are required); the two "require … located in
  the United States" rows are "…, US" titles and were already excluded. Re-classification: **0 bad**
  (checker now also body-aware). Golden set 1.000/1.000. Live re-run `5e2c7dedde72` (copy of the DB):
  628 → merged 17 (was 19 — the level guard keeps 2 cross-level pairs apart) → rejects 413 → survived
  198 → gate 189 (not_target_class 100, role_family 85, not_new 4) → **notified 9**, the same 9 items;
  skipped 0 for every source. Invariant 628−17−413−189 = 9 ✓. **301 passed.**

  **End of pass.** §8 status: (1) invariant holds on every run record, skipped records now attributed ✓;
  (2) 0 bad stored rows ✓; (3) delivery on a real device — pending human check (2); (4) golden 1.0/1.0 ✓
  (in-sample); (5) S6 acceptance A/B/C ✓, today's shipped table → 0 program notifications with a
  reason per round ✓; (6) 14-day observation — starts after merge; (7) pre-existing tests pass or carry
  a one-line justification ✓. Nothing pushed; `main` untouched.
- 2026-10-04 — **Dagi's follow-ups.** (1) Body restriction vs WORLD/USER location (`5819288`): tests first in
  `tests/test_final_review.py` — the 3 reported cases FAILED (all positive), 5 guards passed. Rule: when the
  location is WORLD or USER, a description sentence "must be based/located/reside/live in …", "candidates /
  applicants in …", "residents of …" whose every part names a place outside the user's scope → UNKNOWN 0.5
  ("Check eligibility"), evidence quotes the clause. Results: "Worldwide" + "open to candidates in the US and
  Canada only" → UNKNOWN 0.5; "Worldwide" + "must reside in Europe or North America" → UNKNOWN 0.5; "Remote,
  EMEA" + "Must be based in the United Kingdom." → REQUIRES_WORK_AUTH 0.85 (excluded) — its root cause was the
  step-2 residency window running past the sentence end into the appended location text ("…kingdom. remote,
  emea"); the window now stops at `.;:` / newline. M1 visa-sponsorship behaviour kept (guard test). Live run
  `3bb7a4f9766a`: rule fired on 0 of 628 records; the same 9 selected; re-classification of stored rows 0 bad
  (7 Sourcegraph positives unchanged). **309 passed.** (2) `origin/main` a39feaa (bot run) merged into the branch
  (`b911406`, clean; `data/scout.db` identical to origin/main); suite 309 passed and re-classification 0 bad on
  the merged DB; branch pushed. (3) Pending check (3) rewritten to merge by PR. FACT: local `main` is 4 ahead /
  1 behind `origin/main`; the 4 (80ae5b6, b9e0e96, a6d4fae, 7ec0b85) are ancestors of next-iteration, so the PR
  carries them; local `main` was not touched.

---

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

## NEXT ITERATION — started 2026-10-04 (this section supersedes the freeze below)

**The observation/calibration freeze is ENDED** (2026-10-04, by the user's instruction and spec
§9). The plan is `docs/SPEC-2026-10-04-next-iteration.md` (revision 2): the spec decides what to
build; the repo decides what is true. Order = spec §10; delegation/gates = spec §11; scope limits =
spec §9. One branch per step (`s0-funnel`, `s1-delivery`, …), merged to `main` only after that
step's acceptance criteria pass, rebased first (the bot commits `data/scout.db` to `main` daily).

**Single next action: S0 — reason-coded funnel (no behaviour change)**, branch `s0-funnel`.

### Spec-vs-repo checks (2026-10-04)
- FACT: `origin/main` HEAD = `a2f685b` ("scout: run 2026-10-03T09:30Z"), as the spec states.
  Local `main` was 25 bot commits behind (data only); fast-forwarded.
- FACT: `PYTHONPATH=src python -m pytest -q` → **89 passed** on `a2f685b` (spec: 89). The 85 in
  the header above is stale (commit `fe8a9fe` added tests after it was written).
- FACT: S0 "current" claims match the code — `hard_filter` returns survivors only
  (`score.py`), `select_for_notification` returns the selection only (`notify.py`), `RunSummary`
  has scalar counts (`pipeline.py`), `runs.summary` is a JSON text column (`store.py`).
- FACT: configured sources match spec §2 — greenhouse `gitlab`, `sourcegraph91`; ashby `posthog`,
  `deel`; lever none; `known_programs`.
- Note for S0 (no behaviour change): `select_for_notification` also passes a confident
  `STIPEND_PROGRAM_GLOBAL` below threshold (Decision #8). S0's `gate_reason` must keep that, so
  `below_threshold` applies only to non-best-fit records.

### Step log
*(One entry per step: what changed · acceptance evidence in numbers · single next action.)*
- 2026-10-04 — spec committed (`80ae5b6`); freeze ended; S0 next.
- 2026-10-04 — §11 roles created in `.claude/agents/`: `builder` (claude-opus-4-6, high),
  `hard-logic` (claude-opus-4-8, high), `mechanic` (claude-sonnet-5-5, medium);
  `claude-sonnet-5-5` added to the enforced `availableModels` in `.claude/settings.json`.
  **BLOCKED (FACT):** spawning `builder` from the current session failed — "Agent type 'builder'
  not found" (the session was started in the parent folder, so project agents were not loaded).
  The only available route is `general-purpose` with an `opus`/`sonnet` alias (resolves to the
  newest model, not the pinned version; no effort setting). Per §11, waiting for Dagi's call
  before delegating S0. No S0 code written yet.
- 2026-10-04 — Dagi's decision: restart Claude Code from `job-scout/`; a new prompt and an updated
  spec (revised delegation, single-pass implementation) will follow. **Next action: wait for them.**
  Commits `80ae5b6`..HEAD are local only (not pushed); rebase onto `origin/main` before pushing.

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

## OPERATING MODE — OBSERVATION / CALIBRATION FREEZE (set 2026-09-03; ENDED 2026-10-04 — see §Next iteration; kept for history)

The deployed system is left **running as-is**. This is an observation/calibration period.

**Hard freeze — do NOT, without an explicit new instruction from the user:**
- modify **scoring** (`score.py`), **eligibility** (`eligibility.py`), or the **architecture / frozen
  spine** (`models.py`, `sources/base.py`, pipeline stage order, `store.py` schema);
- change adapters, config logic, or the workflow;
- trigger manual `workflow_dispatch` runs or otherwise babysit the schedule.

**Do:** let the daily GitHub Actions cron run on its own; **preserve all evidence in this file.** When
observations accumulate (e.g. surprising eligibility calls, threshold miscalibration, missed/duplicate
notifications), record them below under *Observation log* as data for a later, explicitly-instructed
calibration pass — do not act on them unilaterally.

### Observation log
*(Append dated entries here as real-run evidence arrives. Empty = none recorded yet.)*
- 2026-09-03 — Deployment run 33754711547 (dispatch): 233→201→23→1 notified. Baseline; see §Phase 3.
- 2026-09-08 — **Diagnostic investigation of five consecutive "0 opportunities" reports (Sep 4–8).
  Read-only; freeze respected (no dispatch, no new runs, no code/config change). Conclusion: the
  pipeline is HEALTHY; the zeros are correct by design (case 3 + case 4 — state gate + scarcity).**
  Evidence from Actions history + the committed `data/scout.db` `runs.summary` (funnel per run):

  | run (UTC)   | run_id (Actions) | conclusion | discovered | deduped | survived | new | upd | active | notified |
  |-------------|------------------|-----------|-----------|---------|----------|-----|-----|--------|----------|
  | 09-03 disp. | 33754711547      | success   | 233       | 201     | 23       | 23  | 0   | 0      | 1        |
  | 09-04 cron  | 33852625836      | success   | 249       | 219     | 31       | 10  | 0   | 21     | 0        |
  | 09-05 cron  | 33953765898      | success   | 245       | 215     | 30       | 1   | 0   | 29     | 0        |
  | 09-06 cron  | 34021097827      | success   | 247       | 217     | 30       | 0   | 0   | 30     | 0        |
  | 09-07 cron  | 34101904712      | success   | 247       | 217     | 30       | 0   | 0   | 30     | 0        |
  | 09-08 cron  | 34204180748      | success   | 245       | 215     | 29       | 0   | 0   | 29     | 0        |

  - **Step 1 (ran?):** All 5 scheduled runs fired daily on `main`, all `conclusion=success`; each
    committed `data/scout.db` back (bot commits `50ae69b`→`985d29b`→`2064562`→`ef5a935`→`30e97c1`,
    Sep 4–8) → ran, succeeded, persisted. All used `config/profile.yaml` (workflow cmd
    `python -m job_scout -c config/profile.yaml -v`). No failed/skipped/silently-green stage. (Local
    `origin/main` ref was stale at `fe8a9fe` until a read-only `git fetch`; the bot commits were on
    the remote all along.)
  - **Step 2/3 (funnel):** Fetch is healthy and stable (~245 discovered, ~215 deduped, ~30 survivors
    each day — greenhouse ~236–240, ashby 9, lever 0 [empty upstream, `ok=true`], known_programs 0).
    Counts equal/exceed the Gate-1 baseline (234→201→23). **The count collapses only at the
    NEW/UPDATED gate**, not at fetch/dedupe/eligibility/hard_filter/scoring.
  - **Step 4 (state gate):** `opportunities` = 34 rows (32 ACTIVE, 2 stale NEW). Exactly **1** row
    ever `notified_at` (the Sep-03 GitLab Intermediate Fullstack Engineer). `first_seen`: 23 on
    Sep-03, 10 on Sep-04, 1 on Sep-05, then 0 new Sep 6–8. The ~30 daily survivors are the SAME
    records, now ACTIVE + already-notified-gate-passed → 0 notifications is the diff notifier
    working as designed (`notify.select_for_notification`: NEW/UPDATED ∧ not-notified ∧
    (score≥threshold ∨ best-fit stipend)).
  - **Step 5 (threshold/coverage/scarcity):** Only ONE opportunity has ever scored ≥ the 0.40
    threshold (0.41). Max score among all records first-seen on the new days (Sep 4–5) = **0.3983**,
    i.e. the Sep-04 (10) and Sep-05 (1) NEW survivors correctly failed the threshold — nothing to
    notify even before the state gate. Survivors are overwhelmingly senior/sales/AE/manager roles
    (`employment_type=unknown`, kept by hard_filter), NOT internships; the structurally best-fit
    class `known_programs`=0 all week (Outreachy opens Dec 7 2026; GSoC 2027), exactly as predicted.
  - **Classification:** case 3 (found-but-already-known / state gate) + case 4 (scarcity), with the
    0.40 threshold and thin worldwide-remote-intern coverage as the secondary reason the low-churn
    new arrivals don't clear the bar. NOT case 1/2/5 (fetch, filtering, runtime all healthy). Working
    hypothesis CONFIRMED.
  - **Warranted change:** NONE required — the scraper is healthy and the zeros are the correct output
    of a working diff notifier against a low-churn, scarce board set. Candidate calibration items for
    a LATER explicitly-instructed pass (do not act now): (a) split `hard_filter` telemetry into
    location-reject vs type/experience-reject counts (currently only one post-filter "survived" count
    is logged); (b) the digest overwrite-on-quiet-run (already logged §Known defects); (c) revisit
    whether entry/intern coverage should widen — but that is a coverage decision, not a bug.

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

**Superseded 2026-10-04: the single next action is S0 — see §Next iteration.** The list below is
the pre-spec state, kept for history.

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

**2026-10-04: the freeze described below is ENDED.** Work in flight = the spec iteration; resume
from §Next iteration (top of file).

**Nothing in flight. DEPLOYED + VERIFIED. Now in an OBSERVATION / CALIBRATION FREEZE** (see
§Operating mode). The project is live at `https://github.com/DagiHabtu/job-scout` (PUBLIC) and runs
daily on GitHub Actions at `$0`; the dispatch run (33754711547) succeeded end-to-end. Local `main`
synced; **85 tests pass**; spine unchanged.

**A future session must NOT modify scoring, eligibility, or architecture, or trigger manual runs,
without an explicit new user instruction.** Let the cron run; append real-run findings to the
§Operating mode → Observation log as evidence for a later, explicitly-instructed calibration pass.
Deferred by choice: Adzuna (needs a key), hard-logic tuning (needs more evidence).
