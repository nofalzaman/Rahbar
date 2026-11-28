# Reviewed question evaluation on 28 November 2026

The student-supplied worksheet adds eight human-authored questions and records eight synthetic reviews. q05 now specifies tuition fee; q06 includes the wider reviewed source pages. Authorship and review are transcribed from the supplied worksheet, not inferred from AI approvals.

Both suites use the same 39 questions and candidate collection, nomic-embed-text, llama3.2:3b, temperature 0, seed 42 and a 512-token generation cap. Baseline top-k is 5; candidate top-k is 3. Each suite runs twice and includes typo noise. Candidate deployment is restored to top-k 3 after the isolated baseline; the live API was never changed.

| Metric | Baseline k5 | Candidate k3 |
| --- | --- | --- |
| recall@3 | 0.657738 | 0.657738 |
| recall@5 | 0.671769 | 0.657738 |
| mrr | 0.657143 | 0.642857 |
| ndcg@5 | 0.632772 | 0.622692 |
| faithfulness_proxy | 0.975529 | 0.964448 |
| citation_validity | 1.000000 | 1.000000 |
| abstention_correctness | 1.000000 | 1.000000 |
| answerable_answer_rate | 0.500000 | 0.607143 |
| latency_p50_seconds | 1.241776 | 1.090543 |
| latency_p95_seconds | 2.282370 | 2.079141 |

Release gate: **PASS** under unchanged thresholds. Coverage: 87.5% on the same 40 live queries. All three Kubernetes Jobs completed. There are 234 persisted request traces. These proxy metrics do not establish full answer correctness.

The exact evaluated input bytes are retained in golden-input.jsonl, with line endings preserved for its recorded SHA-256. The active golden set has identical parsed content; Git may normalize its line endings. Earlier 25- and 31-question experiments remain unchanged.

The final PDF is the exact student-supplied file. Its old measurements are historical and are not substituted for this rerun. It has nine main pages before the screenshot appendix, exceeding the eight-page limit; F1 is missing, and whole-project human review/demo attendance is unconfirmed. These issues remain recorded rather than silently marked complete.
