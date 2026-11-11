# Failure analysis

Experiments ran on 11 November 2026 against real Chroma and nomic embeddings, with
separate calibration collections and temporary API processes. The live corpus was not
replaced by fixture data. B/C/E use the stub to isolate retrieval; F uses llama3.2:3b.
Every API process was stopped after its run; the shipped cluster retains top-k=5,
temperature=0.2, floor=0.35 and the normal source filter.

## Stage B · Chunking
- **What we broke:** 100-word chunks with zero overlap instead of 700/100. We retained
  the existing section-aware algorithm; this is the phase checklist's small-chunk break,
  not a full fixed-size replacement.
- **Symptom:** 1,206 chunks instead of 594; word amplification 1.0405x instead of 1.0640x.
  Recall@5 stayed at 0.8000; recall@3 rose from 0.7333 to 0.8000. The predicted recall
  collapse did **not** happen in this run. More chunks and less shared context were the
  measured effect. See `eval/runs/chunk-100-0.json` and `chunk-measurements.json`.
- **Diagnosis, as if we had not caused it:** inspect the stored chunk settings and the
  per-question retrieved sections, then compare counts and recall using the same labels.
  A small golden set can hide losses; unchanged aggregate recall is not evidence that
  every long definition stayed intact.
- **Remedy:** restore the measured 700/100 choice, reindex, and compare the chunk count
  and amplification with the indexer log. Do not attribute this change to the LLM.

## Stage C · Retrieval
- **What we broke:** top-k=1 while preserving the model and corpus.
- **Symptom:** recall@5 fell from 0.8000 to 0.6667 (13.33 percentage points), even though
  the evaluator still reports recall@5: the API supplied only one passage per request.
  `eval/runs/break-retrieval-top1.json` records the responses. Existing embedding-pin
  evidence also shows a separate retrieval guardrail: `pin-mismatch-log.txt` names the
  index model `nomic-embed-text` and the pod model `all-minilm`.
- **Diagnosis, as if we had not caused it:** inspect the `answered` log's `top_k`, scores
  and chunk IDs; distinguish truncated retrieval from a missing or incompatible index.
  Inspect readiness before blaming generation.
- **Remedy:** restore top-k=5. For an actual model change, rebuild the index with the same
  pin as the API; restarting the API alone correctly leaves the replacement unready.

## Stage E · Source
- **What we broke:** removed the superseded filter in the temporary API's Chroma query.
- **Symptom:** the current-withdrawal question q10 retrieved three superseded 2023
  passages among its five references. q01 and q02 each retrieved two. Aggregate recall@5
  remained 0.8000, so recall alone missed the source-contamination defect.
  See `eval/runs/break-source.json`, whose raw references include `superseded` flags.
  The checklist's additional current-course-repeat query did not return a superseded
  passage; we do not claim that it did.
- **Diagnosis, as if we had not caused it:** inspect the document year/status of each
  retrieved and cited passage and compare it with the user's intended version. An
  authentic citation can still be to a repealed policy. Check the metadata filter first.
- **Remedy:** restore filtering before the query. Current questions exclude superseded
  documents; explicit old-policy questions search them. A date in application statistics
  no longer incorrectly restricts the search to the old policy.

## Stage F · Generation
- **What we broke:** raised temperature from 0.2 to 1.2, with the same collection and
  retrieval configuration, using the real Ollama provider and no cache.
- **Symptom:** 9/17 answer strings changed between the two full runs, while
  recall@5 remained 0.8000 and both abstention/citation gates passed. Five repeated q01
  requests at 1.2 all returned the same safe fallback: `rahbar_fallbacks_total 5.0` and
  `rahbar_invalid_citations_total 10.0`. There was one distinct displayed answer, not
  five different answers. The invalid model citations were dropped before display.
  Evidence: `break-generation-high-temperature.json`, `generation-repeat.json`, and
  `docs/evidence/high-temperature-metrics.txt`.
- **Diagnosis, as if we had not caused it:** compare retrieved IDs/scores first. When
  these stay fixed, inspect generation failures, invalid-citation counters and fallback
  counts. Passing citation validity can coexist with frequent fallbacks because invalid
  answers are withheld.
- **Remedy:** restore 0.2, keep schema validation, retry once, and return the safe
  fallback after repeated invalid output. Low temperature itself does not guarantee
  correctness; the low-temperature run also has failures.

Only stage F is the model's fault, so check A to E first. The four experiments do not
show that the pipeline is flawless; they show which evidence localizes each failure.
