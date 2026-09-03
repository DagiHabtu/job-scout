#!/usr/bin/env bash
# verify_boards.sh — confirm public ATS board tokens resolve to a live JSON board. $0, no auth.
#
# A token is VERIFIED only on HTTP 200 + a JSON body of the expected shape (Greenhouse/Ashby:
# an object with a "jobs" array; Lever: a top-level JSON array). Edit the three arrays, then:
#   bash scripts/verify_boards.sh
#
# Run this wherever you have network egress to the ATS hosts (local shell or a CI step). The
# authoring sandbox blocks these hosts, which is why the token list in profile.yaml was verified
# out-of-band against API-checked sources rather than by this script directly.
set -uo pipefail
UA="job-scout-token-verify/1.0"

# ---- edit these ----------------------------------------------------------------------------- #
GREENHOUSE=(gitlab sourcegraph91)     # board tokens  -> boards-api.greenhouse.io/v1/boards/<t>/jobs
LEVER=()                              # site slugs    -> api.lever.co/v0/postings/<t>?mode=json
ASHBY=(posthog deel)                  # org slugs     -> api.ashbyhq.com/posting-api/job-board/<t>
# --------------------------------------------------------------------------------------------- #

_count() { python3 -c "$1" 2>/dev/null; }   # reads stdin, prints a count or nothing on failure

_check() {  # $1=label  $2=url  $3=python-counter-expr
  local body n
  body=$(curl -fsS -m 15 -A "$UA" "$2" 2>/dev/null) || { printf '  invalid   %-16s (no 200 — 404 / blocked / network)\n' "$1"; return; }
  n=$(printf '%s' "$body" | _count "$3")
  if [ -n "$n" ]; then printf '  VERIFIED  %-16s %s jobs\n' "$1" "$n"
  else               printf '  invalid   %-16s (200 but unexpected body — HTML? wrong shape?)\n' "$1"; fi
}

echo "== Greenhouse =="
for t in "${GREENHOUSE[@]:-}"; do [ -n "$t" ] || continue
  _check "$t" "https://boards-api.greenhouse.io/v1/boards/$t/jobs?content=false" \
    'import sys,json; print(len(json.load(sys.stdin)["jobs"]))'
done

echo "== Lever =="
for t in "${LEVER[@]:-}"; do [ -n "$t" ] || continue
  _check "$t" "https://api.lever.co/v0/postings/$t?mode=json" \
    'import sys,json; d=json.load(sys.stdin); assert isinstance(d,list); print(len(d))'
done

echo "== Ashby =="
for t in "${ASHBY[@]:-}"; do [ -n "$t" ] || continue
  _check "$t" "https://api.ashbyhq.com/posting-api/job-board/$t" \
    'import sys,json; print(len(json.load(sys.stdin)["jobs"]))'
done
