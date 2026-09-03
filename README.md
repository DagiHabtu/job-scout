# Job Scout

Autonomous, **zero-cost** scout for internships / entry-level roles — evaluated for **relevance
AND eligibility** (user in Ethiopia), deduplicated, ranked, and delivered as a digest.

## Where the truth lives (never the conversation)

| File | Role |
|---|---|
| `CLAUDE.md` | the five hard constraints — the compaction-survivable kernel |
| `PLAN.md` | the full plan: phases, gates, the frozen spine, agent roster, risks |
| `STATE.md` | live cursor — current position, gate status, the single next action |
| the code | what actually runs |

After any context reset, re-read `PLAN.md` and `STATE.md` before doing anything.

## Status

**Deployed and running at `$0`.** The scout runs daily on **GitHub Actions** — a dispatch run
succeeded end-to-end (scout executed, digest artifact uploaded, `data/scout.db` committed back for
persistence + schedule keepalive). Four sources are live-verified — **Greenhouse**, **Lever**,
**Ashby**, and a curated **known-programs** source (Outreachy / GSoC / MLH → structurally-worldwide
stipend programs) — aggregating through one frozen pipeline with cross-source dedupe and an
eligibility-first gate. Relevance uses a local MiniLM model with a `$0` lexical fallback. `pytest -q`
→ **85 passing**. See `STATE.md` §Phase 3 / §Live verification for executed evidence. Deferred:
Adzuna discovery (needs a free API key) and hard-logic tuning (pending more real-run data).

Widen coverage without touching code: add board tokens / site slugs / org slugs to
`config/profile.yaml` (`greenhouse_boards`, `lever_sites`, `ashby_orgs`) and push.

## Run it

```bash
python -m pip install -e ".[dev,embeddings]"   # once (a project-local .venv is recommended)
python -m pytest -q                            # 57 tests (offline; the model path is verified out-of-CI)
cp config/profile.example.yaml config/profile.yaml   # then edit: boards, roles, location
python -m job_scout -c config/profile.yaml -v  # one idempotent live run → data/digest.html
# add --no-model to force the lexical fallback (still $0, no torch needed)
```
