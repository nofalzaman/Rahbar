# Engineering notes

## 1. Indexing in API startup
Three API replicas would all rebuild the shared collection, racing through extraction,
deletion and writes, and every container restart would repeat that work. The one-shot
Job is the writer role (k8s/base/indexer-job.yaml:9,
k8s/base/indexer-job.yaml:17); the CronJob uses that same real
pipeline. Chroma has one replica (k8s/base/chroma-statefulset.yaml:10)
and a volume claim template (k8s/base/chroma-statefulset.yaml:84).
`rg "\.add\(|upsert|create_collection" api/app` finds only `seen.add(passage.text)`
in the retriever: that is a Python set used for deduplication, not a vector-store write.
The actual collection `add` and `create_collection` calls live in `indexer/pipeline/store.py`.
Readiness waits for a nonempty collection rather than building one. A writer role is not
a distributed lock: concurrent manual Jobs remain an operational limitation.

## 2. Readiness and liveness swapped
Liveness calls `/healthz` every 20 seconds with failureThreshold=3
(k8s/base/api.yaml:56); readiness calls `/readyz` every 10
seconds with failureThreshold=3 (k8s/base/api.yaml:62).
Three successive liveness failures yield roughly a minute's detection window, depending
on probe alignment/timeouts. If liveness depended on a Chroma outage lasting 90 seconds,
all three API pods could be restarted together. Meanwhile a dependency-free readiness
would keep routing traffic to pods unable to retrieve. Startup probing delays the other
probes until boot is complete. Our real health handler touches no dependency
(api/app/routes/health.py:17); dependency checks belong in readiness.

## 3. HPA and a generation service
The CPU HPA uses utilization=CPU usage/request, with a 70% target and 3–8 replicas
(k8s/base/hpa.yaml:19). The API request is 100m CPU;
waiting on host Ollama is I/O from the pod's perspective, so low CPU can coexist with
long user waits. More replicas also cannot create capacity on a saturated shared model.
Scale on in-flight requests or queue depth, with generation latency as a supporting
signal. `rahbar_generation_seconds` is already exported, but Prometheus plus an adapter
or KEDA and a model-capacity policy would be needed to drive autoscaling from it.
The recorded HPA has known CPU utilization, rather than an unknown denominator.

## 4. Indexer memory and limits
`kubectl top pods -n rahbar -l job-name=phase7-verify` was sampled every five seconds.
The highest observed working set was **427Mi**, in
`docs/evidence/kubectl-top-indexer.txt`; it is a sampled maximum, not a guaranteed
instantaneous peak. The Job's limit is **1Gi = 1024Mi**
(k8s/base/indexer-job.yaml:37), leaving **597Mi** or
58.3% of the limit above that observed maximum. Its 256Mi memory request
reserves normal working memory, while the higher limit accommodates OCR peaks. The
observed CPU reached about 1 core while OCR ran, justifying the 1-core cap; the 100m
request is a scheduling reservation, not a prediction of its peak. Set the memory limit
too low and Linux can OOMKill the container (typically exit 137); CPU over-limit instead
throttles. The current sample also records API around 70Mi, Redis about 5Mi, UI about
2Mi, and Chroma about 123Mi under the calibration workload. Requests include startup
headroom; these laptop measurements do not establish production capacity.

## 5. Recall by type
The committed real run has recall@5 by type {"abstain": null, "exact": 1.0, "injection": 1.0, "ordinary": 0.875, "version": 0.5}.
Version questions are worst at **50%**; ordinary questions are 87.5% and exact terms
100%. We do not repeat the handout's prediction that exact terms must be worst when
our measurements say otherwise. The retriever already supplements vectors with a text
lookup for clause numbers. Broader lexical/BM25 plus vector retrieval and reranking
could improve deadline queries: embeddings blur short exact rules and dates. Strict
section matching also penalizes 4.25 when extraction groups it under 4.24. Recall does
not replace checking whether the generator actually answered the intended question.

## 6. API-only embedding-model change
The index records `embed_model` in collection metadata
(indexer/pipeline/store.py:40); readiness compares it with
the pod configuration (api/app/services/readiness.py:41).
The existing real mismatch log reads: `embedding model mismatch: the index was built
with 'nomic-embed-text' but this pod has EMBED_MODEL='all-minilm'`.
The replacement pod stays 0/1 Ready and the Service excludes it. Equal-dimensional
vectors from different models could otherwise return plausible-looking nonsense;
different dimensions may instead produce an explicit Chroma error. The guardrail
prevents either case from silently joining the ready endpoints.

## 7. The failure and the evidence that corrected it
The clearest observed failure was fresh-cluster indexing in CI. The API pods stayed
unready while the indexer reached extraction/chunking but never created the collection.
The initial assumption, inherited from the phase checklist, was that kind ignored
NetworkPolicy, so the laptop-specific Ollama rule would not matter. The logs disproved
the idea that the index had simply been empty before startup: the run ended with
`error: timed out waiting for the condition on jobs/indexer`, and the API repeatedly
logged `Collection [rahbar] does not exists`. The indexer log had already reported
`"msg": "storage amplification", "original_words": 427, "stored_words": 407`.

We first made Ollama a direct member of the kind Docker network. Checking upstream
kindnet documentation then exposed the mistaken policy assumption. The base allowlist
contained the laptop IP, while CI used a different address. A generated policy permitting
only the actual embedding-container IP on TCP 11434 resolved the startup failure; run
43022332761 passed the real fixture gate. About 35 minutes elapsed between the first
recorded wait at 12:10:31 UTC and the successful gate around 12:45 UTC, including other
work and repeated CI runs. We do not turn that into an invented >1-hour incident.

Another real mistake was trusting recovered local calibration runs: they showed
`recall_at_5: 0.0`, while `git show origin/dev:eval/golden.yaml` still had `section: "?"`.
We verified source labels and reran all configurations. We also found and removed the
CronJob's `args: ["--dummy"]`. The session's security-scan failures were corrected by
updating vulnerable packages and OS libraries, without disabling the scan.

The handoff's blanket claim that kind cannot enforce NetworkPolicy is outdated: recent
kindnet embeds network-policy enforcement. Its first CI indexer stalled with the base
laptop-only Ollama allowlist; the generated overlay now permits the actual CI container
IP on port 11434. See the [upstream network-policy documentation](https://kube-network-policies.sigs.k8s.io/docs/concepts/modularity/).
The local Calico demonstration separately verifies UI-to-API success and UI-to-Chroma timeout.
