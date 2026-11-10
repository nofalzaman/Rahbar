#!/usr/bin/env python3
"""Score a running RAHBAR against a golden set, and gate CI on the result (section 5).

    python eval/run_eval.py --api http://<ingress>                 # your corpus
    python eval/run_eval.py --api ... --golden eval/fixtures/golden.fixture.yaml
    python eval/run_eval.py --api ... --update-baseline            # after a deliberate improvement

Exit code 0 when every gate passes, 1 when any fails. CI relies on that exit code.

recall@k compares the golden `relevant` items with the `retrieved` list of each response;
the gate compares the results with the committed baseline (sections 5.2 to 5.4).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx
import yaml

HERE = Path(__file__).resolve().parent

# The gate from section 5.4. Change these only with a reason written in docs/PIPELINE.md.
MAX_RECALL5_DROP = 0.05        # recall@5 may fall at most 5 points below the baseline
MIN_CITATION_VALIDITY = 0.95   # at least 95% of citations must match retrieved passages
REQUIRED_ABSTENTION = 1.0      # every must-abstain question must be declined


def load_golden(path: Path) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    questions = data.get("questions") or []
    if not questions:
        sys.exit(f"no questions in {path}")
    return questions


def ask(client: httpx.Client, api: str, question: str) -> dict:
    """POST one question and return the AskResponse as a dict (see api/app/schemas.py)."""
    response = client.post(f"{api.rstrip('/')}/api/ask", json={"question": question})
    response.raise_for_status()
    return response.json()


def _norm(text: object) -> str:
    return " ".join(str(text).lower().split())


def section_matches(wanted: str, found: str) -> bool:
    """A retrieved section matches a golden one when they are equal, or when the golden
    one is a prefix that ends at a boundary: "5.4" matches "5.4 Academic Warning" and
    "5.4.1 Scope" but not "5.41 Fees" or "1.21" inside "1.2". Case and spacing are ignored."""
    w, f = _norm(wanted), _norm(found)
    return f == w or (f.startswith(w) and f[len(w)] in " .")


def matches(item: dict, ref: dict) -> bool:
    """A golden `relevant` item names a source and a `section`, a `page` (or a list of
    `pages`), or both. Every key it names must match the retrieved passage."""
    if ref.get("source") != item.get("source"):
        return False
    if "section" in item and not section_matches(str(item["section"]), str(ref.get("section"))):
        return False
    pages = item.get("pages", item.get("page"))
    if pages is None:
        return True
    return ref.get("page") in (pages if isinstance(pages, list) else [pages])


def recall_at_k(relevant: list[dict], retrieved: list[dict], k: int) -> float | None:
    """Fraction of the relevant (source, section) pairs found in the top k retrieved.
    Return None when the question has no relevant passages (must-abstain questions)."""
    if not relevant:
        return None
    top = retrieved[:k]
    found = sum(1 for item in relevant if any(matches(item, ref) for ref in top))
    return found / len(relevant)


def citation_counts(response: dict) -> tuple[int, int]:
    """(citations that match a retrieved passage, all citations) for one response."""
    retrieved = {(r["source"], _norm(r["section"])) for r in response.get("retrieved", [])}
    citations = response.get("citations", [])
    valid = sum(1 for c in citations if (c["source"], _norm(c["section"])) in retrieved)
    return valid, len(citations)


def citation_validity(response: dict) -> float | None:
    """Fraction of the response's citations that match a passage in response['retrieved'].
    Return None when there are no citations."""
    valid, total = citation_counts(response)
    return valid / total if total else None


def _mean(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return round(sum(present) / len(present), 4) if present else None


def summarise(rows: list[dict]) -> dict:
    """Overall recall@3, recall@5, citation validity and abstention correctness, plus
    recall@5 broken down by question type. This dict becomes results.json."""
    per_question = []
    for row in rows:
        response = row["response"]
        refs = response.get("retrieved", [])
        expect = row.get("expect")
        per_question.append({
            "id": row["id"], "type": row["type"], "must_abstain": row["must_abstain"],
            "recall_at_3": recall_at_k(row["relevant"], refs, 3),
            "recall_at_5": recall_at_k(row["relevant"], refs, 5),
            "answered_from_context": response.get("answered_from_context"),
            "citation_validity": citation_validity(response),
            "expect_found": (None if not expect or row["must_abstain"]
                             else _norm(expect) in _norm(response.get("answer", ""))),
            "top_score": refs[0]["score"] if refs else None,
            "answer": response.get("answer"),
            "citations": [f"{c['source']} | {c['section']}" for c in response.get("citations", [])],
            "retrieved": [f"{r['source']} | {r['section']} | p.{r.get('page')} | {r['score']}"
                          for r in refs],
        })
    types = sorted({q["type"] for q in per_question})
    valid = total = 0
    for row in rows:
        v, t = citation_counts(row["response"])
        valid, total = valid + v, total + t
    abstain = [q for q in per_question if q["must_abstain"]]
    expects = [q for q in per_question if q["expect_found"] is not None]
    return {
        "recall_at_3": _mean([q["recall_at_3"] for q in per_question]),
        "recall_at_5": _mean([q["recall_at_5"] for q in per_question]),
        "recall_at_3_by_type": {t: _mean([q["recall_at_3"] for q in per_question
                                          if q["type"] == t]) for t in types},
        "recall_at_5_by_type": {t: _mean([q["recall_at_5"] for q in per_question
                                          if q["type"] == t]) for t in types},
        "citation_validity": round(valid / total, 4) if total else None,
        "citations_checked": total,
        "abstention_correctness": (
            round(sum(1 for q in abstain if not q["answered_from_context"]) / len(abstain), 4)
            if abstain else None),
        "abstention_failures": [q["id"] for q in abstain if q["answered_from_context"]],
        "expected_text_found": (
            round(sum(1 for q in expects if q["expect_found"]) / len(expects), 4)
            if expects else None),
        "expected_text_missing": [q["id"] for q in expects if not q["expect_found"]],
        "per_question": per_question,
    }


def gate(results: dict, baseline: dict | None) -> list[str]:
    """Return one message per failed gate (section 5.4); an empty list means pass."""
    failures = []
    abstention = results.get("abstention_correctness")
    if abstention is not None and abstention < REQUIRED_ABSTENTION:
        failures.append(
            f"must-abstain questions answered from context: {results['abstention_failures']}")
    validity = results.get("citation_validity")
    if validity is not None and validity < MIN_CITATION_VALIDITY:
        failures.append(f"citation validity {validity:.1%} is below {MIN_CITATION_VALIDITY:.0%}")
    recall = results.get("recall_at_5")
    if recall is None:
        failures.append("recall@5 could not be computed: no question has relevant passages")
    elif baseline and baseline.get("recall_at_5") is not None:
        drop = round(baseline["recall_at_5"] - recall, 4)
        if drop > MAX_RECALL5_DROP:
            failures.append(f"recall@5 {recall:.1%} is {drop:.1%} below the baseline "
                            f"{baseline['recall_at_5']:.1%} (allowed: {MAX_RECALL5_DROP:.0%})")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate RAHBAR against a golden set.")
    parser.add_argument("--api", required=True, help="base URL, e.g. http://192.168.49.2")
    parser.add_argument("--host", help="Host header, when your Ingress rule names a host")
    parser.add_argument("--golden", type=Path, default=HERE / "golden.yaml")
    parser.add_argument("--baseline", type=Path, default=HERE / "baseline.json")
    parser.add_argument("--out", type=Path, default=HERE / "results.json")
    parser.add_argument("--update-baseline", action="store_true",
                        help="write these results as the new baseline")
    args = parser.parse_args()

    questions = load_golden(args.golden)
    rows = []
    headers = {"Host": args.host} if args.host else {}
    with httpx.Client(timeout=120.0, headers=headers) as client:
        for q in questions:
            started = time.perf_counter()
            response = ask(client, args.api, q["question"])
            rows.append({
                "id": q["id"], "type": q.get("type", "ordinary"),
                "must_abstain": bool(q.get("must_abstain", False)),
                "relevant": q.get("relevant") or [],
                "expect": q.get("expect"),
                "response": response,
                "seconds": round(time.perf_counter() - started, 2),
            })
            print(f"  {q['id']:<5} {rows[-1]['seconds']:>6.2f}s  {q['question'][:60]}")

    results = summarise(rows)
    baseline = json.loads(args.baseline.read_text()) if args.baseline.exists() else None
    failures = gate(results, baseline)

    results["golden"] = str(args.golden)
    results["questions"] = len(rows)
    args.out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nresults written to {args.out}")
    if args.update_baseline:
        args.baseline.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"baseline updated: {args.baseline}")

    if failures:
        print("\nGATE FAILED")
        for message in failures:
            print(f"  - {message}")
        return 1
    print("\ngate passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())