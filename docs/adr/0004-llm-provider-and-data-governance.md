# ADR 0004: LLM provider and what leaves the cluster

## Status
Accepted · 2026-11-11

## Context
Generation needs a model. Everything else runs in the cluster, and the corpus is public
university documents, but questions are typed by students.

## Decision
The provider sits behind `LLM_PROVIDER` (`api/app/providers/llm/`): `stub` for tests and CI,
`ollama-host` (Ollama on the developer's laptop, reached at `host.minikube.internal`) and
`hosted` (an OpenAI-compatible free tier; the key lives in a Kubernetes Secret created on
the command line). Embeddings always use Ollama's `nomic-embed-text`, pinned in the
ConfigMap and recorded in the collection metadata. We shipped: `ollama-host`, with `llama3.2:3b`.

With a hosted provider, the question and the retrieved passages leave the cluster for that
provider. With `ollama-host`, question and passage generation stays on the laptop. The cache stores questions and responses. Cache-hit logs can include the cached question;
generation diagnostics include a short model rationale. Logs do not intentionally collect
user identities, but questions may contain personal information. No durable chat history
is implemented; retention depends on Redis TTL and the cluster log configuration.

In CI, the embedding container runs on the GitHub runner and the LLM is the stub, so no
question, passage or key leaves the runner.

## Options considered
In-cluster Ollama needs at least 8 GB and slow weight loading; we did not have the memory.

## Consequences
The API request/response and passage contracts gained additive fields (`follow_up`, `cached`, and the passage
`doc_version`/`superseded`). CI runs the stub model with real embeddings, so it tests
retrieval and abstention, not answer quality. Older kind configurations did not enforce
NetworkPolicy; recent kindnet does. CI therefore supplies a narrow egress rule for its
Ollama container. The separately recorded local firewall test uses Calico.

The published indexer contains fictional CI fixtures, not the FAST corpus. Model weights
are downloaded externally; CI disables Chroma telemetry and sends generation to a stub.
