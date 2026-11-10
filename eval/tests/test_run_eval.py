"""The evaluation itself is code, so it is tested: matching, recall, citations, the gate."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run_eval  # noqa: E402


def ref(source: str, section: str, page: int | None = 1, score: float = 0.8) -> dict:
    return {"chunk_id": f"{source}-{section}", "source": source, "section": section,
            "page": page, "score": score}


def row(qid: str, qtype: str = "ordinary", relevant: list[dict] | None = None,
        retrieved: list[dict] | None = None, answered: bool = True, must_abstain: bool = False,
        citations: list[dict] | None = None, answer: str = "", expect: str | None = None) -> dict:
    return {"id": qid, "type": qtype, "must_abstain": must_abstain, "relevant": relevant or [],
            "expect": expect, "seconds": 0.1,
            "response": {"retrieved": retrieved or [], "answered_from_context": answered,
                         "citations": citations or [], "answer": answer}}


@pytest.mark.parametrize(("wanted", "found", "expected"), [
    ("2. Academic warning", "2. Academic warning", True),
    ("2. academic  WARNING", "2. Academic warning", True),
    ("5.4", "5.4 Academic Warning", True),
    ("5.4", "5.4.1 Scope", True),
    ("5.4", "5.41 Fees", False),
    ("1.2", "1.21 Attendance", False),
    ("5.4", "5.3 Probation", False),
    ("5.4", "5", False),
])
def test_section_matching_rule(wanted: str, found: str, expected: bool) -> None:
    assert run_eval.section_matches(wanted, found) is expected


def test_a_relevant_item_may_name_a_page_instead_of_or_as_well_as_a_section() -> None:
    passage = ref("rules.pdf", "5 Standing", page=12)
    assert run_eval.matches({"source": "rules.pdf", "page": 12}, passage)
    assert run_eval.matches({"source": "rules.pdf", "pages": [11, 12]}, passage)
    assert not run_eval.matches({"source": "rules.pdf", "page": 13}, passage)
    assert not run_eval.matches({"source": "rules.pdf", "section": "5.4", "page": 12}, passage)
    assert run_eval.matches({"source": "rules.pdf", "section": "5", "page": 12}, passage)
    assert not run_eval.matches({"source": "other.pdf", "page": 12}, passage)


def test_recall_counts_relevant_items_found_in_the_top_k() -> None:
    relevant = [{"source": "a.pdf", "section": "1"}, {"source": "b.pdf", "section": "2"}]
    retrieved = [ref("a.pdf", "1 Intro"), ref("x.pdf", "9"), ref("b.pdf", "2 Rules")]
    assert run_eval.recall_at_k(relevant, retrieved, 3) == 1.0
    assert run_eval.recall_at_k(relevant, retrieved, 2) == 0.5
    assert run_eval.recall_at_k(relevant, retrieved, 1) == 0.5
    assert run_eval.recall_at_k(relevant, [], 5) == 0.0


def test_a_question_with_nothing_relevant_has_no_recall() -> None:
    assert run_eval.recall_at_k([], [ref("a.pdf", "1")], 5) is None


def test_citation_validity_checks_citations_against_what_was_retrieved() -> None:
    response = {"retrieved": [ref("a.pdf", "1. Attendance")],
                "citations": [{"source": "a.pdf", "section": "1. attendance"},
                              {"source": "a.pdf", "section": "9. Invented"}]}
    assert run_eval.citation_validity(response) == 0.5
    assert run_eval.citation_validity({"retrieved": [], "citations": []}) is None


def test_summary_reports_recall_by_type_and_pooled_citation_validity() -> None:
    hit = ref("a.pdf", "1 A")
    rows = [
        row("q1", "ordinary", [{"source": "a.pdf", "section": "1"}], [hit],
            citations=[{"source": "a.pdf", "section": "1 A"}], answer="It is 80 percent.",
            expect="80"),
        row("q2", "exact", [{"source": "a.pdf", "section": "7"}], [hit]),
        row("q3", "abstain", must_abstain=True, answered=False, retrieved=[hit]),
    ]
    result = run_eval.summarise(rows)
    assert result["recall_at_5"] == 0.5
    assert result["recall_at_5_by_type"] == {"abstain": None, "exact": 0.0, "ordinary": 1.0}
    assert (result["citation_validity"], result["citations_checked"]) == (1.0, 1)
    assert result["abstention_correctness"] == 1.0 and result["abstention_failures"] == []
    assert result["expected_text_found"] == 1.0
    assert result["per_question"][2]["top_score"] == 0.8


def test_an_answered_must_abstain_question_is_reported_by_id() -> None:
    rows = [row("a1", must_abstain=True, answered=False),
            row("a2", must_abstain=True, answered=True)]
    result = run_eval.summarise(rows)
    assert result["abstention_correctness"] == 0.5
    assert result["abstention_failures"] == ["a2"]


GOOD: dict[str, Any] = {"recall_at_5": 0.8, "citation_validity": 1.0,
                        "abstention_correctness": 1.0, "abstention_failures": []}


def test_the_gate_passes_when_nothing_regressed() -> None:
    assert run_eval.gate(GOOD, {"recall_at_5": 0.8}) == []
    assert run_eval.gate(GOOD, None) == []


def test_exactly_five_points_below_the_baseline_still_passes_six_fails() -> None:
    baseline = {"recall_at_5": 0.80}
    assert run_eval.gate({**GOOD, "recall_at_5": 0.75}, baseline) == []
    failures = run_eval.gate({**GOOD, "recall_at_5": 0.74}, baseline)
    assert len(failures) == 1 and "below the baseline" in failures[0]


def test_one_answered_must_abstain_question_fails_the_gate() -> None:
    failures = run_eval.gate({**GOOD, "abstention_correctness": 0.5,
                              "abstention_failures": ["f05"]}, None)
    assert failures and "f05" in failures[0]


def test_citation_validity_below_95_percent_fails_the_gate() -> None:
    assert run_eval.gate({**GOOD, "citation_validity": 0.94}, None)
    assert run_eval.gate({**GOOD, "citation_validity": 0.95}, None) == []


def test_missing_recall_is_a_failure_not_a_pass() -> None:
    assert run_eval.gate({**GOOD, "recall_at_5": None}, None)


def test_main_writes_results_and_the_exit_code_follows_the_gate(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    golden = tmp_path / "golden.yaml"
    golden.write_text(
        "questions:\n"
        "  - id: g1\n"
        "    type: ordinary\n"
        "    question: What is the rule?\n"
        "    expect: '80'\n"
        "    relevant:\n"
        "      - {source: a.pdf, section: '1'}\n"
        "  - id: g2\n"
        "    type: abstain\n"
        "    question: Hostel rules?\n"
        "    must_abstain: true\n",
        encoding="utf-8")
    answers = {
        "What is the rule?": {"answer": "80 percent", "answered_from_context": True,
                              "citations": [{"source": "a.pdf", "section": "1 A"}],
                              "retrieved": [ref("a.pdf", "1 A")]},
        "Hostel rules?": {"answer": "no", "answered_from_context": False, "citations": [],
                          "retrieved": []},
    }
    monkeypatch.setattr(run_eval, "ask", lambda client, api, question: answers[question])
    out, baseline = tmp_path / "results.json", tmp_path / "baseline.json"
    monkeypatch.setattr(sys, "argv", ["run_eval", "--api", "http://x", "--golden", str(golden),
                                      "--out", str(out), "--baseline", str(baseline),
                                      "--update-baseline"])
    assert run_eval.main() == 0
    assert json.loads(out.read_text())["recall_at_5"] == 1.0
    assert json.loads(baseline.read_text())["questions"] == 2

    answers["Hostel rules?"]["answered_from_context"] = True      # now it hallucinates
    monkeypatch.setattr(sys, "argv", ["run_eval", "--api", "http://x", "--golden", str(golden),
                                      "--out", str(out), "--baseline", str(baseline)])
    assert run_eval.main() == 1