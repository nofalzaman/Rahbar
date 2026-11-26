"""Measure live-to-golden semantic coverage; fail below a configurable target."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx

from eval.ragops_suite import cosine, embed, load_golden


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--golden', type=Path, default=Path('eval/golden.jsonl'))
    p.add_argument('--live', type=Path, default=Path('eval/live-queries.jsonl'))
    p.add_argument('--ollama', default='http://host.minikube.internal:11434')
    p.add_argument('--model', default='nomic-embed-text')
    p.add_argument('--similarity', type=float, default=.85)
    p.add_argument('--minimum-coverage', type=float, default=.85)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    golden = load_golden(args.golden)
    live = [json.loads(line) for line in args.live.read_text().splitlines() if line.strip()]
    with httpx.Client(timeout=300) as client:
        vectors = embed(client, args.ollama, args.model,
                        ['search_query: '+q['question'] for q in golden+live])
    rows = []
    for q, v in zip(live, vectors[len(golden):]):
        scores = [cosine(v, g) for g in vectors[:len(golden)]]
        best = max(range(len(scores)), key=scores.__getitem__)
        rows.append({**q, 'nearest_golden': golden[best]['id'], 'similarity': scores[best],
                     'covered': scores[best] >= args.similarity})
    coverage = sum(r['covered'] for r in rows)/max(len(rows), 1)
    result = {'coverage': coverage, 'similarity_threshold': args.similarity,
              'minimum_coverage': args.minimum_coverage, 'pass': coverage >= args.minimum_coverage,
              'queries': rows, 'uncovered_by_topic': {topic: [r['question'] for r in rows
              if not r['covered'] and r['topic'] == topic] for topic in {r['topic'] for r in rows}}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['pass'] else 1)


if __name__ == '__main__':
    main()
