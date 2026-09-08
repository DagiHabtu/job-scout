# Job Scout — Diagnostic: five consecutive "0 opportunities" reports (Sep 4–8, 2026)

**Date of investigation:** 2026-09-08
**Mode:** read-only diagnostic. Observation/calibration **freeze respected** — no `workflow_dispatch`,
no new runs, no code/config/architecture change. All evidence is from existing Actions history and the
committed `data/scout.db`. A read-only `git fetch origin main` was used (triggers nothing) because the
local `origin/main` ref was stale at `fe8a9fe`.

**Verdict:** the scraper is **healthy**. The five zeros are the **correct** output of a working diff
notifier against a low-churn, scarce board set. **No change is warranted.** Working hypothesis
(case 3 + case 4) **CONFIRMED**.

---

## Evidence chain

### Step 1 — Did the runs execute, on the right branch, successfully?
All 5 scheduled runs fired daily on `main`, all `conclusion=success`, all using `config/profile.yaml`
(workflow cmd `python -m job_scout -c config/profile.yaml -v`). Each committed `data/scout.db` back,
proving it ran → succeeded → persisted.

| run (UTC)      | Actions run_id | event    | branch | conclusion | bot commit |
|----------------|----------------|----------|--------|-----------|------------|
| 2026-09-03 12:21 | 33754711547  | dispatch | main   | success   | 53e4ac8    |
| 2026-09-04 08:16 | 33852625836  | schedule | main   | success   | 50ae69b    |
| 2026-09-05 07:53 | 33953765898  | schedule | main   | success   | 985d29b    |
| 2026-09-06 08:10 | 34021097827  | schedule | main   | success   | 2064562    |
| 2026-09-07 08:41 | 34101904712  | schedule | main   | success   | ef5a935    |
| 2026-09-08 08:22 | 34204180748  | schedule | main   | success   | 30e97c1    |

No failed, cancelled, skipped, or silently-green stage. `origin/main` HEAD after fetch = `30e97c1`.

### Step 2/3 — The funnel (from `runs.summary` in `data/scout.db`)

| run (UTC)   | discovered | deduped | survived | new | upd | active | notified |
|-------------|-----------|---------|----------|-----|-----|--------|----------|
| 09-03 disp. | 233       | 201     | 23       | 23  | 0   | 0      | **1**    |
| 09-04 cron  | 249       | 219     | 31       | 10  | 0   | 21     | **0**    |
| 09-05 cron  | 245       | 215     | 30       | 1   | 0   | 29     | **0**    |
| 09-06 cron  | 247       | 217     | 30       | 0   | 0   | 30     | **0**    |
| 09-07 cron  | 247       | 217     | 30       | 0   | 0   | 30     | **0**    |
| 09-08 cron  | 245       | 215     | 29       | 0   | 0   | 29     | **0**    |

Per-source (stable all week): `greenhouse` ~236–240, `ashby` 9, `lever` 0 (empty upstream, `ok=true`),
`known_programs` 0. Fetch/dedupe/survivor counts **equal or exceed** the Gate-1 baseline
(234→201→23). **The count collapses only at the NEW/UPDATED gate** — not at fetch, dedupe,
eligibility, hard_filter, or scoring.

### Step 4 — The NEW/UPDATED state gate (from `opportunities` table)
- 34 rows total: **32 ACTIVE, 2 stale NEW**.
- **Exactly 1 row ever `notified_at`**: GitLab "Intermediate Fullstack Engineer - Data Products",
  notified 2026-09-03T12:23Z.
- `first_seen`: 23 on Sep-03, 10 on Sep-04, 1 on Sep-05, then **0 new** on Sep 6–8.
- The ~30 daily survivors are the **same records**, now ACTIVE and already past the notify gate.
- `notify.select_for_notification` = `status∈{NEW,UPDATED} ∧ notified_at is None ∧
  (relevance.score ≥ threshold ∨ best-fit stipend class)`. With no new/updated survivors and nothing
  above threshold, **0 notifications is the diff notifier working exactly as designed**.

### Step 5 — Threshold / coverage / scarcity (from stored `relevance.score`)
- **Only one opportunity has ever scored ≥ 0.40** (the notified GitLab role, 0.41). All others
  score 0.06–0.40.
- **Max score among everything first-seen on the new days (Sep 4–5) = 0.3983** → the Sep-04 (10) and
  Sep-05 (1) NEW survivors correctly failed the 0.40 threshold; there was nothing to notify even
  before the state gate applied.
- Survivors are overwhelmingly **senior / sales / account-executive / manager / director** roles
  (`employment_type=unknown`, correctly kept by hard_filter), **not internships**. The structurally
  best-fit class `known_programs` returns **0** all week (Outreachy opens Dec 7 2026; GSoC 2027) —
  exactly as `STATE.md` predicted.

---

## Classification

**Case 3 (state gate suppressing already-known survivors) + Case 4 (genuine scarcity)**, with the
0.40 relevance threshold and thin worldwide-remote-internship coverage as the **secondary** reason
the low-churn new arrivals don't clear the bar.

- NOT case 1 — fetch is healthy (~245/day).
- NOT case 2 — filtering is healthy (~30 survivors/day, at/above baseline).
- NOT case 5 — runtime/scheduler is healthy (5/5 success, correct branch, correct config).

Working hypothesis **confirmed**: this is expected scarcity + the NEW/UPDATED state gate behaving
correctly, not a broken scraper.

---

## Is a change warranted?

**No.** Declaring the scraper broken on the strength of the five zeros alone would be wrong. A working
diff notifier fires once on a survivor, then correctly stays silent while that survivor is ACTIVE and
unchanged. Five straight 0-notification days against a small, low-churn, out-of-season board set is
the **expected** behavior, not a fault.

## Smallest next action, if a later (explicitly-instructed) calibration pass wants one

Proposed only — **not executed**:

1. **(highest value, the one real telemetry gap)** Split the `hard_filter` "survived" count into
   *location/eligibility-reject* vs *type/experience/role-reject* sub-counts. Currently a single
   post-filter number is logged, so the pipeline can't yet say *why* survivors are lost inside
   `hard_filter`. This is the only diagnostic the existing evidence cannot answer; it is small and
   `$0`-safe (a counter, no scoring/eligibility/architecture change).
2. Decide the digest overwrite-on-quiet-run policy (already logged in `STATE.md` §Known defects).
3. If daily churn is desired, that is a **coverage** decision (widen entry/intern sources), not a bug
   fix — and it must stay inside the `$0` invariant and the frozen spine.

---

*Condensed evidence is also recorded in `STATE.md` → Operating mode → Observation log (2026-09-08).*
