# Assignment cross-check and release status

Checked against the 20-page Assignment 02 PDF and the supplied phase 5–7 checklist on
11 November 2026. This is an evidence map, not a claim of full marks.

| PDF requirement | Status | Evidence / remaining action |
| --- | --- | --- |
| 1.3 Grounded answer, absent-topic refusal, pod replacement | Verified locally | Real Ingress evaluation and rollout/pod-replacement evidence. |
| 2 Corpus: 6+ documents, 40+ pages, seven properties | Verified | Eight files, 246 PDF pages; `CORPUS.md`, manifest and eight matching checksums. |
| 2 Public documents kept out of Git | Verified | `corpus/raw/` ignored; URLs/checksums/fetch script committed. Public indexer builds use fictional fixtures. |
| 3.1 Extract, OCR, clean, structure-aware overlap, metadata | Implemented and measured | Indexer tests, per-document Job logs, source/version/page metadata. Table/column/OCR limitations are documented. |
| 3.1 Three chunk settings and token amplification | Verified | `PIPELINE.md`, `eval/runs/chunk-measurements.json`, tokenizer counts in `token-amplification.json`. Chunk sizes are words; token ratio is measured separately. |
| 3.2 Query pipeline and version filtering | Implemented | Real retriever, limited clause-number lexical search, relevance floor, generation/validation; dated-report and instruction-intent regressions fixed. |
| 3.3 Semantic cache: threshold, never-cache, invalidate | Verified | Real cache-pair scores; threshold 0.93; tests of follow-ups/abstentions/fallbacks/new index IDs. |
| 3.4 Schema, retry, fallback, provenance, low temperature | Verified mechanically | Real-model evaluation: citation validity 100%, must-abstain correctness 100%. This does not establish factual correctness of every answer. |
| 3.4 Indexed poisoned chunk test | Verified with real model | `eval/runs/poisoned-document-real-model.json`; planted instruction was retrieved and not followed. Offline prompt/fallback tests are separate. |
| 3.5 Provider interface | Implemented | Ollama-host is shipped; hosted and stub providers remain available. ADR 0004 documents data movement and retention. |
| 4.1 Required Kubernetes objects / namespace | Verified | Base and dev/prod overlays; CI strict manifest validation; local cluster evidence. CronJob now runs real indexing. |
| 4.2 Indexer-only writer / reindex | Verified with limitation | Real Job and CronJob. Temporary-collection delete/rename is not atomic; simultaneous manual Jobs are not locked. ADR 0001 makes this explicit. |
| 4.3 Three probes | Verified | Offline dependency-failure tests and actual cluster readiness. Health checks do not call the model. |
| 4.4 Shared embedding pin and mismatch proof | Verified | ConfigMap + collection metadata + readiness guardrail; `pin-mismatch-*` evidence. |
| 4.5 Resources and HPA denominator | Verified locally | `kubectl-top-*`, known HPA utilization, 427Mi sampled indexer maximum versus 1024Mi limit. Samples are not an instantaneous peak guarantee. |
| 4.6 Rolling update, rollback, 3 endpoints, deleted pod | Verified locally | `rollout-rollback.txt`, endpoint and pod evidence. |
| 4.7 Accounts, non-root, readonly, no tokens, firewall | Verified | Manifests, heuristic Git secret audit, Calico UI→API success and UI→Chroma timeout. Git history pattern audit is not exhaustive. |
| 4.8 JSON logs and metrics | Implemented | Request IDs, retrieval IDs/scores, cache and latency/abstention/fallback/token metrics. High-temperature metrics show invalid citations withheld. |
| 5.1 Golden-set composition | Verified | 17 questions: 8 ordinary, 4 version (including 2 genuinely different withdrawal deadlines), 2 exact, 2 abstain, 1 injection. Source labels were repaired against documents; limits are disclosed. |
| 5.2 Recall@3/@5 overall and by type | Measured | 0.7333 / 0.8000; version-sensitive recall@5 50%, ordinary 87.5%, exact 100%. |
| 5.3 Generation checks | Partly automated | 100% citation validity and abstention correctness. Optional expected-text check misses q09; answerable fallbacks and factual-answer weaknesses remain for human review. |
| 5.4 Baseline and strict CI gate | Implemented | Real baseline/results and separate fixture baseline committed; gate thresholds unchanged. |
| 5.5 Four broken stages | Verified | B/C/E/F actual runs in `FAILURE-ANALYSIS.md`. Fixed 100-token chunks cut recall@5 to 46.67%; the separate structure-aware 100-word run did not. F produced withheld invalid citations and fallbacks. |
| 6 CI lint, coverage, manifests, builds, scans, kind eval | Passed | All ten checks passed on the final feature head (43025296270), dev push (43025582220), and approved main PR (43025747419). |
| 6 Protected main: PR, one review, required CI | Configured | Active ruleset, all ten checks, no bypass; JSON and screenshot in `docs/evidence/`. |
| 6 Failed-gate and repaired-gate proof | Verified; screenshots manual | PR #11 failed on f05, then all checks passed after repair, and it was closed without merging. JSON statuses and both eval artifacts are committed. Signed-in screenshot capture stopped because the browser URL could not be verified; greyed-out merge-button and repaired-check screenshots remain manual. |
| 6 CD: test → SHA-tagged Docker Hub images → kind Ingress | Passed | PR #12 received independent approval and merged as `cad1630b5d42f63cef00b4b229771b2d31c5fcb3`. CD run 43026589471 tested, published all three images, deployed them and passed grounded-answer/refusal Ingress smoke tests. Docker Hub repositories are public and have only that SHA tag. |
| 7 Seven engineering answers with file/line references | Written | `ENGINEERING-NOTES.md` uses the real session issues as requested by the owner, including the roughly 35-minute CI incident. No >1-hour duration was fabricated. |
| 8 Honest AI attribution | Written | `AI-USAGE.md` distinguishes handoff attribution, Codex work and unrecorded human review. |
| 8 No direct main pushes / no real Secret manifest | Verified | Feature/dev PR flow; only a Secret placeholder; no matching high-confidence credential patterns in fetched history. |
| 8 Submission checker | Passed | 164 checks passed, 3 warnings, 0 failures at the recorded run. Warnings include heuristic nonempty-readiness detection and historical commit conventions. |
| 1.3 / 8 README clean-clone reproduction | Verified independently | Fresh clone, fresh Python environment, fresh downloads matching the committed manifest, three source-built images and a separate Calico cluster. Real index: 594 chunks; three API replicas ready; grounded answer and absent-topic refusal through Ingress. Isolated image tags/profile and controller port-forward avoided conflicts with the original cluster. See `clean-clone.txt` and `clean-clone-smoke.json`; the test profile was stopped afterwards. |
| 8 Classroom submission | Human action | Submit repository URL, successful CD URL, Docker Hub SHA-tag pages, and committed baseline/results. No Classroom submission has been made by Codex. |

## Release links

- Implementation PR: https://github.com/nofalzaman/Rahbar/pull/10
- Gate demonstration PR: https://github.com/nofalzaman/Rahbar/pull/11
- First security/startup diagnostic run: https://github.com/nofalzaman/Rahbar/actions/runs/43018709426
- All-green CI: https://github.com/nofalzaman/Rahbar/actions/runs/43022332761
- Deliberately failed gate: https://github.com/nofalzaman/Rahbar/actions/runs/43022353774
- Repaired gate: https://github.com/nofalzaman/Rahbar/actions/runs/43023491547

The supplied documents are project requirements and reference material. Their statements
that some prior work was complete were checked against the files and running system,
rather than treated as evidence that the work had actually been done.

## Final release and submission links

- Approved release PR: https://github.com/nofalzaman/Rahbar/pull/12
- Successful CD: https://github.com/nofalzaman/Rahbar/actions/runs/43026589471
- Docker Hub API: https://hub.docker.com/r/nofalz/rahbar-api/tags
- Docker Hub UI: https://hub.docker.com/r/nofalz/rahbar-ui/tags
- Docker Hub indexer: https://hub.docker.com/r/nofalz/rahbar-indexer/tags
- Release SHA: `cad1630b5d42f63cef00b4b229771b2d31c5fcb3`

Final offline CI totals: 82 API tests (96.56% coverage), 48 indexer tests and 20 eval
tests: **150 passing tests**. All app-image scans passed the fixable HIGH/CRITICAL gate.
`cd-result.json`, `cd-deploy-proof.txt`, `dockerhub-tags.json`, `release-pr.json` and
the CI/CD URL files are the release evidence. The final evidence update is retained
on dev; main contains the approved, successfully deployed release.

Remaining manual actions: the exact signed-in blocked-merge/repaired-check screenshots
could not be captured because computer control could not verify the browser URL.
The failed/repaired runs and blocked-state JSON are preserved. Capture Docker Hub tag
screenshots if image evidence is required, and submit the repository/CD/image links
and the committed `eval/results.json` / `eval/baseline.json` on Classroom. No Classroom
submission is claimed. The owner chose the real session incident for engineering Q7;
its measured duration is reported honestly.
