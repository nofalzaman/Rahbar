# Assignment 03 implementation contracts

This implementation map derives from the five-page Assignment 03 PDF and the RAGOps paper, https://arxiv.org/abs/2506.03401. It records the implemented data, evaluation, trace and Kubernetes contracts.

## 1. Data contracts

`_index.json` is an authoritative ordered list with `file`, `title`, `doc_version`, `page_count`, optional `family` and `min_chars`. Files are direct children of the input directory. The manifest's family/version order determines recency; exact bytes determine identity. Reports have four named checks, pass/fail and reasons, acceptance, chunk/fingerprint embedding counts, deletions and counts by document.

`pipeline.ragops` is the sole RAGOps writer. State is per collection and pins embedding/chunk settings. Changed documents embed new chunks; unchanged chunks reuse journalled vectors; obsolete chunk IDs are pruned. Active/archive/state live on the PVC. Source snapshots preserve text, chunks, metadata and vectors. A shared exclusive lock prevents concurrent writers. A stale lock after a killed Job requires operator inspection before removal. This is retryable reconciliation, not an atomic multi-document transaction: use a separate candidate collection for isolation.

## 2. Evaluation contracts

`eval/golden.jsonl` rows contain ID, question, origin (`human` or `synthetic`), `reviewed_by`, hard flag, answerability and relevant source/page pairs. Generated rows must never be relabelled human-written without actual human authorship.

The suite records module cosine scores/gap, time and determinism; component recall@3/@5, MRR and nDCG@5 (duplicate pages cannot inflate gain); e2e citation validity, abstention, latency and a declared lexical support proxy. The support proxy is not factual accuracy. Answerable answer rate is additionally gated to prevent abstention gaming. Two fixed-seed repetitions and query-typo noise results are retained. Results include API deployment identity and input hash.

The gate rejects missing/non-finite required metrics. Thresholds are in `eval/thresholds.json` and the ConfigMap. Release also checks collection, embedding model, top-k and image against the evaluated identity. Baseline and candidate must hold generation settings constant. Exploratory, unbounded trials are retained but not substituted for the bounded controlled comparison.

## 3. Trace contracts

Each query emits `event=ragops_trace` with timestamp/id/query, optional rewritten query, embedding/model versions, collection/build, retrieved chunks/documents/versions/scores, filters/order, actual context/messages/hash, generation attempts and raw replies, output/citations, rail actions, stage times and cache status. JSONL stdout and PVC persistence contain the same records. Cached replies link to their source trace. The local trace endpoint is deliberately unauthenticated and must remain local to the demo.

## 4. Kubernetes and evidence

Everything runs in `rahbar`. PVCs persist Chroma, Redis, lake, quarantine, archive, results and traces. API/candidate use distinct Services and collections. Ingestion and evaluation are Jobs; verified ingestion has a CronJob. Resources are explicit and accompanied by measured samples. NetworkPolicy gates connections, not Chroma HTTP methods; read-only access is enforced by code ownership/behavior.

