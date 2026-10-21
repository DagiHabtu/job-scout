"""Iteration 3 §4.8 — the labels channel: comment grammar, the event-file entry point, the seed file,
and the workflow's handling of untrusted comment text."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from job_scout.labels import LabelParseError, item_map_of, label_lines, latest, main, parse_label_comment, read_labels

ROOT = Path(__file__).resolve().parents[1]
MAP = {"1": "k1", "2": "k2", "3": "k3", "4": "k4"}
BODY = ("## Apply\n\n1. [Backend Intern](https://x/1) — Acme · internship · Remote\n    - **Role:** Build.\n"
        "2. [Data Intern](https://x/2) — Beta · internship\n3. [QA Intern](https://x/3) — Gamma\n"
        "4. [ML Intern](https://x/4) — Delta · pay: $500\n\n"
        "Reply with a comment such as: `apply 1,4 · maybe 2 · skip rest`\n"
        '<!-- scout-items {"1": "k1", "2": "k2", "3": "k3", "4": "k4"} -->\n\ncc @owner\n')


@pytest.mark.parametrize("comment,expected", [
    ("apply 1,4 · maybe 2 · skip rest", [("k1", "apply"), ("k2", "maybe"), ("k3", "skip"), ("k4", "apply")]),
    ("skip all", [(k, "skip") for k in ("k1", "k2", "k3", "k4")]),
    ("apply 2-3", [("k2", "apply"), ("k3", "apply")]),
    ("Apply 1\nskip 2", [("k1", "apply"), ("k2", "skip")]),
    ("APPLY 1; Maybe 3", [("k1", "apply"), ("k3", "maybe")]),
    ("skip rest, apply 1", [("k1", "apply"), ("k2", "skip"), ("k3", "skip"), ("k4", "skip")]),
    ("skip all · apply 2", [("k1", "skip"), ("k2", "apply"), ("k3", "skip"), ("k4", "skip")]),
])
def test_grammar(comment, expected):
    assert parse_label_comment(comment, MAP) == expected


@pytest.mark.parametrize("comment,fragment", [
    ("apply 1, 9", "`9 (no such item)`"),
    ("apply 3-6", "`3-6 (no such item)`"),
    ("", "No decision found"),
    ("thanks, looks good", "`thanks`"),
    ("apply", "No decision found"),
    ("1 apply", "`1`"),
])
def test_errors_list_what_was_not_understood(comment, fragment):
    with pytest.raises(LabelParseError) as e:
        parse_label_comment(comment, MAP)
    assert fragment in str(e.value)


def test_item_map_and_lines_carry_title_and_company():
    assert item_map_of(BODY) == MAP
    lines = label_lines(BODY, "apply 1 · skip 4", issue=7, comment_id=99)
    assert [(ln["key"], ln["title"], ln["company"], ln["decision"]) for ln in lines] == [
        ("k1", "Backend Intern", "Acme", "apply"), ("k4", "ML Intern", "Delta", "skip")]
    assert lines[0]["source"] == "issue-comment" and lines[0]["issue"] == 7 and lines[0]["comment_id"] == 99
    with pytest.raises(LabelParseError):
        item_map_of("an issue without a map")


def test_later_comment_replaces_earlier_decisions_for_the_items_it_names():
    lines = label_lines(BODY, "apply 1 · maybe 2") + label_lines(BODY, "skip 1")
    got = {k: ln["decision"] for k, ln in latest(lines).items()}
    assert got == {"k1": "skip", "k2": "maybe"}


def _event(tmp_path, comment, body=BODY):
    p = tmp_path / "event.json"
    p.write_text(json.dumps({"issue": {"number": 7, "body": body}, "comment": {"id": 99, "body": comment}}),
                 encoding="utf-8")
    return p


def test_main_appends_lines(tmp_path):
    out, err = tmp_path / "labels.jsonl", tmp_path / "err.md"
    assert main(["--event", str(_event(tmp_path, "apply 1,4 · maybe 2 · skip rest")), "--out", str(out),
                 "--error-file", str(err)]) == 0
    assert main(["--event", str(_event(tmp_path, "skip 1")), "--out", str(out), "--error-file", str(err)]) == 0
    lines = read_labels(out)
    assert len(lines) == 5 and latest(lines)["k1"]["decision"] == "skip" and not err.exists()


@pytest.mark.parametrize("comment", ["apply 1 $(touch PWNED)", "apply `touch PWNED` 2", "skip rest; $(rm -rf /)"])
def test_injection_shaped_comment_is_data(tmp_path, monkeypatch, comment):
    monkeypatch.chdir(tmp_path)
    out, err = tmp_path / "labels.jsonl", tmp_path / "err.md"
    assert main(["--event", str(_event(tmp_path, comment)), "--out", str(out), "--error-file", str(err)]) == 2
    assert "Not understood" in err.read_text(encoding="utf-8")
    assert not out.exists() and not (tmp_path / "PWNED").exists()


def test_workflow_never_interpolates_comment_or_issue_text():
    wf = (ROOT / ".github" / "workflows" / "labels.yml").read_text(encoding="utf-8")
    assert "github.event.comment.body" not in wf and "github.event.issue.body" not in wf
    assert "$GITHUB_EVENT_PATH" in wf
    assert "issue_comment" in wf and "github.repository_owner" in wf and "'scout'" in wf
    # branch review M4: a shared concurrency group cancels pending runs → labels has none and retries its push
    assert "concurrency:" not in wf and "pull --rebase" in wf and "for attempt in" in wf
    scout = (ROOT / ".github" / "workflows" / "scout.yml").read_text(encoding="utf-8")
    assert "group: scout-state" in scout and "pull --rebase" in scout and "for attempt in" in scout


def test_seed_file_matches_appendix_a():
    lines = read_labels(ROOT / "data" / "labels.jsonl")
    src = json.loads((ROOT / "tests" / "fixtures" / "labels_2026-10-21.json").read_text(encoding="utf-8"))
    assert len(lines) == sum(len(r["keys"]) for r in src) == 36
    assert all(set(ln) == {"key", "title", "company", "decision", "labelled_at", "source"} for ln in lines)
    assert all(ln["labelled_at"] == "2026-10-21" and ln["source"] == "triage-page" for ln in lines)
    cloudcops = [ln for ln in lines if ln["company"] == "CloudCops"]
    assert len(cloudcops) == 2 and all(ln["decision"] == "maybe" for ln in cloudcops)
