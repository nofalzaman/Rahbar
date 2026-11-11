# ADR 0001: The indexer is a Job, not part of the API

## Status
Accepted · 2026-11-11

## Context
RAHBAR has three api replicas and one Chroma volume. Indexing means extracting and OCR-ing
PDFs, chunking, and embedding every chunk, which takes minutes and a lot of memory. The
obvious place to run it is at API startup, so that a fresh deployment indexes itself.

## Decision
A one-shot Kubernetes Job (`k8s/base/indexer-job.yaml`) is the only writer. A CronJob
(`k8s/base/reindex-cronjob.yaml`) runs the same image and arguments weekly, and a person can
trigger it with `kubectl create job --from=cronjob/reindex manual-reindex-1 -n rahbar`.
The API only reads the index. Its `/readyz` probe (`api/app/services/readiness.py`) reports
not ready until Chroma answers, the collection is non-empty, the embedding model matches
and Redis answers, so a pod is withheld from the Service until there is something to
retrieve.

## Options considered
Indexing in API startup was rejected for four reasons:
1. Three pods race to write one volume, each halfway through a different document, and
   leave an index that no document produced.
2. Every restart (rolling update, OOMKill, node drain) pays the full extraction and
   embedding cost again.
3. Readiness lies: either a pod reports ready before the index exists and serves empty
   retrievals, or it takes minutes to become ready and is killed halfway through.
4. Re-indexing would need a redeploy, so a configuration change means a rebuild.

An init container in each api pod has the same race and the same repeated cost.

## Consequences
Re-indexing is one command with no API redeploy. Indexing failures show up as a failed Job with
its own logs and a `backoffLimit`, not as a crash-looping api. The indexer builds the new
collection under a temporary name and swaps it in by renaming
(`indexer/pipeline/store.py`), so the API keeps serving the old index while the slow work
happens. The price is one more object to understand and a few minutes in which a new
document is not yet searchable.

The delete/rename swap is not atomic and can briefly make retrieval unavailable.
Manual Jobs must be serialized operationally; CronJob Forbid only covers scheduled runs.
