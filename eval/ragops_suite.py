"""Three-level measured evaluation against a running Kubernetes API and Ollama."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x*y for x, y in zip(a, b)) / max(
        math.sqrt(sum(x*x for x in a)*sum(x*x for x in b)), 1e-15)


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = (len(ordered)-1)*q
    lo = int(index)
    return ordered[lo] + (ordered[min(lo+1, len(ordered)-1)]-ordered[lo])*(index-lo)


def load_golden(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    if len({q['id'] for q in rows}) != len(rows):
        raise ValueError('golden question identifiers must be unique')
    for row in rows:
        if row['origin'] not in ('human', 'synthetic'):
            raise ValueError('origin must be human or synthetic')
        if not row.get('must_abstain') and not all('page' in r for r in row['relevant']):
            raise ValueError('answerable questions require ground-truth pages')
    return rows


def retrieval_metrics(relevant: list[dict[str, Any]], refs: list[dict[str, Any]]) -> dict[str, float]:
    def matches(wanted: dict[str, Any], found: dict[str, Any]) -> bool:
        return wanted['source'] == found['source'] and wanted['page'] == found.get('page')
    hits = [any(matches(r, ref) for r in relevant) for ref in refs[:5]]
    # Multiple chunks from the same page count as one relevant retrieval, not repeated gain.
    seen = set()
    gains = []
    for hit, ref in zip(hits, refs):
        key = (ref['source'], ref.get('page'))
        gains.append(int(hit and key not in seen))
        seen.add(key)
    def recall(k: int) -> float:
        return sum(any(matches(r, f) for f in refs[:k]) for r in relevant)/len(relevant)
    dcg = sum(g/math.log2(i+2) for i, g in enumerate(gains))
    ideal = sum(1/math.log2(i+2) for i in range(min(len(relevant), 5)))
    return {'recall@3': recall(3), 'recall@5': recall(5),
            'mrr': next((1/(i+1) for i, hit in enumerate(hits) if hit), 0),
            'ndcg@5': dcg/ideal if ideal else 0}


def embed(client: httpx.Client, url: str, model: str, texts: list[str]) -> list[list[float]]:
    response = client.post(url.rstrip('/')+'/api/embed', json={'model': model, 'input': texts})
    response.raise_for_status()
    return response.json()['embeddings']


def module_level(client: httpx.Client, url: str, model: str,
                 pairs: list[dict[str, str]]) -> dict[str, Any]:
    if len(pairs) < 15:
        raise ValueError('need at least 15 paraphrase and unrelated pairs')
    texts = [p[k] for p in pairs for k in ('a', 'paraphrase', 'unrelated')]
    started = time.perf_counter()
    vectors = embed(client, url, model, ['search_query: '+t for t in texts])
    seconds = time.perf_counter()-started
    repeat = embed(client, url, model, ['search_query: '+texts[0]])[0]
    same = [cosine(vectors[i], vectors[i+1]) for i in range(0, len(vectors), 3)]
    different = [cosine(vectors[i], vectors[i+2]) for i in range(0, len(vectors), 3)]
    return {'paraphrase_cosine': statistics.mean(same), 'unrelated_cosine': statistics.mean(different),
            'gap': statistics.mean(same)-statistics.mean(different),
            'embedding_seconds_per_chunk': seconds/len(texts),
            'determinism_max_difference': max(abs(a-b) for a, b in zip(vectors[0], repeat)),
            'pair_count_each': len(pairs), 'paraphrase_scores': same, 'unrelated_scores': different}


def score_answers(rows: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = [retrieval_metrics(r['golden']['relevant'], r['response']['retrieved'])
               for r in rows if r['golden'].get('relevant')]
    result = {k: statistics.mean(m[k] for m in metrics) for k in metrics[0]} if metrics else {}
    unanswerable = [r for r in rows if r['golden'].get('must_abstain')]
    result['abstention_correctness'] = (statistics.mean(not r['response']['answered_from_context']
        and not r['response']['citations'] for r in unanswerable) if unanswerable else None)
    citations = [(c, r) for r in rows for c in r['response']['citations']]
    result['citation_validity'] = (sum(any(c['source'] == ref['source']
        and c.get('page') == ref.get('page') and c['section'] == ref['section']
        for ref in r['response']['retrieved']) for c, r in citations)/len(citations) if citations else None)
    # Explicit deterministic proxy, not an LLM judge or a claim of semantic factual accuracy.
    supported = [r for r in rows if r['response']['answered_from_context']]
    result['faithfulness_proxy'] = (statistics.mean(r['token_support'] for r in supported) if supported else None)
    result['latency_p50_seconds'] = percentile([r['seconds'] for r in rows], .5)
    result['latency_p95_seconds'] = percentile([r['seconds'] for r in rows], .95)
    result['answered_count'] = len(supported)
    return result


def run(client: httpx.Client, args: argparse.Namespace, questions: list[dict[str, Any]],
        noise: bool = False) -> dict[str, Any]:
    import re
    rows = []
    for q in questions:
        question = q['question']
        if noise:
            question = question.replace('student', 'studnet').replace('academic', 'acadmeic')
            if question == q['question']:
                question = question[:-1]+' plese?'
        trace_id = hashlib.sha256(f'{args.run_id}:{noise}:{q["id"]}'.encode()).hexdigest()[:32]
        started = time.perf_counter()
        response = client.post(args.api.rstrip('/')+'/api/ask', json={'question': question},
                               headers={'X-RAGOps-Eval': '1', 'X-Request-ID': trace_id})
        response.raise_for_status()
        body = response.json()
        seconds = time.perf_counter()-started
        trace = client.get(args.api.rstrip('/')+'/api/traces/'+trace_id)
        trace.raise_for_status()
        record = trace.json()
        context = ' '.join(p['text'] for p in record.get('context', []))
        words = set(re.findall(r'\b\w+\b', body['answer'].lower()))
        evidence = set(re.findall(r'\b\w+\b', context.lower()))
        token_support = len(words & evidence)/max(len(words), 1)
        rows.append({'golden': q, 'response': body, 'seconds': seconds,
                     'trace_id': trace_id, 'token_support': token_support})
        print(json.dumps({'question': q['id'], 'noise': noise, 'seconds': seconds,
                          'answered': body['answered_from_context']}), flush=True)
    return {'metrics': score_answers(rows), 'answers': rows}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--api', default='http://api:8000')
    parser.add_argument('--ollama', default='http://host.minikube.internal:11434')
    parser.add_argument('--model', default='nomic-embed-text')
    parser.add_argument('--golden', type=Path, default=Path('eval/golden.jsonl'))
    parser.add_argument('--pairs', type=Path, default=Path('eval/paraphrases.json'))
    parser.add_argument('--output', type=Path, default=Path('eval/results'))
    parser.add_argument('--label', default='baseline')
    parser.add_argument('--gate', type=Path)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--skip-noise', action='store_true')
    args = parser.parse_args()
    args.run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+args.label
    random.seed(42)
    golden = load_golden(args.golden)
    result: dict[str, Any] = {'run_id': args.run_id, 'seed': 42, 'model': args.model,
        'api': args.api, 'label': args.label, 'golden_sha256': hashlib.sha256(args.golden.read_bytes()).hexdigest(),
        'human_written': sum(q['origin'] == 'human' for q in golden),
        'human_reviewed_synthetic': sum(q['origin'] == 'synthetic' and q.get('reviewed_by')
                                      not in (None, '', 'FILL') for q in golden),
        'faithfulness_method': 'answer token overlap with actual context; proxy requiring human interpretation'}
    with httpx.Client(timeout=300) as client:
        result['module'] = module_level(client, args.ollama, args.model,
                                       json.loads(args.pairs.read_text()))
        for repetition in (1, 2):
            args.run_id = result['run_id']+f'-r{repetition}'
            result[f'run{repetition}'] = run(client, args, golden)
        result['stochasticity_delta'] = {k: (result['run2']['metrics'][k]-v)
            for k, v in result['run1']['metrics'].items() if isinstance(v, (int, float))
            and isinstance(result['run2']['metrics'][k], (int, float))}
        if not args.skip_noise:
            result['noise'] = run(client, args, golden, noise=True)
            result['noise_delta'] = {k: result['noise']['metrics'][k]-result['run1']['metrics'][k]
                                    for k in ('recall@3', 'recall@5', 'mrr', 'ndcg@5')}
    args.output.mkdir(parents=True, exist_ok=True)
    path = args.output / (result['run_id']+'.json')
    path.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({'result': str(path), 'module': result['module'],
                      'summary': result['run1']['metrics'], 'delta': result['stochasticity_delta']}), flush=True)
    if args.gate:
        from ragops.gate import evaluate
        baseline = json.loads(args.baseline.read_text()) if args.baseline else result
        verdict = evaluate(baseline, result, json.loads(args.gate.read_text()))
        (args.output/(result['run_id']+'-gate.json')).write_text(json.dumps(verdict, indent=2))
        print(json.dumps(verdict), flush=True)
        raise SystemExit(0 if verdict['pass'] else 1)


if __name__ == '__main__':
    main()
