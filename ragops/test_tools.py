"""Metric edge cases that would otherwise produce a misleading release verdict."""
from __future__ import annotations

from eval.ragops_suite import percentile, retrieval_metrics
from ragops.gate import evaluate
from ragops.traces import summary


def test_duplicate_page_does_not_inflate_ndcg() -> None:
    refs = [{'source': 'a', 'page': 1}]*5
    scores = retrieval_metrics([{'source': 'a', 'page': 1}], refs)
    assert scores == {'recall@3': 1, 'recall@5': 1, 'mrr': 1, 'ndcg@5': 1}
    assert retrieval_metrics([{'source': 'a', 'page': 2}], refs)['mrr'] == 0
    assert percentile([1, 2, 3], .5) == 2


def test_gate_rejects_missing_nan_and_regression() -> None:
    baseline = {'run1': {'metrics': {'recall@5': .8}}}
    rules = {'recall@5': {'max_drop': .02}}
    assert evaluate(baseline, baseline, rules)['pass']
    for value in (None, float('nan'), .7):
        assert not evaluate(baseline, {'run1': {'metrics': {'recall@5': value}}}, rules)['pass']
    assert not evaluate(baseline, baseline, {})['pass']


def test_trace_summary_handles_empty_and_stage_samples() -> None:
    assert summary([])['queries'] == 0
    result = summary([{'latency_ms': {'embed': 5}, 'cache': 'hit',
                       'guardrail_actions': [{'action': 'exclude_retrieved_instruction'},
                                             {'action': 'generation_retry'}],
                       'answered_from_context': True}])
    assert result['cache_hit_rate'] == 1
    assert result['injection_attempts_flagged'] == 1
    assert result['p95_stage_ms']['embed'] == 5
