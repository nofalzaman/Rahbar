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
We cannot substantiate the handout's required personal story of a failure costing more
than one hour from the available project history, and do not invent one. During this
completion session the most consequential mistaken assumption was that earlier local
chunking measurements were valid. Reading `eval/runs/previous-chunk-400-50.json` showed
`recall_at_5: 0.0`, while `git show origin/dev:eval/golden.yaml` showed `section: "?"`.
Those runs were scoring unresolved labels. We verified labels against source pages,
re-ran all candidates, and kept the remaining genuine misses. Further inspection found
the CronJob's `args: ["--dummy"]` and a live 700/100 ConfigMap versus Git's 400/50.
These were real defects, not model hallucinations. The subsequent first CI scan also
failed on fixed vulnerabilities; package and OS updates were made rather than disabling
the scan. This is an accurate session account, with no claim of an unrecorded one-hour
incident. The team still needs to supply its own longer incident if the marker requires it.

CI's kind network does not enforce NetworkPolicy. The local Calico demonstration verifies
UI-to-API success and UI-to-Chroma timeout; it is separate evidence from CI readiness.
