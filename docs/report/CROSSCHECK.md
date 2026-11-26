# Assignment 03 PDF crosscheck

Crosschecked against all five pages of the supplied Assignment_03.pdf. This is a technical completion/review checklist, not a claim that the submission's human requirements are finished. The report is a **review draft** until those items and screenshots are completed.

## Requirement to implementation and actual evidence

| PDF item | State | Implementation / saved evidence |
| --- | --- | --- |
| Build on RAHBAR; run on Kubernetes | Done | Existing API/Chroma/Redis/UI retained; actual minikube and separate fresh-profile runs. |
| Commits from both members | Done, AI-assisted | Aoun PR #17 and Nofal PR #18; commit identities authorized by both students. AI disclosure distinguishes attribution from human authorship. |
| Read RAGOps paper | Done | arXiv:2506.03401v1 sections 3.2, 4.2, 5.1, 6.2, Tables 1-2 and Figure 3 inform the report; exact version cited. |
| A1 quality, completeness, recency, uniqueness | Done | `indexer/pipeline/ragops.py`; per-document four-check reports under `eval/results/verification/`. |
| Quarantine failing ingested documents | Done | Staged copies are physically moved to persistent quarantine/archive, not indexed; upstream raw originals remain immutable. |
| Exact hashes and embedding near-duplicates | Done | Batch B catches two exact copies and one near-copy; `demo-b.txt`. |
| A2 unchanged embeds zero chunks | Done | `ingest-unchanged.txt`, `demo-unchanged.txt`, final writer repeat; fingerprint embeddings reported separately. |
| Changed document replaces only own chunks | Done | `demo-change.txt`: one chunk embedded, other accepted documents unchanged. |
| Deleted document leaves no orphan chunks | Done | `demo-delete.txt`: lab.md count becomes zero. |
| Archive, exclude and restore superseded version | Done | `demo-a.txt`, `demo-b.txt`, `demo-restore.txt`; archived snapshot restored by an ingestion Job. |
| Batch B >=10 with every planted problem | Done | 12 explicitly synthetic files in `corpus/batch_b`; missing metadata, truncation, duplicates, newer notice and injection. Old notice is seeded by `corpus/batch_a_demo`. |
| Golden >=25 / >=15 answerable / >=5 unanswerable / >=5 hard | Done | `eval/golden.jsonl`: 25 / 20 / 5; source/page labels and hard flags; audit verifies counts. |
| >=8 questions written by group | **NEEDS HUMAN / FILL** | Currently zero human-origin rows. User requested generated drafts; those remain honestly synthetic. Students must write/rewrite eight themselves. |
| >=8 synthetic questions hand-reviewed | **NEEDS HUMAN / FILL** | Fill `reviewed_by` only after real review; `eval/review-questions.md`. |
| B module: 15 pairs each, gap, time, determinism | Done | Every suite has module arrays/counts, mean cosines, timing and repeated-vector maximum difference. |
| B retrieval: recall@3/@5, MRR, nDCG@5 and noise | Done | Baseline/passing-candidate full runs include typo noise and metric deltas; duplicate pages cannot inflate gain. |
| B e2e: faithfulness, abstention, citations, p50/p95 | Done with declared measurement limitation | Faithfulness is an explicit lexical support proxy, not factual accuracy; actual answers retained. No LLM judge or invented hand-judge agreement. |
| B repeat whole suite with fixed seeds | Done | Two repetitions per suite, seed 42, temperature 0, 512-token cap for controlled runs; variation retained. |
| B one suite command and timestamped results | Done | `python -m eval.ragops_suite` / `kubectl apply -f k8s/eval-job.yaml`; actual JSON under `eval/results/`. |
| C one pipeline change and three-level comparison | Done | Bounded top-k 5 vs 3, same model/generation settings; exploratory unbounded runs kept separate. |
| C file thresholds, pass/fail and exit code | Done | `eval/thresholds.json`, `ragops/gate.py`; bounded k=1 fails at recall .75 vs .85. |
| C controlled rollout | Done | `release-pass.txt`, `release-final.txt`, rejection proof and versioned rollback logs. |
| D1 complete per-query JSONL traces | Done | `api/app/ragops.py`; context, prompt attempts/hash, versions, filters/order, outputs, rail actions, times and cache status. Error traces also retain their error response. |
| D2 exact context/prompt reconstruction | Done | `python -m ragops.traces ... --trace-id ...`; `rebuilt-prompt.txt`, `traces/demo-answer.json`. |
| D3 all requested metrics | Done | `/metrics` via actual port-forward; `trace-summary.json` has top-1 distribution, abstention/cache rates, stage p95 and injection exclusions. |
| D4 injected Batch B document tested | Done | `guardrail-cache-checks.json`, `traces/injection-demo.json`; actual injected chunk excluded before generation. |
| D5 root cause from trace only, five report lines | Done | `root-cause-trace-only.txt`; CGPA answer fails because its citation label does not match retrieved tags. |
| E 40 live-style queries / uncovered topics | Done | 28 university + 12 transport/housing/food in `eval/live-queries.jsonl`. |
| E coverage, nearest golden, threshold and grouping | Done | .85 similarity and .85 target; .75 before, .875 after; uncovered topics and nearest IDs saved. |
| E data drift suite after Batch B | Done | `20261126T140316-drift.json`: recall unchanged, MRR .800 -> .775, nDCG .8131 -> .7946. |
| E >=6 added golden cases, re-run coverage | Done | `eval/golden.expanded.jsonl`; six additions from uncovered topics, correct action remains abstention. |
| F1 Deployment, StatefulSet/PVC, Service, persistent lake | Done | `k8s/ragops.yaml` plus existing base; `pvc-persistence.txt` proves state/reports/traces survive data-shell replacement. |
| F2 ingestion Job + CronJob, only ingestion writes vectors | Done | `k8s/ingest-job.yaml`, `ragops-cronjob.yaml`; old schedule suspended. API/eval have no Chroma writes. |
| F2 exact eval Job path, persistent results, failing status | Done | `k8s/eval-job.yaml`; actual bad-k1 Job Failed and passing candidate Jobs Complete. |
| F2 ConfigMap flip without image rebuild | Done | Gate tight/normal Jobs use identical image digest; fixed saved measurements are re-gated, not remeasured. |
| F3 candidate own Deployment/Service/collection | Done | Candidate is isolated until release; `maxUnavailable: 0`. |
| F3 rejected candidate never rolled out; undo trace versions | Done | `rejected-release.txt`, `live-after-rejection.txt`, `rollback-versioned.txt`, `rollback-versioned-trace.txt`. |
| F4 stdout JSONL + volume + reachable metrics | Done | Actual kubectl logs, `traces/cluster.jsonl`, `metrics-portforward.txt`. |
| F5 measured resource requests/limits | Done | `resource-summary.json` derives sampled maxima; report copies actual numbers and chosen requests/limits. No unobserved peak claim. |
| Fresh cluster works; all manifests/commands committed | Done | Separate `rahbar-a3-clean` profile completed ingestion, candidate indexing, full eval and sourced smoke; `fresh-*` evidence and `eval/results/fresh/`. Temporary profile stopped afterwards. |
| G <=8 main pages, names/roll numbers, mappings/qualities/results | Done | Seven main report pages plus pending screenshot appendix; all pages rendered and visually checked. |
| G six short answers, contribution table, AI statement | Done | Report page 7; AI statement is three rendered lines. |
| Required manual screenshots in report appendix | **NEEDS HUMAN / FILL** | `SCREENSHOTS.md` gives all 17 categories and exact commands. No fabricated screenshots. |
| Both students explain work and attend demo | **NEEDS HUMAN / FILL** | Actual student review and participation cannot be completed by an agent. |

## Interpretation and remaining steps

The top-k 3 candidate improves answerable answer rate from .50 to .65 while preserving recall@5 .85. That still leaves unanswered questions and does not establish 100% factual accuracy. The faithfulness proxy can miss semantic errors; archived-version requests and citation-label mismatches are intentionally visible in the results. Data fingerprint embeddings are separate from zero unchanged **chunk** embeddings.

All saved results belong to the current generated golden set, identified by SHA-256 in each suite. After the students write/rewrite questions or change labels, rerun baseline/candidate/bad/drift as appropriate and rebuild the report; the audit deliberately flags stale golden hashes.

Run `python -m scripts.check_ragops` to regenerate `eval/results/assignment03-audit.json`. A non-zero exit while human items remain is intentional. The final audit must not be represented as complete submission readiness until those items are finished.

Submit the repository's **dev branch**, containing both authorized commit identities, and the completed report PDF with the actual screenshot appendix. Main retains the earlier Assignment 02 release until a separate release is requested.
