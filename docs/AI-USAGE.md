# AI usage

This submission uses AI assistance. The supplied phase checklist attributes earlier
Dockerfiles, manifests, pipeline code and tests to Claude (Anthropic, claude.ai); that
attribution comes from the project handoff, not independent proof of every earlier chat.
Codex (OpenAI coding agent) completed and reviewed the remaining work on 11 November 2026.
Students must review the resulting code and be able to explain it; this document does
not claim that a human review happened when it has not been recorded.

| Tool | What it wrote or shaped | Validation and changes afterwards |
| --- | --- | --- |
| Claude, per supplied handoff | Earlier Dockerfiles, Kubernetes manifests, indexer/query pipelines, tests and evaluation drafts | Codex inspected the actual files, removed dummy weekly indexing, preserved standalone numbered rules, and fixed year-only historical report filtering. |
| Claude, per supplied handoff | Draft phase 5–7 documentation and workflow examples | Codex corrected unsupported zero-downtime/StatefulSet claims, filled actual provider and measurement values, and separated fixture from real-corpus results. |
| Codex | CI/CD workflows, helper scripts and fixture calibration | Ran GitHub Actions; kept real embeddings and stub generation separate, measured the 0.6399 fixture floor, retained strict security scans and updated vulnerable dependencies/OS packages. |
| Codex | Golden source labels, measurements, failure analysis, engineering notes, README, architecture and ADRs | Verified source pages and all eight corpus hashes, reran four chunk settings and cache pairs, exercised real Ollama through Kubernetes, recorded actual misses/fallbacks and resource samples. |
| Codex | Small implementation fixes and regression tests | Ran ruff, mypy, offline API/indexer/eval tests, manifest validation in CI and live experiments; raised cache threshold from 0.92 to measured 0.93 after an old/current deadline false hit. |

The generated prose and code were committed by the existing configured Git identity;
commit authorship does not mean the human typed the AI-written content. Results are
actual tool outputs, not invented measurements. We do not invent a >1-hour incident,
an external PR approval, a green deployment, or a Classroom submission. Final status
and any remaining human actions are recorded in `docs/FINAL-CHECKLIST.md`.
