# RAGOps / Assignment 03

Run from the repository root with Python 3.12, Docker Desktop, minikube, kubectl and host Ollama running. All commands below run the pipeline on Kubernetes. The data-shell only prepares files and reads results; only ingestion Jobs write Chroma.

```powershell
ollama pull nomic-embed-text
ollama pull llama3.2:3b
python -m pip install -r api/requirements-dev.txt -r indexer/requirements-dev.txt
# If corpus/raw is absent: python corpus/fetch.py
./scripts/bootstrap_ragops.ps1
kubectl apply -f k8s/eval-job.yaml
kubectl logs -n rahbar -f job/ragops-eval
```

The bootstrap is for a fresh cluster. Existing Jobs are immutable: retain logs/results and use `scripts/run_ragops.ps1` with a new `-Name` for repeats. Do not delete PVCs to rerun. On the existing Assignment 02 cluster, suspend the old `reindex` CronJob before starting RAGOps. The new `ragops-reindex` is the verified ingestion schedule.

The Windows Docker Desktop Ollama allow rule uses `192.168.65.254/32:11434`. If your host gateway differs, resolve `host.minikube.internal` inside a pod and update that single rule in `k8s/ragops.yaml`. Chroma/Redis accept internal traffic only. API and eval code have no vector-store writes; NetworkPolicy controls connections, not HTTP write permissions.

Storage: `ragops-data` PVC holds `/data/corpus`, `/data/lake/{active,archive,quarantine,state,reports}`, `/data/results` and `/data/traces`. Chroma and Redis have their own PVCs. A shared exclusive ingestion lock prevents concurrent writers across collections. After an interrupted Job, first confirm no ingestion Job is active, then remove a stale `/data/lake/ingestion.lock` from data-shell. Never remove it while a writer is running.

## A - verification and incremental update

```powershell
./scripts/demo_ragops_data.ps1
./scripts/run_ragops.ps1 -Kind ingest -Name ragops-repeat
kubectl logs -n rahbar -f job/ragops-repeat
```

`chunks_embedded` counts chunk embeddings; `verification_embeddings` separately counts document fingerprints. The immutable upstream inputs remain available; rejected documents are placed in the persistent quarantine and never reach Chroma. Older snapshots are retained for restore. A restore lasts until the authoritative input manifest requests another version: pin the manifest to keep a rollback across scheduled ingestions.

The committed demo Batch A is one synthetic old library notice. Batch B has 12 synthetic notices, including two exact copies, one near-copy, truncation, missing metadata, a newer library notice and a planted injection. Official raw documents are not committed.

## B - all three levels, two seeds-fixed repetitions and query noise

```powershell
kubectl apply -f k8s/eval-job.yaml
kubectl logs -n rahbar -f job/ragops-eval
```

Results are timestamped on `/data/results`; traces on `/data/traces`. Fixed seed is 42, generation temperature 0 and a 512-token response limit. The semantic cache is bypassed by `X-RAGOps-Eval: 1`; query-vector memoization can still make a repeated request faster. Faithfulness is explicitly a token-support proxy, not an LLM judge or factual-accuracy guarantee. Gate also forbids a drop in answerable answer rate so abstaining cannot manufacture a good faithfulness score.

## C - controlled change, gate and release

Baseline top-k is 5; candidate is 3 in a separate Deployment, Service and collection. `eval/thresholds.json` and the `ragops-thresholds` ConfigMap contain the same thresholds. The 2-point recall budget preserves retrieval, citation validity must be >= .95, abstention cannot regress, text support must be >= .8, and p95 <= 15 seconds leaves headroom above the measured baseline. The answerable answer rate may not decline. The original permissive exploratory gate and later strengthened gate are retained as separate evidence, not rewritten.

```powershell
python -m ragops.gate --baseline eval/results/baseline.json --candidate eval/results/candidate.json --thresholds eval/thresholds.json
python -m scripts.release_ragops --baseline eval/results/drift.json --candidate eval/results/final-verification.json --thresholds eval/thresholds.json --collection rahbar-a3-candidate --top-k 3
kubectl rollout status deployment/api -n rahbar
kubectl rollout undo deployment/api -n rahbar
```

Release checks both metrics and evaluated collection/model/top-k/image identity. Release-relevant values are in the pod template, so undo restores them; ConfigMap changes alone cannot restore a release. Rolling update has `maxUnavailable: 0`.

## D - trace and metrics

```powershell
kubectl logs -n rahbar deployment/api
kubectl port-forward -n rahbar service/api 18080:8000
# In another terminal:
Invoke-WebRequest http://localhost:18080/metrics
python -m ragops.traces traces/cluster.jsonl --trace-id TRACE_ID
python -m ragops.traces traces/cluster.jsonl --since 2026-11-26T00:00:00+00:00
```

`/api/traces/ID` is an unauthenticated local-demo inspection endpoint. It contains source context and user queries; keep the demo service local. The trace tool reconstructs actual messages, including retries, rather than regenerating a prompt from current configuration. Cache hits link to their source trace.

## E - drift and coverage

```powershell
./scripts/stage_ragops_drift.ps1 -Name ragops-new-drift -Collection rahbar-a3-candidate
./scripts/run_ragops.ps1 -Kind eval -Name ragops-new-drift-eval -Label drift -Baseline /data/results/candidate.json
kubectl apply -f k8s/runs/coverage-before.yaml
kubectl logs -n rahbar job/ragops-coverage-before
kubectl apply -f k8s/runs/coverage-after.yaml
kubectl logs -n rahbar job/ragops-coverage-after
```

Coverage uses cosine >= .85 and a target share >= .85. Before/after use exactly the same 40 live queries. Expanded questions are six new abstention cases: better test coverage does not add missing housing/food/transport facts to the corpus. Golden origin/review metadata remains pending until actual human authorship/review.

### Unseen-batch live demo

Keep the existing manifest as the base; an unseen-only authoritative manifest would remove the existing corpus. Put the new files and their actual metadata (`file`, `title`, `doc_version`, `page_count`) in a local `unseen/` folder with `_index.json`, then run:

```powershell
./scripts/stage_ragops_drift.ps1 -Name ragops-unseen-demo -BatchDir ./unseen -BaseCorpus /data/corpus/with-b -Destination /data/corpus/unseen-demo -Collection rahbar-a3-candidate
kubectl logs -n rahbar job/ragops-unseen-demo
# If retaining the new batch for scheduled ingestion:
kubectl set env cronjob/ragops-reindex CORPUS_DIR=/data/corpus/unseen-demo -n rahbar
```

The helper merges existing/new entries by file name, with incoming metadata replacing the same file's older entry. It never makes up missing metadata; invalid documents are quarantined by the Job. Use a new Job name for every run. On a fresh setup before Batch B, use `/data/corpus/active` as the base instead.

## F - cluster inspection, resources and export

```powershell
kubectl get all,pvc,configmap,cronjob,job -n rahbar
kubectl top pods -n rahbar
```

Only sampling is claimed; samples do not prove an instantaneous peak. API requests/limits retain headroom over observed resident memory. Job limits include OCR/extraction bursts; Ollama GPU/host memory is outside Kubernetes and is not included in pod numbers.

The final report and completed question worksheet are in `docs/report/`; evaluation artifacts are in `eval/results/`.
