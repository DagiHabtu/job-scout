"""Labels channel (spec 2026-10-21 §4.8): Dagi replies to a delivery issue with a comment such as
`apply 1,4 · maybe 2 · skip rest`; this parses it against the issue's hidden item map and appends one
line per item to `data/labels.jsonl`. Stdlib only, no model.

`labels.jsonl` is append-only; the latest line for a key is its decision (`latest`), so a later comment
on the same issue replaces the earlier decisions for the items it names.

The comment is untrusted input: it is read from the event JSON file and only ever handled as data —
nothing here runs a shell or evaluates it.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

DECISIONS = ("apply", "maybe", "skip")
_SEPARATORS = re.compile(r"[·;,\s]+")
_RANGE = re.compile(r"(\d+)-(\d+)")
_MAP = re.compile(r"<!-- scout-items (\{.*?\}) -->")
_ITEM = re.compile(r"^(\d+)\. \[(.+?)\]\(.*?\)(?: — ([^·\n]+))?", re.MULTILINE)


class LabelParseError(ValueError):
    """The comment could not be read; the message lists what was not understood."""


def item_map_of(issue_body: str) -> dict[str, str]:
    """The hidden `{"<number>": "<record key>"}` map at the end of a delivery issue (§4.6)."""
    m = _MAP.search(issue_body or "")
    if not m:
        raise LabelParseError("this issue has no item map (`<!-- scout-items … -->`), so its numbers cannot be read")
    return json.loads(m.group(1))


def parse_label_comment(comment: str, item_map: dict[str, str]) -> list[tuple[str, str]]:
    """[(record key, decision)] in item order. Grammar (case-insensitive; separators `·` `;` `,` and
    whitespace): a verb (apply|maybe|skip) followed by item numbers, ranges `2-4`, `all`, or `rest` —
    the items this comment does not name otherwise. A later mention of an item wins."""
    chosen: dict[int, str] = {}
    rest: str | None = None
    verb: str | None = None
    bad: list[str] = []
    numbers = sorted(int(n) for n in item_map)
    for tok in (t for t in _SEPARATORS.split((comment or "").lower()) if t):
        if tok in DECISIONS:
            verb = tok
            continue
        if verb is None:
            bad.append(tok)
            continue
        if tok == "rest":
            rest = verb
        elif tok == "all":
            chosen.update((n, verb) for n in numbers)
        elif tok.isdigit() or _RANGE.fullmatch(tok):
            lo, hi = (int(x) for x in (_RANGE.fullmatch(tok).groups() if "-" in tok else (tok, tok)))
            wanted = range(lo, hi + 1)
            if not wanted or any(str(n) not in item_map for n in wanted):
                bad.append(f"{tok} (no such item)")
                continue
            chosen.update((n, verb) for n in wanted)
        else:
            bad.append(tok)
    if rest is not None:
        chosen.update((n, rest) for n in numbers if n not in chosen)
    if bad:
        raise LabelParseError("Not understood: " + ", ".join(f"`{b}`" for b in bad))
    if not chosen:
        raise LabelParseError("No decision found — write e.g. `apply 1,4 · maybe 2 · skip rest`.")
    return [(item_map[str(n)], chosen[n]) for n in sorted(chosen)]


def label_lines(issue_body: str, comment: str, *, issue: int | None = None, comment_id: int | None = None,
                now: datetime | None = None) -> list[dict]:
    """The `labels.jsonl` lines for one comment on one delivery issue."""
    item_map = item_map_of(issue_body)
    shown = {n: (t, (c or "").strip() or None) for n, t, c in _ITEM.findall(issue_body)}
    when = (now or datetime.now(timezone.utc)).date().isoformat()
    number_of = {k: n for n, k in item_map.items()}
    out = []
    for key, decision in parse_label_comment(comment, item_map):
        title, company = shown.get(number_of[key], (None, None))
        out.append({"key": key, "title": title, "company": company, "decision": decision, "labelled_at": when,
                    "source": "issue-comment", "issue": issue, "comment_id": comment_id})
    return out


def read_labels(path: str | Path) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def latest(lines: list[dict]) -> dict[str, dict]:
    """key → its latest line (later lines replace earlier ones)."""
    return {ln["key"]: ln for ln in lines}


def main(argv: list[str] | None = None) -> int:
    """Read the issue body and comment from the GitHub event JSON file; append the lines to `--out`.
    Exit 0 on success; exit 2 with the reason written to `--error-file` when the comment is not understood."""
    ap = argparse.ArgumentParser(prog="python -m job_scout.labels")
    ap.add_argument("--event", required=True, help="path to the issue_comment event JSON ($GITHUB_EVENT_PATH)")
    ap.add_argument("--out", default="data/labels.jsonl")
    ap.add_argument("--error-file", required=True)
    args = ap.parse_args(argv)
    event = json.loads(Path(args.event).read_text(encoding="utf-8"))
    issue, comment = event.get("issue") or {}, event.get("comment") or {}
    try:
        lines = label_lines(issue.get("body") or "", comment.get("body") or "", issue=issue.get("number"),
                            comment_id=comment.get("id"))
    except LabelParseError as exc:
        Path(args.error_file).write_text(f"Job Scout could not read this reply. {exc}\n", encoding="utf-8")
        return 2
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as f:
        for ln in lines:
            f.write(json.dumps(ln, ensure_ascii=False) + "\n")
    print(f"recorded {len(lines)} label(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
