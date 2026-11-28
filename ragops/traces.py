"""Rebuild actual prompts and summarize a bounded UTC trace window."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    v = sorted(values)
    return v[min(int((len(v)-1)*q), len(v)-1)]


def summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    stages = {k for r in rows for k in r.get('latency_ms', {})}
    return {'queries': n, 'abstention_rate': sum(not r.get('answered_from_context', False) for r in rows)/max(n, 1),
        'cache_hit_rate': sum(r.get('cache') == 'hit' for r in rows)/max(n, 1),
        'injection_attempts_flagged': sum(a.get('action') == 'exclude_retrieved_instruction'
            for r in rows for a in r.get('guardrail_actions', []) if isinstance(a, dict)),
        'top1_similarity': [r['retrieved'][0]['score'] for r in rows if r.get('retrieved')],
        'p95_stage_ms': {k: percentile([r['latency_ms'][k] for r in rows if k in r.get('latency_ms', {})], .95)
                         for k in stages}}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('log', type=Path)
    p.add_argument('--trace-id')
    p.add_argument('--since', default='1970-01-01T00:00:00+00:00')
    p.add_argument('--until', default=datetime.now(timezone.utc).isoformat())
    args = p.parse_args()
    rows = []
    for line in args.log.read_text(encoding='utf-8').splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get('event') == 'ragops_trace' and args.since <= row['timestamp'] <= args.until:
            rows.append(row)
    if args.trace_id:
        row = next((r for r in rows if r['trace_id'] == args.trace_id), None)
        if row is None:
            raise SystemExit('trace id not found in window')
        if row.get('cache_source_trace'):
            source = next((r for r in rows if r['trace_id'] == row['cache_source_trace']), None)
            if source is None:
                raise SystemExit('cached answer source trace is outside this log/window')
            row = source
        print(json.dumps({'trace_id': row['trace_id'], 'context': row['context'],
                          'generation_attempts': row['generation_attempts'],
                          'prompt_hash': row['prompt_hash']}, indent=2))
    else:
        print(json.dumps(summary(rows), indent=2))


if __name__ == '__main__':
    main()
