"""Assignment 03 artifact audit; distinguish technical evidence from human requirements."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pypdf import PdfReader

from eval.ragops_suite import load_golden
from ragops.gate import evaluate


def main() -> None:
    checks = []
    def check(item: str, passed: bool, detail: str, human: bool = False) -> None:
        checks.append({'item': item, 'status': 'PASS' if passed else 'NEEDS HUMAN' if human else 'FAIL', 'detail': detail})
    def read(path: str) -> dict:
        return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    golden = load_golden(Path('eval/golden.jsonl'))
    initial = load_golden(Path('eval/golden.initial.jsonl'))
    answerable = [q for q in golden if not q.get('must_abstain')]
    check('B golden counts', len(golden) >= 25 and len(answerable) >= 15
          and len(golden)-len(answerable) >= 5 and sum(bool(q.get('hard')) for q in golden) >= 5,
          f'{len(golden)} total / {len(answerable)} answerable / {len(golden)-len(answerable)} unanswerable')
    written = sum(q['origin'] == 'human' for q in golden)
    reviewed = sum(q['origin'] == 'synthetic' and q.get('reviewed_by') not in (None, '', 'FILL') for q in golden)
    check('B human-written questions', written >= 8, f'{written}/8 actually labelled human', True)
    check('B hand-reviewed synthetic questions', reviewed >= 8, f'{reviewed}/8 recorded', True)
    verification = [read(str(p)) for p in Path('eval/results/verification').glob('*.json')]
    check('A four checks and counts', bool(verification) and all(
        all(set(d['checks']) == {'quality', 'completeness', 'recency', 'uniqueness'} for d in r['documents'])
        and 'count_by_document' in r for r in verification), f'{len(verification)} actual run reports')
    check('A unchanged zero chunks', any(r['chunks_embedded'] == 0 for r in verification), 'Separate fingerprint counts remain visible')
    for label, filename in [('baseline', 'baseline.json'), ('candidate', 'candidate.json'), ('bad', 'bad-candidate.json')]:
        r = read('eval/results/'+filename)
        check('B suite '+label, r['module']['pair_count_each'] >= 15 and all(k in r for k in ('run1', 'run2', 'stochasticity_delta')),
              r['run_id'])
        digest = hashlib.sha256(Path('eval/golden.initial.jsonl').read_bytes()).hexdigest()
        check('B controlled golden identity '+label, r['golden_sha256'] == digest, 'Historical controlled comparison retains its original 25-question version')
    baseline, candidate, bad = [read('eval/results/'+f) for f in ('baseline.json', 'candidate.json', 'bad-candidate.json')]
    rules = read('eval/thresholds.json')
    check('C passing candidate', evaluate(baseline, candidate, rules)['pass'], 'Actual saved measurements under committed thresholds')
    check('C failing candidate', not evaluate(baseline, bad, rules)['pass'], 'Bad candidate must be rejected')
    rows = [json.loads(s) for s in Path('traces/cluster.jsonl').read_text(encoding='utf-8-sig').splitlines() if s.strip()]
    required = {'trace_id', 'timestamp', 'user_query', 'embedding_model', 'embedding_version', 'collection', 'retrieved',
                'filters', 'reranked_order', 'context', 'generation_attempts', 'prompt_hash', 'model', 'parameters',
                'response', 'citations', 'guardrail_actions', 'latency_ms', 'cache'}
    check('D complete successful traces', bool(rows) and all(required <= r.keys() for r in rows if r.get('status_code') == 200),
          f'{len(rows)} saved main-cluster trace records')
    guardrails = read('eval/results/guardrail-cache-checks.json')
    check('D planted injection', bool(guardrails[1]['guardrail_actions']), 'Actual retrieved injected chunk excluded')
    check('D cache provenance', guardrails[-1]['cached'] and bool(guardrails[-1]['source_trace']), 'Actual Redis cache hit references original trace')
    before, after = [read('eval/results/coverage-'+p+'.json') for p in ('before', 'after')]
    check('E coverage improvement', after['coverage'] > before['coverage'] and len(before['queries']) >= 40,
          f'{before["coverage"]:.3f} -> {after["coverage"]:.3f}')
    check('E six extra active questions', len(golden) >= len(initial)+6, 'Expanded questions are active in eval/golden.jsonl')
    active = read('eval/results/reviewed-20261128/current.json')
    reviewed_summary = read('eval/results/reviewed-20261128/summary.json')
    reviewed_baseline = read('eval/results/reviewed-20261128/'+reviewed_summary['baseline'])
    check('B reviewed suite', active['human_written'] >= 8 and active['human_reviewed_synthetic'] >= 8
          and all(k in active for k in ('run1', 'run2', 'noise')),
          'Updated 39-question suite completed twice plus typo noise')
    check('C reviewed candidate', reviewed_baseline['golden_sha256'] == active['golden_sha256']
          and evaluate(reviewed_baseline, active, rules)['pass'], 'Same reviewed input and unchanged thresholds')
    snapshot = Path('eval/results/reviewed-20261128/golden-input.jsonl')
    check('E active suite identity', active['golden_sha256'] == hashlib.sha256(snapshot.read_bytes()).hexdigest()
          and load_golden(snapshot) == golden, 'Exact evaluated input snapshot hash and active question content agree; Git newline conversion does not change questions')
    rollback = read('eval/results/rollback-proof.json')
    check('F versioned rollback', rollback['collection'] == 'rahbar-a3-candidate' and len(rollback['embedding_version']) == 64,
          rollback['trace_id'])
    check('F ConfigMap flip', not read('eval/results/gate-configmap-tight.json')['pass']
          and read('eval/results/gate-configmap-normal.json')['pass'], 'Same eval image digest; stored measurements are re-gated')
    check('F fresh-cluster smoke', Path('docs/evidence/ragops/fresh-smoke.txt').exists(), 'Readiness and actual sourced answer on separate fresh profile')
    fresh = [read(str(p)) for p in Path('eval/results/fresh').glob('*.json')]
    check('F fresh-cluster suite', any(isinstance(r, dict) and r.get('run1') for r in fresh)
          and any(isinstance(r, dict) and r.get('pass') is True for r in fresh), 'Fresh namespace completed ingestion, candidate indexing and full evaluation')
    pages = PdfReader('docs/report/RAHBAR_Assignment03_Report.pdf').pages
    main_pages = next((i for i, p in enumerate(pages) if 'Appendix /' in p.extract_text() or 'A1 verification' in p.extract_text()), len(pages))
    check('G report main-page limit', main_pages <= 8, f'{main_pages} main pages; {len(pages)} total including appendix')
    screenshots = [p for p in Path('docs/report/screenshots').glob('*') if p.suffix.lower() in ('.png', '.jpg', '.jpeg')]
    check('G manual screenshot appendix', any(p.stem == 'F1-cluster' for p in screenshots) and len(screenshots) >= 17, f'{len(screenshots)} supplied images; combined coverage image accepted, cluster overview F1 still missing', True)
    human = read('docs/report/HUMAN-REVIEW.json')
    owners = {'nofalzaman', 'itsmeaounmuhammad-boop'}
    human_complete = (owners <= set(human['reviewed_by']) and bool(human['reviewed_at'])
                      and owners <= set(human['demo_attended_by']) and bool(human['demo_at']))
    check('G actual student review/demo', human_complete, 'FILL: record actual review/demo in HUMAN-REVIEW.json', True)
    result = {'technical_failures': sum(c['status'] == 'FAIL' for c in checks),
              'needs_human': [c for c in checks if c['status'] == 'NEEDS HUMAN'], 'checks': checks}
    Path('eval/results/assignment03-audit.json').write_text(json.dumps(result, indent=2))
    for c in checks:
        print(f"{c['status']}: {c['item']} - {c['detail']}")
    print(json.dumps({'technical_failures': result['technical_failures'], 'human_items': len(result['needs_human'])}))
    raise SystemExit(1 if result['technical_failures'] or result['needs_human'] else 0)


if __name__ == '__main__':
    main()
